"""Executes the original SVPWM routine (file 0x1EE60) for voltage vectors of magnitude M and
derives the line-line output amplitude as a fraction of the bus.  Phase currents are set to
0 so dead-time compensation is neutral.  Run: MI5MAX_ROOT=<root> python p1_svpwm.py OUTDIR"""
import json, math, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from opus_emu import M0, load_initial_ram
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '../evidence')
ram = load_initial_ram('farm')
TH = 3072
def duties(M, deg):
    m = M0('farm', ram)
    m.put(0x12C, round(M * math.cos(math.radians(deg))), 'h'); m.put(0x12E, round(M * math.sin(math.radians(deg))), 'h')
    for o in (0x122, 0x124, 0x126): m.put(o, 0, 'h')
    m.call(0x1EE60)
    r = struct.unpack('<6i', m.u.mem_read(0x40010C00, 24))
    # each phase: compare pair (-t, +t); output is on for |CNT| < t over the -TH..TH count -> duty = t/TH
    return [r[1] / TH, r[3] / TH, r[5] / TH], (m.get(0x119, 'B'), m.get(0x11A, 'B'), m.get(0x11B, 'B'))
res = {}
for M in (500, 900, 1023):
    ll = []
    for deg in range(0, 360, 3):
        d, flags = duties(M, deg)
        ll.append(max(abs(d[0] - d[1]), abs(d[1] - d[2]), abs(d[2] - d[0])))
    res[M] = dict(max_line_line_fraction_of_Vbus=round(max(ll), 4), min_over_angle=round(min(ll), 4))
res['flags_at_1023_30deg'] = duties(1023, 30)[1]
print(json.dumps(res, indent=1))
ok = abs(res[1023]['max_line_line_fraction_of_Vbus'] - 1.0) < 0.01 and abs(res[500]['max_line_line_fraction_of_Vbus'] - 500 / 1023) < 0.01
(OUT / 'P1_svpwm_evidence.json').write_text(json.dumps(dict(result={str(k): v for k, v in res.items()},
    claim='|V|=1023 gives a line-line peak equal to the bus (full linear SVPWM, phase peak Vbus/sqrt3); 500 gives 0.489', ok=ok), indent=1))
sys.exit(0 if ok else 1)
