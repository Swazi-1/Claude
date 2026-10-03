"""S03: annotated full disassembly + RAM cross-reference for a program.

usage: python3 s03_disasm_dump.py <image> <mc|a>
Output: evidence/asm_<image>_<prog>.txt, evidence/xref_<image>_<prog>.json
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
import fwlib  # noqa: E402
import s02_survey  # noqa: E402

EV = os.path.join(os.path.dirname(__file__), "..", "evidence")
GEN = os.path.join(EV, "generated")


def ascii_of(b):
    return "".join(chr(c) if 32 <= c < 127 else "." for c in b)


def main(img, which):
    os.makedirs(GEN, exist_ok=True)
    d = fwlib.load(img)
    p = fwlib.Prog(d, which)
    nvec = 48 if which == "mc" else 84
    vec = p.vectors(nvec)
    entries = set(v & ~1 for v in vec[1:] if v and p.in_code(v & ~1))
    ptrs = s02_survey.code_pointers(p) | s02_survey.reset_targets(p, vec[1] & ~1)
    funcs = fwlib.discover_functions(p, list(entries | ptrs))
    covered = set()
    for f in funcs.values():
        covered.update(f["insns"].keys())
    extra = [a for a in s02_survey.prologue_scan(p) if a not in covered]
    funcs = fwlib.discover_functions(p, list(funcs.keys()) + extra)
    callers = defaultdict(set)
    for fa, f in funcs.items():
        for c in f["calls"]:
            callers[c].add(fa)
    insn_owner = {}
    for fa, f in funcs.items():
        for a, ins in f["insns"].items():
            insn_owner[a] = fa
    xref = defaultdict(lambda: {"ld": set(), "st": set(), "lit": set()})
    lit_addrs = set()
    for fa, f in funcs.items():
        for a, ins in f["insns"].items():
            lv = p.lit(ins)
            if lv is not None:
                lit_addrs.add(lv[0])
        for (ia, kind, size, ea) in fwlib.mem_accesses(p, f["insns"]):
            if 0x20000000 <= ea < 0x20010000 or 0x40000000 <= ea < 0x50000000:
                xref[ea][kind].add(hex(fa))
    lines = []
    a = p.rt0
    while a < p.rt1:
        if a in funcs:
            f = funcs[a]
            lines.append("")
            lines.append(f"; ===== FUNCTION {a:#x}  end~{f['end']:#x}  callers: "
                         + ", ".join(hex(c) for c in sorted(callers.get(a, ()))) )
            if f["calls"]:
                lines.append("; calls: " + ", ".join(hex(c) for c in sorted(f["calls"])))
        if a in insn_owner:
            ins = funcs[insn_owner[a]]["insns"][a]
            s = fwlib.fmt(ins)
            lv = p.lit(ins)
            if lv is not None:
                v = lv[1]
                s += f"   ; ={v:#x}"
                if p.in_code(v & ~1) and (v & ~1) in funcs:
                    s += " (func)"
            t = fwlib.branch_target(ins)
            if t is not None and t in funcs and ins.mnemonic.startswith("bl"):
                s += f"   ; -> {t:#x}"
            lines.append(s)
            a += ins.size
        else:
            if a % 4 == 0 and a + 4 <= p.rt1:
                w = p.r32(a)
                tag = " (lit)" if a in lit_addrs else ""
                lines.append(f"{a:#08x}: .word    {w:#010x}  ; {ascii_of(d[p.fo(a):p.fo(a)+4])}{tag}")
                a += 4
            else:
                lines.append(f"{a:#08x}: .hword   {p.r16(a):#06x}")
                a += 2
    out = os.path.join(GEN, f"asm_{img}_{which}.txt")
    open(out, "w").write("\n".join(lines) + "\n")
    xj = {hex(k): {kk: sorted(vv) for kk, vv in v.items()} for k, v in sorted(xref.items())}
    json.dump(xj, open(os.path.join(GEN, f"xref_{img}_{which}.json"), "w"), indent=0)
    print(out, len(lines), "lines;", len(funcs), "functions;", len(xj), "addresses cross-referenced")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
