"""S02: function discovery and hardware-register survey for both programs.

Output: evidence/s02_functions_<prog>.json, evidence/s02_peripherals_<prog>.txt
"""
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(__file__))
import fwlib  # noqa: E402

EV = os.path.join(os.path.dirname(__file__), "..", "evidence")
GEN = os.path.join(EV, "generated")


def code_pointers(p):
    """Words anywhere in the program that look like Thumb pointers to a push prologue."""
    ptrs = set()
    for fo in range(p.f0, p.f1 - 3, 4):
        w = fwlib.u32(p.data, fo)
        if w & 1 and p.in_code(w & ~1):
            ins = p.insn_at(w & ~1)
            if ins is not None and (ins.mnemonic.startswith("push") or ins.mnemonic.startswith("stmdb")):
                ptrs.add(w & ~1)
    return ptrs


def reset_targets(p, reset):
    """Code reached from the reset handler via 'ldr r0,=X; blx/bx r0' (SystemInit, __main)."""
    out = set()
    for a, ins in p.disasm(reset, reset + 0x20):
        if ins is None:
            break
        lv = p.lit(ins)
        if lv is not None and lv[1] & 1 and p.in_code(lv[1] & ~1):
            out.add(lv[1] & ~1)
        if ins.mnemonic == "bx":
            break
    return out


def prologue_scan(p):
    """Every 'push {..., lr}' that is not inside an already-known function body."""
    found = set()
    for fo in range(p.f0, p.f1 - 1, 2):
        rt = p.rt(fo)
        ins = p.insn_at(rt)
        if ins is not None and ins.mnemonic.startswith("push") and "lr" in ins.op_str:
            found.add(rt)
    return found


def run(name, which, nvec):
    d = fwlib.load(name)
    p = fwlib.Prog(d, which)
    vec = p.vectors(nvec)
    entries = set(v & ~1 for v in vec[1:] if v and p.in_code(v & ~1))
    ptrs = code_pointers(p) | reset_targets(p, vec[1] & ~1)
    funcs = fwlib.discover_functions(p, list(entries | ptrs))
    # add stray prologues not covered by any function body
    covered = set()
    for f in funcs.values():
        covered.update(f["insns"].keys())
    extra = [a for a in prologue_scan(p) if a not in covered]
    funcs2 = fwlib.discover_functions(p, list(funcs.keys()) + extra)
    callers = defaultdict(set)
    for fa, f in funcs2.items():
        for c in f["calls"]:
            callers[c].add(fa)
    periph = Counter()
    ram = Counter()
    per_func = {}
    for fa, f in funcs2.items():
        acc = fwlib.mem_accesses(p, f["insns"])
        lst = []
        for (ia, kind, size, ea) in acc:
            if 0x40000000 <= ea < 0x60000000 or ea >= 0xE0000000:
                periph[ea] += 1
            if 0x20000000 <= ea < 0x20010000 and kind in ("ld", "st"):
                ram[ea] += 1
            if kind in ("ld", "st"):
                lst.append([hex(ia), kind, size, hex(ea)])
        per_func[hex(fa)] = {
            "end": hex(f["end"]),
            "n_insns": len(f["insns"]),
            "calls": sorted(hex(c) for c in f["calls"]),
            "callers": sorted(hex(c) for c in callers.get(fa, ())),
            "is_vector": fa in entries,
            "is_code_pointer": fa in ptrs,
            "mem": lst,
        }
    covered = set()
    for f in funcs2.values():
        for a, i in f["insns"].items():
            covered.update(range(a, a + i.size))
    code_bytes = p.rt1 - p.rt0
    summary = {
        "program": which,
        "image": name,
        "runtime_range": [hex(p.rt0), hex(p.rt1)],
        "n_functions": len(funcs2),
        "bytes_in_discovered_instructions": len(covered),
        "fraction_of_region": round(len(covered) / code_bytes, 3),
        "vectors": [hex(v) for v in vec],
    }
    json.dump({"summary": summary, "functions": per_func},
              open(os.path.join(GEN, f"s02_functions_{which}.json"), "w"), indent=0)
    with open(os.path.join(EV, f"s02_peripherals_{which}.txt"), "w") as fh:
        fh.write(f"# hardware-register constants referenced by discovered code ({which}, {name})\n")
        for ea, n in sorted(periph.items()):
            fh.write(f"{ea:#010x} {n}\n")
    print(json.dumps(summary, indent=1)[:1500])
    # coarse peripheral blocks
    blocks = Counter()
    for ea, n in periph.items():
        blocks[ea & ~0x3FF] += n
    print("peripheral 1KB blocks referenced:", ", ".join(f"{b:#x}:{n}" for b, n in sorted(blocks.items())))
    return p, funcs2


if __name__ == "__main__":
    os.makedirs(GEN, exist_ok=True)
    run("stock", "mc", 48)
    run("stock", "a", 84)
