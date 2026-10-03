"""Shared helpers for the Mi 5 Max firmware study (read-only).

Nothing here writes firmware or talks to a device. Every image is checked
against its SHA-256 before use.

Set MI5MAX_ROOT to the unpacked package folder (the one containing
START_HERE.md). Python 3.11+, capstone 5.0.x.
"""
import hashlib
import os
import struct
from collections import defaultdict

from capstone import (CS_ARCH_ARM, CS_MODE_MCLASS, CS_MODE_THUMB, Cs)
from capstone.arm import (ARM_OP_IMM, ARM_OP_MEM, ARM_OP_REG, ARM_REG_PC,
                          ARM_REG_SP)

ROOT = os.environ.get("MI5MAX_ROOT", "")

IMAGES = {
    "stock": ("inputs/firmware/370dbaba96a88d7f4dd7bc8d7aafd78b_mcu_xiaomi.scooter.5max.bin",
              "015718dd81261662c322a4ea183f98486ab4062bfb367ce0c7208fa1ba153aeb"),
    "v71": ("inputs/firmware/mi5max_farm_v7_1_regenfix.bin",
            "b4c64d8464dbee8b4d238b02758ff36cf57acf94b0492fc3693cb68dedd56a4a"),
    "rc01": ("outputs/v8_child_cap_candidate_2026-09-30/mi5max_v8_rc01_child_ceiling_UNVERIFIED.bin",
             "1c58131d6be735481ad4f1cb07c4ade276908fc52c689a370fc032a3329f8c8e"),
    "rc02": ("outputs/v8_rc02_sport35_REVIEW_ONLY_2026-10-01/mi5max_v8_rc02_child_cap_sport35_REVIEW_ONLY_NOT_HARDWARE_TESTED.bin",
             "f1037de2f08b647c31ab3b6f853665a84357480f1607d2f9d3cec8bf693abe1a"),
}

# ---- layout (confirmed from bytes, see scripts/s01_layout_and_checksums.py)
FILE_SIZE = 0x24000
A_FILE_START, A_FILE_END = 0x1000, 0x19224      # battery-side program (Cortex-M3/M4 class)
A_DELTA = 0x08002000                             # runtime = file + A_DELTA
MC_HDR = 0x19800                                 # size, CRC32, "LKS32MC071CBT8FFP"
MC_FILE_START = 0x19818                          # vector table of motor controller
MC_DELTA = 0x17018                               # runtime = file - MC_DELTA


def load(name):
    rel, want = IMAGES[name]
    if not ROOT:
        raise SystemExit("Set MI5MAX_ROOT to the unpacked package folder")
    path = os.path.join(ROOT, rel)
    data = open(path, "rb").read()
    got = hashlib.sha256(data).hexdigest()
    if got != want:
        raise SystemExit(f"SHA-256 mismatch for {name}: {got}")
    return data


def u8(d, o):
    return d[o]


def u16(d, o):
    return struct.unpack_from("<H", d, o)[0]


def s16(d, o):
    return struct.unpack_from("<h", d, o)[0]


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


class Prog:
    """One program inside the image (MC or A) with address mapping."""

    def __init__(self, data, which):
        self.data = data
        self.which = which
        if which == "mc":
            size = u32(data, MC_HDR)
            self.f0 = MC_FILE_START
            self.f1 = MC_FILE_START + size
            self.rt0 = MC_FILE_START - MC_DELTA
            self.delta = -MC_DELTA
        elif which == "a":
            self.f0, self.f1 = A_FILE_START, A_FILE_END
            self.rt0 = A_FILE_START + A_DELTA
            self.delta = A_DELTA
        else:
            raise ValueError(which)
        self.rt1 = self.f1 + self.delta
        self.md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
        self.md.detail = True
        self._cache = {}

    # address helpers
    def fo(self, rt):
        return rt - self.delta

    def rt(self, fo):
        return fo + self.delta

    def in_code(self, rt):
        return self.rt0 <= rt < self.rt1

    def r8(self, rt):
        return self.data[self.fo(rt)]

    def r16(self, rt):
        return u16(self.data, self.fo(rt))

    def rs16(self, rt):
        return s16(self.data, self.fo(rt))

    def r32(self, rt):
        return u32(self.data, self.fo(rt))

    def insn_at(self, rt):
        if rt in self._cache:
            return self._cache[rt]
        fo = self.fo(rt)
        ins = next(self.md.disasm(self.data[fo:fo + 4], rt), None)
        self._cache[rt] = ins
        return ins

    def disasm(self, start, end):
        out = []
        a = start
        while a < end:
            i = self.insn_at(a)
            if i is None:
                out.append((a, None))
                a += 2
                continue
            out.append((a, i))
            a += i.size
        return out

    def vectors(self, count):
        return [self.r32(self.rt0 + 4 * k) for k in range(count)]

    # literal pool value for "ldr rX, [pc, #imm]"
    def lit(self, ins):
        if ins is None or ins.id == 0:
            return None
        if not ins.mnemonic.startswith("ldr"):
            return None
        ops = ins.operands
        if len(ops) != 2 or ops[1].type != ARM_OP_MEM or ops[1].mem.base != ARM_REG_PC:
            return None
        addr = ((ins.address + 4) & ~3) + ops[1].mem.disp
        if not self.in_code(addr):
            return None
        size = {"ldr": 4, "ldr.w": 4, "ldrh": 2, "ldrb": 1}.get(ins.mnemonic, 4)
        if size == 4:
            return addr, self.r32(addr)
        if size == 2:
            return addr, self.r16(addr)
        return addr, self.r8(addr)


