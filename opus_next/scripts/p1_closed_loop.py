"""P1: full-throttle acceleration with the REAL nested routines in the loop and a
simple motor/battery/vehicle plant.  Analysis only; no device I/O.

Executed original routines (file offsets, runtime = file-0x17018), in the
scheduler order decoded at file 0x22A00..0x22AE8 (one 'tick' = 16 PWM periods,
nominal 1.0241667 ms):
  every tick, 4x  0x1D654 (DC/q limiter, FE ring, filtered q)   [D7 cadence]
  t%5==0  0x1E3D0 speed supervisor (DA step, coast)              [5-slot 0]
  t%5==1  0x22F38 converted voltage 0x210, U/OV monitor         [5-slot 1]
  t%5==2  0x1DDCC throttle->request                              [5-slot 2]
  t%10==4 0x1FC0C demand envelope BE->CA->C8->EA                 [10-slot 4]
  t%10==7 0x2036C optional q-trend governor detector             [10-slot 7]
  t%10==8 0x1DCB0 active-brake request                           [10-slot 8]
  t%10==9 0x1D9C0 hold detector                                  [10-slot 9]
The MCPWM ISR is NOT executed per PWM period; its command step is reproduced in
Python exactly as decoded at 0x1CD56..0x1CD8E (11C copies 140 when D8!=0, else
moves 1 count per ISR toward 140 -> up to 16 per tick) and the voltage circle of
0x1D5B8 (|11E|<=920, |11C|<=isqrt(1023^2-11E^2)).  Steady d-current regulation
(Id=0 target, decoded 0x1D5B8) is assumed converged: Vd = -w*L*Iq.

Plant assumptions are PARAMETERS (see PLANT); every run records them.
"""
import argparse, json, math, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from opus_emu import M0, load_initial_ram, BASE

TICK = 16 * (2 * 3072 + 1) / 96e6        # nominal, from TH0=3072 and prescaler 16
SQ3 = math.sqrt(3)

PLANT = dict(
    R_batt=0.161,      # ohm, from owner sample 54.15V rest / 50.87V @20.41A (includes polarisation)
    Voc=54.15,         # V, owner resting reading (near full)
    k_dc=0.0373,       # A battery per DC count (owner 20.41A at mean DC~547 under EA=560; Xiaomi 1000+-50W@54.6V at 493 -> 0.038+-0.002)
    k_fe=1000/54.0,    # FE counts per volt (0x210 = FE*8850>>14 decivolts)
    q_per_A=25.0,      # q counts per phase-peak amp  (UNCALIBRATED; swept)
    Rs=0.15,           # ohm phase resistance (assumed)
    X25=0.25,          # ohm phase reactance w*L at 25 km/h (assumed; L~0.25 mH @ ~160 Hz)
    ke=None,           # V phase-peak back-EMF per km/h (fitted unless given)
    eta_inv=0.96,      # inverter efficiency
    pole_pairs=15,     # assumed (only sets L = X25/w_e for the current dynamics)
    dynamic=True,      # integrate L di/dt (4 sub-steps per tick) instead of quasi-static current
    mass=100.0, crr=0.015, cda=0.55, rho=1.2, grade=0.0,
    r_wheel=0.127,     # m (10-inch tyre)
    eta_mech=0.95,
)

def put_frame(m, recovery=0x5A, throttle=100, mode=0x33):
    body = [0x51, 0x10, 0x06, mode, 0x01, 0x88, throttle, 0x00, recovery]
    fr = bytes(body + [sum(body) & 0xFF, 0xAE])
    m.u.mem_write(BASE + 0x68A, fr)
    m.call(0x20A14)
    return fr

