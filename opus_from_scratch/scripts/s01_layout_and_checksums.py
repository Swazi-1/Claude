"""S01: file layout, checksums and which regions differ between images.

Output: evidence/s01_layout_and_checksums.json (+ printed summary)
All checks here CAN fail (a wrong range or a modified byte changes the CRC).
"""
import binascii
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
import fwlib  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "evidence", "s01_layout_and_checksums.json")

_T = []
for i in range(256):
    c = i << 24
    for _ in range(8):
        c = ((c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if c & 0x80000000 else (c << 1) & 0xFFFFFFFF
    _T.append(c)


def crc32_mpeg2(b, init=0xFFFFFFFF):
    c = init
    for x in b:
        c = ((c << 8) & 0xFFFFFFFF) ^ _T[((c >> 24) ^ x) & 0xFF]
    return c


assert crc32_mpeg2(b"123456789") == 0x0376E6E7          # published check value
assert binascii.crc_hqx(b"123456789", 0) == 0x31C3       # CRC-16/XMODEM check value


def ff_runs(d, minlen=32):
    runs, i, n = [], 0, len(d)
    while i < n:
        if d[i] == 0xFF:
            j = i
            while j < n and d[j] == 0xFF:
                j += 1
            if j - i >= minlen:
                runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


def diff_regions(a, b, gap=4):
    out, i, n = [], 0, len(a)
    while i < n:
        if a[i] != b[i]:
            last = i
            j = i
            while j < n and (j - last) <= gap:
                if a[j] != b[j]:
                    last = j
                j += 1
            out.append((i, last + 1))
            i = last + 1
        else:
            i += 1
    return out


def main():
    res = {"images": {}, "pairs": {}}
    D = {k: fwlib.load(k) for k in fwlib.IMAGES}
    for k, d in D.items():
        pkg_size = struct.unpack_from(">I", d, 0)[0]
        stored16 = struct.unpack_from(">H", d, 0x0A)[0]
        calc16 = binascii.crc_hqx(d[0x19800:], 0)
        msz, mcrc = struct.unpack_from("<II", d, 0x19800)
        body = d[0x19818:0x19818 + msz]
        body += b"\xff" * ((-len(body)) % 4)
        calc32 = crc32_mpeg2(body)
        res["images"][k] = {
            "len": len(d),
            "pkg_size_be_at_0": hex(pkg_size),
            "version_ascii_0x12": d[0x12:0x16].decode(),
            "model_id_ascii_0x22": d[0x22:0x2E].decode(),
            "subheader_0x800": d[0x800:0x80D].hex(),
            "mc_header_ascii": d[0x19808:0x19819].decode(errors="replace"),
            "hdr_crc16_stored": hex(stored16),
            "hdr_crc16_calc_over_0x19800_to_end": hex(calc16),
            "hdr_crc16_ok": stored16 == calc16,
            "mc_size": hex(msz),
            "mc_crc32_stored": hex(mcrc),
            "mc_crc32_calc": hex(calc32),
            "mc_crc32_ok": mcrc == calc32,
            "a_vector_sp_reset": [hex(fwlib.u32(d, 0x1000)), hex(fwlib.u32(d, 0x1004))],
            "mc_vector_sp_reset": [hex(fwlib.u32(d, 0x19818)), hex(fwlib.u32(d, 0x1981C))],
            "data_regions": [],
        }
        prev = 0
        for a, b in ff_runs(d):
            if a > prev:
                res["images"][k]["data_regions"].append([hex(prev), hex(a)])
            prev = b
        if prev < len(d):
            res["images"][k]["data_regions"].append([hex(prev), hex(len(d))])

    for x, y in [("stock", "rc02"), ("stock", "v71"), ("v71", "rc02"), ("rc01", "rc02"), ("stock", "rc01")]:
        regs = diff_regions(D[x], D[y])
        n = sum(sum(1 for k in range(a, b) if D[x][k] != D[y][k]) for a, b in regs)
        res["pairs"][f"{x}_vs_{y}"] = {
            "regions": len(regs),
            "bytes_differing": n,
            "in_header_0_0x1000": sum(1 for a, _ in regs if a < 0x1000),
            "in_program_A_0x1000_0x19800": sum(1 for a, _ in regs if 0x1000 <= a < 0x19800),
            "in_motor_controller_0x19800_end": sum(1 for a, _ in regs if a >= 0x19800),
            "program_A_identical": D[x][0x1000:0x19800] == D[y][0x1000:0x19800],
        }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=1)
    for k, v in res["images"].items():
        print(f"{k:6s} ver={v['version_ascii_0x12']} id={v['model_id_ascii_0x22']} "
              f"hdrCRC16 ok={v['hdr_crc16_ok']} MC size={v['mc_size']} MC CRC32 ok={v['mc_crc32_ok']}")
    for k, v in res["pairs"].items():
        print(f"{k:16s} regions={v['regions']:3d} bytes={v['bytes_differing']:4d} "
              f"programA_identical={v['program_A_identical']} MC_regions={v['in_motor_controller_0x19800_end']}")


if __name__ == "__main__":
    main()
