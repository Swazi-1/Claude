# Xiaomi Electric Scooter 5 Max firmware — from-scratch analysis

Read-only study of the owner's own files. No device was contacted, no firmware was written, no flashable file was produced, and nothing here recommends a settings change. Evidence labels: **[C] confirmed** (bytes or executed code), **[S] strong evidence**, **[L] likely**, **[U] unknown**. Where a check could not fail, it is marked as such.

Package verified: `MI5Max_Opus_FromScratch_2026-10-03.zip`, SHA-256 `3fc32c2…234327ec` (matches the value you gave). All 57 files inside match `SHA256SUMS.txt` **[C, this check can fail]**.

Reproduce everything: `pip install capstone==5.0.9 unicorn==2.1.4`, then `MI5MAX_ROOT=<unpacked folder> bash scripts/run_all.sh`. Scripts are in `scripts/`, results in `evidence/` (large listings land in `evidence/generated/`, re-created on each run). Public-source hashes are in `evidence/s00_public_sources.md`.

I formed the findings below from the firmware first; the cross-checks against `prior_work_claims_to_check/` are noted where relevant and were done last.

---

## Summary

**What I now know (high confidence).**
- The 147,456-byte image holds two separate programs. File `0x1000–0x19223` is the **battery-side processor** (an ARM Cortex‑M4F, Nations **N32L40x**-class part; runtime = file + `0x08002000`); file `0x19818–0x2381B` is the **motor controller** (**LKS32MC071CBT8**, Cortex‑M0/M3-class; runtime = file − `0x17018`). Both header checksums and the motor-controller body CRC verify. **[C]**
- RC02 differs from the stock original in **exactly 647 bytes, all inside the motor controller**; the battery-side program is **byte-for-byte identical** between stock, v7.1, RC01 and RC02. **[C, this check can fail]**
- Nothing on the **power-button / power-hold (P3.9) / wake / sleep / power-off / dashboard-handshake** path differs between stock and RC02: 68 functions on that path are byte-identical, and no RC02 change writes a RAM location that path reads under a condition that could flip it. Your one-press button behaviour is unchanged by RC02. **[C]** (full argument in `FOLLOWUP_POWER_REGEN_HEADROOM.md` §1.)
- The motor controller is **q-axis voltage-commanded with the d-axis current reference held at zero — there is no field weakening**. Once motor back-EMF uses up the available phase voltage, torque (and so current and power) must fall with rising speed. This is the firmware's own structure, not a model. **[C]**
- Regen has three independent brakes near full charge, **all byte-identical to stock**: coast regen is gated off while the controller's battery-voltage reading is **≥ 54.0 V**; the Strong depth table is capped to Medium at **BMS SOC ≥ 90 %**; and brake-lever (E‑ABS) regen is disabled at **charge ≥ 95 %**. **[C for the thresholds; S for the volt/percent units]**
- RC02 is the farm "Sport/45" lineage plus a child-speed cap: it raises the Sport **speed target** 25.3 → 45.0 km/h and the Sport **current/demand ceiling** 493 → 560 counts (~20.4 A), and it adds a cap that limits speed to 60 / 150 / 200 (×0.1 km/h) when a specific dashboard child-profile byte is present. **[C]**

**What I do not know.**
- The absolute calibration of phase current (amps per count), the motor constant, and the exact volts-per-count of the battery ADC. I give the firmware's internal conversions and one empirical amps/count from your ride, but these need a measured point to pin down. **[U/L]**
- How the physical power button is wired to either chip. The firmware sets/clears the P3.9 hold line from dashboard frames, but the button → dashboard → controller path is not in these files (the dashboard and bootloader firmware are not in the package). **[U]**
- What the dashboard *does* with the bytes it receives (the beep, icons, exact speed shown). I can only show the bytes the controller sends and receives; the dashboard firmware is not here. **[U]**
- Most of the battery-side program's function bodies: I mapped its tasks, the BQ769x2 traffic, the sleep/wake path and the serial link, but read in depth only ~5 % of its 98 KB (coverage table below).

**What to do next (one measurement).** Ride at full throttle in Sport from a **low state of charge (~30 %, ~48 V at rest)** on flat ground and read the dashboard speed at the moment watts start to fall. The two leading explanations for the 23–25 km/h fade make clearly different predictions there: the voltage-headroom explanation puts the onset near **17–20 km/h**, a fixed speed-linked limit keeps it near **23–25 km/h**. Details and a full prediction table are in the follow-up report.

---

## Task 1 — Public research and how the firmware relates to it

