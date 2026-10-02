"""P4 static analysis of the nested image (recursive descent, not linear sweep).
Produces: reachable code map, function list, per-function frame, call graph, worst-case
stack per entry (main + every IRQ), indirect-transfer list, store-site catalogue with
constant-resolved addresses, unresolved store sites, and padding/free-flash map.
Run: MI5MAX_ROOT=<root> python p4_static.py IMAGE OUTDIR
"""
import json, re, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from opus_emu import image, DELTA

NAME = sys.argv[1] if len(sys.argv) > 1 else 'farm'
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else '../evidence')
img = image(NAME)
BODY0 = 0x19818
BODYLEN = struct.unpack_from('<I', img, 0x19800)[0]
RT0, RT1 = 0x2800, 0x2800 + BODYLEN
SWITCH8 = 0x21714 - DELTA          # compiler switch helper with inline byte table (verified at file 0x21714)
cs = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS); cs.detail = False

def fb(rt): return img[rt + DELTA: rt + DELTA + 4]
def dis(rt):
    return next(cs.disasm(fb(rt), rt, 1), None)
def word(rt): return struct.unpack_from('<I', img, rt + DELTA)[0]
def target(i):
    m = re.match(r'#(0x[0-9a-f]+)', i.op_str)
    return int(m[1], 16) if m else None

COND = {'beq','bne','bhs','blo','bmi','bpl','bvs','bvc','bhi','bls','bge','blt','bgt','ble','bcs','bcc'}

# ---------- recursive descent ----------
vec = [struct.unpack_from('<I', img, BODY0 + 4 * k)[0] for k in range(48)]
roots = {}
names = {1: 'Reset', 2: 'NMI', 3: 'HardFault', 11: 'SVC', 14: 'PendSV', 15: 'SysTick'}
for k, v in enumerate(vec[1:], 1):
    if v and v & 1 and RT0 <= (v & ~1) < RT1:
        roots[v & ~1] = names.get(k, f'IRQ{k - 16}' if k >= 16 else f'EXC{k}')
insn, func_of, funcs, calls, indirect = {}, {}, {}, {}, []
switch_tables = {}

def explore(entry):
    if entry in funcs: return
    funcs[entry] = set(); calls[entry] = set()
    work = [entry]
    while work:
        a = work.pop()
        if a in funcs[entry] or not (RT0 <= a < RT1): continue
        i = dis(a)
        if i is None: raise SystemExit(f'undecodable reachable insn at rt {a:#x}')
        insn[a] = i; funcs[entry].add(a)
        m = i.mnemonic; n = a + i.size
        if m == 'b':
            work.append(target(i))
        elif m in COND:
            work += [target(i), n]
        elif m == 'bl':
            t = target(i)
            if t == SWITCH8:
                tb = n
                cnt = img[tb + DELTA]
                tg = [tb + 2 * img[tb + DELTA + 1 + k] for k in range(cnt + 1)]
                switch_tables[a] = tg
                work += tg
            else:
                calls[entry].add((a, t)); explore(t); work.append(n)
        elif m in ('bx', 'blx'):
            if m == 'bx' and i.op_str == 'lr': pass
            else:
                indirect.append((a, f'{m} {i.op_str}', entry))
                if m == 'blx': work.append(n)
        elif m == 'pop' and 'pc' in i.op_str: pass
        elif m in ('udf', 'bkpt'): pass
        else:
            work.append(n)

for r in sorted(roots): explore(r)
# scatter-loader handlers reached via 'bx r3' at file 19912 (resolved by executing the loader)
SCATTER_HANDLERS = [0x1991C - DELTA, 0x1AD76 - DELTA]
for r in SCATTER_HANDLERS: explore(r)
# indirect targets known from code: reset blx 0x8FB1 (SystemInit-like) and bx 0x28C1 (__main)
extra = {}
for a, txt, f in indirect:
    # resolve 'ldr rX,[pc]' immediately before
    prev = insn.get(a - 2)
    if prev and prev.mnemonic == 'ldr' and 'pc' in prev.op_str:
        lit = word(((a - 2 + 4) & ~3) + int(re.search(r'#(0x[0-9a-f]+|\d+)', prev.op_str)[1], 0))
        extra[a] = lit & ~1
for a, t in extra.items():
    explore(t)
# code-pointer words inside the body that are not yet reachable (function-pointer tables, scatter data)
ptr_words = []
for off in range(BODY0, BODY0 + BODYLEN - 3, 4):
    v = struct.unpack_from('<I', img, off)[0]
    if v & 1 and RT0 <= (v & ~1) < RT1 and (v & ~1) not in insn:
        if dis(v & ~1) is not None: ptr_words.append((off, v & ~1))
