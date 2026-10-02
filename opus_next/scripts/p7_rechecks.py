"""P7 independent re-derivations with the Opus fixture (opus_emu / p1_closed_loop),
not the earlier harness.  Run: MI5MAX_ROOT=<root> python p7_rechecks.py OUTDIR"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from opus_emu import M0, load_initial_ram, image
from p1_closed_loop import PLANT, Sim, TICK
from p1_experiments import fit_ke

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '../evidence')
checks = []; res = {}
def check(name, ok, detail=None):
    checks.append(dict(check=name, ok=bool(ok), detail=detail)); print(('OK   ' if ok else 'FAIL ') + name, detail if detail is not None else '')

p = dict(PLANT); p['ke'] = fit_ke(dict(p), 750, p['k_dc'] * 547)

# (1) regen speed flatness with Hall-period injection, own fixture, motor plant OFF (speed forced, q prescribed)
flat = {}
for im in ('stock', 'farm', 'rc01', 'rc02'):
    rows = {}
    for kmh in (7, 8, 8.5, 10, 15, 20, 22, 23, 24, 25, 26, 28, 30, 35):
        s = Sim(im, p, v0_kmh=kmh)
        m = s.m; m.put(0x158, 0, 'H'); m.call(0x1DDCC)
        for a in (0xDA, 0x140, 0x11C): m.put(a, 900, 'H')     # same coherent start command at every speed
        da0 = m.get(0xDA, 'h'); first_drop = None
        for t in range(400):
            per = s.period_for(kmh); m.put(0x8C, per, 'H'); m.put(0x2F6, per, 'H')
            for a in (0x50, 0x52, 0x54, 0x56): m.put(a, 960 * 16, 'h')      # FE 960 -> 0x210 = 518 (< 540)
            m.put(0xFE, 960, 'H'); m.put(0x132, -100, 'h')
            for a in (0x48, 0x4A, 0x4C, 0x4E): m.put(a, 0, 'h')
            for _ in range(4): m.call(0x1D654)
            if t % 5 == 0: m.call(0x1E3D0)
            if t % 5 == 1: m.call(0x22F38)
            if t % 5 == 2: m.call(0x1DDCC)
            if t % 10 == 4: m.call(0x1FC0C)
            if first_drop is None and m.get(0xDA, 'h') < da0: first_drop = t
        rows[str(kmh)] = dict(A6=m.get(0x1A6, 'h'), B2=m.get(0x1B2), BA_max_seen=m.get(0x1BA, 'h'), first_DA_drop_tick=first_drop)
        if abs(m.get(0x1A6, 'h') - kmh * 10) > max(2, 0.02 * kmh * 10):
            raise SystemExit(f'speed not realised {im} {kmh}: {m.get(0x1A6, "h")}')
    flat[im] = rows
res['regen_flatness'] = flat
for im, rows in flat.items():
    hi = [v for k, v in rows.items() if float(k) >= 8.5]
    lo = [v for k, v in rows.items() if float(k) <= 8.0]
    check(f'(1) {im}: below the gate, coast target 320, step 10 and the same first DA-drop tick at every forced speed 8.5..35 km/h; '
          f'7..8 km/h target 0',
          all(v['B2'] == 320 and v['BA_max_seen'] == 10 for v in hi) and len({v['first_DA_drop_tick'] for v in hi}) == 1
          and all(v['B2'] == 0 for v in lo), {k: (v['B2'], v['BA_max_seen'], v['first_DA_drop_tick']) for k, v in rows.items()})

# (2) 540 gate: first raw FE giving (FE*8850)>>14 >= 540, and the executed gate edge
fe_first = next(fe for fe in range(900, 1100) if (fe * 8850) >> 14 >= 540)
res['gate_first_FE'] = fe_first
edge = {}
for fe in (998, 999, 1000, 1001):
    s = Sim('farm', p, v0_kmh=25); m = s.m; m.put(0x158, 0, 'H'); m.call(0x1DDCC)
    for t in range(60):
        for a in (0x50, 0x52, 0x54, 0x56): m.put(a, fe * 16, 'h')
        per = s.period_for(25); m.put(0x8C, per, 'H'); m.put(0x2F6, per, 'H'); m.put(0x132, -50, 'h')
        for _ in range(4): m.call(0x1D654)
        if t % 5 == 0: m.call(0x1E3D0)
        if t % 5 == 1: m.call(0x22F38)
    edge[fe] = dict(V210=m.get(0x210), BA=m.get(0x1BA, 'h'))
res['gate_edge'] = edge
check('(2) gate edge: first raw FE with converted >= 540 is 1000, and BA is 0 exactly from FE 1000', fe_first == 1000 and
      edge[999]['BA'] > 0 and edge[1000]['BA'] == 0, edge)

# (3) NTC conversion and sensor-fault substitution
m = M0('farm', load_initial_ram('farm'))
def setx(x):
    for a in (0x60, 0x62, 0x64, 0x66): m.put(a, x * 8, 'h')
def conv(x, n=80):
    for _ in range(n): setx(x); m.call(0x1D92C)
    return m.get(0xC2, 'h')
pts = {x: conv(x) for x in (600, 661, 700, 1000, 1116, 1300, 1787, 1800, 1900)}
res['ntc_points_tenths'] = pts
expect = {x: (2000 if x < 661 else (-400 if x > 1787 else int((340800 - 213 * x) / 100))) for x in pts}
# First run asserted 'within 1' and FAILED at x<661 (1993 vs 2000): the (7*old+new)>>3 filter truncates, so its fixed
# point lies in [f-7, f].  That was a test-design error; the assertion below encodes the exact fixed-point property.
check('(3a) NTC line: settled C2 lies in [f-7, f] of the decoded piecewise formula f (truncating IIR fixed point)',
      all(expect[x] - 7 <= pts[x] <= expect[x] for x in pts if 600 <= x <= 1900), {x: (pts[x], expect[x]) for x in pts})
conv(1116); setx(3000); m.call(0x1D92C); one = (m.get(0xC2, 'h'), m.get(0xB8, 'B'))
for _ in range(3): setx(1116); m.call(0x1D92C)
rec3 = m.get(0xC2, 'h')
for _ in range(8): setx(100); m.call(0x1D92C)
stuck = (m.get(0xC2, 'h'), m.get(0xB8, 'B'))
res['ntc_fault'] = dict(one_invalid_sample=one, after_3_valid=rec3, sustained_short=stuck)
check('(3b) one invalid NTC sample forces C2 = 300 at once without the fault flag; sustained invalid -> C2 300 and B8 = 1',
      one == (300, 0) and stuck == (300, 1), res['ntc_fault'])
# derate cap line at C2 (farm/stock) via 1FC0C
cap = {}
for im in ('stock', 'farm'):
    row = {}
    for c2 in (890, 900, 901, 1000, 1020, 1021, 1050, 1099, 1100):
        mm = M0(im, load_initial_ram('stock' if im == 'stock' else 'farm'))
        for off, v, f in ((0xBE, 560, 'H'), (0xCA, 560, 'H'), (0xC8, 560, 'H'), (0xEA, 560, 'H'), (0xC2, c2, 'h'),
                          (0x328, 25, 'b'), (0x10, 60559, 'I'), (0xF3, 80, 'B'), (0x1A6, 200, 'h')):
            mm.put(off, v, f)
        mm.call(0x1FC0C); row[c2] = mm.get(0xC8)
    cap[im] = row
res['thermal_cap_C8'] = cap
check('(3c) local thermal cap: stock min(560, 3193-3*C2) above 900, farm min(560, 3620-3*C2) above 1020, 3 at >=1100',
      all(cap['stock'][c] == (min(560, max(0, 3193 - 3 * c)) if 900 < c < 1100 else (3 if c >= 1100 else 560)) for c in cap['stock']) and
      all(cap['farm'][c] == (min(560, max(0, 3620 - 3 * c)) if 1020 < c < 1100 else (3 if c >= 1100 else 560)) for c in cap['farm']), cap)

# (4) hold engagement: needs enable bit 16D; engaged reference = request
hold = {}
for en in (0, 1):
    s = Sim('farm', p, v0_kmh=20); m = s.m; m.put(0x16D, en, 'B')
    t_eng = None
    for t in range(8000):
        s.v = 20 / 3.6; s.tick()
        if t_eng is None and m.get(0x16C, 'B'): t_eng = t
    hold[en] = dict(engaged_tick=t_eng, seconds=None if t_eng is None else round(t_eng * TICK, 2), held_178=m.get(0x178))
res['hold'] = hold
check('(4) hold never engages with enable bit 0x16D = 0; engages after >= 4 s of steady throttle when enabled',
      hold[0]['engaged_tick'] is None and hold[1]['engaged_tick'] is not None and hold[1]['seconds'] >= 4.0, hold)

res['checks'] = checks
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'P7_rechecks_evidence.json').write_text(json.dumps(res, indent=1, default=str))
sys.exit(0 if all(c['ok'] for c in checks) else 1)