# ---------------------------------------------------------------- functions
TERMINATORS = ("pop", "bx")


def _is_ret(ins):
    m = ins.mnemonic
    if m.startswith("pop") and "pc" in ins.op_str:
        return True
    if m == "bx" and ins.op_str == "lr":
        return True
    if m.startswith("ldm") and "pc" in ins.op_str:
        return True
    if m.startswith("ldr") and ins.op_str.startswith("pc,"):
        return True
    return False


def branch_target(ins):
    if ins.mnemonic.split(".")[0] in ("b", "bl", "beq", "bne", "bcs", "bhs", "bcc", "blo", "bmi",
                                       "bpl", "bvs", "bvc", "bhi", "bls", "bge", "blt", "bgt",
                                       "ble", "cbz", "cbnz"):
        for op in ins.operands:
            if op.type == ARM_OP_IMM:
                return op.imm
    return None


_SW8 = {}


def is_switch8(p, tgt):
    """armcc switch helper: push {r4,r5}; mov r4,lr; subs r4,#1; ldrb r5,[r4]."""
    if tgt not in _SW8:
        try:
            ok = p.in_code(tgt) and p.r16(tgt) == 0xB430 and p.r16(tgt + 2) == 0x4674 \
                and p.r16(tgt + 4) == 0x1E64 and p.r16(tgt + 6) == 0x7825
        except Exception:
            ok = False
        _SW8[tgt] = ok
    return _SW8[tgt]


def explore_function(p, entry, limit=0x4000):
    """Recursive descent inside one function. Returns (insns dict, calls set, end)."""
    seen = {}
    calls = set()
    work = [entry]
    while work:
        a = work.pop()
        litreg = {}
        while p.in_code(a) and a not in seen:
            ins = p.insn_at(a)
            if ins is None:
                break
            seen[a] = ins
            m = ins.mnemonic.split(".")[0]
            tgt = branch_target(ins)
            lv = p.lit(ins)
            if lv is not None and ins.operands and ins.operands[0].type == ARM_OP_REG:
                litreg[ins.operands[0].reg] = lv[1]
            if m in ("blx", "bx") and ins.operands and ins.operands[0].type == ARM_OP_REG:
                v = litreg.get(ins.operands[0].reg)
                if v is not None and v & 1 and p.in_code(v & ~1):
                    calls.add(v & ~1)
            if m == "bl":
                if tgt is not None:
                    calls.add(tgt)
                    if is_switch8(p, tgt):
                        # armcc __ARM_common_switch8: table of byte offsets follows the bl
                        base = a + 4
                        n = p.r8(base)
                        for k in range(n + 1):
                            work.append(base + 2 * p.r8(base + 1 + k))
                        break
                a += ins.size
                continue
            if m == "blx":
                a += ins.size
                continue
            if _is_ret(ins):
                break
            if m == "bx":
                break
            if m in ("tbb", "tbh"):
                # table branch: decode table right after the insn
                base = a + 4
                n = 0
                entries = []
                while n < 64:
                    off = p.r8(base + n) if m == "tbb" else p.r16(base + 2 * n)
                    t = base + 2 * off
                    if not (entry <= t < entry + limit) or t < base:
                        break
                    entries.append(t)
                    n += 1
                work.extend(entries)
                break
            if tgt is not None:
                if m == "b":
                    a = tgt
                    continue
                work.append(tgt)
            # thumb-1 jump tables used by armcc: "add pc, rX" etc.
            if m == "add" and ins.op_str.startswith("pc,"):
                break
            if m == "mov" and ins.op_str.startswith("pc,"):
                break
            a += ins.size
            if len(seen) > limit:
                break
    end = max(seen) + seen[max(seen)].size if seen else entry
    return seen, calls, end