Sources, reliability and download hashes are listed in `evidence/s00_public_sources.md` (S1–S12). Headlines:

**Official specifications (S1, S2 — Xiaomi product pages).** Max speed 25 km/h (Walking 6 / Standard 20 / Sport 25 km/h); rated motor power **400 W**, max **1000 W** ("measured at a maximum voltage of 54.6 V and the maximum cut-off current"); **48 V** system; battery 10.2 Ah / 477 Wh (model named T2336-BD4A on the spec page, T2356-BD4A on one manual page — unresolved); standard charger output **54.6 V DC, 1.3 A**; working temperature −10…40 °C; drum brake + **E‑ABS**; TCS; **regen** ("energy recovery") settable in the app with automatic slope adjustment; slope parking (>2°, <3 km/h, brake held >3 s → P); turn-signal **buzzer**; IPX5.

**Buttons and beeps (S5 — official user manual; S3 — official 5 Max FAQ).**
- Power button: **press = on; hold 2–3 s = off; short press = head/tail light on/off; double press = cycle riding mode.** Auto-off after 10 min in standby.
- The scooter "starts working only at **≥ 5 km/h**" (push-start).
- Fault indication: wrench icon blinks red, the speedometer shows an **error code**, and the **buzzer rings 5 times in a 3-second cycle** (S3).
- Turn-signal button → winglight blinks and the **buzzer sounds at the same frequency**.
- Factory reset = brake + throttle + power held 7 s → beep; BLE reset = throttle + 5 power presses → beep; an un-activated scooter beeps and is limited to 10 km/h.
- No cruise-control button is documented for the 5 Max.

**Error codes (S4 — official 6 Pro list, same scheme).** 10 dashboard↔controller comms, 11 controller over-current, 12 current sampling, 14 throttle not at rest at power-on, 15 brake not at rest, 18 motor Hall, 21 controller↔battery comms, 28/29 MOSFET bridge, 35/36 SN/authentication, 39 battery NTC, 40 controller temperature sensor, 53 cell imbalance, 54/56 battery over-temp, 58/59 battery over-current, 61 battery MOSFET.

