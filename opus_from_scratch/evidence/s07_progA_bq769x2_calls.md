# Program A: calls into BQ769x2-style I2C helpers (stock image; identical in RC02)

Constant arguments recovered from the instructions just before each call; '?' = computed at runtime.

## subcmd(cmd) at 0x8003bdc: 29 call sites

| caller function | call at | arg | meaning (TI TRM) |
|---|---|---|---|
| 0x8004a5c | 0x8004a62 | 0x009a | SLEEP_DISABLE |
| 0x8005b20 | 0x8005b24 | 0x009a | SLEEP_DISABLE |
| 0x80068f8 | 0x8006946 | 0x0094 | CHG_PCHG_OFF |
| 0x80069b8 | 0x80069f2 | 0x0099 | SLEEP_ENABLE |
| 0x8006de0 | 0x8006de6 | 0x0093 | DSG_PDSG_OFF |
| 0x8006de0 | 0x8006dee | 0x0094 | CHG_PCHG_OFF |
| 0x8006e08 | 0x8006e0e | 0x0094 | CHG_PCHG_OFF |
| 0x8007274 | 0x80072e4 | 0x0093 | DSG_PDSG_OFF |
| 0x8007ee0 | 0x8007eee | 0x0090 | SET_CFGUPDATE |
| 0x8007ee0 | 0x8007f08 | 0x00a1 | OTP_WRITE |
| 0x8007ee0 | 0x8007f50 | 0x0092 | EXIT_CFGUPDATE |
| 0x8007ee0 | 0x8007f74 | 0x0092 | EXIT_CFGUPDATE |
| 0x8007ee0 | 0x8007f92 | 0x0092 | EXIT_CFGUPDATE |
| 0x800b134 | 0x800b188 | 0x0093 | DSG_PDSG_OFF |
| 0x800b134 | 0x800b1a6 | 0x0094 | CHG_PCHG_OFF |
| 0x800b134 | 0x800b1e6 | 0x0094 | CHG_PCHG_OFF |
| 0x800b134 | 0x800b22e | 0x0093 | DSG_PDSG_OFF |
| 0x800b134 | 0x800b284 | 0x0093 | DSG_PDSG_OFF |
| 0x800c7ec | 0x800c80a | 0x009e | LOAD_DETECT_ON |
| 0x800c7ec | 0x800c88e | 0x009f | LOAD_DETECT_OFF |
| 0x800e158 | 0x800e17c | 0x0090 | SET_CFGUPDATE |
| 0x800e158 | 0x800e1d6 | 0x0092 | EXIT_CFGUPDATE |
| 0x800e20c | 0x800e22a | 0x009a | SLEEP_DISABLE |
| 0x800e20c | 0x800e25e | 0x009a | SLEEP_DISABLE |
| 0x8013de8 | 0x8014186 | 0x009f | LOAD_DETECT_OFF |
| 0x8013de8 | 0x8014270 | 0x0010 | SHUTDOWN |
| 0x8013de8 | 0x8014288 | 0x0010 | SHUTDOWN |
| 0x8013de8 | 0x8014316 | 0x0012 | RESET |
| 0x8013de8 | 0x801432e | 0x0012 | RESET |

## subcmd_i2c2(cmd) at 0x8003c1c: 3 call sites

| caller function | call at | arg | meaning (TI TRM) |
|---|---|---|---|
| 0x8007b5a | 0x8007b70 | 0x0090 | SET_CFGUPDATE |
| 0x8007fb4 | 0x8007fb8 | 0x0092 | EXIT_CFGUPDATE |
| 0x8013c3c | 0x8013c42 | 0x29bc | unknown |

## subcmd_read(dev,cmd,buf,len) at 0x8003c7a: 3 call sites

| caller function | call at | arg | meaning (TI TRM) |
|---|---|---|---|
| 0x8003d78 | 0x8003d8a | 0x0005 | STATIC_CFG_SIG |
| 0x8003d78 | 0x8003db6 | 0x0005 | STATIC_CFG_SIG |
| 0x800418c | 0x800419a | 0x0083 | CB_ACTIVE_CELLS |

## read_reg(dev,reg,buf,len) at 0x8003c60: 28 call sites

| caller function | call at | arg | meaning (TI TRM) |
|---|---|---|---|
| 0x80040c4 | 0x80040ce | 0x0038 | LD Pin Voltage |
| 0x8004138 | 0x8004142 | 0x0036 | PACK Pin Voltage |
| 0x80041dc | 0x80041e6 | 0x0012 | Battery Status |
| 0x80041f0 | 0x80041fa | 0x0014 | Cell 1 Voltage |
| 0x8004204 | 0x800420e | 0x0016 | Cell 2 Voltage |
| 0x8004218 | 0x8004222 | 0x0018 | Cell 3 Voltage |
| 0x800422c | 0x8004236 | 0x001a | Cell 4 Voltage |
| 0x8004240 | 0x800424a | 0x001c | Cell 5 Voltage |
| 0x8004254 | 0x800425e | 0x001e | Cell 6 Voltage |
| 0x8004268 | 0x8004272 | 0x0020 | Cell 7 Voltage |
| 0x800427c | 0x8004286 | 0x0022 | Cell 8 Voltage |
| 0x8004290 | 0x800429a | 0x0024 | Cell 9 Voltage |
| 0x80042a4 | 0x80042ae | 0x0026 | Cell 10 Voltage |
| 0x80042b8 | 0x80042c2 | 0x0028 | Cell 11 Voltage |
| 0x80042cc | 0x80042d6 | 0x002a | Cell 12 Voltage |
| 0x80042e0 | 0x80042ea | 0x0032 | Cell 16 Voltage |
| 0x80042f4 | 0x80042fe | 0x003a | CC2 Current |
| 0x8004308 | 0x8004312 | 0x007f | FET Status |
| 0x800431c | 0x8004326 | 0x0003 | Safety Status A |
| 0x8004330 | 0x800433a | 0x0005 | Safety Status B |
| 0x8004344 | 0x800434e | 0x0007 | Safety Status C |
| 0x8004358 | 0x8004362 | 0x0070 | TS1 Temperature |
| 0x80068f8 | 0x8006968 | 0x007f | FET Status |
| 0x8007274 | 0x80072ba | 0x007f | FET Status |
| 0x8007274 | 0x8007304 | 0x007f | FET Status |
| 0x8007ee0 | 0x8007f28 | 0x003e | Subcommand (low) |
| 0x800f33c | 0x800f358 | 0x007f | FET Status |
| 0x8013de8 | 0x80141a4 | 0x0038 | LD Pin Voltage |

