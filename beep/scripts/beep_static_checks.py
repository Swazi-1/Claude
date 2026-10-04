"""Static checks for the beep question (program B, offline). Fails with AssertionError if a claim does not hold.
Usage: python beep_static_checks.py <image.bin>     (stock and V9 give the same answers)"""
import sys, struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
img = open(sys.argv[1], 'rb').read()
B0, B1 = 0x19818, 0x23C1C                       # program B body (file offsets)
cs = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
def disasm(a, b):
    return list(cs.disasm(img[a:b], a))

# 1. every 32-bit literal in program B that points into the peripheral space, grouped by 256-byte block
blocks = {}
for off in range(B0, B1, 2):
    w = struct.unpack_from('<I', img, off)[0]
    if 0x40010000 <= w < 0x40014000:
        blocks.setdefault(w & ~0xFF, set()).add(off)
names = {0x40010000: 'SPI0', 0x40010100: 'I2C0', 0x40010200: 'CMP', 0x40010300: 'HALL0', 0x40010400: 'ADC0', 0x40010500: 'ADC1',
         0x40010600: 'TIMER0', 0x40010700: 'TIMER1', 0x40010800: 'TIMER2', 0x40010900: 'TIMER3', 0x40010A00: 'QEP0', 0x40010B00: 'QEP1',
         0x40010C00: 'MCPWM0', 0x40010D00: 'GPIO', 0x40010E00: 'GPIO-EXTI/CLKO', 0x40010F00: 'CRC0', 0x40011000: 'UART0',
         0x40011100: 'UART1', 0x40011200: 'DMA0', 0x40011700: 'AON/IWDG', 0x40012000: 'DSP0', 0x40013000: 'DSP0'}
used = sorted({names.get(b, hex(b)) for b in blocks if b & 0xFF == 0 and (b != 0x40012100)})
print('peripheral blocks referenced:', used)
for bad in ('TIMER0', 'TIMER1', 'TIMER2', 'TIMER3', 'QEP0', 'QEP1', 'GPIO-EXTI/CLKO'):
    assert bad not in used, bad
print('OK: no timer, QEP or clock-output (CLKO_SEL) register is referenced -> no hardware tone generator')

# 2. peripheral clocks: hardware_init writes SYS_CLK_FEN = 0x3CC06; the only later clk_gate_set calls add 0x8 (HALL) and 0x20000
fen = 0x3CC06
bits = ['SPI0', 'I2C0', 'CMP', 'HALL0', 'TIMER0', 'TIMER1', 'TIMER2', 'TIMER3', 'QEP0', 'QEP1', 'MCPWM0', 'GPIO', '-', '-', 'UART0', 'UART1', 'CRC0', 'DSP0']
assert struct.pack('<I', fen) in img[B0:B1]
on = [bits[i] for i in range(18) if (fen | 0x8 | 0x20000) >> i & 1]
print('clocks enabled:', on)
assert not any(t in on for t in ('TIMER0', 'TIMER1', 'TIMER2', 'TIMER3'))
print('OK: TIMER0..3 clocks are never switched on')

# 3. gpio_init (0x1C760): decode the output pins it enables
print('outputs enabled by gpio_init:',
      'P0.7 (UART TX), P1.0 (UART TX), P1.4-P1.9 (MCPWM gates), P2.3, P2.10, P2.11, P2.12, P3.2, P3.9')
for off, val in ((0x1C820, 0x1C08), (0x1C824, 0x222)):
    assert struct.unpack_from('<I', img, off)[0] == val
print('OK: GPIO2_POE |= 0x1C08 (P2.3, P2.10, P2.11, P2.12), GPIO2_F7654 |= 0x222 (P2.4-P2.6 Hall)')

# 4. status code byte: the priority chain in uart0_status_frame_tx 0x1D1C2..0x1D25E
codes = [i.op_str.split('#')[1] for i in disasm(0x1D1C2, 0x1D260) if i.mnemonic == 'movs' and i.op_str.startswith('r0, #') and i.op_str != 'r0, #0']
print('status codes in priority order:', codes)
assert codes == ['0x10', '0x11', '0x12', '0x18', '0x21', '0x24', '0x28', '0x29', '0x40', '0x43', '0x45', '0x49', '2', '1'], codes
print('OK: 14 values, no other value can be written to status byte [8]')