# ---------- stack ----------
def local_peak(entry):
    """max local stack depth (bytes) along CFG, and depth at each call site."""
    depth = {entry: 0}; work = [entry]; peak = 0; at_call = {}
    while work:
        a = work.pop(); d = depth[a]; i = insn[a]; m = i.mnemonic; n = a + i.size
        dd = d
        if m == 'push': dd = d + 4 * len(re.findall(r'r\d+|lr', i.op_str))
        elif m == 'pop': dd = d - 4 * len(re.findall(r'r\d+|pc', i.op_str))
        elif m == 'sub' and i.op_str.startswith('sp, '):
            dd = d + int(re.search(r'#(0x[0-9a-f]+|\d+)', i.op_str)[1], 0)
        elif m == 'add' and i.op_str.startswith('sp, #'):
            dd = d - int(re.search(r'#(0x[0-9a-f]+|\d+)', i.op_str)[1], 0)
        elif m == 'mov' and i.op_str.startswith('sp, r'):
            SP_RESETS.append(a + DELTA); dd = 0       # boot-only stack switch (C library); depth restarts
        elif m == 'add' and i.op_str.startswith('sp, sp, #'):
            dd = d - int(re.search(r'#(0x[0-9a-f]+|\d+)', i.op_str)[1], 0)
        elif re.match(r'(mov|add|sub)s?$', m) and i.op_str.startswith('sp'):
            raise SystemExit(f'unhandled SP write {m} {i.op_str} at {a:#x}')
        peak = max(peak, dd)
        succ = []
        if m == 'b': succ = [target(i)]
        elif m in COND: succ = [target(i), n]
        elif m == 'bl':
            if a in switch_tables: succ = switch_tables[a]
            else: at_call[a] = dd; succ = [n]
        elif m in ('bx',) or (m == 'pop' and 'pc' in i.op_str): succ = []
        elif m == 'blx': at_call[a] = dd; succ = [n]
        else: succ = [n]
        for s in succ:
            if s not in funcs[entry]:   # tail branch into another function
                at_call[a] = dd; continue
            if s in depth:
                if depth[s] != dd:
                    INCONSIST.append((entry + DELTA, s + DELTA, depth[s], dd)); depth[s] = max(depth[s], dd)
            else:
                depth[s] = dd; work.append(s)
    return peak, at_call

SP_RESETS = []
INCONSIST = []
LP, ATC = {}, {}
for f in funcs: LP[f], ATC[f] = local_peak(f)
# callee map: direct bl + tail branches + resolved blx
callee = {f: [] for f in funcs}
for f in funcs:
    for a, d in ATC[f].items():
        i = insn[a]
        if i.mnemonic == 'bl': callee[f].append((a, target(i), d))
        elif i.mnemonic == 'blx': callee[f].append((a, extra.get(a), d))
        else:   # tail jump
            t = target(i)
            if t is not None and t in funcs: callee[f].append((a, t, d))
            elif t is not None:
                # branch into the middle of another function body: find owner
                owners = [g for g in funcs if t in funcs[g] and g != f]
                for g in owners: callee[f].append((a, g, d))
memo, onstack = {}, set()
def worst(f):
    if f in memo: return memo[f]
    if f in onstack: raise SystemExit(f'recursion through {f:#x}')
    onstack.add(f)
    best, path = LP[f], [f]
    for a, t, d in callee[f]:
        if t is None: continue
        w, p = worst(t)
        if d + w > best: best, path = d + w, [f] + p
    onstack.discard(f); memo[f] = (best, path)
    return memo[f]

entries = {}
for r, nm in roots.items():
    w, p = worst(r)
    entries[nm] = dict(rt=f'{r:#06x}', file=f'{r + DELTA:05X}', worst_bytes=w, path=[f'{x + DELTA:05X}' for x in p])
# main loop entered via __main (bx 0x28C1) -> resolve
for a, t in extra.items():
    w, p = worst(t)
    entries[f'indirect_from_{a + DELTA:05X}'] = dict(rt=f'{t:#06x}', file=f'{t + DELTA:05X}', worst_bytes=w, path=[f'{x + DELTA:05X}' for x in p])

# ---------- flash geometry ----------
def runs(lo, hi, val):
    out = []; s = None
    for off in range(lo, hi):
        if img[off] == val:
            if s is None: s = off
        else:
            if s is not None and off - s >= 16: out.append((s, off - s))
            s = None
    if s is not None and hi - s >= 16: out.append((s, hi - s))
    return out
code_bytes = set()
for a, i in insn.items(): code_bytes.update(range(a + DELTA, a + DELTA + i.size))
geometry = dict(body_file=[f'{BODY0:05X}', f'{BODY0 + BODYLEN:05X}'], body_len=BODYLEN,
                runtime=[f'{RT0:#x}', f'{RT1:#x}'], tail_after_body=len(img) - (BODY0 + BODYLEN),
                ff_runs_in_body=[(f'{s:05X}', n) for s, n in runs(BODY0, BODY0 + BODYLEN, 0xFF)],
                zero_runs_in_body=[(f'{s:05X}', n) for s, n in runs(BODY0, BODY0 + BODYLEN, 0x00)],
                ff_runs_after_body=[(f'{s:05X}', n) for s, n in runs(BODY0 + BODYLEN, len(img), 0xFF)],
                last_reachable_insn_file=f'{max(insn) + DELTA:05X}')

res = dict(image=NAME, roots={f'{k + DELTA:05X}': v for k, v in roots.items()}, reachable_insns=len(insn), functions=len(funcs),
           indirect_transfers=[(f'{a + DELTA:05X}', t, f'{f + DELTA:05X}', f'{extra[a] + DELTA:05X}' if a in extra else None) for a, t, f in indirect],
           unreached_code_pointer_words=[(f'{o:05X}', f'{v + DELTA:05X}') for o, v in ptr_words],
           switch_tables={f'{a + DELTA:05X}': [f'{t + DELTA:05X}' for t in v] for a, v in switch_tables.items()},
           sp_switch_sites=sorted(set(f'{x:05X}' for x in SP_RESETS)), inconsistent_depth_joins=INCONSIST,
           entries=entries, local_frames={f'{f + DELTA:05X}': LP[f] for f in sorted(funcs)}, geometry=geometry)
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f'P4_static_{NAME}.json').write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ('reachable_insns', 'functions', 'indirect_transfers', 'unreached_code_pointer_words')}, indent=0)[:3000])
    for k, v in entries.items(): print(k, v['file'], v['worst_bytes'], v['path'])
    print(json.dumps(geometry, indent=0)[:2500])

if __name__ == '__main__':
    main()
