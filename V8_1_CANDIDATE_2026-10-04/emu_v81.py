import sys
from unicorn import *
from unicorn.arm_const import *
OFF=0x17018
def load(p): return open(p,'rb').read()
def mk(img):
    mu=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
    mu.mem_map(0,0x20000); mu.mem_write(0,img[OFF:OFF+0x20000][:0x20000].ljust(0x20000,b'\xff'))
    mu.mem_map(0x20000000,0x4000); return mu
def run(mu,start,stop,regs):
    for r,v in regs.items(): mu.reg_write(r,v)
    mu.emu_start((start-OFF)|1,stop-OFF,count=500)
def lit(img,pc,imm): import struct; a=((pc-OFF+4)&~3)+imm; return struct.unpack_from('<I',img,a+OFF)[0]
BASE=0x20001000
def lowcharge(img,soc,env=600):
    mu=mk(img); socaddr=lit(img,0x1FD82,0x148)
    mu.mem_write(socaddr,bytes([soc])); mu.mem_write(BASE+0x12,env.to_bytes(2,'little'))
    run(mu,0x1FD82,0x1FDA6,{UC_ARM_REG_R4:BASE,UC_ARM_REG_R2:0x112})
    return int.from_bytes(mu.mem_read(BASE+0x12,2),'little')
def thermal(img,t,env=600):
    mu=mk(img); mu.mem_write(BASE+0xC,(t&0xffff).to_bytes(2,'little')); mu.mem_write(BASE+0x12,env.to_bytes(2,'little'))
    run(mu,0x1FC8C,0x1FCC4,{UC_ARM_REG_R4:BASE,UC_ARM_REG_R5:0,UC_ARM_REG_R6:1})
    return int.from_bytes(mu.mem_read(BASE+0x12,2),'little')
def child(img,target,sel,profile,flag):
    mu=mk(img); mu.mem_write(BASE+0xA0,bytes([profile])); mu.mem_write(BASE+0x34C,flag.to_bytes(4,'little')); mu.mem_write(BASE+1,bytes([sel]))
    mu.mem_map(0x30000000,0x1000)
    run(mu,0x2381C,0x30000000+OFF,{UC_ARM_REG_R0:target,UC_ARM_REG_R1:BASE,UC_ARM_REG_SP:0x20003F00,UC_ARM_REG_LR:(0x30000000)|1})
    return int.from_bytes(mu.mem_read(BASE+0xE,2),'little')
old=load(sys.argv[1]); new=load(sys.argv[2])
print("Low-charge cap (Sport env 600):  SOC | V8 counts/A | V8.1 counts/A")
for s in (25,20,19,18,17,15,13,12,11,10,5,0):
    a,b=lowcharge(old,s),lowcharge(new,s); print(f"  {s:3d}% | {a:4d} {a/27.2:5.1f} A | {b:4d} {b/27.2:5.1f} A")
print("Thermal cap (temp_local tenths):  T | V8 | V8.1")
for t in (750,850,864,865,880,900,950,1000,1020,1021,1050,1100,1200):
    a,b=thermal(old,t),thermal(new,t); print(f"  {t/10:5.1f} C | {a:4d} {a/27.2:5.1f} A | {b:4d} {b/27.2:5.1f} A")
print("Child cap helper (target in: D 250 / S 450 / walk 200):")
for prof in (30,60,90):
  for flag in (0,0xC1):
    row=[]
    for sel,tgt in ((2,250),(3,450),(0x0B,200)):
        row.append(f"{child(old,tgt,sel,prof,flag)}/{child(new,tgt,sel,prof,flag)}")
    print(f"  profile {prof} flag {flag:#04x}:  D {row[0]}  S {row[1]}  walk {row[2]}   (V8/V8.1, 0.1 km/h)")
