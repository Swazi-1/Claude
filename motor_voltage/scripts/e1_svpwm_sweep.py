"""E1: run the real svpwm_output (B:1EE60) for voltage vectors of magnitude M at 360 angles.

For each M it reports:
* t per phase (the half on-time in counts, 1536 = 50 %), the TH register pairs written;
* whether any compare value falls outside the counter range -3072..+3072;
* the share of angles where the next ISR cannot reconstruct the current
  (the ISR uses a fixed phase pair per sector and needs both 'valid' flags);
* the fundamental phase amplitude the PWM would produce, as a fraction of Vbus/sqrt(3),
  for an ideal bridge that clamps each phase's on-time to 0..100 % and for which the
  dead-time compensation exactly cancels the dead time (so duty = 2t/6144).
Two current cases: zero current (compensation neutral) and a sinusoidal phase current
of 600 counts peak in phase with the voltage (compensation fully active, |i| > 120).
Run: MI5MAX_ROOT=<project> python e1_svpwm_sweep.py <outdir>
"""
import json, math, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mv_emu import *

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '../evidence')
TH, VALID_LIM, PERIOD = 3072, 0x57 << 5, 6144   # 0x57<<5 = 2784
PAIR = {4: 'AB', 6: 'AB', 0: 'AB', 2: 'BC', 3: 'BC', 1: 'AC', 5: 'AC'}  # ISR_MCPWM0 B:1CBxx, by sector_prev

m = M0('v10')

def one(M, deg, ipk):
    a = math.radians(deg)
    m.put(V_ALPHA, int(round(M * math.cos(a)))); m.put(V_BETA, int(round(M * math.sin(a))))
    # phase currents in phase with the voltage vector (a = alpha axis = phase A)
    for k, off in enumerate((I_A, I_B, I_C)):
        m.put(off, int(round(ipk * math.cos(a - 2 * math.pi * k / 3))))
    m.call(0x1EE60)
    r = m.pwm()
    sector = m.get(SECTOR, 'B')
    valid = {p: m.get(o, 'B') for p, o in zip('ABC', (VA_NEXT, VB_NEXT, VC_NEXT))}
    th = {'A': (r[0], r[1]), 'B': (r[2], r[3]), 'C': (r[4], r[5])}
    return sector, valid, th

def fundamental(duty):
    # duty arrays (3, N) over one electrical turn -> phase-voltage fundamental / (Vbus/sqrt3)
    v = np.array(duty)
    vn = v - v.mean(axis=0)            # remove common mode
    c = np.fft.rfft(vn[0])[1] * 2 / v.shape[1]
    return abs(c) * math.sqrt(3)

res = {}
for M in (500, 800, 900, 950, 1000, 1023, 1050, 1100, 1182, 1200, 1300, 1400, 1500, 1600):
    row = {}
    for ipk in (0, 600):
        tmax = {'A': 0, 'B': 0, 'C': 0}; oor = 0; inval = 0; mid_t = []
        duty_ideal, duty_raw = [[], [], []], [[], [], []]
        sectors = set()
        for deg in np.arange(0, 360, 1.0):
            sector, valid, th = one(M, deg, ipk)
            sectors.add(sector)
            ts = []
            for k, p in enumerate('ABC'):
                th0, th1 = th[p]
                t_nom = th1 if th0 == -th1 else None
                # on-time actually requested (ignoring compensation): recover t from the pair
                on = th1 - th0
                if th0 < -TH or th1 > TH: oor += 1
                eff = min(max(on, 0), PERIOD)              # ideal clamp
                # remove the compensation part: effective volt-seconds = 2t (dead time cancels)
                comp = on - 2 * (th1 if th0 <= -th1 else -th0)
                duty_raw[k].append(eff / PERIOD)
                tmax[p] = max(tmax[p], max(th1, -th0))
                ts.append(max(th1, -th0))
            # ideal duty: 2t / period clamped
            for k in range(3):
                pass
            mid_t.append(sorted(ts)[1])
            pair = PAIR.get(sector, '')
            if not pair or not all(valid[p] for p in pair):
                inval += 1
        # ideal fundamental from t without compensation: rerun with zero current to get t
        row[f'i{ipk}'] = dict(t_max={k: int(v) for k, v in tmax.items()}, compare_out_of_range_phase_angles=oor,
                              angles_without_current_sample=inval, max_middle_phase_t=int(max(mid_t)),
                              fundamental_fraction_of_vbus_over_sqrt3=round(fundamental(duty_raw), 4),
                              sectors=sorted(sectors))
    res[M] = row
    print(M, json.dumps(row))
(OUT / 'E1_svpwm_sweep.json').write_text(json.dumps(res, indent=1))
