"""E4: what a higher voltage limit or field weakening would do, on the project's virtual scooter.

The real program-B control code (V10 image) runs in Unicorn exactly as in 06_VIRTUAL_SCOOTER; only the
Python plant is changed:
* k_om  : the inverter's phase-voltage fundamental at drive command 1023 is multiplied by k_om
          (models a changed vq_like-to-duty scale with overmodulation; E1 gives the achievable fundamental:
          1.040 at |V|=1100, 1.055 at 1182, at most 1.10 in six-step). Harmonic losses are NOT modelled.
* id_fw : field weakening. While the drive command is at >= 1000 (voltage-limited) and speed > 10 km/h,
          the d-axis current is driven to -id_fw amps (peak) with a 30 ms lag. The plant then uses
          vq = e + R*iq + X*id, vd = R*id - X*iq, |V| <= vmax, and copper loss 1.5*R*(iq^2 + id^2).
Nothing here is firmware: it is a what-if on the fitted plant (labels S/L, not C).
Run: python e4_vscooter_variants.py <outdir>   (needs MI5MAX_ROOT; imports 06_VIRTUAL_SCOOTER)
"""
import json, math, os, sys
from dataclasses import replace
from pathlib import Path
ROOT = Path(os.environ['MI5MAX_ROOT'])
sys.path.insert(0, str(ROOT / '06_VIRTUAL_SCOOTER'))
import vscooter
from vscooter import VScooter, ocv_at, r0_at, SQ3
from calibrate import load_params

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '../evidence')


class VS(VScooter):
    def __init__(self, *a, k_om=1.0, id_fw=0.0, **kw):
        self.k_om, self.id_fw, self.id = k_om, id_fw, 0.0
        self.max_iph, self.max_id = 0.0, 0.0
        super().__init__(*a, **kw)

    def _plant(self, dt):
        p, m = self.p, self.m
        vq_cnt = m.rs('vq_like')
        vbus = self.v_term
        vmax = p.m_max * self.k_om * vbus / SQ3
        v_kmh = self.speed * 3.6
        x = p.xl * v_kmh
        # field weakening request (only when voltage-limited)
        want = -self.id_fw if (self.id_fw and vq_cnt >= 1000 and v_kmh > 10) else 0.0
        self.id += (want - self.id) * min(1.0, dt / 0.03)
        idd = self.id
        vd = p.r_phase * idd - x * max(self.iq, 0.0)
        avail = math.sqrt(max(0.0, vmax * vmax - vd * vd))
        vq = max(-avail, min(avail, vq_cnt / 1023.0 * vmax))
        e = p.ke * v_kmh
        iq_ss = (vq - e - x * idd) / p.r_phase
        tau = max(self.DT, p.l_per_xl * p.xl / p.r_phase) if p.xl > 0 else self.DT
        self.iq += (iq_ss - self.iq) * min(1.0, dt / tau)
        iq = self.iq
        p_in = 1.5 * (e * iq + p.r_phase * (iq * iq + idd * idd)) + p.p_idle
        self.i_dc = p_in / max(vbus, 20.0)
        self.max_iph = max(self.max_iph, math.hypot(iq, idd)); self.max_id = min(self.max_id, idd)
        i = self.i_dc
        self.vp += (i * p.r1 - self.vp) * dt / p.tau_p
        self.v_term = ocv_at(p, self.soc) - i * r0_at(p, self.soc) - self.vp
        self.soc -= i * self.v_term * dt / (p.cap_wh * 3600.0) * 100.0
        force = 1.5 * p.ke * 3.6 * iq
        g = 9.81
        res = (p.crr * p.mass * g * math.cos(self.slope) + 0.5 * p.rho * p.cda * self.speed ** 2
               + p.mass * g * math.sin(self.slope) + p.c_fe * v_kmh)
        net = force - res
        if self.speed <= 0.0 and net < 0: net = 0.0
        self.speed = max(0.0, self.speed + net / (p.mass + p.rot_mass) * dt)
        self.dist += self.speed * dt
        heat = p.k_heat * (iq * iq + idd * idd) + 3.0
        self.temp += (heat - p.g_th * (self.temp - p.amb_c)) / p.c_th * dt


def launch(k_om=1.0, id_fw=0.0, soc=97, slope=0.0, chip_rules=True):
    p = load_params()
    s = VS('V10', p=p, soc=soc, speed_kmh=3.0, slope_deg=slope, ctrl_c=45, k_om=k_om, id_fw=id_fw,
           chip='real' if chip_rules else 'python', trip_cuts_power=chip_rules)
    s.set_boost_switch(True)
    s.run([(0.3, 0)]); t0 = s.t
    s.run_until(100, 60.0, 40.0)            # hold full throttle 40 s (top speed)
    rows = [r for r in s.rows if r['t'] >= t0]
    top = max(r['v'] for r in rows[-200:])
    def amps(v):
        xs = [r['a'] for r in rows if abs(r['v'] - v) <= 0.3]
        return round(sum(xs) / len(xs), 1) if xs else None
    return dict(k_om=k_om, id_fw=id_fw, soc=soc, slope=slope,
                t3_20=round(s.time_to(20.0, t0) or -1, 2), t3_30=round(s.time_to(30.0, t0) or -1, 2),
                t20_30=round((s.time_to(30.0, t0) or 99) - (s.time_to(20.0, t0) or 0), 2),
                top_kmh=round(top, 2), batt_peak_A=round(max(r['a'] for r in rows), 1),
                amps_at_25=amps(25), amps_at_28=amps(28), amps_at_30=amps(30), amps_at_top=round(rows[-1]['a'], 1),
                phase_peak_A=round(s.max_iph, 1), id_min=round(s.max_id, 1), temp_end=round(s.temp, 1),
                chip_trip=s.dead)


if __name__ == '__main__':
    cases = [dict(), dict(k_om=1.025), dict(k_om=1.040), dict(k_om=1.055),
             dict(id_fw=10), dict(id_fw=20), dict(id_fw=30)]
    res = []
    for soc, slope in ((97, 0.0), (75, -2.0), (50, 0.0)):
        for c in cases:
            r = launch(soc=soc, slope=slope, **c)
            res.append(r); print(json.dumps(r), flush=True)
    (OUT / 'E4_vscooter_variants.json').write_text(json.dumps(res, indent=1))
