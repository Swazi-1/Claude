"""E3b: fundamental (fraction of Vbus/sqrt3, dead time included as in E3) for the patch options, using the real
svpwm_output compare values and then post-processing them the way a patched routine would:
* stock          : compare values as written, clamped to the counter range
* drop           : 'pulse dropping' - a phase whose requested on-time is within 2*DTH of 100 % is written as
                   TH0=-3072, TH1=+3072 (manual 14.1.3 case 2, 100 %, no switching, no dead time); one within 2*DTH
                   of 0 % is written as TH0=TH1=0 (case 1, 0 %)
* overmod M      : |V| = M (>1023), each phase's requested on-time clamped to 0..100 % (no inverted pairs), + drop
Also the low-order harmonics (5th, 7th) of the phase voltage, in % of the fundamental (torque ripple source).
Currents: 600 counts peak lagging 20 deg (typical full-throttle cruise)."""
import json, math, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mv_emu import *
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '../evidence')
TH, DT, P = 3072, 76, 6144
m = M0('v10')
def wave(M, I=600, phi=20, mode='stock'):
    duty = [[], [], []]
    for deg in np.arange(0, 360, 0.25):
        a = math.radians(deg)
        m.put(V_ALPHA, int(round(M * math.cos(a)))); m.put(V_BETA, int(round(M * math.sin(a))))
        cur = [I * math.cos(a - math.radians(phi) - 2 * math.pi * k / 3) for k in range(3)]
        for k, off in enumerate((I_A, I_B, I_C)): m.put(off, int(round(cur[k])))
        m.call(0x1EE60); r = m.pwm()
        for k in range(3):
            th0, th1 = r[2 * k], r[2 * k + 1]
            if mode != 'stock':
                if th0 > th1: th0 = th1 = 0                      # an inverted pair is treated as 0 % (safe clamp)
                th0 = max(-TH, th0); th1 = min(TH, th1)
                on = th1 - th0
                if on >= P - 2 * DT: th0, th1 = -TH, TH
                elif on <= 2 * DT: th0 = th1 = 0
            th0 = max(-TH, min(TH, th0)); th1 = max(-TH, min(TH, th1))
            on = th1 - th0
            if 0 < on < P: on -= DT * (1 if cur[k] > 0 else -1)
            duty[k].append(min(max(on, 0), P) / P)
    v = np.array(duty); vn = v - v.mean(axis=0)
    # line-line voltage carries what the motor sees; phase-to-neutral = vn
    F = np.fft.rfft(vn[0]) * 2 / v.shape[1]
    f1 = abs(F[1]) * math.sqrt(3)
    return dict(fundamental=round(f1, 4), h5_pct=round(100 * abs(F[5]) / abs(F[1]), 2), h7_pct=round(100 * abs(F[7]) / abs(F[1]), 2))
res = {'stock_1023': wave(1023), 'drop_1023': wave(1023, mode='drop'),
       'stock_1000': wave(1000), 'stock_900': wave(900)}
for M in (1050, 1100, 1182, 1300, 1500):
    res[f'overmod_clamped_drop_{M}'] = wave(M, mode='drop')
print(json.dumps(res, indent=1))
(OUT / 'E3b_options_fundamental.json').write_text(json.dumps(res, indent=1))
