"""P4.1: whole-program memory-access classification on the recursively-disassembled
nested image (p4_static).  Per-function forward constant propagation over the CFG with
join, SP tracking, switch8 tables, and 4 rounds of call-site constant contexts (r0..r3).
Every reachable load/store is classified:
  CONST  : address fully known
  INDEXED: constant base + register index (index unknown)
  STACK  : SP-relative
  UNRES  : base not known (pointer from memory or unknown argument)
Run: MI5MAX_ROOT=<root> python p4_mem.py IMAGE OUTDIR
"""
import json, re, struct, sys
from pathlib import Path
sys.argv = sys.argv[:3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import p4_static as S
from opus_emu import DELTA

insn, funcs, img = S.insn, S.funcs, S.img
SZ = {'strb': 1, 'strh': 2, 'str': 4, 'ldrb': 1, 'ldrh': 2, 'ldr': 4, 'ldrsb': 1, 'ldrsh': 2}
SP = ('sp',)
PTRSTORES = {}
CALLER_SAVED = {'r0', 'r1', 'r2', 'r3', 'r12', 'ip'}
CALLEE_SAVED_WRITERS = set()
from opus_emu import load_initial_ram
INIT_RAM = load_initial_ram('stock' if S.NAME == 'stock' else 'farm')

def imm(x):
    m = re.search(r'#(-?0x[0-9a-f]+|-?\d+)', x); return int(m[1], 0) if m else None

def lit(a, i):
    t = ((a + 4) & ~3) + (imm(i.op_str) or 0)
    return struct.unpack_from('<I', img, t + DELTA)[0]

def flash_word(addr, size):
    """read-only constant data from the app flash image (runtime address)"""
    if S.RT0 <= addr < S.RT1:
        return int.from_bytes(img[addr + DELTA: addr + DELTA + size], 'little')
    return None

def dest_regs(i):
    m = i.mnemonic; ops = [o.strip() for o in i.op_str.split(',')]
    if m in ('pop',): return set(re.findall(r'r\d+', i.op_str))
    if m in ('ldm', 'ldmia'): return set(re.findall(r'r\d+', i.op_str)[1:]) | ({ops[0].rstrip('!')} if '!' in i.op_str else set())
    if m in ('stm', 'stmia') and '!' in i.op_str: return {ops[0].rstrip('!')}
    if m in ('push', 'cmp', 'cmn', 'tst', 'b', 'bx', 'bl', 'blx', 'nop', 'cpsid', 'cpsie', 'dsb', 'isb', 'dmb', 'msr') or m in S.COND: return set()
    if m.startswith('str'): return set()
    if ops and re.match(r'r\d+$|ip$|lr$', ops[0]): return {ops[0]}
    return set()
_CLOB = {}
def clobbers(f, stack=()):
    if f in _CLOB: return _CLOB[f]
    if f in stack or f not in funcs: return {f'r{k}' for k in range(13)} | {'ip', 'lr'}
    saved = set()
    first = insn[f]
    if first.mnemonic == 'push': saved = set(re.findall(r'r\d+', first.op_str))
    out = set()
    for a in funcs[f]:
        i = insn[a]
        if i.mnemonic == 'push' and a == f: continue
        if i.mnemonic == 'pop' and 'pc' in i.op_str: continue
        out |= dest_regs(i)
        if i.mnemonic == 'bl' and a not in S.switch_tables:
            out |= clobbers(S.target(i), stack + (f,))
        if i.mnemonic == 'blx': out |= {f'r{k}' for k in range(4)} | {'ip', 'lr'}
    out -= saved
    out |= {'r0'} if any(insn[a].mnemonic != 'push' for a in funcs[f]) else set()
    _CLOB[f] = out
    return out

def succs(f, a):
    i = insn[a]; m = i.mnemonic; n = a + i.size
    if m == 'b': out = [S.target(i)]
    elif m in S.COND: out = [S.target(i), n]
    elif m == 'bl': out = S.switch_tables.get(a, [n])
    elif m == 'bx' or (m == 'pop' and 'pc' in i.op_str): out = []
    else: out = [n]
    return [x for x in out if x in funcs[f]]

def analyse(ctxs):
    acc, newctx = [], {}
    for f in funcs:
        for ctx in (list(ctxs.get(f, ())) + [(None,) * 4]):
            env0 = {f'r{k}': K(ctx[k]) for k in range(4)}; env0['sp'] = ('sp', 0)
            IN = {f: env0}; work = [f]; it = 0
            while work and it < 50000:
                it += 1; a = work.pop(); env = dict(IN[a]); i = insn[a]
                step(f, a, i, env, acc, newctx, ctx)
                for s in succs(f, a):
                    if s not in IN: IN[s] = dict(env); work.append(s)
                    else:
                        j = {k: jn(IN[s].get(k), env.get(k)) for k in set(IN[s]) | set(env)}
                        if j != IN[s]: IN[s] = j; work.append(s)
    return acc, newctx

MAXSET = 16
def K(v):
    """normalise: int -> frozenset({int}); frozenset kept if small; else None"""
    if isinstance(v, int): return frozenset({v & 0xFFFFFFFF})
    if isinstance(v, frozenset): return v if 0 < len(v) <= MAXSET else None
    return v
def binop(x, y, fn):
    x, y = K(x), K(y)
    if isinstance(x, frozenset) and isinstance(y, frozenset):
        return K(frozenset(fn(a, b) & 0xFFFFFFFF for a in x for b in y))
    return None
def val(env, x):
    x = x.strip()
    if x.startswith('#'): return K(imm(x))
    return K(env.get(x))
def jn(a, b):
    a, b = K(a), K(b)
    if a == b: return a
    if isinstance(a, frozenset) and isinstance(b, frozenset): return K(a | b)
    return None

def step(f, a, i, env, acc, newctx, ctx):
    m, ops = i.mnemonic, [o.strip() for o in i.op_str.split(',')]
    if (m in SZ) and '[' in i.op_str:
        inside = i.op_str[i.op_str.index('[') + 1:i.op_str.index(']')]
        parts = [p.strip() for p in inside.split(',')]
        base = parts[0]; off = parts[1] if len(parts) > 1 else '#0'
        rd = ops[0]
        if base == 'pc':
            if m == 'ldr': env[rd] = K(lit(a, i))
            else: env[rd] = None
            return
        b = K(env.get(base)); o = val(env, off)
        if isinstance(b, tuple) and b[0] == 'mem':
            acc.append(dict(site=a, func=f, ctx=ctx, op=m, kind='VIA_MEM', addr=b[1], size=SZ[m], text=f'{m} {i.op_str}', base_reg=base))
            if m.startswith('ldr'): env[rd] = None
            return
        if isinstance(b, tuple):
            acc.append(dict(site=a, func=f, ctx=ctx, op=m, kind='STACK', addr=None, size=SZ[m], text=f'{m} {i.op_str}', base_reg=base))
            if m.startswith('ldr'): env[rd] = None
            return
        if isinstance(b, frozenset) and isinstance(o, frozenset):
            addrs = sorted({(x + y) & 0xFFFFFFFF for x in b for y in o})
            for ad in addrs:
                acc.append(dict(site=a, func=f, ctx=ctx, op=m, kind='CONST', addr=ad, size=SZ[m], text=f'{m} {i.op_str}', base_reg=base))
            if m.startswith('ldr'):
                vs = set()
                for ad in addrs:
                    v = flash_word(ad, SZ[m]) if m in ('ldr', 'ldrh', 'ldrb') else None
                    if v is None and m == 'ldr' and 0x20000000 <= ad < 0x20003000 and len(addrs) == 1:
                        vs = None; env[rd] = ('mem', ad); break
                    if v is None: vs = None; env[rd] = None; break
                    vs.add(v)
                if vs is not None: env[rd] = K(frozenset(vs))
            elif m == 'str':
                sv = K(env.get(rd))
                for ad in addrs:
                    if 0x20000000 <= ad < 0x20003000:
                        PTRSTORES.setdefault(ad, set()).update(sv if isinstance(sv, frozenset) else {None})
            return
        if isinstance(b, frozenset):
            for bb in b:
                acc.append(dict(site=a, func=f, ctx=ctx, op=m, kind='INDEXED', addr=bb, size=SZ[m], text=f'{m} {i.op_str}', base_reg=base))
            if m.startswith('ldr'): env[rd] = None
            return
        acc.append(dict(site=a, func=f, ctx=ctx, op=m, kind='UNRES', addr=None, size=SZ[m], text=f'{m} {i.op_str}', base_reg=base))
        if m.startswith('ldr'): env[rd] = None
        return
    if m in ('ldm', 'ldmia', 'stm', 'stmia'):
        base = ops[0].rstrip('!'); regs = re.findall(r'r\d+|lr|pc', i.op_str)[1:]
        b = K(env.get(base))
        if isinstance(b, frozenset):
            for bb in b:
                acc.append(dict(site=a, func=f, ctx=ctx, op=m, kind='CONST', addr=bb, size=4 * len(regs), text=f'{m} {i.op_str}', base_reg=base))
        else:
            kind = ('VIA_MEM' if b[0] == 'mem' else 'STACK') if isinstance(b, tuple) else 'UNRES'
            acc.append(dict(site=a, func=f, ctx=ctx, op=m, kind=kind, addr=(b[1] if kind == 'VIA_MEM' else None), size=4 * len(regs),
                            text=f'{m} {i.op_str}', base_reg=base))
        if m.startswith('ldm'):
            for r in regs: env[r] = None
        if '!' in i.op_str:
            if isinstance(b, frozenset): env[base] = binop(b, 4 * len(regs), lambda x, y: x + y)
            elif isinstance(b, tuple) and b[0] == 'sp': env[base] = ('sp', b[1] + 4 * len(regs))
            else: env[base] = None
        return
    if m == 'push':
        n = len(re.findall(r'r\d+|lr', i.op_str)); env['sp'] = ('sp', env['sp'][1] - 4 * n) if isinstance(env.get('sp'), tuple) else None
        acc.append(dict(site=a, func=f, ctx=ctx, op='push', kind='STACK', addr=None, size=4 * n, text=i.op_str, base_reg='sp')); return
    if m == 'pop':
        regs = re.findall(r'r\d+|pc', i.op_str)
        for r in regs: env[r] = None
        env['sp'] = ('sp', env['sp'][1] + 4 * len(regs)) if isinstance(env.get('sp'), tuple) else None
        acc.append(dict(site=a, func=f, ctx=ctx, op='pop', kind='STACK', addr=None, size=4 * len(regs), text=i.op_str, base_reg='sp')); return
    if m == 'bl':
        t = S.target(i)
        if a not in S.switch_tables:
            newctx.setdefault(t, set()).add(tuple(next(iter(K(env.get(f'r{k}')))) if isinstance(K(env.get(f'r{k}')), frozenset) and len(K(env.get(f'r{k}'))) == 1 else None for k in range(4)))
        cl = (clobbers(t) & CALLER_SAVED) if t in funcs else set(CALLER_SAVED)
        if t in funcs and clobbers(t) - CALLER_SAVED - {'lr'}:
            CALLEE_SAVED_WRITERS.add(t)
        for k in cl | {'lr'}: env[k] = None
        return
    if m == 'blx':
        for k in ('r0', 'r1', 'r2', 'r3', 'r12', 'ip', 'lr'): env[k] = None
        return
    rd = ops[0] if ops else None
    if m == 'adr':
        env[rd] = K(((a + 4) & ~3) + imm(i.op_str)); return
    if m in ('movs', 'mov') and len(ops) == 2:
        env[rd] = val(env, ops[1]) if not isinstance(env.get(ops[1].strip()), tuple) else env.get(ops[1].strip()); return
    if m in ('adds', 'add', 'subs', 'sub'):
        if len(ops) == 2: x, y = K(env.get(rd)), val(env, ops[1])
        else: x, y = (K(env.get(ops[1])) if ops[1] != 'pc' else None), val(env, ops[2])
        sign = 1 if m.startswith('add') else -1
        y1 = next(iter(y)) if isinstance(y, frozenset) and len(y) == 1 else None
        if isinstance(x, tuple) and x[0] == 'sp' and y1 is not None: env[rd] = ('sp', x[1] + sign * (y1 if y1 < 0x80000000 else y1 - (1 << 32)))
        elif isinstance(x, tuple) and x[0] == 'mem': env[rd] = ('mem', x[1])
        elif isinstance(x, frozenset) and isinstance(y, frozenset): env[rd] = binop(x, y, (lambda p, q: p + q) if sign > 0 else (lambda p, q: p - q))
        else: env[rd] = None
        return
    if m in ('lsls', 'lsrs', 'asrs') and len(ops) == 3:
        x, y = val(env, ops[1]), val(env, ops[2])
        if m == 'lsls': env[rd] = binop(x, y, lambda p, q: p << q)
        elif m == 'lsrs': env[rd] = binop(x, y, lambda p, q: p >> q)
        else: env[rd] = binop(x, y, lambda p, q: (p - (1 << 32) if p & 0x80000000 else p) >> q)
        return
    if m in ('mvns',) and len(ops) == 2:
        env[rd] = binop(val(env, ops[1]), 0, lambda p, q: ~p); return
    if m in ('rsbs', 'negs'):
        env[rd] = binop(val(env, ops[1]), 0, lambda p, q: -p); return
    if m in ('cmp', 'cmn', 'tst', 'b', 'nop', 'cpsid', 'cpsie', 'dsb', 'isb', 'dmb', 'msr', 'svc', 'wfi', 'wfe', 'bkpt') or m in S.COND:
        return
    if rd and re.match(r'r\d+$|ip$|r12$|lr$', rd):
        env[rd] = None

def main():
    OUT = Path(sys.argv[2] if len(sys.argv) > 2 else '../evidence')
    ctxs = {}
    for rnd in range(4):
        acc, new = analyse(ctxs)
        changed = False
        for t, s in new.items():
            cur = ctxs.setdefault(t, set())
            for tup in s:
                if any(isinstance(c, int) and (0x20000000 <= c < 0x20003000 or 0x40000000 <= c < 0x40100000) for c in tup) and tup not in cur and len(cur) < 24:
                    cur.add(tup); changed = True
        if not changed: break
    uniq = {}
    for x in acc:
        k = (x['site'], x['kind'], x['addr'])
        uniq.setdefault(k, x)
    acc = list(uniq.values())
    ram = [x for x in acc if x['kind'] in ('CONST', 'INDEXED') and isinstance(x['addr'], int) and 0x20000000 <= x['addr'] < 0x30000000]
    via = {}
    for x in acc:
        if x['kind'] == 'VIA_MEM':
            via.setdefault(x['addr'], []).append(x)
    via_report = {}
    for X, xs in sorted(via.items()):
        vals = PTRSTORES.get(X, set())
        via_report[hex(X)] = dict(sites=sorted({f"{x['site'] + DELTA:05X} {x['text']}" for x in xs}),
                                  stored_values=sorted(hex(v) if isinstance(v, int) else 'UNKNOWN' for v in vals),
                                  scatter_initial=hex(int.from_bytes(INIT_RAM[X - 0x20000000:X - 0x20000000 + 4], 'little')))
    high = [x for x in ram if x['addr'] + x['size'] > 0x20001050]
    unres_sites = {}
    for x in acc:
        if x['kind'] == 'UNRES':
            unres_sites.setdefault(x['site'], x)
    resolved_sites = {x['site'] for x in acc if x['kind'] not in ('UNRES',)}
    truly_unres = {s: x for s, x in unres_sites.items() if s not in resolved_sites}
    byfunc = {}
    for s, x in truly_unres.items():
        byfunc.setdefault(x['func'] + DELTA, []).append(f"{s + DELTA:05X} {x['text']}")
    stores_unres = {s: x for s, x in truly_unres.items() if x['op'].startswith('str') or x['op'].startswith('stm')}
    indexed = [x for x in ram if x['kind'] == 'INDEXED']
    res = dict(image=S.NAME, accesses=len(acc), ram_const_or_indexed=len(ram),
               max_const_ram_addr=hex(max(x['addr'] + x['size'] - 1 for x in ram if x['kind'] == 'CONST')),
               const_or_indexed_touching_ge_0x1050=[dict(site=f"{x['site'] + DELTA:05X}", text=x['text'], addr=hex(x['addr']), kind=x['kind']) for x in high],
               indexed_ram_bases=sorted({hex(x['addr']) for x in indexed}),
               indexed_detail=[dict(site=f"{x['site'] + DELTA:05X}", func=f"{x['func'] + DELTA:05X}", text=x['text'], base=hex(x['addr'])) for x in indexed],
               pointer_variables=via_report,
               callees_whose_naive_clobber_set_includes_r4_r11=sorted(f'{t + DELTA:05X}' for t in CALLEE_SAVED_WRITERS),
               unresolved_sites=len(truly_unres), unresolved_store_sites=len(stores_unres),
               unresolved_by_function={f'{k:05X}': v for k, v in sorted(byfunc.items())})
    (OUT / f'P4_mem_{S.NAME}.json').write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k not in ('unresolved_by_function', 'indexed_detail')}, indent=1))
    print('unresolved by function (count):', {k: len(v) for k, v in res['unresolved_by_function'].items()})

if __name__ == '__main__':
    main()
