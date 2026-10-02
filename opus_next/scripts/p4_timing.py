"""P4.4: cycle-counted execution of the PWM interrupt (IRQ16, file 0x1CB14) and the
scheduler tasks, on states taken from the P1/P3 closed-loop runs plus randomised
ISR-specific inputs.  Cortex-M0 cycle table from the ARM Cortex-M0 TRM (single-cycle
multiplier assumed); flash wait states handled as a separate factor (manual 7.2.1.6:
96 MHz needs 2-cycle flash reads, sequential prefetch).  Emulator DSP divide/sqrt and
CORDIC are modelled with ZERO latency -> real numbers are higher by the DSP latency.
Run: MI5MAX_ROOT=<root> python p4_timing.py OUTDIR
"""
import json, random, re, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from unicorn import UC_HOOK_CODE
import unicorn.arm_const as A
from opus_emu import DELTA, BASE, STOP
from p1_closed_loop import PLANT, Sim, TICK
from p1_experiments import fit_ke

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '../evidence')
cs = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
COND = {'beq','bne','bhs','blo','bmi','bpl','bvs','bvc','bhi','bls','bge','blt','bgt','ble','bcs','bcc'}
_cache = {}

def cost(i, taken):
    m = i.mnemonic
    n = len(re.findall(r'r\d+|lr|pc', i.op_str)) if m in ('push', 'pop', 'ldm', 'ldmia', 'stm', 'stmia') else 0
    if m in COND: return 3 if taken else 1
    if m == 'b': return 3
    if m == 'bl': return 4
    if m in ('bx', 'blx'): return 3
    if m == 'pop': return (4 + n - 1) if 'pc' in i.op_str else 1 + n
    if m in ('push', 'ldm', 'ldmia', 'stm', 'stmia'): return 1 + n
    if m.startswith('ldr') or m.startswith('str'): return 2
    if m in ('mrs', 'msr', 'dsb', 'isb', 'dmb'): return 4
    if m in ('wfi', 'wfe'): return 2
    return 1

COVER = set()
class Counter:
    def __init__(self, uc):
        self.prev = None; self.cycles = 0; self.insns = 0; self.flash_fetch_words = 0
        self.img = None
        uc.hook_add(UC_HOOK_CODE, self.hook)
        uc.ctl_flush_tb()          # hooks added after translation are otherwise skipped for cached blocks
    def hook(self, uc, addr, size, _):
        if self.prev is not None:
            p = self.prev
            taken = addr != p.address + p.size
            self.cycles += cost(p, taken); self.insns += 1
        COVER.add(addr + DELTA)
        if addr not in _cache:
            _cache[addr] = next(cs.disasm(bytes(uc.mem_read(addr, 4)), addr, 1))
        self.prev = _cache[addr]
    def finish(self):
        if self.prev is not None:
            self.cycles += cost(self.prev, True); self.insns += 1; self.prev = None
    def reset(self):
        self.prev = None; self.cycles = 0; self.insns = 0

def measure_call(sim, file_off, counter):
    counter.reset()
    sim.m.call(file_off)
    counter.finish()
    return counter.cycles, counter.insns