def init_state(name, recovery=0x5A, soc=80, temp_remote=16, region=60559):
    m = M0(name, load_initial_ram('stock' if name == 'stock' else 'farm'))
    fr = put_frame(m, recovery)
    for off, v, f in ((0x108, 0, 'B'), (0x112, 0, 'B'), (0x158, 0, 'H'), (0x1F, 1, 'B'),
                      (0x14D, 3, 'B'), (0x164, 1, 'B'), (0x168, 0, 'B'), (0x169, 0, 'B'),
                      (0x1D7, 0, 'B'), (0x498, 0, 'I'), (0x328, temp_remote, 'b'),
                      (0x10, region, 'I'), (0xC2, 300, 'h'), (0xE8, 0, 'h'), (0xF3, soc, 'B'),
                      (0x8CB, soc, 'B'), (0x16D, 0, 'B'), (0x16C, 0, 'B'),
                      # settings block normally restored at boot (farm defaults, catalog):
                      (0x438, 250, 'H'), (0x43A, 450, 'H'), (0x43C, 91, 'H'), (0x43E, 160, 'H'),
                      (0x440, 320, 'H'), (0x1EC, 90, 'B'), (0x1B0, 90, 'B'),
                      # demand envelope settled at the farm Sport value (boot slew already done)
                      (0xBE, 560, 'H'), (0xCA, 560, 'H'), (0xC8, 560, 'H'), (0xEA, 560, 'H')):
        m.put(off, v, f)
    m.call(0x1DDCC)            # no-throttle pass initialises mode state
    m.put(0x158, 100, 'H')
    m.call(0x1DDCC)
    if m.get(0x1AA) != 450:
        raise SystemExit(f'request 1AA={m.get(0x1AA)} not 450: fixture incoherent')
    return m, fr

