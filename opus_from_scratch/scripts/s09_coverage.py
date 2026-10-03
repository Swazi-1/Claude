"""S09: coverage per file region.

'mapped'     = bytes that lie in instructions reached by function discovery.
'understood' = bytes inside functions I read and explained in the report
               (list below; weight 1.0 = fully read, 0.5 = partly read).
The 'understood' list is a human judgement, so treat that column as an
honest estimate, not a measurement.

Output: evidence/s09_coverage.md
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import fwlib  # noqa: E402
import s02_survey  # noqa: E402

EV = os.path.join(os.path.dirname(__file__), "..", "evidence")

MC_READ = {  # motor controller (runtime addresses), weight
    0x2984: 1, 0x28C0: 1, 0xB914: 1, 0x5AFC: 0.5, 0x9470: 1, 0x9724: 0.5, 0x99FC: 0.8, 0x96CC: 1,
    0x98C8: 1, 0x6084: 1, 0x7D00: 1, 0x663C: 0.8, 0x6DB4: 0.4, 0x73B8: 0.6, 0x8BF4: 1, 0xBF20: 1,
    0x4DB8: 1, 0x6C98: 1, 0x5144: 1, 0x70F0: 1, 0x9354: 1, 0x834C: 1, 0x7B1C: 0.7, 0x7C3C: 1,
    0x84C0: 1, 0x8FC4: 1, 0x65A0: 1, 0x642C: 1, 0x6450: 1, 0x64A8: 1, 0x5810: 1, 0xA6FC: 1,
    0x4024: 0.4, 0x6634: 1, 0x4D04: 0.3, 0x64F4: 0.7, 0x4E8C: 0.3, 0x5524: 0.5, 0x5694: 0.2,
}
A_READ = {  # battery-side program (runtime addresses), weight
    0x0801907A: 1, 0x08006CBC: 1, 0x08006C84: 1, 0x08003DF4: 1, 0x0800BA44: 1, 0x080149B4: 1,
    0x08014470: 1, 0x08013DE8: 0.3, 0x080130FC: 1, 0x08007B5A: 1, 0x08007B98: 1, 0x08007BC4: 1,
    0x08007C9C: 1, 0x08007CC0: 1, 0x08007CD0: 1, 0x08007DBC: 1, 0x0800E20C: 1, 0x0800E2A8: 1,
    0x08007908: 1, 0x08007874: 1, 0x08007888: 1, 0x080078F6: 1, 0x0800797C: 1, 0x080079A4: 0.5,
    0x0800532C: 0.5, 0x08003BDC: 1, 0x08003C1C: 1, 0x08003C60: 1, 0x08003C7A: 1, 0x0800B134: 0.7,
    0x080076BC: 1, 0x0800BB5C: 0.5, 0x0800BC18: 0.5, 0x0800E9FC: 1, 0x0800ABEC: 0.3,
}
# the 22 one-call register-read wrappers 0x80040c4..0x8004358 (pattern-identified)
for a in (0x080040C4, 0x08004138, 0x080041DC) + tuple(range(0x080041F0, 0x0800436C, 0x14)):
    A_READ.setdefault(a, 1)


def funcs(d, which, nvec):
    p = fwlib.Prog(d, which)
    vec = p.vectors(nvec)
    entries = set(v & ~1 for v in vec[1:] if v and p.in_code(v & ~1))
    ptrs = s02_survey.code_pointers(p) | s02_survey.reset_targets(p, vec[1] & ~1)
    f = fwlib.discover_functions(p, list(entries | ptrs))
    cov = set()
    for x in f.values():
        cov.update(x["insns"].keys())
    extra = [a for a in s02_survey.prologue_scan(p) if a not in cov]
    return p, fwlib.discover_functions(p, list(f.keys()) + extra)


def bytes_of(f):
    s = set()
    for a, i in f["insns"].items():
        s.update(range(a, a + i.size))
    return s


def main():
    d = fwlib.load("stock")
    rows = []
    for which, nvec, read in (("a", 84, A_READ), ("mc", 48, MC_READ)):
        p, F = funcs(d, which, nvec)
        mapped = set()
        for f in F.values():
            mapped |= bytes_of(f)
        under = 0.0
        missing = []
        for a, w in read.items():
            if a in F:
                under += w * len(bytes_of(F[a]))
            else:
                missing.append(hex(a))
        total = p.rt1 - p.rt0
        rows.append((which, total, len(mapped), under, len(F), missing))
    out = ["# Coverage table (stock image; RC02 is identical outside the motor-controller changes)", "",
           "| file region | what it is | size (bytes) | mapped | understood (estimate) |",
           "|---|---|---|---|---|",
           "| 0x00000-0x0002D | package header (size, CRC-16, version '0108', model id '001600010001') | 46 | 100 % | 100 % (every field checked; CRC verified) |",
           "| 0x0002E-0x007FF | padding 0xFF | 2002 | 100 % | 100 % |",
           "| 0x00800-0x0080C | tag 'DEPRD5C' + 5 bytes | 13 | 100 % | tag: likely a battery-pack vendor/product code; 5 bytes unknown |",
           "| 0x0080D-0x00FFF | padding 0xFF | 2035 | 100 % | 100 % |"]
    for which, total, m, u, nf, missing in rows:
        if which == "a":
            out.append(f"| 0x01000-0x19223 | battery-side program (N32L40x-class Cortex-M4, runtime +0x08002000), {nf} functions | {total} | {100*m/total:.1f} % | {100*u/total:.1f} % |")
            out.append("| 0x19224-0x197FF | padding 0xFF | 1500 | 100 % | 100 % |")
        else:
            out.append("| 0x19800-0x19817 | motor-controller header (size, CRC-32, 'LKS32MC071CBT8FFP') | 24 | 100 % | 100 % (CRC verified) |")
            out.append(f"| 0x19818-0x2381B | motor-controller program (LKS32MC071, Cortex-M0, runtime -0x17018), {nf} functions | {total} | {100*m/total:.1f} % | {100*u/total:.1f} % |")
            out.append("| 0x2381C-0x23FFF | padding 0xFF (RC02 uses 0x2381C-0x23C1B for added code) | 2020 | 100 % | 100 % |")
    out.append("")
    out.append("'mapped' counts only bytes inside instructions reached by discovery; literal pools and tables count as unmapped, so 100 % is not reachable.")
    for which, total, m, u, nf, missing in rows:
        if missing:
            out.append(f"Functions listed as read but not found by discovery ({which}): {', '.join(missing)}")
    open(os.path.join(EV, "s09_coverage.md"), "w").write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
