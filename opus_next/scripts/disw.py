"""Tiny disassembly window printer: python disw.py IMAGE FILE_START FILE_END"""
import sys, struct, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from opus_emu import image, DELTA
img = image(sys.argv[1]); a, b = int(sys.argv[2], 16), int(sys.argv[3], 16)
cs = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
off = a
while off < b:
    i = next(cs.disasm(img[off:off + 4], off - DELTA, 1), None)
    if i is None:
        print(f'{off:05X}  .hword {img[off]|img[off+1]<<8:#06x}'); off += 2; continue
    extra = ''
    if i.mnemonic == 'ldr' and 'pc' in i.op_str:
        t = ((i.address + 4) & ~3) + int(re.search(r'#(0x[0-9a-f]+|\d+)', i.op_str)[1], 0)
        extra = f'  ; ={struct.unpack_from("<I", img, t + DELTA)[0]:#x}'
    elif i.mnemonic.startswith('b') and i.op_str.startswith('#'):
        extra = f'  ; -> file {int(i.op_str[1:], 16) + DELTA:05X}'
    print(f'{off:05X} {i.address:04X}  {i.mnemonic:6s} {i.op_str}{extra}')
    off += i.size
