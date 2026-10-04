# Xiaomi 5 Max: can the motor controller make the dashboard beep?

Date: 2026-10-04. Offline analysis of program B (the motor controller) only. Nothing was sent to the scooter and no firmware file was produced. Files used: `01_STOCK_ORIGINAL.bin`, `MI5Max_V9_0_BOOST_GESTURE_CANDIDATE.bin` (SHA-256 `5874…a374`), the `kb/` notes and the LKS32MC07x manual. Labels: **[C]** confirmed in code, **[S]** strong, **[L]** likely, **[U]** unknown. Addresses are file offsets.

Scripts: [`beep/scripts/beep_static_checks.py`](beep/scripts/beep_static_checks.py) (pin, timer and status-code checks; fails on any wrong claim) and [`beep/scripts/emu_blink.py`](beep/scripts/emu_blink.py) (runs your real hook1, hook2 and `gpio_outputs_update` in Unicorn and counts the tail-light blinks). Needs Python 3, `capstone`, `unicorn`.

## Short answer

**No. I found no safe way for the controller to make the dashboard beep.**
- The controller has no sound hardware it drives [C].
- The only signals it sends that a dashboard might react to with a beep are **fault codes** and the **speed value**. Faking either would show a false error or a false speed, and what the dashboard does with them is unknown [U].
- Both dashboard beeps you know about (≈30 km/h, and levers held at power-on) come from the dashboard. The controller only supplies the speed number for the first one [L].

**Best lower-risk option:** keep the tail-light blink, but make the two states easier to tell apart: **3 blinks = ON, 1 blink = OFF**. This only changes two constants, adds **0 bytes**, and was checked in emulation (see the design sketch below).

## 1. Does the controller drive a buzzer? No [C]

- **No tone hardware is used.** The code never refers to TIMER0–3, QEP0/1 or the clock-output register (CLKO_SEL), and the timer clocks are never switched on (`SYS_CLK_FEN` = 0x3CC06, plus HALL later; checked by the script) [C]. MCPWM channel 3 is never given a duty value (only TH00..TH21 are written, per the KB peripheral map) [S].
- **Pins that gpio_init (0x1C760) sets as outputs:**
  - P0.7 / P1.0: UART TX.
  - P1.4–P1.9: the six motor gate signals.
  - P2.3: software PWM in `gpio_p23_blink`. About 40 % with the light on, 100 % when braking, so it is the tail/brake light [S].
  - P2.10 + P2.12: always switched together from the light-mode nibble (off / steady / blink). This is the light you already blink [S].
  - P3.9: the power latch.
  - **P2.11 and P3.2:** switched on as outputs, held low, and never written again [C]. What they are wired to is unknown [U].
- A buzzer on P2.10/P2.12 would sound every time the light is on, so these are not buzzers [S].

## 2. Status frame 0x61 (`uart0_status_frame_tx`, 0x1D09C)

Sent every ~102 ms, alternating the two types, so each type goes out every ~205 ms. A slot is skipped if another UART0 reply was just queued [C].

**Type 0** (`61 30 0A …`, 15 bytes) [C]:

| byte | content |
|---|---|
| 3 | echo of the control byte 3: high nibble, plus the riding mode in the low nibble |
| 4 | echoes of control byte 4: bit7, bit3, bit0 |
| 5 | b7 latch on (`power_off_flag`==0), b6 control b5.6 (debounced), b5 cruise active, b3 echo of control b5.3, b2 low-speed state |
| 6 | controller temperature, °C, 0–255 |
| 7 | NTC-A temperature, 0–200 |
| 8 | **status code** (table below) |
| 9–10 | \|`speed_trend_ref`\|, big-endian. This is a smoothed speed and the **only speed the controller sends** [C]. Units are 0.1 km/h [S] |
| 11 | b3 = any of RAM 0x19A–0x19D. No code ever writes them, so this bit is always 0 [S] |
| 12 | b7 sustained IMU/decel flag (0x374), b6 low-speed-brake state (0x207), b5 power-dip detector (0x90), b3–0 **light-mode nibble echo (RAM 0x1DC)** |
| 13, 14 | sum8, 0x9E |

