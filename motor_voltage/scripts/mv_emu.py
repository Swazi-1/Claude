"""Minimal Cortex-M0 fixture for program B (motor controller) of the Mi 5 Max image.

Written for the motor-voltage study. Runs single firmware functions in Unicorn.
* Project root: env MI5MAX_ROOT (the extracted 'MI5Max_project' folder).
* Program B runtime address = file offset - 0x17018 (flash mapped at 0).
* RAM 0x20000000..0x20002FFF; initial data from 04_FIRMWARE_KNOWLEDGE_BASE/data/B_initial_ram.bin.
* Peripherals 0x40000000..0x40020FFF are plain memory, plus a host model of the
  DSP block: divider (0x40013020/24 -> 0x28), integer sqrt (0x40013030 -> 0x34),
  sin/cos (0x40013004 -> 0x10/0x14), as used by the image.
"""
import hashlib, math, os, struct
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
import unicorn.arm_const as A

ROOT = Path(os.environ.get('MI5MAX_ROOT', '.'))
DELTA, RAM, STOP = 0x17018, 0x20000000, 0x1000
IMAGES = {
    'v10': ('01_FIRMWARE/1h_V10_BOOST648_not_flashed/MI5Max_V10_BOOST648_CANDIDATE.bin', '28dce28c9a0d'),
    'stock': ('01_FIRMWARE/2_ORIGINAL_STOCK/01_STOCK_ORIGINAL.bin', '015718dd8126'),
    'v8': ('01_FIRMWARE/1_CURRENT_ON_SCOOTER_V8_FINAL_600/MI5Max_V8_FINAL_600.bin', '901ce6cea8fa'),
}
PWM = 0x40010C00  # MCPWM0_TH00; TH01 +4, TH10 +8, TH11 +0xC, TH20 +0x10, TH21 +0x14

def load_image(name):
    rel, sha = IMAGES[name]
    b = (ROOT / rel).read_bytes()
    h = hashlib.sha256(b).hexdigest()
    if not h.startswith(sha) or len(b) != 147456:
        raise SystemExit(f'hash mismatch for {name}: {h[:12]}')
    return b

def rt(file_off):
    return file_off - DELTA

class M0:
    def __init__(self, name='v10', patches=None):
        img = bytearray(load_image(name))
        for off, data in (patches or {}).items():
            img[off:off + len(data)] = data
        self.img = bytes(img)
        u = self.u = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        u.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_M0)
        u.mem_map(0, 0x20000)
        u.mem_write(0, self.img[DELTA:DELTA + 0x20000])
        u.mem_map(RAM, 0x3000)
        u.mem_write(RAM, (ROOT / '04_FIRMWARE_KNOWLEDGE_BASE/data/B_initial_ram.bin').read_bytes())
        u.mem_map(0x40000000, 0x21000)

        def dsp(uc, acc, addr, size, val, _):
            if addr == 0x40013024:
                n = struct.unpack('<i', uc.mem_read(0x40013020, 4))[0]
                d = struct.unpack('<i', struct.pack('<I', val & 0xFFFFFFFF))[0]
                q = 0 if d == 0 else abs(n) // abs(d)
                if d and (n < 0) != (d < 0):
                    q = -q
                uc.mem_write(0x40013028, struct.pack('<I', q & 0xFFFFFFFF))
            elif addr == 0x40013030:
                uc.mem_write(0x40013034, struct.pack('<I', math.isqrt(val & 0xFFFFFFFF)))
            elif addr == 0x40013004:
                th = struct.unpack('<h', struct.pack('<H', val & 0xFFFF))[0] * math.pi / 32768
                uc.mem_write(0x40013010, struct.pack('<i', int(round(math.sin(th) * 32767))))
                uc.mem_write(0x40013014, struct.pack('<i', int(round(math.cos(th) * 32767))))
        u.hook_add(UC_HOOK_MEM_WRITE, dsp, begin=0x40013000, end=0x40013FFF)

    def put(self, a, v, f='h'):
        self.u.mem_write(RAM + a, struct.pack('<' + f, v))

    def get(self, a, f='h'):
        return struct.unpack('<' + f, self.u.mem_read(RAM + a, struct.calcsize(f)))[0]

    def pwm(self):
        return struct.unpack('<6i', self.u.mem_read(PWM, 24))

    def call(self, file_off, count=500000):
        self.u.reg_write(A.UC_ARM_REG_SP, 0x20001050)
        self.u.reg_write(A.UC_ARM_REG_LR, STOP | 1)
        self.u.emu_start(rt(file_off) | 1, STOP, count=count)
        if self.u.reg_read(A.UC_ARM_REG_PC) != STOP:
            raise RuntimeError(f'call {file_off:#x} did not return')
        return self.u.reg_read(A.UC_ARM_REG_R0)

# RAM cells used here (offsets from 0x20000000, names from B_RAM_MAP.md)
SECTOR, VA_NEXT, VB_NEXT, VC_NEXT = 0x118, 0x119, 0x11A, 0x11B
VQ, VD = 0x11C, 0x11E
I_A, I_B, I_C = 0x122, 0x124, 0x126
V_ALPHA, V_BETA = 0x12C, 0x12E
I_D, I_Q = 0x130, 0x132
DUTY_A = 0x134
ELEC_ANGLE = None  # looked up by the scripts from the disassembly when needed
