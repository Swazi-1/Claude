"""S05: is the power-button / power-hold / wake / sleep / power-off / dashboard
handshake path byte-identical between stock and RC02?  And can any RC02
change reach it through shared RAM?

Method (each step can fail):
 1. Seed functions = every MC function that touches GPIO port 3 (P3.9 power
    hold lives there), the SYS/AON/power blocks, the PWRDN interrupt, the two
    UART interrupts, and the dashboard-frame handler 0x99fc.
 2. Close over callees.
 3. Compare the bytes of every function body + the literal-pool words it
    loads, stock vs RC02.
 4. Compare the whole battery-side program and the package header.
 5. Data flow: RAM addresses READ by the power path  vs  RAM addresses
    WRITTEN by (a) the new RC02 code, (b) functions containing a changed byte.

Output: evidence/s05_power_path.json and evidence/s05_power_path.md
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import fwlib  # noqa: E402
import s02_survey  # noqa: E402
from s01_layout_and_checksums import diff_regions  # noqa: E402

EV = os.path.join(os.path.dirname(__file__), "..", "evidence")


def funcs_of(img):
    d = fwlib.load(img)
    p = fwlib.Prog(d, "mc")
    vec = p.vectors(48)
    entries = set(v & ~1 for v in vec[1:] if v and p.in_code(v & ~1))
    ptrs = s02_survey.code_pointers(p) | s02_survey.reset_targets(p, vec[1] & ~1)
    f = fwlib.discover_functions(p, list(entries | ptrs))
    cov = set()
    for x in f.values():
        cov.update(x["insns"].keys())
    extra = [a for a in s02_survey.prologue_scan(p) if a not in cov]
    f = fwlib.discover_functions(p, list(f.keys()) + extra)
    return d, p, f


def touched(p, f):
    acc = fwlib.mem_accesses(p, f["insns"])
    return acc


def main():
    S, ps, fs = funcs_of("stock")
    R, pr, fr = funcs_of("rc02")
    seeds = set()
    why = {}
    for fa, f in fs.items():
        for (ia, kind, size, ea) in touched(ps, f):
            tag = None
            if 0x40010DC0 <= ea < 0x40010E00:
                tag = "GPIO3 (P3.x incl. P3.9 power hold)"
            elif 0x40000000 <= ea < 0x40000100:
                tag = "SYS block (clock/power/reset control)"
            elif 0x40011700 <= ea < 0x40011800:
                tag = "AON block (IWDG/PMU: watchdog, sleep/wake)"
            if tag:
                seeds.add(fa)
                why.setdefault(hex(fa), set()).add(tag)
    vec = ps.vectors(48)
    named = {vec[39] & ~1: "PWRDN interrupt (supply-low)",
             vec[26] & ~1: "UART0 interrupt", vec[27] & ~1: "UART1 interrupt",
             0x99FC: "dashboard frame handler (0x51/0x52/0x53 frames, stay-on bit -> P3.9)",
             0x96CC: "idle auto-off timer (clears P3.9)"}
    for a, t in named.items():
        seeds.add(a)
        why.setdefault(hex(a), set()).add(t)
    # closure over callees
    path = set()
    work = list(seeds)
    while work:
        a = work.pop()
        if a in path or a not in fs:
            continue
        path.add(a)
        work.extend(c for c in fs[a]["calls"] if c in fs)
    rows = []
    all_same = True
    for a in sorted(path):
        f = fs[a]
        rng = []
        for ia, ins in f["insns"].items():
            rng.append((ia, ia + ins.size))
            lv = ps.lit(ins)
            if lv is not None:
                rng.append((lv[0], lv[0] + 4))
        diff = [x for (s, e) in rng for x in range(s, e) if S[ps.fo(x)] != R[pr.fo(x)]]
        nbytes = sum(e - s for s, e in rng)
        same = not diff
        all_same &= same
        rows.append({"func": hex(a), "end": hex(f["end"]), "bytes_compared": nbytes,
                     "identical": same, "first_diff": hex(diff[0]) if diff else None,
                     "role": sorted(why.get(hex(a), {"callee of power path"}))})
    # data flow
    reads = {}
    for a in path:
        for (ia, kind, size, ea) in touched(ps, fs[a]):
            if kind == "ld" and 0x20000000 <= ea < 0x20002000:
                for k in range(size):
                    reads.setdefault(ea + k, set()).add(hex(a))
    regs = [(a - fwlib.MC_DELTA, b - fwlib.MC_DELTA) for a, b in diff_regions(S, R) if a >= fwlib.MC_FILE_START]
    changed_funcs = set()
    for s, e in regs:
        for fa, f in fr.items():
            if any(s <= ia < e or ia <= s < ia + ins.size for ia, ins in f["insns"].items()):
                changed_funcs.add(fa)
    new_funcs = {fa for fa in fr if fa >= ps.rt1}
    # functions in RC02 reachable from new code (they run under new conditions)
    writes = {}
    for fa in changed_funcs | new_funcs:
        for (ia, kind, size, ea) in touched(pr, fr[fa]):
            if kind == "st" and 0x20000000 <= ea < 0x20002000:
                for k in range(size):
                    writes.setdefault(ea + k, set()).add(hex(fa))
    overlap = {hex(k): {"read_by_power_path": sorted(reads[k]), "written_by_changed_or_new": sorted(writes[k])}
               for k in sorted(set(reads) & set(writes))}
    new_calls = sorted({hex(c) for fa in new_funcs for c in fr[fa]["calls"]})
    res = {
        "power_path_functions": rows,
        "all_power_path_functions_identical": all_same,
        "battery_side_program_identical": S[0x1000:0x19800] == R[0x1000:0x19800],
        "changed_regions_rt": [[hex(s), hex(e)] for s, e in regs],
        "rc02_functions_containing_changes": sorted(hex(x) for x in changed_funcs),
        "rc02_new_functions": sorted(hex(x) for x in new_funcs),
        "functions_called_by_new_code": new_calls,
        "ram_read_by_power_path_and_written_by_changed_code": overlap,
    }
    json.dump(res, open(os.path.join(EV, "s05_power_path.json"), "w"), indent=1)
    print("power-path functions:", len(rows), "all identical:", all_same,
          "| battery-side identical:", res["battery_side_program_identical"])
    for r in rows:
        print(f"  {r['func']:>7} identical={r['identical']} bytes={r['bytes_compared']:4d} {', '.join(r['role'])}")
    print("changed functions:", res["rc02_functions_containing_changes"])
    print("new functions:", res["rc02_new_functions"], "call:", new_calls)
    print("RAM overlap (power path reads  x  changed/new code writes):")
    for k, v in overlap.items():
        print("  ", k, v)


if __name__ == "__main__":
    main()
