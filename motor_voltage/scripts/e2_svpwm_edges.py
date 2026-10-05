"""E2: edge cases of the real svpwm_output (B:1EE60) around and beyond |V| = 1023.

For each magnitude M and current case it counts, over 360 angles x 3 phases:
* t_min / t_max (requested half on-time, from the zero-current run);
* compare pairs with TH0 < -3072 or TH1 > +3072 (outside the counter range);
* INVERTED pairs (TH0 > TH1): what the hardware does with them is not in the manual text;
* which phase is above the 2784 sampling limit when the ISR loses its current sample,
  and whether the ISR's fixed phase pair per sector is the pair of the two lowest duties.
Current cases: 0; 600 counts peak in phase with the voltage; 600 counts lagging 60 deg (regen-like / high reactance).
Run: MI5MAX_ROOT=<project> python e2_svpwm_edges.py <outdir>
"""
import json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mv_emu import *

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '../evidence')
TH, LIM = 3072, 2784
PAIR = {4: 'AB', 6: 'AB', 0: 'AB', 2: 'BC', 3: 'BC', 1: 'AC', 5: 'AC'}
m = M0('v10')

def run(M, deg, ipk, lag):
    a = math.radians(deg)
    m.put(V_ALPHA, int(round(M * math.cos(a)))); m.put(V_BETA, int(round(M * math.sin(a))))
    for k, off in enumerate((I_A, I_B, I_C)):
        m.put(off, int(round(ipk * math.cos(a - math.radians(lag) - 2 * math.pi * k / 3))))
    m.call(0x1EE60)
    r = m.pwm()
    return m.get(SECTOR, 'B'), [m.get(o, 'B') for o in (VA_NEXT, VB_NEXT, VC_NEXT)], [(r[0], r[1]), (r[2], r[3]), (r[4], r[5])]

out = {}
pair_ok = True
for M in (1000, 1023, 1050, 1100, 1182, 1300):
    row = {}
    for name, ipk, lag in (('i0', 0, 0), ('i600_inphase', 600, 0), ('i600_lag60', 600, 60), ('i600_lead120', 600, 120)):
        tmin, tmax, oor, inv, lost, lost_by = 9999, -9999, 0, 0, 0, {}
        for deg in range(360):
            sec, val, th = run(M, deg, ipk, lag)
            if name == 'i0':
                # recover t: zero-current branch writes TH0 = -max(t,0)... use the pair directly
                for th0, th1 in th:
                    tmin = min(tmin, th1); tmax = max(tmax, th1)
                # is the sector pair the two lowest duties?
                order = sorted(range(3), key=lambda k: th[k][1])
                lowest2 = ''.join(sorted('ABC'[k] for k in order[:2]))
                if PAIR[sec] != lowest2: pair_ok = False
            for th0, th1 in th:
                if th0 < -TH or th1 > TH: oor += 1
                if th0 > th1: inv += 1
            p = PAIR[sec]
            bad = [c for c in p if not val['ABC'.index(c)]]
            if bad:
                lost += 1
                key = 'middle' if True else ''
                lost_by[''.join(bad)] = lost_by.get(''.join(bad), 0) + 1
        row[name] = dict(out_of_range=oor, inverted_pairs=inv, angles_without_sample=lost, invalid_phase_in_pair=lost_by)
        if name == 'i0':
            row[name].update(t_min_zero_current=tmin, t_max_zero_current=tmax)
    out[M] = row
    print(M, json.dumps(row))
out['isr_pair_is_two_lowest_duties_for_all_angles'] = pair_ok
print('pair = two lowest duties at every angle:', pair_ok)
(OUT / 'E2_svpwm_edges.json').write_text(json.dumps(out, indent=1))