**Type 1** (`61 31 09 …`): the battery data, passed through. It holds the max-cell byte, the controller's SOC, pack mV, current, the battery temperature byte and two flag bytes [C].

**Status code byte.** The first condition that is true wins. No other value is possible [C].

| code | condition (where set) | when it can happen | dashboard reaction | risk if faked |
|---|---|---|---|---|
| 0x10 | no valid control frame for 10 status periods, ≈1 s (status TX / dispatcher) | dashboard link lost | U | high |
| 0x11 | hardware over-current trip (`ISR_MCPWM0`, MCPWM fault input) | power-stage fault | U | high |
| 0x12 | current-sensor zero offset outside ±500 (startup / `throttle_mode_block`) | sensor fault | U | high |
| 0x18 | Hall code 0 or 7 (`rotor_estimator`) | Hall fault | U | high |
| 0x21 | BMS link timeout, `remote_state`=3 (`uart1_request_builder`) | battery link lost | U | high |
| 0x24 | bus over-voltage, raw > 1075 ≈ 58 V, clears < 1037 (`voltage_monitor`) | regen at full charge | U | high |
| 0x28 / 0x29 | power-stage self-test trip, patterns 0–2 / 3–5 (`power_stage_selftest`) | MOSFET fault | U | high |
| 0x40 | controller temperature reading out of range 5 times (`temp_local_update`) | sensor fault | U | high |
| 0x43 | IMU not found (`imu_init`) | IMU fault | U | high |
| 0x45 | controller temperature > 90.0 °C, also derates power (`envelope_protection`) | overheating | U | high |
| 0x49 | service/update mode active (0x1D6) | service tool only | U | high |
| 2 / 1 | motor drive running / idle (`run_latch`) | every ride | no beep expected [L] | low, but no beep |

All 0x1x–0x4x values are fault conditions [C]. Several match the error list Xiaomi published for older models: E10 link, E18 Hall, E21 BMS link, E24 voltage, E28/E29 MOSFET. So "the dashboard shows E + the hex number" is **[L]** (this evidence comes from outside your files, as the earlier P6 note also found). Whether a code beeps, locks the ride, or gets logged to the app is **[U]**.

## 3. Dashboard → controller direction

None of these commands asks for a sound, and the controller has nothing that could play one [C]. The commands are:
- the 0x51/0x10 control frame;
- the 0x52 family (snapshot, identity, serial, activation, key);
- the 0x53 queries (data reads, BMS poll requests, IMU calibration, CRC).

Small correction to KB 05 §2.2: the query frames use header **0x53**, laid out as `53 TT (53+TT) AC` (dispatcher 0x20A14), not 0x51 [C].

## 4. The two dashboard beeps you know

- **Levers held at power-on (red blink + beep):** the throttle and brake values travel from the dashboard to the controller (control bytes 6–7). So the dashboard reads the levers itself [S]. The status frame has no lever field and no "lever held" flag [C], and at that moment the controller is still booting [S]. The controller plays no part, so this cannot be reused [S].
- **≈30 km/h beep:** the only speed the dashboard gets from the controller is bytes 9–10 [C]. No controller code compares speed to ~30 km/h (earlier P1/P6 sweeps) [C]. So the dashboard probably beeps on that number [L]. Reusing it would mean sending a fake ≥30 km/h while standing still. That would show a wrong speed and could end up in trip or max-speed statistics [U], so I rejected it.

## Candidate table

