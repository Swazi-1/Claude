# MI5 Max firmware V8.1 CANDIDATE (built 2026-10-04): review only, NOT flashed, NOT hardware tested

**File:** `MI5Max_V8_1_CANDIDATE.bin`, 147,456 bytes
**SHA-256:** `9218c5ef58b78d39a172d6a85d5c046d5ff85e4bfaa3e644f1e04c20b4e2f63b`
**Built from:** V8 FINAL 600 (`901ce6cea8fa6751bd00f147caad86fcd95bc6e29f08f0a6bf997bd7dcdf1df9`), the build on the scooter now.

Flashing is the owner's own decision and action. Claude did not and does not send anything to the scooter.
Labels: **C** confirmed (bytes/code/emulator), **S** strong, **L** likely, **U** unknown.

## 1. What changed (owner's choices 2026-10-04)
| # | change | file offset | V8 600 | V8.1 | effect |
|---|---|---|---|---|---|
| 1 | Smooth low-battery power: base | 0x1FD96..99 | `FF 20 EE 30` (493) | `96 20 80 00` (150x4 = 600) | no power step at 20 % |
| 1 | Smooth low-battery power: slope | 0x1FD92 | `16` (22 per %) | `21` (33 per %) | straight line 600 at 20 % -> 274 floor at 10 %, no step at 10 % either |
| 2 | Remove "Medium recovery = child cap" | 0x23824 | `05 D0` (beq) | `00 BF` (nop) | Medium is just Medium regen; child cap only from the six-press gesture |
| 4 | Heat fade start | 0x1FC90 | `FF` (255x4 = 1020) | `D8` (216x4 = 864) | controller-temperature fade starts at 86.4 C |
| 4 | Heat fade formula constant | 0x1FEB8..B9 | `24 0E` (3620, from farm v7.1) | `79 0C` (3193, Xiaomi stock) | fade 3193 - 3T joins the 600 cap smoothly at 86.4 C and reaches 0 at 106.4 C |
| - | Inner CRC32 / outer CRC16 | 0x19804..07 / 0x0A..0B | | recomputed | `fw_image_tool.py recrc` |

Item 3 (Drive mode): **no change**. D stays 25.0 km/h, current cap 400. Analysis showed the D cap changes flat-ground range by only ~0.3 %; speed is the real range lever (see section 4).

Unchanged: Sport 600 (22.1 A) and 45.0 km/h target; walking/eco mode 20 km/h; regen 91/146/292; coast regen from 5.0 km/h; child cap values D 15 / S 20 / other 6 km/h and the six-press toggle; region-free; RC02 governor mask; **program A (battery) byte-identical; B vectors/reset, `startup_calibrate_and_load`, `hardware_init`, `dash_loss_poweroff`, the dashboard frame decoder and `main` byte-identical (power-button path untouched).**

## 2. Verification (all pass) **C**
* Input hash checked; every old byte checked before writing; 15 differing bytes vs V8 600 = 9 behaviour bytes + 6 checksum bytes (`DIFF_vs_V8_FINAL_600.txt`).
* Both checksums verify (`IMAGE_INFO.txt`).
* The heat constant at 0x1FEB8 is used by exactly one instruction (`ldr` at 0x1FCAC, `envelope_protection`); full scan of B and the appended code.
* The real changed code was run in the Unicorn emulator for V8 and V8.1 side by side (`emu_v81.py`, output `EMULATOR_RESULTS.txt`):

**Low-battery cap (Sport):**
| battery | V8 600 | V8.1 |
|---|---|---|
| 20 % or more | 22.1 A | 22.1 A |
| 19 % | 17.3 A | 20.8 A |
| 17 % | 15.7 A | 18.4 A |
| 15 % | 14.1 A | 16.0 A |
| 13 % | 12.5 A | 13.6 A |
| 11 % | 10.8 A | 11.1 A |
| 10 % or less | 10.1 A | 10.1 A |
D mode (cap 400 = 14.7 A) is limited by the ramp only below about 14 %.

**Controller-temperature cap ("Scooter temperature" in the app, L for the field mapping):**
| controller temp | V8 600 | V8.1 |
|---|---|---|
| up to 86 C | 22.1 A | 22.1 A |
| 90 C | 22.1 A | 18.1 A |
| 95 C | 22.1 A | 12.6 A |
| 100 C | 22.1 A | 7.1 A |
| 102.1 C | 20.5 A | 4.8 A |
| 105 C | 17.3 A | 1.6 A |
| 110 C and above | **0.1 A (sudden cut from ~11.8 A)** | 0.1 A (already faded) |
Owner's highest reading so far: 75 C (100 m climb over 2.2 km, cool day). Correction to the KB: farm v7.1 also changed this constant (3193 -> 3620); V8 fades from 102 C and then cuts at 110 C (it does not drop to 5 A at 102 C as stated in chat before the emulator check).

**Child cap helper (target in 0.1 km/h, V8 / V8.1):** with recovery Medium (60) and the flag off, V8 caps D/S/walk to 150/200/60, V8.1 leaves 250/450/200. With the six-press flag on (0xC1), both cap to 150/200/60 for every recovery level. Weak and Strong are unchanged.

Not checked: real hardware, the power button on this exact image, the dashboard's reaction (U).

## 3. Flash and test (owner)
Use `POWER_BUTTON_TEST_AND_FLASH_CHECKLIST.md` (this folder). Short version: button test BEFORE on V8 600, battery 60 % or more, flash once, button test AFTER, then:
1. Set **Medium** in the app, change mode once: D should still reach about 25 km/h (not capped to 15).
2. Six mode changes while standing still: child cap still switches on (D about 15); six more switch it off.
3. Sport full throttle: still about 22 A peak.
4. Later ride from about 22 % down to about 12 %: amps fall gradually, no sudden drop at 20 %.
5. Long climb: note "Scooter temperature". Above 86 C power starts to fade gently (expected, not a fault).

**Revert:** flash V8 FINAL 600 (`01_FIRMWARE/1_CURRENT_ON_SCOOTER_V8_FINAL_600/`) with the same method.

## 4. Range note (D mode, flat ground, 81 kg rider + ~24.5 kg scooter; model fitted to the owner's ~340 W at ~31 km/h; S for ratios, L for absolute km)
| D speed | power | Wh/km | range (ideal, flat, no wind) |
|---|---|---|---|
| 30 km/h | 305 W | 10.2 | ~42 km |
| 25 km/h (V8/V8.1) | 204 W | 8.2 | ~53 km |
| 23 km/h | 172 W | 7.5 | ~58 km |
| 22 km/h | 157 W | 7.1 | ~60 km |
D current cap 400 vs 328: ~0.01 Wh per start (about 0.3 % range), so it was left at 400. If more range is wanted later, the D speed target (literal 250 at 0x20054) is the lever; not changed here.

ON THE SCOOTER since 2026-10-04 (owner): button 10/10, all checks OK. V8 FINAL 600 is the rollback.
