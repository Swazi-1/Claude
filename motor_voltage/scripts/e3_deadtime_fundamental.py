"""E3: phase-voltage fundamental at |V| = 1023 including the dead time, from the real compare values of svpwm_output.

Bridge model (complementary mode of the LKS MCPWM, manual 14.1.4.1): high side on from TH<n>0 + DTH to TH<n>1,
dead time DTH = 76 counts at both edges. During a dead time the phase follows the current: positive (out of the
phase) -> low diode -> phase low; negative -> high diode -> phase high. So the effective high time is
  on_eff = (TH1 - TH0) - 76 * sign(i)           (clamped to the period 0..6144)
Compare values outside -3072..3072 are clamped to the counter range (assumes the hardware saturates; the stock
firmware already writes such values at full voltage, see E2). Currents are sinusoidal, amplitude I counts, lagging
the voltage by phi. Prints the fundamental as a fraction of Vbus/sqrt3.
"""
import json, math, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mv_emu import *
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '../evidence')
TH, DT, P = 3072, 76, 6144
m = M0('v10')
def fund(M, I, phi, comp=True, dead=True):
    duty = [[], [], []]
    for deg in np.arange(0, 360, 0.5):
        a = math.radians(deg)
        m.put(V_ALPHA, int(round(M * math.cos(a)))); m.put(V_BETA, int(round(M * math.sin(a))))
        cur = [I * math.cos(a - math.radians(phi) - 2 * math.pi * k / 3) for k in range(3)]
        for k, off in enumerate((I_A, I_B, I_C)):
            m.put(off, int(round(cur[k])) if comp else 0)
        m.call(0x1EE60); r = m.pwm()
        for k in range(3):
            th0 = max(-TH, min(TH, r[2 * k])); th1 = max(-TH, min(TH, r[2 * k + 1]))
            on = th1 - th0
            if dead and on > 0 and on < P:      # a phase that does not switch has no dead time
                on -= DT * (1 if cur[k] > 0 else -1)
            duty[k].append(min(max(on, 0), P) / P)
    v = np.array(duty); vn = v - v.mean(axis=0)
    return abs(np.fft.rfft(vn[0])[1] * 2 / v.shape[1]) * math.sqrt(3)
res = {}
for I in (0, 60, 200, 600, 1200):
    for phi in (0, 20, 40):
        res[f'I{I}_phi{phi}'] = dict(with_comp=round(fund(1023, I, phi), 4), no_comp=round(fund(1023, I, phi, comp=False), 4))
res['ideal_no_deadtime_I0'] = round(fund(1023, 0, 0, comp=False, dead=False), 4)
print(json.dumps(res, indent=1))
(OUT / 'E3_deadtime_fundamental.json').write_text(json.dumps(res, indent=1))
