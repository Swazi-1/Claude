"""P4.1 evidence: candidate private RAM 0x20000104..0x20000107 and the high-RAM region.
Static (p4_mem, all four images) + boot (executed scatter loader) + dynamic watch while
running the real scheduler routines, ISR, parsers and main-loop slot functions.
Run: MI5MAX_ROOT=<root> python p4_ram_evidence.py OUTDIR"""
import json, random, struct, sys, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from unicorn import UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ, UC_HOOK_CODE, UcError
import unicorn.arm_const as A
from opus_emu import M0, DELTA, BASE, STOP, image, load_initial_ram
from p1_closed_loop import PLANT, Sim, TICK
from p1_experiments import fit_ke

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '../evidence')
checks = []
def check(name, ok, detail=None):
    checks.append(dict(check=name, ok=bool(ok), detail=detail)); print(('OK   ' if ok else 'FAIL ') + name, detail if detail is not None else '')

CAND = (0x20000104, 0x20000108)
# 1) static, four images
static = {}
for im in ('stock', 'farm', 'rc01', 'rc02'):
    r = subprocess.run([sys.executable, str(Path(__file__).parent / 'p4_mem.py'), im, str(OUT)], capture_output=True, text=True)
    if r.returncode: raise SystemExit(r.stderr)
    d = json.loads((OUT / f'P4_mem_{im}.json').read_text())
    static[im] = dict(max_const_ram=d['max_const_ram_addr'], touching_ge_1050=d['const_or_indexed_touching_ge_0x1050'],
                      unresolved_store_sites=d['unresolved_store_sites'])
check('static: no constant or array-base access at/above 0x20001050 in any image', all(not v['touching_ge_1050'] for v in static.values()), static)

# 2) boot: executed scatter loader writes 0..0x104F only and leaves 0x104..0x107 = 0
boot = {}
for im in ('stock', 'farm', 'rc02'):
    m = M0(im, b'\xAA' * 0x3000)
    m.u.reg_write(A.UC_ARM_REG_SP, 0x20001050); m.u.reg_write(A.UC_ARM_REG_LR, STOP | 1)
    m.u.emu_start((0x198E0 - DELTA) | 1, 0x19944 - DELTA, count=3_000_000)
    ram = m.ram(0x3000)
    boot[im] = dict(cand_after_boot=ram[0x104:0x108].hex(), high_untouched=all(b == 0xAA for b in ram[0x1050:]),
                    low_all_written=all(b != 0xAA for b in ram[:0x1050]) or ram[:0x1050].count(0xAA) < 64)
check('boot: scatter/zero-init leaves candidate 0x104..0x107 = 00000000 and never writes 0x1050..0x2FFF',
      all(v['cand_after_boot'] == '00000000' and v['high_untouched'] for v in boot.values()), boot)

# 3) dynamic watch
hits = []
def watch(sim, tag):
    def w(uc, acc, addr, size, value, _):
        if CAND[0] <= addr < CAND[1] or addr + size > CAND[0] and addr < CAND[0]:
            hits.append((tag, hex(uc.reg_read(A.UC_ARM_REG_PC) + DELTA), hex(addr)))
        if 0x20001050 <= addr < 0x20003000:          # stack starts at 0x20001050 and grows down, so any write here is non-stack
            hits.append((tag + ':HIGH', hex(uc.reg_read(A.UC_ARM_REG_PC) + DELTA), hex(addr)))
    sim.m.u.hook_add(UC_HOOK_MEM_WRITE, w, begin=0x20000000, end=0x20002FFF); sim.m.u.ctl_flush_tb()
p = dict(PLANT); p['ke'] = fit_ke(dict(p), 750, p['k_dc'] * 547)
rnd = random.Random(7)
calls = 0
extra = [0x22F38, 0x22D4C, 0x22058, 0x1E108, 0x1ED18, 0x1D3D8, 0x1EDFC, 0x1AF94, 0x1B2E8, 0x1C994, 0x1E398, 0x1E21C, 0x1D09C, 0x20A14, 0x1CB14]
skipped = {}
for im in ('farm', 'rc02'):
    for scen in ('accel', 'coast'):
        s = Sim(im, p, v0_kmh=5 if scen == 'accel' else 28)
        if scen == 'coast': s.m.put(0x158, 0, 'H'); s.m.call(0x1DDCC); s.p['grade'] = -0.08
        watch(s, f'{im}/{scen}')
        for t in range(4000):
            s.tick(); calls += 1
            if t % 20 == 0:
                snap = s.m.ram(0x1050)
                for fo in extra:
                    try:
                        s.m.call(fo, count=200000); calls += 1
                    except (RuntimeError, UcError) as e:
                        skipped[f'{fo:05X}'] = str(e)[:60]
                    s.m.u.mem_write(BASE, snap)
check('dynamic: no write to 0x104..0x107 and no non-stack write above 0x1050 in the executed routines', not hits,
      dict(hits=hits[:10], routine_calls=calls, routines_that_could_not_complete_in_fixture=skipped))
res = dict(candidate=[hex(x) for x in CAND], static=static, boot=boot, checks=checks,
           note='0x104..0x107 lies between halfword 0x102 (written at file 0x20360) and byte flags 0x108..0x10B; no code '
                'reads or writes it by constant address or array base in stock/farm/RC01/RC02.  Residual: pointer-based store '
                'sites listed in P4_mem_<image>.json (classified by hand in the report).')
(OUT / 'P4_ram_evidence.json').write_text(json.dumps(res, indent=1))
sys.exit(0 if all(c['ok'] for c in checks) else 1)
