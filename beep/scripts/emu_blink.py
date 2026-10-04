"""Closed-loop emulation of the V9 feedback blink: real hook1 (0x23A98) + real gpio_outputs_update (0x1CA24, with hook2).
Usage: python emu_blink.py <image.bin> [FB_ON FB_OFF]   (optional patch of the two movs immediates at 0x23B16/0x23B1C)"""
import sys, struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_MEM_UNMAPPED
from unicorn.arm_const import *
OFF = 0x17018
img = bytearray(open(sys.argv[1], 'rb').read())
if len(sys.argv) > 3:
    on, off = int(sys.argv[2]), int(sys.argv[3])
    assert img[0x23B17] == 0x21 and img[0x23B1D] == 0x21      # movs r1,#imm8
    img[0x23B16], img[0x23B1C] = on, off
RAM, GPIO2 = 0x20000000, 0x40010D80
def run(fn_file, lightmode_fn=None):
    uc.reg_write(UC_ARM_REG_SP, RAM + 0x1000)
    uc.reg_write(UC_ARM_REG_LR, 0xFFF1)            # sentinel
    uc.emu_start((fn_file - OFF) | 1, 0xFFF0, count=5000)
uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
uc.mem_map(0, 0x20000); uc.mem_write(0, bytes(img[OFF:OFF + 0x20000]))
uc.mem_write(0xFFF0, b'\x00\xbf\x00\xbf')
uc.mem_map(RAM, 0x3000); uc.mem_map(0x40010000, 0x2000)
w8 = lambda a, v: uc.mem_write(a, bytes([v])); w16 = lambda a, v: uc.mem_write(a, struct.pack('<H', v))
r16 = lambda a: struct.unpack('<H', uc.mem_read(a, 2))[0]
def scenario(dash_light, label):
    uc.mem_write(RAM, bytes(0x3000)); uc.mem_write(0x40010000, bytes(0x2000))
    w8(RAM + 0x14D, 3); w8(RAM + 0xF3, 80); w16(RAM + 0xC2, 300)       # Sport, SOC 80, 30.0 C
    w8(RAM + 0x1DC, dash_light)
    trace, toggles, prev_en = [], [], None
    for tick in range(1400):
        hold = 100 <= tick < 500                                      # gesture: speed 0, brake 60, throttle 100
        w16(RAM + 0x110, 60 if hold else 0); w16(RAM + 0x158, 100 if hold else 0); w16(RAM + 0x1A6, 0)
        if tick in (100 + 0, 600):                                   # second press later toggles OFF
            pass
        if 600 <= tick < 1000:
            w16(RAM + 0x110, 60); w16(RAM + 0x158, 100)
        if r16(0x20000900 + 12) == 0: w8(RAM + 0x1DC, dash_light)    # dashboard frame restores its own nibble
        run(0x1CA24)                                                 # mod10 slot 3 (gpio_outputs_update + hook2)
        run(0x23A98)                                                 # mod10 slot 4 (hook1 inside envelope_protection)
        en = uc.mem_read(RAM + 0x908, 1)[0]
        if en != prev_en: toggles.append((tick, en)); prev_en = en
        pdo = struct.unpack('<I', uc.mem_read(GPIO2 + 0xC, 4))[0]
        trace.append(1 if pdo & 0x1400 == 0x1400 else 0)
    def pulses(a, b, level):
        seg = trace[a:b]; n = 0
        for i in range(1, len(seg)):
            if seg[i] == level and seg[i - 1] != level: n += 1
        return n
    t_on, t_off = toggles[1][0], toggles[2][0]
    print(f"{label}: switch toggled ON at tick {t_on}, OFF at tick {t_off}")
    for name, t in (("ON ", t_on), ("OFF", t_off)):
        seg = ''.join('#' if x else '.' for x in trace[t:t + 260])
        print(f"  after {name}: light-on pulses {pulses(t, t+260, 1)}, dark gaps {pulses(t, t+260, 0)}")
        print("   ", seg[:130]); print("   ", seg[130:])
scenario(0, "light OFF on dashboard")
scenario(1, "light ON on dashboard")
