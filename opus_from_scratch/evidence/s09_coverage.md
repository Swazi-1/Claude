# Coverage table (stock image; RC02 is identical outside the motor-controller changes)

| file region | what it is | size (bytes) | mapped | understood (estimate) |
|---|---|---|---|---|
| 0x00000-0x0002D | package header (size, CRC-16, version '0108', model id '001600010001') | 46 | 100 % | 100 % (every field checked; CRC verified) |
| 0x0002E-0x007FF | padding 0xFF | 2002 | 100 % | 100 % |
| 0x00800-0x0080C | tag 'DEPRD5C' + 5 bytes | 13 | 100 % | tag: likely a battery-pack vendor/product code; 5 bytes unknown |
| 0x0080D-0x00FFF | padding 0xFF | 2035 | 100 % | 100 % |
| 0x01000-0x19223 | battery-side program (N32L40x-class Cortex-M4, runtime +0x08002000), 824 functions | 98852 | 85.6 % | 4.9 % |
| 0x19224-0x197FF | padding 0xFF | 1500 | 100 % | 100 % |
| 0x19800-0x19817 | motor-controller header (size, CRC-32, 'LKS32MC071CBT8FFP') | 24 | 100 % | 100 % (CRC verified) |
| 0x19818-0x2381B | motor-controller program (LKS32MC071, Cortex-M0, runtime -0x17018), 223 functions | 40964 | 86.3 % | 23.4 % |
| 0x2381C-0x23FFF | padding 0xFF (RC02 uses 0x2381C-0x23C1B for added code) | 2020 | 100 % | 100 % |

'mapped' counts only bytes inside instructions reached by discovery; literal pools and tables count as unmapped, so 100 % is not reachable.