| candidate | where | evidence | label | risk | verdict / minimal test |
|---|---|---|---|---|---|
| Controller buzzer/tone pin | `gpio_init` 0x1C760, literal scan, `SYS_CLK_FEN` | no timer/CLKO use, timer clocks off | C | – | does not exist |
| P2.11 / P3.2 (unused outputs) | `gpio_init` | output, held low, never written | U | high: unknown wiring. P3.2 is on the power-latch port (excluded by your rules) | not a firmware test; only looking at the board could tell |
| Status code = a fault value | 0x1D1C2–0x1D25E | fault meanings; E-code display likely | S / L / U | **high**: false error, possible ride lock or app log | not recommended |
| Status code 1 ↔ 2 | 0x1D250 | flips on every ride without a beep | C / L | low | gives no beep, so useless |
| Speed bytes 9–10 | 0x1D262 | only speed sent; 30 km/h beep is likely the dashboard reacting | C / L | **high**: false speed | not recommended |
| Light-nibble echo (byte 12) | 0x1D2D8 | V9's hook2 already makes it 2 during the blink | C (echo) / U (use) | low (already happening) | watch the dashboard during the blink (test below) |
| Other status bits | bytes 4, 5, 11, 12 | internal states, meaning on the dashboard unknown | C / U | medium | not recommended |
| Motor-winding tone (small high-frequency voltage on the motor at standstill) | `ISR_MCPWM0` | done by some other ESCs (general knowledge); needs power-stage changes in an ISR with no spare time (P4) | U | high | not proposed |
| **Tail-light blink** (V9) | hook2 0x23BF4 → `gpio_outputs_update` | emulated (below) | C | low | **recommended, with the refinement below** |

## Design sketch: clearer blink, constants only (no new code, 0 bytes)

In `boost_code_v9.py`, change **`FB_ON` 150 → 218** and **`FB_OFF` 60 → 67**. Both are 8-bit `movs r1,#imm` values. The only bytes that change are **0x23B16** (0x96→0xDA) and **0x23B1C** (0x3C→0x43), plus the two checksums via `fw_image_tool.py recrc`.

One blink phase lasts 34 calls × 10.24 ms ≈ 0.35 s. Emulation output (real code, gesture held 3.07 s):

```
V9 now   ON : 2 blinks   OFF: 1 short blink (0.27 s)
proposed ON : 3 blinks   OFF: 1 full blink  (0.35 s)   - same with the headlight on (3 / 1 dark gaps)
```

Nothing protected changes. `Reset_Handler`, startup, `hardware_init`, `dash_loss_poweroff`, the dispatcher, `main`, the vectors and GPIO3 all stay the same, and no new RAM is used.

**Test, in your usual style:**
1. *Static:* rebuild with the generator at base **0x23A98**. Then `fw_image_tool.py diff` V9 against the new file: there must be exactly 2 code bytes plus the checksum/header bytes, and nothing inside any protected function.
2. *Emulation:* `python beep/scripts/emu_blink.py new.bin` must print 3 / 1 blinks for both light states.
3. *Scooter:* run the power-button tests B1–B11, flash, then repeat B1–B11. At a standstill, do the gesture with the light off, then with it on: 3 blinks = ON, 1 = OFF. During each blink, **watch the dashboard for any icon, error or beep**. This also tests the light-nibble echo. Finish with a short Sport ride.
4. *Undo:* flash the V9 file you use now.

## Side notes from the checks

- **Compare "byte-identical" against V9, not stock.** V9 already differs from stock inside `startup_calibrate_and_load`: the call at 0x1C5B8 now goes to 0x23918 instead of `settings_load`, and the literal words at 0x1C6A0 and 0x1C6A8 (0xEC85 / 0xEEC4) are zeroed [C]. I assume this was kept on purpose from earlier builds. My proposal does not touch it.
- **Generator start address.** `boost_code_v9.py` `__main__` assembles at **0x23AA0**, but the real block (the `bl` targets) starts at **0x23A98**. At 0x23A98 it reproduces V9 byte for byte [C]. At 0x23AA0 it would run 8 bytes past the end of the body.
