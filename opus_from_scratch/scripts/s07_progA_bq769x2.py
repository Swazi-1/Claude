"""S07: battery-side program (A): which BQ769x2 commands does it send?

Finds every call to the I2C helper functions and recovers constant
arguments (r0..r3 set by movs/mov.w/movw/ldr= shortly before the call).
Names subcommands / direct commands / data-memory addresses from the TI
BQ76952 TRM (SLUUBY2B) tables shipped in the package.

Output: evidence/s07_progA_bq769x2_calls.md
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
import fwlib  # noqa: E402
import s02_survey  # noqa: E402

EV = os.path.join(os.path.dirname(__file__), "..", "evidence")

SUBCMD = {0x0001: "DEVICE_NUMBER", 0x0002: "FW_VERSION", 0x0003: "HW_VERSION", 0x0004: "IROM_SIG",
          0x0005: "STATIC_CFG_SIG", 0x0009: "DROM_SIG", 0x000E: "EXIT_DEEPSLEEP", 0x000F: "DEEPSLEEP",
          0x0010: "SHUTDOWN", 0x0012: "RESET", 0x001C: "PDSGTEST", 0x001D: "FUSE_TOGGLE", 0x001E: "PCHGTEST",
          0x001F: "CHGTEST", 0x0020: "DSGTEST", 0x0022: "FET_ENABLE", 0x0024: "PF_ENABLE", 0x0030: "SEAL",
          0x0035: "SECURITY_KEYS", 0x0053: "SAVED_PF_STATUS", 0x0057: "MANUFACTURING_STATUS",
          0x0070: "MANU_DATA", 0x0071: "DASTATUS1", 0x0072: "DASTATUS2", 0x0073: "DASTATUS3",
          0x0074: "DASTATUS4", 0x0075: "DASTATUS5", 0x0076: "DASTATUS6", 0x0077: "DASTATUS7",
          0x0080: "CUV_SNAPSHOT", 0x0081: "COV_SNAPSHOT", 0x0082: "RESET_PASSQ", 0x0083: "CB_ACTIVE_CELLS",
          0x0084: "CB_SET_LVL", 0x0085: "CBSTATUS1", 0x0086: "CBSTATUS2", 0x0087: "CBSTATUS3",
          0x008A: "PTO_RECOVER", 0x0090: "SET_CFGUPDATE", 0x0092: "EXIT_CFGUPDATE", 0x0093: "DSG_PDSG_OFF",
          0x0094: "CHG_PCHG_OFF", 0x0095: "ALL_FETS_OFF", 0x0096: "ALL_FETS_ON", 0x0097: "FET_CONTROL",
          0x0098: "REG12_CONTROL", 0x0099: "SLEEP_ENABLE", 0x009A: "SLEEP_DISABLE", 0x009B: "OCDL_RECOVER",
          0x009C: "SCDL_RECOVER", 0x009D: "LOAD_DETECT_RESTART", 0x009E: "LOAD_DETECT_ON",
          0x009F: "LOAD_DETECT_OFF", 0x00A0: "OTP_WR_CHECK", 0x00A1: "OTP_WRITE", 0x0F00: "READ_CAL1",
          0x0F81: "CAL_CUV", 0x0F82: "CAL_COV"}
DIRECT = {0x00: "Control Status", 0x02: "Safety Alert A", 0x03: "Safety Status A", 0x04: "Safety Alert B",
          0x05: "Safety Status B", 0x06: "Safety Alert C", 0x07: "Safety Status C", 0x0A: "PF Alert A",
          0x0B: "PF Status A", 0x0C: "PF Alert B", 0x0D: "PF Status B", 0x0E: "PF Alert C",
          0x0F: "PF Status C", 0x10: "PF Alert D", 0x11: "PF Status D", 0x12: "Battery Status",
          0x34: "Stack Voltage", 0x36: "PACK Pin Voltage", 0x38: "LD Pin Voltage", 0x3A: "CC2 Current",
          0x3E: "Subcommand (low)", 0x40: "Subcommand data buffer", 0x60: "Subcommand checksum",
          0x62: "Alarm Status", 0x64: "Alarm Raw Status", 0x66: "Alarm Enable", 0x68: "Int Temperature",
          0x6A: "CFETOFF Temperature", 0x6C: "DFETOFF Temperature", 0x6E: "ALERT Temperature",
          0x70: "TS1 Temperature", 0x72: "TS2 Temperature", 0x74: "TS3 Temperature", 0x76: "HDQ Temperature",
          0x78: "DCHG Temperature", 0x7A: "DDSG Temperature", 0x7F: "FET Status"}
for k in range(16):
    DIRECT[0x14 + 2 * k] = f"Cell {k + 1} Voltage"


def const_args(p, func_insns, call_addr):
    regs = {}
    for a in sorted(x for x in func_insns if x < call_addr)[-10:]:
        ins = func_insns[a]
        ops = ins.operands
        if not ops or ops[0].type != fwlib.ARM_OP_REG:
            continue
        r = ins.reg_name(ops[0].reg)
        if r not in ("r0", "r1", "r2", "r3"):
            continue
        lv = p.lit(ins)
        if lv is not None:
            regs[r] = lv[1]
        elif ins.mnemonic in ("movs", "mov.w", "movw", "mov") and len(ops) == 2 and ops[1].type == fwlib.ARM_OP_IMM:
            regs[r] = ops[1].imm & 0xFFFFFFFF
        else:
            regs.pop(r, None)
    return regs


def main():
    d = fwlib.load("stock")
    p = fwlib.Prog(d, "a")
    vec = p.vectors(84)
    entries = set(v & ~1 for v in vec[1:] if v and p.in_code(v & ~1))
    ptrs = s02_survey.code_pointers(p) | s02_survey.reset_targets(p, vec[1] & ~1)
    funcs = fwlib.discover_functions(p, list(entries | ptrs))
    cov = set()
    for f in funcs.values():
        cov.update(f["insns"].keys())
    extra = [a for a in s02_survey.prologue_scan(p) if a not in cov]
    funcs = fwlib.discover_functions(p, list(funcs.keys()) + extra)
    # helpers identified by hand from the listing (see report):
    helpers = {
        0x08003BDC: ("subcmd(cmd)", "r0"),            # writes [cmd lo, cmd hi] to reg 0x3E, dev 0x08
        0x08003C1C: ("subcmd_i2c2(cmd)", "r0"),       # same via hardware I2C2 at 0x40005800
        0x08003C7A: ("subcmd_read(dev,cmd,buf,len)", "r1"),
        0x08003C60: ("read_reg(dev,reg,buf,len)", "r1"),
    }
    rows = defaultdict(list)
    for fa, f in funcs.items():
        for a, ins in f["insns"].items():
            if ins.mnemonic.startswith("bl") and fwlib.branch_target(ins) in helpers:
                t = fwlib.branch_target(ins)
                args = const_args(p, f["insns"], a)
                rows[t].append((fa, a, args))
    out = ["# Program A: calls into BQ769x2-style I2C helpers (stock image; identical in RC02)", "",
           "Constant arguments recovered from the instructions just before each call; '?' = computed at runtime.", ""]
    seen_names = set()
    for t, (name, argreg) in helpers.items():
        out.append(f"## {name} at {t:#x}: {len(rows[t])} call sites")
        out.append("")
        out.append("| caller function | call at | arg | meaning (TI TRM) |")
        out.append("|---|---|---|---|")
        for fa, a, args in sorted(rows[t]):
            v = args.get(argreg)
            if v is None:
                meaning = "?"
                vs = "?"
            else:
                vs = f"{v:#06x}"
                if "subcmd" in name:
                    meaning = SUBCMD.get(v, ("data memory " if 0x9000 <= v < 0x9400 else "unknown"))
                else:
                    meaning = DIRECT.get(v, "unknown")
                seen_names.add(meaning)
            out.append(f"| {fa:#x} | {a:#x} | {vs} | {meaning} |")
        out.append("")
    open(os.path.join(EV, "s07_progA_bq769x2_calls.md"), "w").write("\n".join(out) + "\n")
    for t, (name, _) in helpers.items():
        vals = sorted({(args.get(helpers[t][1])) for _, _, args in rows[t]}, key=lambda x: -1 if x is None else x)
        print(name, len(rows[t]), "calls; args:", [hex(v) if v is not None else "?" for v in vals])


if __name__ == "__main__":
    main()
