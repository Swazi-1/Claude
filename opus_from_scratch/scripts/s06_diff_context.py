"""S06: side-by-side disassembly of every region that differs between two
images (default stock vs RC02), with owning function and context.

usage: python3 s06_diff_context.py [a] [b]
Output: evidence/s06_diff_<a>_vs_<b>.md
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import fwlib  # noqa: E402
from s01_layout_and_checksums import diff_regions  # noqa: E402

EV = os.path.join(os.path.dirname(__file__), "..", "evidence")
GEN = os.path.join(EV, "generated")


def ctx(p, s, e, before=10, after=10):
    # walk back from s along instruction boundaries using a coarse resync
    start = max(p.rt0, s - 2 * before - 8)
    a = start
    seq = []
    while a < e + 2 * after:
        i = p.insn_at(a)
        if i is None:
            seq.append((a, f".hword {p.r16(a):#06x}", 2))
            a += 2
        else:
            t = f"{i.mnemonic} {i.op_str}"
            lv = p.lit(i)
            if lv is not None:
                t += f"  ; ={lv[1]:#x}"
            seq.append((a, t, i.size))
            a += i.size
    return seq


def main(x="stock", y="rc02"):
    os.makedirs(GEN, exist_ok=True)
    A, B = fwlib.load(x), fwlib.load(y)
    pa, pb = fwlib.Prog(A, "mc"), fwlib.Prog(B, "mc")
    out = [f"# Byte differences {x} vs {y} (motor-controller runtime addresses)", "",
           "runtime = file - 0x17018. Regions merged when <=4 bytes apart.", ""]
    for fs, fe in diff_regions(A, B):
        if fs < fwlib.MC_FILE_START:
            out.append(f"## file {fs:#07x}-{fe:#07x} (header) old `{A[fs:fe].hex()}` new `{B[fs:fe].hex()}`")
            out.append("")
            continue
        s, e = fs - fwlib.MC_DELTA, fe - fwlib.MC_DELTA
        out.append(f"## rt {s:#06x}-{e:#06x} (file {fs:#07x}), {fe-fs} bytes")
        out.append(f"old `{A[fs:fe].hex()}`  new `{B[fs:fe].hex()}`")
        if fe - fs > 64 and set(A[fs:fe]) == {0xFF}:
            out.append("(new code/data in previously empty flash; see asm_rc02_mc.txt)")
            out.append("")
            continue
        out.append("```")
        sa, sb = ctx(pa, s, e), ctx(pb, s, e)
        n = max(len(sa), len(sb))
        for k in range(n):
            l = f"{sa[k][0]:#06x} {sa[k][1]:<40}" if k < len(sa) else " " * 47
            r = f"{sb[k][0]:#06x} {sb[k][1]}" if k < len(sb) else ""
            mark = "*" if (k < len(sa) and k < len(sb) and (sa[k][1] != sb[k][1] or sa[k][0] != sb[k][0])) else " "
            out.append(f"{mark} {l} | {r}")
        out.append("```")
        out.append("")
    path = os.path.join(GEN, f"s06_diff_{x}_vs_{y}.md")
    open(path, "w").write("\n".join(out) + "\n")
    print(path, len(out), "lines")


if __name__ == "__main__":
    main(*(sys.argv[1:3] if len(sys.argv) > 2 else ()))