**Motor / controller / battery parts.** Community firmware tooling (S9, scooterteam/bw-patcher, read-only clone at commit `95a8f33`) identifies the 5 Max controller as a **Brightway LKS32MC071** image with header model id `001600010001`; the firmware string `LKS32MC071CBT8FFP` and the LKS32 manual (S8) agree. The battery-side part matches the **Nations N32L40x** memory map (S6). The pack uses a **TI BQ769x2** protection chip (confirmed from the firmware's command traffic — Task 4; TI docs S7 in the package).

**Regional limits (S11, S12).** German-market units are electronically limited to 20 km/h (eKFV: design speed ≤ 20 km/h, ≤ 500 W continuous). Your image's internal speed targets (Task 5) are far above that, consistent with a non-DE / modified unit.

**Which of these the firmware can confirm or contradict.**
- **Confirms:** 48 V class / 54.6 V charge ceiling (the controller's over-voltage error fires at raw 1075 ≈ 58.1 V and under-voltage stop at ≈ 32.6 V; the regen gate sits at 54.0 V) **[C/S]**; the three speed modes (the mode byte selects Walk/D/S targets) **[C]**; E‑ABS regen with app Low/Med/High depths **[C]**; the fault model — the controller emits exactly the public error numbers (10, 11/12, 18, 21, 24, 28/29, 40, 45) as a prioritized state byte in its status frame **[C]**, and the "5 beeps in 3 s" is a dashboard response to that byte (the controller sends the number; the beep itself is in the dashboard, not here) **[S]**; the ≥ 5 km/h push-start (stock) **[C]**; slope parking (>2°, <3 km/h, 3 s) **[C]**.
- **Cannot confirm (not in these files):** anything the dashboard decides on its own — the beep near 30 km/h, icon rendering, exact displayed speed, turn-signal timing, ambient/wing lights. These live in the dashboard firmware. **[U]**
- **Nuance / apparent contradiction:** the public "≥ 5 km/h to start" is **stock only** — v7.1 and RC02 set the push-start thresholds to zero (throttle-from-standstill; Task 5). And the community **0x55AA / 0x5AA5 Ninebot BLE framing (S10) is not what this scooter uses internally**: the controller↔dashboard link here uses `0x51–0x54` / `0x61` frames and the controller↔battery link uses `0x74`/`0x64` frames (Task 3/4). S10 describes the *app* BLE layer, a different bus.

---

## Task 2 — What RC02 changes, byte by byte

Method: `scripts/s01_layout_and_checksums.py` (region diff + checksums) and `scripts/s06_diff_context.py` (side-by-side disassembly of every changed region → `evidence/generated/s06_diff_stock_vs_rc02.md`). Owning functions from `scripts/s03_disasm_dump.py`. I reproduced the package's own `briefing/mi5max_v7_1_vs_stock_diff.csv` exactly (305 differing bytes stock↔v7.1, every row's bytes verified) before trusting it **[C, this check can fail]**.

**Counts (all can fail):** stock↔RC02 = 647 bytes in 30 regions, **all in the motor controller + header**; battery-side program identical. stock↔v7.1 = 305 bytes; v7.1↔RC02 = 358 bytes in 7 regions; RC01↔RC02 = 342 bytes in 5 regions.

Two checksum fields change mechanically with any edit and are not behaviour: the package CRC-16/XMODEM at file `0x0A` and the motor-controller size+CRC-32 at `0x19800`/`0x19804`. RC02's declared body grew 0xA004 → 0xA404 (1 KB of appended helper code). **[C]**

RC02 = **v7.1 lineage (the "farm/Sport-45" changes) + RC01's child cap + one new conditional governor**. The table groups the changes by what they are. "counts" are internal controller units; conversions are given with their own confidence.

| Region (file / runtime) | Function | Was (stock) → RC02 | What it is | Label |
|---|---|---|---|---|
| mode block `0x1DFE4–0x1E030` / `0x6fcc–0x7014` | `0x6db4` throttle→demand | Sport demand/current reference **493 → 560** counts; mode scalars rewritten; calls new helper `0xc804` | Raises the Sport current/demand ceiling to ~20.4 A; the mode table now clamps via the child-cap helper | [C] value; [S] amps |
| `0x1E120`, `0x1E130` / `0x7108`, `0x7118` | `0x70f0` kick-start | motor-disable **30 → 0**, motor-enable **50 → 0** (×0.1 km/h) | **Removes the ≥ 5 km/h push-start**: throttle works from standstill. **Affects starting up.** | [C] |
| `0x1C1BC` / `0x51a4` | `0x5144` slope park | brake-hold **30 → 90** (×100 ms) | Slope-parking engages after **9 s** instead of 3 s | [C] value; [S] unit |
| `0x1BDDE` / `0x4dc6` | `0x4db8` regen level | regen re-select min speed **60 → 50** (×0.1 km/h) | Regen depth re-selected above 5.0 km/h instead of 6.0 | [C] |
| config block `0x1FEB8`, `0x1FF00`, `0x20020–0x20064` / `0x8ea0`, `0x8ee8`, `0x9008–0x9064` | `0x8fc4` boot config + `0x8e9c` | D target 20.3 → 25.0, S target 25.3 → **45.0** km/h; regen Medium depth **146 → 160** (High = 2× → 292 → 320); demand ceiling constant raised; child-cap call added | The "Sport45" tune: higher top-speed targets and regen depths | [C] values; [S/L] units |
| thermal cap entry (in `0x8bf4` path; catalog P-items) | `0x8bf4` | derate entry **90.0 → 102.0 °C**, cap constant K scaled with the 560 demand | Thermal derate starts later and at the higher demand | [S] (prior-work cross-check; I confirmed the 560/K pairing) |
| region constants `0x1C6A0/A8`, `0x1CB04/08`, `0x1DC48/4C`, `0x1FED4/DC`, `0x200A4` / several | region-free | serial-number words `0xEC85`, `0xEEC4` **→ 0x0000** | "Region free": the controller no longer rejects on those SN words (bw-patcher `region_free`) | [C] bytes; [S] purpose |
| appended code `0x2381C–0x23A98` / `0xc804–0xca12` | new | 0xFF → four new functions | New helpers (below) | [C] |

**The three appended helpers (new flash, runtime `0xc804+`):**
- `0xc804` **child speed cap**: if a dashboard profile byte (`[base+0xA0]==0x3C`) or a stored word (`[base+0x34C]==0xC1`) is set, clamp the mode demand to **60 / 150 / 200** (×0.1 km/h) for modes 2/3/other. Called from the mode block and the Sport-target path. **[C]** This is what RC01 introduced and RC02 keeps.
- `0xc840` **child-cap state machine**: debounces the profile byte (6-count and larger timers) and persists it via the settings-save routine `0x834c`. **[C]**
- `0xc938` **optional governor gate** (RC02's only change over RC01): returns "eligible" only when a long list of RAM fields match — profile word 0, selector 3 (Sport), throttle 100, three request/target/reference fields = 450 (= the 45 km/h target), q-feedback ≤ 1461, DC feedback ≤ the dynamic ceiling, a voltage-like field in 753…1075, SOC/charge fields in range, and no brake/inhibit/recovery flag. On any mismatch it returns the original flag. Called from the supervisor `0x663c` (twice) and the current path `0x5524`. **[C]** In plain terms: under full-throttle Sport at the 45 km/h target it allows one extra governor contribution; in every other state it is a no-op. It does **not** touch the power-button, sleep or current-limit instructions.

**Differences among the modified builds.** v7.1 → RC01 added the child-cap compare-and-clamp (`0xc804`/`0xc825` grew the min-logic). RC01 → RC02 added only the `0xc938` governor gate (328 appended bytes) plus the two 4-byte call sites in `0x663c`. v7.1 and RC01 are otherwise the Sport45 tune; RC02 = RC01 + that gate. **[C]**

---

## Task 3 — The motor controller's dashboard interface

The controller talks to the dashboard on **UART0** (`0x40011000`) and to the battery on **UART1** (`0x40011100`); both are set to 8N1 at divisor 5000 (baud = UART clock / 5000, clock not independently verified) **[C for the config; S for baud]**. Decoded from `0x9470` (UART0 ISR), `0x99fc` (RX frame handler), `0x6084`/`0x7d00`/`0x98c8` (TX), with the RAM cross-reference in `evidence/generated/xref_stock_mc.json`. This matches, and in places extends, the prior `mi5max_buttons_and_comms.md`.

**Framing (controller ↔ dashboard).** A frame begins `0x51`, `0x52`, `0x53` or `0x54`. For `0x51/0x52` the length is at byte 2, the checksum is a mod-256 sum of the preceding bytes, and the leading byte + its complement must equal 0xFF. `0x53` is a short 4-byte request route requiring `byte2 = (byte0+byte1) mod 256` and `byte3 = 0xAC`. Received frames are assembled in a 150-byte buffer at RAM `0x200005F4` and copied to `0x2000068A`. **[C]**

**Received fields that matter (frame `0x51`, command byte1 = `0x10`), decoded in `0x99fc`:**

| Field | → RAM | Meaning | Label |
|---|---|---|---|
| byte3 low nibble | `0x2000014D` | **riding mode** 0..15 (dashboard double-press lands here) | [C] |
| byte3 high nibble | `0x2000015C` | secondary selector/state | [C] extraction, [U] meaning |
| byte5 **bit7** | `0x20000196` (and the P3.9 stay-on logic) | **power-hold / stay-alive** flag | [C] |
| byte5 bits | `0x2000014C`, `0x20000165`, `0x2000016D`, `0x200001D4+0x17`, `0x2000010A` | light / enable / misc booleans | [C] bits, [L] exact meaning |
| byte6 | `0x20000158` | throttle (0..100-ish; `0x5144` reads it) | [S] |
| byte7 | `0x20000110` | brake | [S] |
| byte8 (≤0x64) | `0x200001D4+0x18` | a 0..100 field | [C] range |
| byte9 bits | `0x200001D4+4,5,6,8` | flags incl. a light/throttle-related set | [L] |

**Which received field turns the motor on and off.** Not a single on/off bit — the enable is a **latch** built from several received fields plus the controller's own faults. The decisive ones **[C]**:
- **The power-hold / stay-alive flag (frame `0x51/0x10`, byte5 bit7).** A valid frame with it **set** causes P3.9 to be driven (power held on); three valid frames with it **clear** run the shutdown path — disable the motor, save settings once, clear P3.9 (functions `0x99fc`→`0xa0ac`; the GPIO3 writes are at `0x970a`/`0x9af2`/`0x9b10`). A comms-loss timeout also clears it. This is the master "keep running / shut down" control from the dashboard. (Byte-identical stock↔RC02 — follow-up §1.)
- **The mode byte `0x2000014D`** selects the demand/current ceiling and speed target each 5 ms (`0x6db4`); mode 0 or certain selector states hold the demand at zero (no drive).
- The drive loop `0x73b8` enables torque only when a long AND of "no fault" conditions holds (throttle present, brake absent, no Hall/voltage/thermal/over-current flags), and requires measured speed to clear the kick-start threshold (stock 5 km/h; **0 in RC02**).

**What the controller sends back, and which field could cause a dashboard beep near 30 km/h.** The periodic status frame is `0x61 0x30 0x0A …` (header, length 0x30, payload 0x0A), built in `0x6084` and queued by `0x98c8` into the 50-byte TX ring at `0x20000720`:

| Payload byte | Source | Meaning | Label |
|---|---|---|---|
| 2 | — | sub-type (0x0A status / 0x09 identity) | [C] |
| 3 | `0x2000015C`<<4 \| `0x2000014D` | selector + mode echo | [C] |
| 4 | bit-packed: `0x20000166`, `0x19`, `0x20000196` | flags incl. TCS/engage | [C] bits |
| 5 | bit-packed: `0x20000347` (inv.), `0x167`, `0x16C`, `0x165`, `0x169` | status/light flags | [C] bits |
| 6 | `0x200000C2 / 10` | **controller NTC temperature** (°C) | [S] |
| 7 | `0x200000C4 / 10` | a second temperature channel | [L] |
| **8** | prioritized state via `0xa6fc` switch | **fault/state code** (0x10,0x11,0x18,0x21,0x24,0x28,0x29,0x40,0x43,0x45,0x49,…) | [C] codes |
| 9–10 | `0x200001AC` | **speed** (signed, >>8 / byte) | [C] |

The field most able to make the dashboard **beep near 30 km/h is byte 9–10, the speed the controller reports**: the dashboard owns the speaker and the speed-limit chime, and the controller only tells it the speed. The internal speed is `RAM 0x1A6 = (0x36CAB / Hall-period RAM 0x8C) / 10` in tenths of km/h **[C formula; S unit]**. A dashboard that beeps at its configured limit would beep when **this reported number** crosses that limit; nothing in the controller issues the beep itself. **The controller contains no 30 km/h constant** on the status-send path — the nearest speed numbers are the mode targets (25.3/45.0 km/h) and a cruise/hold engagement limit of 26.0 km/h in an unused path. So: the beep is a dashboard reaction to the transmitted speed, not a controller event. **[S]** I cannot show the dashboard's threshold because its firmware is not in the package **[U]**.

(There is also an identity/telemetry frame `0x61 … 0x09` carrying firmware/HW strings and a `0x62`-type extended block; neither affects drive.)

---

## Task 4 — The battery-side processor (file `0x800–0x197FF`, ~69 % of the image)

This is the largest and least-documented region. It is an **ARM Cortex‑M4F** application (CPACR/FPU enabled at reset; runtime = file + `0x08002000`; reset `0x0800315D` → SysInit `0x08013CB5` → `0x0801907A` main). Its peripheral use (RTC, IWDG, PWR, EXTI, GPIOA/B, I2C2, UART1/USART1, DMA, ADC3 — `evidence/s02_peripherals_a.txt`) matches the **Nations N32L40x** memory map (S6) **[S]**. 824 functions discovered; I read the task skeleton and the battery/sleep paths in depth and ~5 % of the bodies overall (coverage table).

**Tasks (cooperative scheduler).** Main `0x801907a` runs init then an endless `0x8006cbc` dispatcher over a 6-slot table at RAM `0x2000164c`; `0x8006c84` arms a slot with a tick delay. The big periodic worker is `0x8013de8` (the **power-state / charge manager**), scheduled via `0x80149b4`→`0x8014470` on a 10-slot rota. **[C]**

**Serial link to the motor controller.** `0x80076bc` builds frames led by **`0x74`** (and the controller's UART1 ISR `0x9724` parses `0x74`/`0x64` from the battery). This is the battery→controller telemetry path; the controller writes the received signed byte to RAM `0x328` (its "remote temperature" cap input) and a voltage/SOC set. So the controller's "remote" thermal and SOC inputs **originate as battery-side telemetry over UART**, not as local controller sensors. **[C]** (Confirms prior `mi5max_buttons_and_comms.md` point 5.)

**Protection-chip communication (confirmed BQ769x2).** `scripts/s07_progA_bq769x2.py` recovered every call into the I2C helpers and named the constants from the TI manual (`evidence/s07_progA_bq769x2_calls.md`). This is **confirmed BQ769x2 traffic [C]**:
- **Direct-command reads** (`read_reg`, dev `0x08`/I2C2 `0x40005800`): Cell voltages 1–12 and 16 (`0x14`…`0x32`), **Stack / PACK / LD pin voltages** (`0x34/0x36/0x38`), **CC2 current** (`0x3A`), **Battery Status** (`0x12`), **Safety Status A/B/C** (`0x03/05/07`), **FET Status** (`0x7F`), **TS1 temperature** (`0x70`).
- **Subcommands** (`subcmd` via reg `0x3E`): `SET_CFGUPDATE`/`EXIT_CFGUPDATE`, **`DSG_PDSG_OFF` / `CHG_PCHG_OFF`** (open discharge / charge FETs), `SLEEP_ENABLE`/`SLEEP_DISABLE`, `LOAD_DETECT_ON`/`OFF`, `OTP_WRITE`, `SHUTDOWN`, `RESET`, `CB_ACTIVE_CELLS` (cell balancing), `STATIC_CFG_SIG`.
- A configuration writer (`0x800b134`) maps BQ769x2 Safety-Status bits to actions: on an over-current/short/over-temp alert it issues `DSG_PDSG_OFF` / `CHG_PCHG_OFF`. So the **BMS chip detects and latches the protections; this processor reads them and commands the FETs**. **[C]**

**Current / voltage / temperature limits and what each does.** The hard cell/pack **protection thresholds live in the BQ769x2's own data memory**, which this firmware configures but which is not a plaintext table in this image (it is written via `OTP_WRITE`/config-update with values this code computes) **[U for the exact amps/volts]**. What the processor *does* on a trip **[C]**: over-current / short-circuit / over-temperature Safety-Status bits → open the discharge and/or charge FETs (motor loses current entirely); cell-imbalance/NTC/MOS faults → error state and FET action; it also mirrors a discharge-current and temperature telemetry to the controller, which the controller uses for its *own* softer remote caps. A `0x800bb5c`/`0x800bc18` block loads a table of limit-like constants (e.g. `0x5dc`, `0x898`, `0x1194`, `0x7530`, `0x2710`) into a RAM struct at boot — **[L]** these are the BMS parameter set (currents/timers) but their units are unconfirmed without the matching data-memory addresses.

**What this processor can do to the current available to the motor (plain terms).** It can **cut the motor's current to zero** by opening the discharge FET (a BQ769x2 `DSG`/`PDSG` off), and it gates charge the same way. These are hard, protection-driven cuts (over-current, over/under-voltage, over/under-temperature, cell imbalance), not smooth throttling. Smooth current shaping is done by the *motor controller*, using current/voltage/temperature numbers this processor sends it. **[C]**

**Idle sleep and wake.** `0x8013de8` runs a small state machine (states 0..3 at RAM `0x2000002F`): it counts idle time and, on timeout with no activity, calls `0x8007cd0`/`0x800e20c` which put the **BQ769x2 to `SLEEP_ENABLE`/DEEPSLEEP** and the **N32 into STOP2/STANDBY** via the PWR block (`0x40007000`) and `WFI/WFE` (`0x800e2a8`). Wake is by **EXTI edge interrupts** configured in `0x800532c` from the pin table at `0x08019984`: **PB9 (falling), PA8 (both edges), PB7 (falling)** are the edge-triggered wake inputs; `0x8007908` latches which fired into RAM `0x20000100/0103/0104`. A charger-present / load-detect path also wakes it. **[C that these pins are the EXTI wake sources; L which physical signal each is]**.

**Connection to the physical power button.** I could **not** establish it from these files **[U]**. The battery-side processor's wake comes from EXTI pins (above) and the motor controller's stay-on comes from the dashboard's `0x51/0x10` byte5-bit7 flag over UART0 (Task 3). One of the battery-side EXTI pins (or the charger line) is the most likely physical wake, but the button→dashboard→MCU wiring and the dashboard firmware are not in the package, so I flag this as unresolved rather than guess. **Nothing on either chip's button/hold/wake/sleep path differs between stock and RC02** (follow-up §1), so whatever the real wiring is, RC02 does not change it.

**Coverage (honest estimate).**

| region | size | mapped (instructions reached) | understood in depth (estimate) |
|---|---|---|---|
| battery-side program `0x1000–0x19223` | 98,852 B | **85.6 %** | **~5 %** |
| motor controller `0x19818–0x2381B` | 40,964 B | **86.3 %** | **~23 %** |

Full per-region table with the header/padding rows: `evidence/s09_coverage.md`. "Mapped" counts only bytes inside discovered instructions (literal pools and jump tables read as unmapped, so 100 % is unreachable); "understood" is a hand judgement of the functions I actually traced and explained.

---

## Task 5 — Parameter table (RC02 vs original)

Values read from the bytes of all four images (`scripts/s06_diff_context.py`, `scripts/s03_disasm_dump.py`; cross-checked against the package's `briefing/mi5max_settings_catalog_FILTERED.csv`, which I reproduced). Units carry their own confidence; "counts" are internal. **▲ marks anything that can affect starting up, waking, switching off, lights or modes.**

| Parameter | Addr (runtime / RAM) | Original | RC02 | Unit / scale | Meaning | Label |
|---|---|---|---|---|---|---|
| ▲ Kick-start motor-enable speed | `0x7118` | 50 | **0** | ×0.1 km/h | coast speed needed before throttle works (official 5 km/h) → **throttle from standstill** | [C] val / [S] unit |
| ▲ Kick-start motor-disable speed | `0x7108` | 30 | **0** | ×0.1 km/h | speed below which the enable clears | [C]/[S] |
| ▲ Walk-mode target | `0x7004` | 62 | 62* | ×0.1 km/h | 6.2 km/h (unchanged; *child-cap may override) | [C]/[S] |
| ▲ Drive (D) speed target | `[0x20000438]` | 203 | 250 | ×0.1 km/h | 20.3 → 25.0 km/h | [C] val / [S] unit |
| ▲ Sport (S) speed target | `[0x2000043A]` | 253 | **450** | ×0.1 km/h | 25.3 → 45.0 km/h | [C] val / [S] unit |
| ▲ Sport demand / current ceiling | `[0x200000BE]` via `0x7016` | 493 | **560** | counts (≈ /27.5 A) | ~17.9 → ~20.4 A ceiling; owner's 20.35 A plateau fits 560 | [C] val / [S] amps |
| ▲ Mode select source | `[0x2000014D]` | — | — | 0..15 | riding mode from dashboard double-press | [C] |
| ▲ Child speed cap (new) | `0xc804` | absent | 60/150/200 | ×0.1 km/h | caps Walk/D/S when the child profile byte is present | [C] |
| ▲ Power-hold flag source | `0x51/0x10` byte5 bit7 → `0x20000196`/P3.9 | — | — (identical) | bit | dashboard "keep on"; clear → shutdown | [C] |
| ▲ Standby auto-off | (dashboard) | 10 min | — | min | per manual; not a controller constant | [S] |
| Regen depth Low | `[0x2000043C]` | 91 | 91 | q counts | app "Low" coast-regen depth | [C] val / [L] unit |
| Regen depth Medium | `[0x2000043E]` | 146 | 160 | q counts | "Medium"; High = 2× (292 → 320) | [C] val / [L] unit |
| Regen coast voltage gate | `0x7718` (raw 1000) | 540 | 540 | ×0.1 V | coast regen off while V ≥ **54.0 V** | [C] val / [S] V |
| Regen coast min speed | `0x7724` | 30 | 30 | ×0.1 km/h | coast regen only above 3.0 km/h | [C]/[S] |
| Regen depth-cap SOC | `0x4df6` (`[0x200008CB]`) | 90 | 90 | % | Strong → Medium at SOC ≥ 90 % | [C] val / [S] % |
| Regen level re-select min speed | `0x4dc6` | 60 | 50 | ×0.1 km/h | 6.0 → 5.0 km/h | [C]/[S] |
| E‑ABS (brake) regen off | `0x6d2a` (`[0x200000F3]`) | 95 | 95 | % | brake regen disabled at charge ≥ 95 % | [C] val / [S] % |
| E‑ABS voltage reference | `0x6d98` | 1013 | 1013 | raw (≈ 54.7 V) | scales brake regen by ref/actual V | [C]/[S] |
| Under-voltage motor stop | `0xbfe0` | 603 | 603 | raw (≈ 32.6 V) | stop + flag | [C] val / [S] V |
| Over-voltage error 24 | `0xbfe4` | 1075 | 1075 | raw (≈ 58.1 V) | over-voltage fault | [C] val / [S] V |
| Battery-V scale | `0xbfd8` | 8850 | 8850 | raw×k>>14 = 0.1 V | ADC→0.1 V | [C] val / [S] scale |
| Thermal derate entry (local NTC) | catalog P-item | 900 (90.0 °C) | **1020 (102.0 °C)** | ×0.1 °C | local cap starts later | [S] |
| Thermal NTC line | `0x1D92C` | (340800−213·x)/100 | same | ×0.1 °C | ADC→°C; failed NTC reads 30.0 °C (removes derate) | [C] formula |
| ▲ Slope-parking hold | `0x51a4` | 30 | 90 | ×100 ms | 3 s → 9 s brake-hold before P | [C] val / [S] unit |
| Slope-parking tilt / speed | `0x517c` / `0x5186` | 41 / 30 | same | ×0.1° / ×0.1 km/h | >2.0°, <3.0 km/h | [C]/[S] |
| ▲ Region SN words | `0xEC85`,`0xEEC4` refs | present | **zeroed** | — | "region free" (no SN rejection) | [C] bytes / [S] purpose |

**Unit gaps I can close vs cannot.** Speeds are ×0.1 km/h **[S]** (the firmware's own `_calc_speed = kmh×10`, and the targets land at 20.3/25.0/25.3/45.0). Voltage raw→0.1 V is firmware arithmetic **[C]** anchored by the 54.6 V charger and the 54.0 V gate **[S]**. Temperature °C is firmware arithmetic **[C]**. The one I **cannot** close from files alone is **amps per count**: the 27.5 counts/A comes only from your single ride (560 counts ↔ 20.35 A). To pin it, log app amps against a known demand at steady state. The BQ769x2 protection thresholds (hard trip amps/volts) are in the chip's data memory, not plaintext here **[U]**.

---

## Task 6 — The two things that bother you

Short version here; the full treatment, with predictions you can check and a self-audit, is in **`FOLLOWUP_POWER_REGEN_HEADROOM.md`** (that file answers your 2026-10-03 follow-up in order).

**(a) Power falls near 23–25 km/h at full throttle, even on cool days.** The firmware structure gives a clean, non-speculative reason to expect this and two things it is **not**:
- **Leading explanation [C structure / L that it's the operative one]:** the q-axis is **voltage-commanded with zero d-axis current (no field weakening)**. Torque is available only while the commanded voltage exceeds motor back-EMF; back-EMF rises with speed, so above some speed the current the motor can draw falls and power rolls off. The roll-off speed scales with the **loaded battery voltage**, so it drifts down as the pack discharges. Your 100 % run (54.15 V rest, 51.14 V at 20.35 A, first fall at a recalled 20–22 km/h) is consistent.
- **Not the current ceiling:** 560 counts ≈ 20.4 A is above your plateau only slightly; you were essentially at it, but raising the *target* to 45 km/h (RC02) did not move the fade, which is what a voltage limit predicts and a current ceiling would not.
- **Not a thermal cap and not a speed constant:** the thermal caps depend on temperature, not speed (and you see it cold); there is **no speed threshold near 23–25 km/h anywhere in the drive or regen path** (searched; confirmed with the prior work's emulator result). A fixed speed-linked limit would keep the fade at the same km/h at every charge level — that is the discriminating prediction.

Alternatives I could not rule out from files: a phase-current or modulation limit binding just below the demand ceiling, or a battery-side remote current cap arriving over UART. Each would show differently in your logs (follow-up §3).

**(b) Regen weak above ~90–95 %, with a downhill delay.** Three independent, **stock-identical** brakes, all confirmed in bytes:
1. **Coast (throttle-release) regen** is zeroed while the controller's **battery-voltage reading ≥ 54.0 V** (`0x7718`, raw 1000). A full pack sits above this, so coast regen is essentially off until voltage sags under load/lower charge. This also explains the **downhill delay**: regen current raises the terminal voltage; near the gate it can only grow until the reading hits 54.0 V, so it engages weakly then abruptly as speed/charge fall — no speed number needed.
2. **Coast regen depth** is capped Strong → Medium at **BMS SOC ≥ 90 %** (`0x4df6`).
3. **Brake-lever (E‑ABS) regen** is **disabled at charge ≥ 95 %** (`0x6d2a`, value 95).

All three are byte-identical in stock, v7.1, RC01 and RC02 — matching your statement that it behaves the same as the default firmware. The 54.0 V gate fits "doesn't work at 90–100 %" better than the SOC rule alone, because near-full voltage stays above the gate.

**The single most valuable measurement:** a full-throttle Sport run from **~30 % charge (~48 V rest)** on flat ground, reading dashboard speed at the watt-drop. It separates voltage-headroom (onset ~17–20 km/h) from a fixed speed limit (onset stays ~23–25 km/h) in one ride. Prediction tables for 54/50/48/46 V and for the regen onset voltage are in `evidence/s10_predictions.md` and the follow-up report.

---

## What I could not finish / verify

- **Absolute calibration** (amps/count, motor constant, exact volts/count) — needs a measured point; I give the internal conversions and one empirical amps/count only.
- **BQ769x2 hard trip thresholds** in amps/volts — they live in the chip's data memory, configured via `OTP_WRITE`, not as a plaintext table in this image.
- **The physical power-button wiring** and the dashboard's own behaviour (the beep, icons, displayed speed) — the dashboard and bootloader firmware are not in the package.
- **Deep coverage of the battery-side program** — ~5 % of its bodies read; the task skeleton, BMS traffic, sleep/wake and serial link are mapped, the rest is not.
- **Scheduler tick in real milliseconds** — I use the prior work's nominal ~5.12 ms/5-tick slot; I did not re-derive the PWM clock, so all "seconds" from tick counts are nominal.
