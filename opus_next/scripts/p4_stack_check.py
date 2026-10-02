"""P4.3 cross-check: static worst-case stack (p4_static) vs emulator-measured minimum SP
for the scheduler/ISR routines, plus main-loop call-site depths and the combined
interrupt-nesting bound.  Run: MI5MAX_ROOT=<root> python p4_stack_check.py IMAGE OUTDIR"""
import json, sys
from pathlib import Path
img_name = sys.argv[1] if len(sys.argv) > 1 else 'farm'
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else '../evidence')
sys.argv = ['p4_static.py', img_name]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import p4_static as S
from opus_emu import DELTA
from unicorn import UC_HOOK_CODE
import unicorn.arm_const as A
from p1_closed_loop import PLANT, Sim, TICK
from p1_experiments import fit_ke

def worst_file(f): return S.worst(f - DELTA)[0]
routines = [0x1D654, 0x1E3D0, 0x1DDCC, 0x1FC0C, 0x2036C, 0x1DCB0, 0x1D9C0, 0x1CB14, 0x20A14, 0x1D09C, 0x200A8]
static = {f'{f:05X}': worst_file(f) for f in routines}
# dynamic
p = dict(PLANT); p['ke'] = fit_ke(dict(p), 750, p['k_dc'] * 547)
s = Sim(img_name, p, v0_kmh=5)
lo = {'v': 0x20001050}
def h(uc, a, sz, _):
    sp = uc.reg_read(A.UC_ARM_REG_SP)
    if sp < lo['v']: lo['v'] = sp
s.m.u.hook_add(UC_HOOK_CODE, h); s.m.u.ctl_flush_tb()
dyn = {}
for t in range(3000):
    for _ in range(4):
        s.electrical(TICK / 4); s.write_sensors()
        lo['v'] = 0x20001050; s.m.call(0x1D654); dyn['1D654'] = max(dyn.get('1D654', 0), 0x20001050 - lo['v'])
        s.isr_command()
    s.mechanical(TICK)
    for cond, fo in ((t % 5 == 0, 0x1E3D0), (t % 5 == 2, 0x1DDCC), (t % 10 == 4, 0x1FC0C), (t % 10 == 7, 0x2036C),
                     (t % 10 == 8, 0x1DCB0), (t % 10 == 9, 0x1D9C0)):
        if cond:
            lo['v'] = 0x20001050; s.m.call(fo); k = f'{fo:05X}'; dyn[k] = max(dyn.get(k, 0), 0x20001050 - lo['v'])
    s.t += 1
lo['v'] = 0x20001050; s.m.call(0x1CB14); dyn['1CB14'] = 0x20001050 - lo['v']
bad = {k: (dyn[k], static[k]) for k in dyn if dyn[k] > static[k]}
if bad: raise SystemExit(f'dynamic stack exceeds static bound: {bad}')
# main-loop call-site depths
main = 0x2292C - DELTA
d_main = {}
for a, t, d in S.callee[main]:
    if t is not None:
        d_main[f'{t + DELTA:05X}'] = max(d_main.get(f'{t + DELTA:05X}', 0), d + S.worst(t)[0])
reset_to_main = S.entries['indirect_from_199A8']['worst_bytes']
irq = {k: v['worst_bytes'] for k, v in S.entries.items() if k.startswith('IRQ')}
FRAME = 32 + 4     # M0 basic frame + worst-case 8-byte alignment padding
nest = reset_to_main + (FRAME + max(irq['IRQ10'], irq['IRQ11'])) + (FRAME + irq['IRQ16']) + (FRAME + max(irq['IRQ6'], irq['IRQ23']))
res = dict(image=img_name, static_worst=static, emulated_peak=dyn, main_thread_worst=reset_to_main,
           main_loop_children_worst=dict(sorted(d_main.items(), key=lambda kv: -kv[1])[:12]),
           irq_worst=irq, priorities={'IRQ6 I2C0': 0, 'IRQ23 PWRDN': 0, 'IRQ16 MCPWM0': 1, 'IRQ10 UART0': 3, 'IRQ11 UART1': 3},
           nesting_bound_bytes=nest, reservation=1024, margin=1024 - nest,
           lab_helper_added_bytes={'coast leaf': 24, 'cleanup wrapper': 16, 'child leaf': 24, 'rc02 helper': 16})
(OUT / f'P4_stack_{img_name}.json').write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
