"""E5: verify the proposed 'SVPWM gain' patch (option B) in the emulator. NOT a build: the bytes are only written
into the emulated flash. The three multiplier sites in svpwm_output (movs rX,#3 ; lsls rX,rX,#9 = 1536 = 1.5*1024)
become movs rX,#200 ; lsls rX,rX,#3 = 1600 (+4.17 %). The four 'center' sites that also build 1536 are NOT touched.
Checks: disassembly of the patched bytes, t at |V| = 0 (center unchanged = 1536), gain against stock at |V| = 500,
the |V| at which the top phase first reaches 100 %, and the fundamental with dead time (E3 model) at 1023."""
import json, math, sys
from pathlib import Path
import numpy as np
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mv_emu import *
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '../evidence')
PATCH = {0x1EE9E: (bytes.fromhex('03214902'), bytes.fromhex('c821c900')),
         0x1EEA6: (bytes.fromhex('0322'), bytes.fromhex('c822')),
         0x1EEAA: (bytes.fromhex('5202'), bytes.fromhex('d200')),
         0x1EEB0: (bytes.fromhex('03235b02'), bytes.fromhex('c823db00'))}
img = load_image('v10')
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
out = {'sites': {}}
for off, (old, new) in PATCH.items():
    assert img[off:off + len(old)] == old, hex(off)
    out['sites'][hex(off)] = dict(old=old.hex(), new=new.hex(),
        old_asm=[f'{i.mnemonic} {i.op_str}' for i in md.disasm(old, off - DELTA)],
        new_asm=[f'{i.mnemonic} {i.op_str}' for i in md.disasm(new, off - DELTA)])
base, pat = M0('v10'), M0('v10', patches={o: n for o, (_, n) in PATCH.items()})
def ts(m, M, deg):
    a = math.radians(deg)
    m.put(V_ALPHA, int(round(M * math.cos(a)))); m.put(V_BETA, int(round(M * math.sin(a))))
    for o in (I_A, I_B, I_C): m.put(o, 0)
    m.call(0x1EE60); r = m.pwm(); return [r[1], r[3], r[5]]
out['center_at_zero'] = dict(stock=ts(base, 0, 0), patched=ts(pat, 0, 0))
sw = lambda m, M: max(max(ts(m, M, d)) - min(ts(m, M, d)) for d in range(0, 360, 2))
out['swing_ratio_at_500'] = round(sw(pat, 500) / sw(base, 500), 4)
first = None
for M in range(900, 1030):
    if max(max(ts(pat, M, d)) for d in range(0, 360, 2)) >= 3072: first = M; break
out['patched_first_M_with_100pct'] = first
print(json.dumps(out, indent=1))
(OUT / 'E5_scale_patch.json').write_text(json.dumps(out, indent=1))
