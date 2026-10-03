"""S04: emulate only the C-runtime RAM initialisation (__scatterload) of the
motor controller and dump the initial RAM image (initial values of all
variables). Compares with work/default_initial_ram.bin from the package.

Output: evidence/s04_mc_initram_<image>.bin and a printed comparison.
"""
import hashlib
import os
import sys

from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_MCLASS, UC_MODE_THUMB, Uc
from unicorn.arm_const import (UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP)

sys.path.insert(0, os.path.dirname(__file__))
import fwlib  # noqa: E402

EV = os.path.join(os.path.dirname(__file__), "..", "evidence")
GEN = os.path.join(EV, "generated")
RAM0, RAMSZ = 0x20000000, 0x1050


def init_ram(img):
    d = fwlib.load(img)
    p = fwlib.Prog(d, "mc")
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    uc.mem_map(0, 0x20000)
    uc.mem_write(p.rt0, d[p.f0:p.f1])
    uc.mem_map(RAM0, 0x2000)
    # fill RAM with a marker so we can tell untouched bytes
    uc.mem_write(RAM0, b"\xA5" * 0x2000)
    uc.reg_write(UC_ARM_REG_SP, 0x20001050)
    stop = 0x292C  # __rt_entry: scatter-load finished
    uc.reg_write(UC_ARM_REG_LR, stop | 1)
    hits = {"n": 0}

    def hook(u, addr, size, user):
        hits["n"] += 1
        if addr == stop:
            u.emu_stop()

    uc.hook_add(UC_HOOK_CODE, hook)
    uc.emu_start(0x28C8 | 1, 0xFFFFFFF0, count=5_000_000)
    ram = bytes(uc.mem_read(RAM0, RAMSZ))
    return ram, hits["n"]


def main():
    os.makedirs(GEN, exist_ok=True)
    for img in ("stock", "rc02"):
        ram, n = init_ram(img)
        out = os.path.join(GEN, f"s04_mc_initram_{img}.bin")
        open(out, "wb").write(ram)
        untouched = sum(1 for b in ram if b == 0xA5)
        print(f"{img}: {n} instructions emulated, sha256={hashlib.sha256(ram).hexdigest()[:16]}, "
              f"bytes still 0xA5 (untouched or real 0xA5): {untouched}")
    ref = os.path.join(fwlib.ROOT, "work", "default_initial_ram.bin")
    if os.path.exists(ref):
        r = open(ref, "rb").read()
        s = open(os.path.join(GEN, "s04_mc_initram_stock.bin"), "rb").read()
        diffs = [i for i in range(min(len(r), len(s))) if r[i] != s[i]]
        print(f"package default_initial_ram.bin: len={len(r)}, differs from my emulation at {len(diffs)} bytes",
              ("first: " + ", ".join(hex(0x20000000 + i) for i in diffs[:12])) if diffs else "")


if __name__ == "__main__":
    main()