class Sim:
    def __init__(self, name, plant, recovery=0x5A, v0_kmh=5.0, soc=80):
        self.p = dict(plant)
        self.m, self.frame = init_state(name, recovery, soc=soc)
        self.v = v0_kmh / 3.6
        self.Ib = 0.0
        self.Vbus = self.p['Voc']
        self.Iq = 0.0
        self.t = 0
        self.vq_cmd = 0
        self.pb = 0.0
        self.vq_applied = 0.0
        m = self.m
        # coherent start: command at the back-EMF so current starts near zero
        e = self.p['ke'] * v0_kmh
        start = int(1023 * e / (self.Vbus / SQ3))
        for a in (0xDA, 0x140, 0x11C):
            m.put(a, start, 'H')
        self.vq_cmd = start
        m.put(0x158, 100, 'H')
        self.write_sensors()

    def period_for(self, kmh):
        return max(1, min(0x41E7, int(round(22442.7 / max(kmh * 10, 1e-3)))))

    def write_sensors(self):
        m, p = self.m, self.p
        kmh = self.v * 3.6
        per = self.period_for(kmh)
        m.put(0x8C, per, 'H'); m.put(0x2F6, per, 'H')
        dc = int(round(self.Ib / p['k_dc']))
        for a in (0x48, 0x4A, 0x4C, 0x4E):
            m.put(a, max(-2048, min(2047, dc)) * 16, 'h')
        fe = int(round(self.Vbus * p['k_fe']))
        for a in (0x50, 0x52, 0x54, 0x56):
            m.put(a, fe * 16, 'h')
        m.put(0xFE, fe, 'H'); m.put(0x210, (fe * 8850) >> 14, 'H')
        q = int(round(self.Iq * p['q_per_A']))
        m.put(0x132, max(-32768, min(32767, q)), 'h')
        m.put(0x130, 0, 'h')

    def electrical(self, dt):
        """advance q-current over dt with the command currently applied (11C)."""
        p = self.p
        kmh = self.v * 3.6
        vmax = self.Vbus / SQ3
        E = p['ke'] * kmh
        X = p['X25'] * kmh / 25.0
        cmd = self.vq_cmd * vmax / 1023
        vd = min(920, abs(X * self.Iq) / vmax * 1023)
        lim = math.isqrt(int(1023 * 1023 - vd * vd)) * vmax / 1023
        vq = min(cmd, lim)
        if p.get('dynamic', True):
            w25 = (25 / 3.6) / p['r_wheel'] * p['pole_pairs']
            L = p['X25'] / w25
            tau = L / p['Rs']
            i_inf = (vq - E) / p['Rs']
            self.Iq = i_inf + (self.Iq - i_inf) * math.exp(-dt / tau)
        else:
            self.Iq = (vq - E) / p['Rs']
        self.vq_applied = vq
        pel = 1.5 * vq * self.Iq
        pb = pel / p['eta_inv'] if pel > 0 else pel * p['eta_inv']
        disc = p['Voc'] ** 2 - 4 * p['R_batt'] * pb
        self.Vbus = (p['Voc'] + math.sqrt(max(disc, 1.0))) / 2
        self.Ib = pb / self.Vbus
        self.pb = pb

    def mechanical(self, dt):
        p = self.p
        kmh = self.v * 3.6
        F = 1.5 * p['ke'] * 3.6 * self.Iq * (p['eta_mech'] if self.Iq > 0 else 1 / p['eta_mech'])
        Fr = p['mass'] * 9.81 * (p['crr'] + p['grade']) + 0.5 * p['rho'] * p['cda'] * self.v ** 2
        self.v = max(0.0, self.v + (F - Fr) / p['mass'] * dt)

    def isr_command(self):
        m = self.m
        target = m.get(0x140, 'h')
        if m.get(0xD8, 'B'):
            self.vq_cmd = target
        else:
            d = target - self.vq_cmd
            self.vq_cmd += max(-16, min(16, d))
        m.put(0x11C, self.vq_cmd & 0xFFFF, 'H')

    def tick(self):
        m, t = self.m, self.t
        for _ in range(4):
            self.electrical(TICK / 4); self.write_sensors()
            m.call(0x1D654)
            self.isr_command()
        self.mechanical(TICK)
        if t % 5 == 0: m.call(0x1E3D0)
        if t % 5 == 1: m.call(0x22F38)      # 0x210 = FE*8850>>14, under/over-voltage monitor (5-slot phase 1)
        if t % 5 == 2: m.call(0x1DDCC)
        s = t % 10
        if s == 4: m.call(0x1FC0C)
        if s == 7: m.call(0x2036C)
        if s == 8: m.call(0x1DCB0)
        if s == 9: m.call(0x1D9C0)
        self.t += 1

    def snapshot(self):
        m = self.m
        return dict(t_s=round(self.t * TICK, 4), kmh=round(self.v * 3.6, 3), A6=m.get(0x1A6, 'h'),
                    P_batt_W=round(self.pb, 1), I_batt_A=round(self.Ib, 2), Vbus=round(self.Vbus, 2),
                    Iq_A=round(self.Iq, 2), DA=m.get(0xDA, 'h'), R140=m.get(0x140, 'h'), V11C=self.vq_cmd,
                    DC=m.get(0xDC, 'h'), EA=m.get(0xEA), C8=m.get(0xC8), q132=m.get(0x132, 'h'),
                    q14A=m.get(0x14A, 'h'), D8=m.get(0xD8, 'B'), flag90=m.get(0x90, 'B'), deb91=m.get(0x91, 'B'),
                    step1C6=m.get(0x1C6, 'h'), step1C8=m.get(0x1C8, 'h'), AA=m.get(0x1AA), gate1DA=m.get(0x1DA, 'B'),
                    vq_applied_frac=round(self.vq_applied / (self.Vbus / SQ3), 4))

def run(name, plant, seconds=40.0, every=0.25, recovery=0x5A, soc=80):
    s = Sim(name, plant, recovery, soc=soc)
    rows, nxt = [], 0.0
    first_sat = first_flag = None
    while s.t * TICK < seconds:
        s.tick()
        snap = None
        if first_sat is None and s.m.get(0xDA, 'h') >= 1023:
            snap = s.snapshot(); first_sat = snap
        if first_flag is None and s.m.get(0x90, 'B'):
            snap = snap or s.snapshot(); first_flag = snap
        if s.t * TICK >= nxt:
            rows.append(snap or s.snapshot()); nxt += every
    return dict(image=name, recovery=hex(recovery), frame=s.frame.hex(' '), plant=plant,
                first_DA_1023=first_sat, first_governor_flag=first_flag, rows=rows)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    print(json.dumps({'tick_ms': TICK * 1e3}))