def isr_case(sim, counter, rnd):
    m = sim.m
    # randomise ISR-owned inputs within their decoded ranges
    m.put(0x0C, rnd.choice([1, 1, 1, 0]), 'B')                   # ISR enable byte checked at file 0x1CCD6
    m.put(0x1D, rnd.choice([2, 2, 2, 1, 0, 3]), 'B')             # r7[9]: run state (2 normal)
    m.put(0x1C, rnd.choice([0, 1, 2, 5, 9, 10, 31]), 'B')        # r7[8]: start counter
    m.put(0x1B, rnd.randrange(0, 4), 'B')                         # r7[7]: D7 divider
    m.put(0x2E, rnd.randrange(0, 0x61A), 'H')                     # r7[26]
    m.put(0x19, rnd.randrange(0, 7), 'B')                         # previous sector
    for o in (0x24, 0x25, 0x26, 0x119, 0x11A, 0x11B): m.put(o, rnd.randrange(0, 2), 'B')
    m.put(0x1DF, rnd.choice([0, 1, 2]), 'B')
    m.put(0x142, rnd.randrange(0, 2), 'H'); m.put(0xD8, rnd.randrange(0, 2), 'B')
    m.put(0x109, rnd.choice([0, 0, 1]), 'B'); m.put(0x113, rnd.randrange(0, 2), 'B')
    m.put(0xF0, 0, 'B'); m.put(0xF1, 0, 'B'); m.put(0x20, rnd.randrange(0, 2), 'B')
    m.put(0x310, rnd.randrange(0, 65536), 'H')
    m.put(0x11E, rnd.randrange(-920, 921), 'h')
    m.put(0x140, rnd.randrange(0, 1024), 'H')
    for base in (0x40010400, 0x40010500):
        for k in range(16):
            m.u.mem_write(base + 4 * k, struct.pack('<I', (rnd.randrange(-2000, 2000) & 0xFFF) << 4))
    m.u.mem_write(0x40010C84, struct.pack('<I', 1))               # PWM status bit polled at 1CDEE
    return measure_call(sim, 0x1CB14, counter)

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(20261002)
    p = dict(PLANT); p['ke'] = fit_ke(dict(p), 750, p['k_dc'] * 547)
    res = {'cycle_model': 'Cortex-M0 TRM, single-cycle MULS, zero-latency DSP/CORDIC model, flash wait states excluded',
           'pwm_period_cycles': 2 * 3072 + 1, 'd7_window_cycles': 4 * (2 * 3072 + 1)}
    isr = []
    tasks = {}
    for image in ('farm', 'rc02'):
        for scenario in ('accel', 'coast'):
            s = Sim(image, p, v0_kmh=5 if scenario == 'accel' else 28)
            if scenario == 'coast':
                s.m.put(0x158, 0, 'H'); s.m.call(0x1DDCC); s.p['grade'] = -0.08
            c = Counter(s.m.u)
            stats = {}
            for t in range(6000):
                # per tick: 4 x 1D654, then the scheduled tasks (same order as p1_closed_loop.Sim.tick)
                for _ in range(4):
                    s.electrical(TICK / 4); s.write_sensors()
                    cyc, n = measure_call(s, 0x1D654, c); stats.setdefault('1D654', []).append(cyc)
                    s.isr_command()
                s.mechanical(TICK)
                sl5, sl10 = t % 5, t % 10
                for cond, fo in ((sl5 == 0, 0x1E3D0), (sl5 == 2, 0x1DDCC), (sl10 == 4, 0x1FC0C), (sl10 == 7, 0x2036C),
                                 (sl10 == 8, 0x1DCB0), (sl10 == 9, 0x1D9C0)):
                    if cond:
                        cyc, n = measure_call(s, fo, c); stats.setdefault(f'{fo:05X}', []).append(cyc)
                s.t += 1
                if t % 50 == 0:
                    snap = s.m.ram(0x1050)
                    for _ in range(6):
                        cyc, n = isr_case(s, c, rnd)
                        isr.append(dict(image=image, scenario=scenario, t=t, cycles=cyc, insns=n))
                        s.m.u.mem_write(BASE, snap)
            for k, v in stats.items():
                d = tasks.setdefault(k, dict(max=0, mean=0.0, n=0))
                d['max'] = max(d['max'], max(v)); d['mean'] = (d['mean'] * d['n'] + sum(v)) / (d['n'] + len(v)); d['n'] += len(v)
            print(image, scenario, {k: max(v) for k, v in stats.items()}, flush=True)
    need = {0x1D468, 0x1D5B8, 0x1EE60, 0x1D4C0, 0x22038, 0x1B7EC, 0x1C828}
    if not need <= COVER:
        raise SystemExit(f'ISR coverage incomplete: missing {[hex(x) for x in need - COVER]}')
    res_cover = sorted(hex(x) for x in need)
    if any(v['max'] == 0 for v in tasks.values()):
        raise SystemExit('a task measured 0 cycles: hook not applied')
    res['isr_paths_required_and_seen'] = res_cover
    res['isr_samples'] = len(isr)
    res['isr_max_cycles'] = max(x['cycles'] for x in isr)
    res['isr_max_case'] = max(isr, key=lambda x: x['cycles'])
    res['isr_mean_cycles'] = sum(x['cycles'] for x in isr) / len(isr)
    res['task_cycles'] = tasks
    E = 16 + 16   # M0 exception entry + exit (zero wait state)
    W = res['d7_window_cycles']
    for factor in (1.0, 1.5, 2.0):
        isr_load = 4 * (res['isr_max_cycles'] + E) * factor
        res[f'budget_x{factor}'] = dict(isr_share_of_pwm_period=round((res['isr_max_cycles'] + E) * factor / res['pwm_period_cycles'], 3),
                                        main_cycles_left_per_D7_window=round(W - isr_load),
                                        slowest_task=max(tasks, key=lambda k: tasks[k]['max']),
                                        slowest_task_cycles=round(tasks[max(tasks, key=lambda k: tasks[k]['max'])]['max'] * factor))
    (OUT / 'P4_timing_evidence.json').write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != 'isr_max_case'}, indent=1))

if __name__ == '__main__':
    main()
