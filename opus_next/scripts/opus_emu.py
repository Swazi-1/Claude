"""Minimal independent Cortex-M0 fixture for the nested LKS32MC071 image.

Written fresh for the Opus investigation (does not import the earlier harness).
Project root is taken from env MI5MAX_ROOT (the extracted ZIP folder).
Nested runtime = file - 0x17018.  RAM 0x20000000..0x20002FFF mapped.
Peripherals 0x40000000..0x40020FFF mapped as plain memory, with a host model of
the DSP divider (0x40013020/24/28) and integer sqrt (0x40013030/34), as in the
earlier fixture; CORDIC sin/cos (0x40013004/10/14) is modelled on demand.
"""
import hashlib, math, os, struct
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
import unicorn.arm_const as A

ROOT = Path(os.environ.get('MI5MAX_ROOT', Path(__file__).resolve().parents[2] / 'MI5Max_Opus_Next_Investigation'))
DELTA, BASE, STOP = 0x17018, 0x20000000, 0x1000
IMAGES = {
    'stock': ('inputs/firmware/370dbaba96a88d7f4dd7bc8d7aafd78b_mcu_xiaomi.scooter.5max.bin',
              '015718dd81261662c322a4ea183f98486ab4062bfb367ce0c7208fa1ba153aeb'),
    'farm': ('inputs/firmware/mi5max_farm_v7_1_regenfix.bin',
             'b4c64d8464dbee8b4d238b02758ff36cf57acf94b0492fc3693cb68dedd56a4a'),
    'rc01': ('outputs/v8_child_cap_candidate_2026-09-30/mi5max_v8_rc01_child_ceiling_UNVERIFIED.bin',
             '1c58131d6be735481ad4f1cb07c4ade276908fc52c689a370fc032a3329f8c8e'),
    'rc02': ('outputs/v8_rc02_sport35_REVIEW_ONLY_2026-10-01/mi5max_v8_rc02_child_cap_sport35_REVIEW_ONLY_NOT_HARDWARE_TESTED.bin',
             'f1037de2f08b647c31ab3b6f853665a84357480f1607d2f9d3cec8bf693abe1a'),
}
_cache = {}

def image(name):
    if name not in _cache:
        rel, sha = IMAGES[name]
        b = (ROOT / rel).read_bytes()
        if hashlib.sha256(b).hexdigest() != sha or len(b) != 147456:
            raise SystemExit(f'HASH MISMATCH for {name}: refusing to continue')
        _cache[name] = b
    return _cache[name]

def rt(file_off):
    return file_off - DELTA

def scatter_ram(img):
    """Run the image's own reset-time scatter/zero-init by executing the C runtime
    init would need the full boot; instead the project already saved default/farm
    initial RAM.  We use the image's scatter table through the earlier saved
    snapshots only when asked (see load_initial_ram)."""
    raise NotImplementedError

class M0:
    def __init__(self, name='farm', ram=None, sp=0x20001050):
        img = image(name)
        self.name = name
        self.img = img
        u = self.u = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        u.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_M0)
        u.mem_map(0, 0x20000)
        u.mem_write(0x2800, img[0x19818:])
        u.mem_map(BASE, 0x3000)
        u.mem_map(0x40000000, 0x21000)
        if ram is not None:
            u.mem_write(BASE, ram)
        self.sp0 = sp
        self.min_sp = sp
        self.trace = None
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

    def enable_trace(self):
        self.trace = []
        def code(uc, addr, size, _):
            self.trace.append(addr)
            sp = uc.reg_read(A.UC_ARM_REG_SP)
            if sp < self.min_sp:
                self.min_sp = sp
        self.u.hook_add(UC_HOOK_CODE, code)

    def put(self, a, v, f='H'):
        self.u.mem_write(BASE + a, struct.pack('<' + f, v))

    def get(self, a, f='H'):
        return struct.unpack('<' + f, self.u.mem_read(BASE + a, struct.calcsize(f)))[0]

    def ram(self, n=0x1050):
        return bytes(self.u.mem_read(BASE, n))

    def call(self, file_off, r0=None, r1=None, count=400000):
        if r0 is not None: self.u.reg_write(A.UC_ARM_REG_R0, r0 & 0xFFFFFFFF)
        if r1 is not None: self.u.reg_write(A.UC_ARM_REG_R1, r1 & 0xFFFFFFFF)
        self.u.reg_write(A.UC_ARM_REG_SP, self.sp0)
        self.u.reg_write(A.UC_ARM_REG_LR, STOP | 1)
        self.u.emu_start(rt(file_off) | 1, STOP, count=count)
        pc = self.u.reg_read(A.UC_ARM_REG_PC)
        if pc != STOP:
            raise RuntimeError(f'call {file_off:#x} did not return (pc={pc:#x})')
        return self.u.reg_read(A.UC_ARM_REG_R0)

def load_initial_ram(kind='farm'):
    p = ROOT / 'work' / ('farm_initial_ram.bin' if kind != 'stock' else 'default_initial_ram.bin')
    return p.read_bytes()