def discover_functions(p, entries):
    funcs = {}
    work = [e & ~1 for e in entries if p.in_code(e & ~1)]
    while work:
        e = work.pop()
        if e in funcs:
            continue
        insns, calls, end = explore_function(p, e)
        funcs[e] = {"insns": insns, "calls": calls, "end": end}
        for c in calls:
            if p.in_code(c) and c not in funcs:
                work.append(c)
    return funcs


# --------------------------------------------------------- memory accesses
LOADS = {"ldr": 4, "ldrh": 2, "ldrb": 1, "ldrsh": 2, "ldrsb": 1, "ldr.w": 4,
         "ldrh.w": 2, "ldrb.w": 1, "ldrsh.w": 2, "ldrsb.w": 1, "ldrd": 8}
STORES = {"str": 4, "strh": 2, "strb": 1, "str.w": 4, "strh.w": 2, "strb.w": 1, "strd": 8}


def mem_accesses(p, func_insns):
    """Very small constant-propagation pass over one function (linear order).

    Approximate: registers keep their value across labels. Good enough to index
    which RAM / peripheral addresses a function touches; key findings are
    checked by hand or by emulation.
    """
    regs = {}
    out = []
    for a in sorted(func_insns):
        ins = func_insns[a]
        m = ins.mnemonic
        ops = ins.operands
        lv = p.lit(ins)
        if lv is not None and ops and ops[0].type == ARM_OP_REG:
            regs[ops[0].reg] = lv[1]
            out.append((a, "lit", 4, lv[1]))
            continue
        base = m.split(".")[0]
        if (m in LOADS or m in STORES) and len(ops) >= 2 and ops[-1].type == ARM_OP_MEM:
            mem = ops[-1].mem
            if mem.base in regs and mem.index == 0:
                ea = (regs[mem.base] + mem.disp) & 0xFFFFFFFF
                kind = "ld" if m in LOADS else "st"
                out.append((a, kind, LOADS.get(m, STORES.get(m, 4)), ea))
            if m in LOADS and ops[0].type == ARM_OP_REG:
                regs.pop(ops[0].reg, None)
            continue
        if base in ("adds", "add", "subs", "sub") and len(ops) == 3 and ops[0].type == ARM_OP_REG \
                and ops[1].type == ARM_OP_REG and ops[2].type == ARM_OP_IMM and ops[1].reg in regs:
            v = regs[ops[1].reg] + (ops[2].imm if base.startswith("add") else -ops[2].imm)
            regs[ops[0].reg] = v & 0xFFFFFFFF
            continue
        if base in ("adds", "add", "subs", "sub") and len(ops) == 2 and ops[0].type == ARM_OP_REG \
                and ops[1].type == ARM_OP_IMM and ops[0].reg in regs:
            v = regs[ops[0].reg] + (ops[1].imm if base.startswith("add") else -ops[1].imm)
            regs[ops[0].reg] = v & 0xFFFFFFFF
            continue
        if base in ("movs", "mov") and len(ops) == 2 and ops[0].type == ARM_OP_REG:
            if ops[1].type == ARM_OP_REG and ops[1].reg in regs:
                regs[ops[0].reg] = regs[ops[1].reg]
            else:
                regs.pop(ops[0].reg, None)
            continue
        if base == "bl" or base == "blx":
            for r in list(regs):
                # r0-r3, r12 are caller-saved
                if ins.reg_name(r) in ("r0", "r1", "r2", "r3", "r12"):
                    regs.pop(r, None)
            continue
        # any other write to a register invalidates it
        try:
            _, wr = ins.regs_access()
            for r in wr:
                regs.pop(r, None)
        except Exception:
            if ops and ops[0].type == ARM_OP_REG:
                regs.pop(ops[0].reg, None)
    return out


def fmt(ins):
    return f"{ins.address:#08x}: {ins.mnemonic:8s} {ins.op_str}"


def listing(p, start, end, annotate=True):
    lines = []
    for a, ins in p.disasm(start, end):
        if ins is None:
            lines.append(f"{a:#08x}: .hword {p.r16(a):#06x}")
            continue
        s = fmt(ins)
        if annotate:
            lv = p.lit(ins)
            if lv is not None:
                s += f"   ; ={lv[1]:#x}"
        lines.append(s)
    return "\n".join(lines)
