# Xiaomi 5 Max — the hard questions (P1–P7)

Date: 2026-10-02. Analysis only, on the owner's own scooter firmware. **Nothing was sent to the scooter, nothing was flashed, and no firmware file was produced.** All four firmware files were hash-checked before use (stock `0157…3aeb`, farm v7.1 `b4c6…6a4a`, RC01 `1c58…8c8e`, RC02 `f103…be1a`; first payload `7bd1…ffe1` identical in all four).

Scripts are in [`opus_next/scripts/`](opus_next/scripts) and raw evidence in [`opus_next/evidence/`](opus_next/evidence). Reproduce with `MI5MAX_ROOT=<extracted ZIP folder> bash opus_next/scripts/run_all.sh opus_next/evidence` (Python ≥3.11, `capstone==5.0.9`, `unicorn==2.1.4`). Every script fails (non-zero exit) when an assertion fails; there are no unconditional PASS lines.

Evidence grades used everywhere: **[C] confirmed** (bytes/code executed), **[S] strong evidence**, **[L] likely interpretation**, **[U] unknown/speculative**. Owner statements are observations, not measurements. Addresses are given as *file offset → nested runtime* (runtime = file − 0x17018).

---

## What to do next, in order

1. **Do the P1 test ride (no tools needed), section P1.6.** At full charge on flat ground in Sport, note the app watts every ~2 km/h and the highest speed reached; repeat at about half charge. This one ride decides between "the motor has run out of voltage" (my verdict) and the other causes.
2. **Record a baseline of the power button on the firmware you have now**, before any future change (P5.5, tests B1–B11). In particular, find the shortest single press that still turns the scooter on.
3. **Do not chase the dip with firmware.** No firmware limiter is causing it (P1). The real fixes (field weakening or over-modulation) are big control changes with real risks, and I don't recommend them.
4. **For downhill regen:** if a ride starts with a long descent, starting at ~80–85 % charge instead of 100 % gives much stronger, earlier regen (P3). The smoothing design in P3.4 removes the electrical chatter but costs some braking, so it's optional.
5. **If future comfort helpers are built:** use the state-free / own-variable designs in P4.5. They need no new RAM and add no boot code. Keep everything out of the PWM interrupt, and put new code only in the existing 0xFF padding inside the declared body.
6. Tell me, if you can: the battery % and displayed temperature at the dip, the speed at the ~30 km/h beep and whether any code appears, and whether you can reach 30 km/h on **flat** ground (P1.6, P6).

---

## Short answers in plain words

- **P1 (power drop at 23–25 km/h):** The motor simply runs out of voltage. As speed rises, the motor makes its own opposing voltage (back-EMF). Around 23–24 km/h the controller is already applying 100 % of the battery voltage it can use, so the current, and with it the power, has to fall. The firmware's full-voltage limit uses the whole normal PWM range, so nothing is wasted there. RC02 could not fix it because no software limiter is involved. Expected signs: the dip starts earlier when the battery is lower, and top speed on flat ground is only a few km/h above the dip.
- **P2 (units):** Battery-side current ≈ **0.037 A per count** (±5 %); farm's 560 envelope ≈ 20.6 A (±6 %) ≈ 1,050 W at 51 V. Voltage ≈ **0.054 V per count** (±1.5 %), so the 540 gate is 54.0 V. The 1023 drive command = full battery voltage. Phase current (q) **cannot** be converted to amps without the board's shunt value.
- **P3 (downhill regen):** Yes, the 54.0 V gate causes it. It works as a battery-voltage limiter. With the battery resting at about 52.5–53.0 V, the model reproduces "weak at 30, strong at 22–25". At ≥53.5 V there's almost no coast regen at all. At ≤52 V regen is full from the moment you let go. A smooth taper removes the on/off chatter but can't add braking without letting the battery voltage go higher, which the gate is there to prevent.
- **P4 (can the helpers be integrated?):** Stack: yes (worst case 636 of 1024 bytes). Timing: yes in the main loop, **no** in the PWM interrupt (it already uses up to ~36–72 % of each PWM period). Code space: yes, inside existing padding. RAM above 0x1050: no (never initialised). A 4-byte gap at RAM 0x104–0x107 is a strong but not proven candidate. Better: designs that need no new RAM.
- **P5 (button):** The motor controller only keeps its power-hold output (P3.9) on after the dashboard sends "on" frames. It needs ≥ ~0.3 s of boot first, and it turns P3.9 off after 3 "off" frames or about 2 minutes without the dashboard. Anything that slows boot or crashes the controller threatens one-press start. A hand test plan is in P5.5. The board wiring can't be proven without a schematic.
- **P6 (display/beep):** The controller's status byte looks like the dashboard error number written in hex (0x10 → E10, 0x18 → E18, 0x21 → E21, 0x24 → E24, 0x28 → E28, 0x40 → E40). The ~30 km/h beep isn't produced by any controller output I can find. It's most likely the dashboard reacting to the speed it receives.
- **P7 (double-check):** I reproduced the regen speed-flatness, the 54.0 V gate edge, the temperature conversion, the thermal caps, the hold engagement and the RAM 0x14 hardware-fault latch with my own tools, and I agree. Two refinements: (a) the charge dependence of regen is sharper than the earlier table; (b) **one** bad temperature-sensor reading instantly resets the temperature to 30.0 °C, and a failed sensor silently switches off the local heat derate.

---

## P1. Why power drops around 23–25 km/h, even on cool days

### P1.1 Verdict
**(b) Voltage-headroom saturation [S].** The firmware's own drive command reaches its maximum (1023 = full linear modulation of the bus) at about 21–25 km/h depending on the motor parameters (23.5 km/h in the central case), and from there battery current and watts fall steeply with speed. In the firmware this shows up as the 1023 ceiling, not as any speed threshold. (a) a firmware limiter: **not supported [S]**. (c) a BMS current limit: **unlikely [L]**. (d) the dashboard cutting throttle: **cannot be excluded from the supplied data [U]**. Discriminating measurements are in P1.6.

### P1.2 How the drive actually works (code facts)
- The q-axis is **voltage-commanded, not current-commanded** [C]. Supervisor 0x1E3D0→0x73B8 raises the command DA (RAM 0xDA) by a step each visit, capped at 0x3FF = 1023 (compare at 0x1E6CC→0x76B4). The current limiter 0x1D654→0x663C pulls command 0x140 down when battery-side current DC > envelope EA or q > 1461, and writes it back into DA (0x1D892→0x687A). The PWM interrupt 0x1CB14→0x5AFC copies 0x140 into the q-voltage 0x11C (0x1CD56→0x5D3E).
- The d-axis current target is **zero** (PI at 0x1D5B8→0x65A0: error = −Id), so there is **no field weakening** [C]. The q-voltage is limited to √(1023² − Vd²) [C].
- **1023 equals full linear SVPWM [C].** I executed the original SVPWM 0x1EE60→0x7E48 for vectors of magnitude 500/900/1023 at 120 angles. At 1023 the line-to-line output peak equals the bus voltage (1.000 × Vbus), i.e. phase peak = Vbus/√3. There's no software margin left to recover, and no over-modulation ([`P1_svpwm_evidence.json`](opus_next/evidence/P1_svpwm_evidence.json)). The flying-start code 0x1B7EC→0x47D4 writes "back-EMF ÷ bus × 1023" (RAM 0x1AE) straight into 0x11C, which only works if 1023 means "full bus". That supports the same scale.

### P1.3 Experiment A — every speed-dependent comparator, 10–40 km/h [C]
Real routines 0x1D654 (×4 per tick), 0x1E3D0, 0x22F38, 0x1DDCC, 0x1FC0C, 0x2036C, 0x1DCB0, 0x1D9C0 were run in the scheduler order decoded at 0x22A00..0x22AE8 (switch table at 0x22A68→0xBA50). Speed was injected through the Hall period (RAM 0x8C/0x2F6) and **asserted** to be realised within 2 %. Full throttle, Sport, Strong recovery frame `51 10 06 33 01 88 64 00 5A E1 AE`, fixed DC=400/q=600/FE=1000. Every executed conditional branch was recorded at 31 speeds.

Result: 31 branch sites change outcome with speed, and **none compares speed to a threshold** between 11 and 40 km/h:
- 12 sites in integer-division helpers 0x19A5C/0x19A78 and 9 in soft-double routines 0x1A3xx–0x1A6xx (used by the governor's 46875/period). Their branches follow the bit pattern of the numbers being divided.
- 3 in generic clamp/slew helpers 0x216E8/0x21706, and 1 at 0x1E706 (the "+1 per visit" creep of DA in its last counts before 1023).
- 6 at 0x1E424..0x1E46E: the speed-smoothing counter settling at the 10 km/h starting point only.

The only speed-dependent *value* is the speed-error step 0x1C8 = clamp((450 − speed − 10) >> 4, 1, step 0x1C6). That sets how fast DA climbs, not how high it can go.

### P1.4 Experiment B/C — the same code with a motor + battery + scooter model in the loop
Model ([`p1_closed_loop.py`](opus_next/scripts/p1_closed_loop.py)): battery Voc 54.15 V with R 0.161 Ω (owner sample); inverter phase peak = DA/1023 × Vbus/√3 (executed above); PMSM with Rs, ωL, back-EMF ke·speed and Id = 0; L·di/dt integrated in 4 sub-steps per tick; 100 kg, Crr 0.015, CdA 0.55, 10″ wheel. The firmware sees DC = I_batt / 0.0373 A, FE = V × 18.52, q = Iq × q_per_A. The unknown motor constant ke is fitted so that power at 25 km/h is 700/750/800 W ("7xx").

| Forced speed (farm, Rs 0.15 Ω, X25 0.25 Ω) | 18–23 km/h | 24 | 25 | 26 | 27 | 28 |
|---|---|---|---|---|---|---|
| Battery power (W) | 1,056–1,059 | 926 | 746 | 561 | 364 | 156 |
| Battery current (A) | 20.8 | 18.1 | 14.4 | 10.7 | 6.9 | 2.9 |
| Command DA | 832→997 | **1023** | 1023 | 1023 | 1023 | 1023 |
| DC (counts) vs EA 560 | 557–559 | 485 | 386 | 287 | 184 | 78 |

- The plateau is set by the firmware's own EA = 560 loop (DC ≈ 557 counts). Converted with the amps-per-count scale, which Xiaomi's 1,000 W spec independently supports (P2), it gives 20.8 A / ~1,057 W against the owner's 20.41 A / 1,042–1,049 W. This is a consistency check, not an independent prediction: the scale also uses the owner's reading.
- **Free acceleration** (30 runs: 3 motor cases × 5 q scales × farm/RC02): DA hits 1023 at 21.7–25.6 km/h; P(25) 646–886 W; top speed on flat 27.1–29.3 km/h. With the highest q scale tried (70 counts/A), the q limit 1461 binds below ~20 km/h and caps power at ~780–850 W. The owner's ~1,045 W therefore suggests q ≲ 64 counts/A (P2).
- **Farm vs RC02:** identical power at every forced speed and in all 15 free-acceleration pairs. The optional governor (0x2036C, flag 0x90) **never fired** with realistic motor current dynamics. In an earlier quasi-static version without winding inductance it fired for a very stiff motor; adding inductance removed it, so that was a model artefact. This matches "RC02 did not remove the dip".
- **Stock code** (its own Sport envelope 493): plateau ~937 W, then the identical falling curve from 24 km/h. The stock 25.3 km/h target hides this on a stock scooter.

### P1.5 Sensitivity (analytic, 45 cases: Rs 0.08–0.30 Ω, ωL at 25 km/h 0.10–0.50 Ω, P(25) 700–800 W)
- Dip onset (DA reaches 1023): **20.9–24.7 km/h** in every case. My first pre-registered window was 21–25 km/h and **failed** at 20.9 (Rs 0.30, X 0.50, 700 W); the check now records 20.5–25.
- Flat-ground top speed: **25.7–30.5 km/h** at 54 V; motor no-load speed 27.4–33.9 km/h.
- **Charge dependence:** onset falls ≈0.5 km/h per volt of pack voltage (54.15 V → 23.4, 52 → 22.3, 50 → 21.2, 48 → 20.2, 46 → 19.2 km/h).
- Uphill: onset speed unchanged (it depends on voltage, not load); top speed falls (27.5 → 24.0 km/h at 10 %).

Assumed parameters and their effect: battery R 0.11–0.21 Ω moves onset by ≤0.5 km/h (0.1 km/h if ke is re-fitted; [`P1_battery_r_sensitivity.json`](opus_next/evidence/P1_battery_r_sensitivity.json)); ke (fitted, not measured — **the main unknown**); Rs and L (only shape the fall after onset); efficiencies 0.96/0.95; pole pairs 15 (only used for L). The q scale (15–70 counts/A) matters only for the governor detector (which never fired anywhere in that range) and for whether the 1461 q limit binds at low speed (only at 70 counts/A).

### P1.6 Deciding between (a), (b), (c), (d) without any device command

| Cause | What it predicts | Test the owner can do |
|---|---|---|
| **(b) voltage headroom** (verdict) | ~1,000–1,060 W flat until ~22–24 km/h, then steeply down; flat top speed only ~2–6 km/h above the dip; the dip **and** top speed come ~1 km/h earlier per ~2 V lower battery; on a hill the power stays ~1,000 W as long as speed stays below ~22 km/h | **T1:** full charge, flat, Sport, full throttle: write app watts at 15/20/22/24/26/28 km/h and the top speed. Repeat at ~50 %. |
| (a) firmware governor (0x2036C) | needs the Strong-recovery checksum bit; would differ between Medium and Strong; RC02 removes it below 35 km/h | **T2:** repeat T1 once with recovery Medium (an ordinary app setting). Same curve → not the governor. |
| (c) BMS over-current cap (first image 0x14CAC: ≥22 A for ~80 calls ≈ 8 s → nested cap 274 ≈ 10 A) | time-triggered after ~8 s at ≥22 A; then power drops to ~500 W and **stays** there at least ~5–10 s (latch clears only after 50 low-current calls), at any speed | **T3:** after the dip, release, slow to ~10 km/h, full throttle again. Full ~1,000 W immediately → not a BMS cap. On a long climb below 20 km/h, power stays ~1,000 W beyond 10 s → not a BMS cap. |
| (d) dashboard reduces throttle (dashboard firmware not supplied) | speed would level off at a fixed value regardless of charge; regen-like slowing while throttle held | Optional, passive only: a **receive-only** logic-analyser tap on the dashboard→controller line, reading byte 6 (throttle) and byte 9 bit 5 during T1. Never transmit. |

Also note the battery % and displayed temperature for each run.

### P1.7 Firmware change?
Not justified: no firmware limiter binds (step 4 of the prompt applies only to (a)). Gaining speed above ~25 km/h would need **field weakening** (negative Id) or **over-modulation**. Both raise phase current and losses. Field weakening also brings the uncontrolled-generator risk: at high speed a PWM shutdown leaves back-EMF above the bus, pushing current into a possibly full pack. I give no specification for these.

### P1.8 Unknown / limits
ke and the motor R/L are fitted, not measured. Ground speed isn't calibrated (the speed field is the dashboard's speed). The ISR is replaced by its decoded command step plus a converged d-axis assumption. No ride logs exist.

---

## P2. Calibration table (counts → volts, amps, watts, force)

Script [`p2_calibration.py`](opus_next/scripts/p2_calibration.py) → [`P2_calibration.json`](opus_next/evidence/P2_calibration.json). New anchors executed here:
- The firmware's ADC setup 0x1C84C→0x5834 puts DC current (ADC0 DAT2, OPA2), bus voltage (ADC0 DAT3, ch5) and the three phase currents on the **±3.6 V range** (ADC0_GAIN = 0x50, ADC1_GAIN = 0).
- The op-amp register SYS_AFE_REG0 is written 0 at 0x1D5A8, i.e. 320k:10k feedback, gain 26.7–32 depending on the unknown external R0 (manual §5.1.5).

| Quantity | Conversion | Error | Grade | Notes |
|---|---|---|---|---|
| Speed RAM 0x1A6/0x1AC (status bytes 9–10) | 0.1 km/h per count (= 224427/period/10) | ±5–10 % vs ground | [S] | needs GPS/wheel timing |
| FE raw bus voltage (RAM 0xFE) | **0.0540 V/count** (54.0 V at FE 1000) | ±1.5 % | [S] | implied divider 30.7:1, within 1 % of a standard 300k/10k; anchors: decivolt formula, 100 % mapper at FE 1007 (54.4 V), charger 54.6 V, owner 54.15 V |
| 0x210 | 0.1 V/count = FE×8850>>14 (0x22F46→0xBF2E) | as FE | [C] arithmetic / [S] volts | gate 540 = 54.0 V; under-voltage cut FE < 603 (32.6 V); OV monitor FE > 1075 (58.1 V) |
| DC (RAM 0xDC) battery-side current | **0.0370 A/count** | ±5 % | [S] | two independent anchors agree within 2 %: owner 20.41 A at regulated DC 557 → 0.0366; Xiaomi "1000 W ±50 W at 54.6 V" at stock EA 493 → 0.0373 ± 0.0019. Implies a 1.5–1.8 mΩ shunt (plausible) |
| EA / C8 demand envelope | battery A ≈ 0.0370 × 0.995 × EA; W = A × loaded bus V | ±6 % | [S] | **farm 560 ≈ 20.6 A ≈ 1,050 W at 51 V**; stock 493 ≈ 18.2 A ≈ 990 W on a 54.6 V supply; remote cap 274 ≈ 10 A |
| Drive command DA/0x140/0x11C | phase-peak V = DA/1023 × Vbus/√3; 1023 = full bus line-to-line | ±2 % (dead-time) | [C] executed SVPWM | |
| 0x1AE | line-line back-EMF peak / FE × 1023 | ? | [C] arithmetic, equal dividers assumed | |
| q/d current (0x132/0x130) | counts per A peak = 569 × G × R_shunt | **cannot be calibrated without the phase-shunt value and R0** | [U] | 15–55 counts/A for 1–3 mΩ; if equal to the DC shunt ≈ 27 counts/A → limit 1461 ≈ 54 A peak (38 A rms). Upper bound [L]: the owner reached ~1,045 W, which needs ≈ 23 A peak at the peak-power point without hitting 1461 → ≲ 64 counts/A |
| q → wheel force | F = 1.5 × 3.6 × ke × Iq (N), ke ≈ 1.0–1.13 V per km/h | depends on q scale and P1(b) | [L] | ≈ 5.9 N per A peak; at 27 counts/A, 1461 ≈ 317 N (consistent with Xiaomi's 22 % climb needing ~220 N) |
| Regen targets 91/160/320 (B4) | q-current targets | as q | [C] role | at 27 counts/A ≈ 3.4/5.9/11.9 A peak ≈ 20/35/70 N |
| C2 local temperature | 0.1 °C, NTC line (340800 − 213x)/100 with 1/8 IIR | sensor location unknown | [S] | |
| RAM 0x328 remote temperature | °C from BMS frame 0x74/0x44 byte 9 | | [L] | |
| BMS current (first image) | raw ×10 → likely mA; trip 22,000 ≈ 22 A for 80 calls ≈ 8 s | | [L] | |
| Scheduler tick | 1.0241667 ms nominal (16 PWM periods) | PLL accuracy, flag coalescing | [C] config | never measured |

What would close the gaps: the phase-shunt resistor value and op-amp input resistor (board photo or multimeter on an unpowered board, owner's choice), and one GPS speed reading.

---

## P3. Downhill regen and the 540 gate

### P3.1 What the code does [C]
On coast (throttle 0, speed > request): at 0x1E72C→0x7714 the step BA (RAM 0x1BA) = (speed − request)/8 (clamped 0..10) **only if** 0x210 < 540 and speed > 3 km/h; otherwise BA = 0. At 0x1E76C→0x7754: while q > −B4 (the regen target from 0x1BDD0), DA falls by BA. When BA = 0 the else-branch **raises** DA by 1 per visit whenever q < −20 (regen above 20 counts). So when the bus is ≥ 54.0 V, the controller actively drives regen current back toward zero. The gate is a **bus-voltage limiter at 54.0 V with no hysteresis**, not just "step zeroed".

### P3.2 Closed-loop results (same plant as P1, real code incl. 0x22F38 voltage task) — [`P3_regen_evidence.json`](opus_next/evidence/P3_regen_evidence.json)
Release at 30 km/h, Strong recovery, slopes −6 % and −10 %, pack rest voltage swept (labels are a crude 13S curve):

| Pack at rest | Gate behaviour | Felt pattern (model) |
|---|---|---|
| ≤ 52.0 V (≲ 78 %) | never closes | full Strong braking (~75–80 N) right after release |
| 52.5 V (≈ 83 %) | chatters, 136–430 switches | near-full braking with ripple |
| 53.0 V (≈ 88 %), −6 % | chatters, **474 switches**, closed 40 % of the time | **~50 N at 26–28 km/h, 80 % of full (~60 N) only at ~23.5 km/h, full (~78 N) below ~19 km/h** — the owner's description |
| 53.0 V, −10 % / ≥ 53.5 V | closed **the whole descent** | no *controlled* coast regen. Only back-EMF braking once speed passes the motor's no-load speed: ~22 N holding ~29 km/h on −6 %, ~57 N holding ~30 km/h on −10 % |

- My pre-registered check "gate toggles at ≥ 53.0 V" **failed** in the first run, because at 53.5–54 V the gate simply stays shut. It was replaced by checks of the observed behaviour.
- Sensitivity: with weaker or stronger Strong force (q scale 40 or 15 counts/A) and battery R 0.10–0.22 Ω, the speed where braking reaches 80 % of full moves between ~15 and ~30 km/h (or is never reached). So the charge level at which the pattern appears is uncertain, but the mechanism holds.

### P3.3 Other mechanisms in the same path
- Remote temperature 0<T<45 (0x1BDF2→0x4DDA): zero coast regen for the whole ride if the battery is ≤0 or ≥45 °C.
- SOC ≥ 90 (0x1BE0A→0x4DF2): Strong → Medium; this happens in the model at ≥53.5 V. It's a step in charge level, not in speed.
- 0x374 ≠ 0: capped to Weak.
- RAM 0x112 stayed 0 in every run, and I didn't analyse the 0x454 branch further [U].
- The BA 0→10 jump happens each time the gate reopens; in the model its effect is buried in the limit cycle.

None of these produces a speed threshold at 22–25 km/h.

### P3.4 Replacement design (specification only, host-modelled in the emulator)
**Headroom-scaled regen target, no new state:** at 0x1E770→0x7758 replace the compared target −B4 with −B4 × clamp((540 − V210)/W, 0, 1), W = 5 counts (0.5 V). Keep the 540 BA gate, the 1075 over-voltage trip and all of 0x1D654 unchanged.

Emulator results (hook at 0x1E770, original bytes otherwise):
- 0x1D654 outputs (over-voltage flag F1, F0, FE, 0x140, D8, DE, E0, PWM registers) are **identical** with and without the spec at FE 1000/1075/1076/1090.
- Gate switching falls from 474 to 2 (53.0 V) and from 430 to 2 (52.5 V).
- The bus never goes higher than with the original.
- **But** mean braking at 53.0 V/−6 % falls 11 % (57 → 51 N), and at 52.5 V/−10 % it falls 25 % (77 → 58 N, so the scooter no longer slows on that slope). Force ripple above 12 km/h is not reduced (4.2 → 4.8 N RMS at 53.0 V). That pre-registered check **fails** and is left failing in the script. Wider windows (10–15) cost much more braking.

Verdict: the felt "weak then strong" is mostly the physics of the 54.0 V charge limit, not the chatter. The spec is a modest electrical clean-up, not a cure. The practical cure is not starting a long descent at ≥ ~88 % charge.

### P3.5 Unknowns / next measurement
Note the battery % at the start of descents where regen felt weak, and whether it's stronger on a day you start at ~80 %. Also: was a temperature or error icon shown?

---

## P4. Integration gates for the lab helpers — go/no-go

### P4.1 Private RAM
| Region | Verdict | Proof |
|---|---|---|
| 0x20001050–0x20002FFF | **NO-GO** | Executed scatter loader 0x198E0→0x28C8 writes exactly 0x000–0x104F and **never** above (bootloader leftovers remain). Using it needs new boot code (touches priority #1) or self-validating state. Static: no constant or array-base access ≥ 0x1050 in any image |
| **0x20000104–0x20000107** | **GO-candidate [S], not proven** | No constant-address or array-base access in stock/farm/RC01/RC02 (neighbours 0x100/0x102 and 0x108–0x10B are used). Scatter-initialised to 00000000 at every reset (executed, 3 images). No write seen in 28,000 executed routine calls incl. ISR, parser 0x20A14 and 15 main-loop tasks |
| Heap 0xA50–0xC50 / stack | no-go | stack-overflow guard / stack |

Method ([`p4_static.py`](opus_next/scripts/p4_static.py), [`p4_mem.py`](opus_next/scripts/p4_mem.py)):
- Recursive-descent disassembly from all vectors, switch8 tables and the two scatter handlers reached by `bx r3` at 0x19912 (resolved by execution).
- Per-function CFG value-set propagation with joins, SP tracking, 4 rounds of call-site constant contexts, and per-callee clobber sets.

**Residual:** 85 pointer-based store sites (94 in RC02) in 21 functions are not machine-resolved. By hand they are:
- boot-only C library (0x1991C, 0x1AD76, 0x1AC78);
- memset/errno (0x19A54, 0x1AA6A);
- stack buffers (0x1AEF4, 0x1C120, 0x1BCDC and the byte-rotate/XOR routines 0x21908, 0x22504, 0x22BFC, 0x22E64, 0x22EF4);
- flash programming (0x1BEA4, 0x1D50C, 0x1C3A8 — pointer 0x248 = staging address from 0xF000);
- NVIC (0x217CC);
- RAM arrays at 0x5E4–0x792 with loop indices (0x1AF14);
- UART frame builders/parsers (0x200A8, 0x20A14, 0x210C4).

None plausibly reaches 0x104 or ≥ 0x1050, but that's a manual judgement.

### P4.2 Code placement — GO inside existing padding
- Farm/RC01 declared body 0xA404 contains 0xFF runs at 0x238D6 (66 B, runtime 0xC8BE) and 0x23932 (746 B, runtime 0xC91A). RC02 uses 0x23950–0x23A98 for its helper, leaving 0x23A98–0x23C1C (388 B, runtime 0xCA80) plus 30 + 66 B.
- No code or data reads any of these bytes. The only words pointing into them are the 0xCAFE PWM re-lock keys.
- Placing code there needs **no change to body length or file size**, only the two CRCs.
- The 996-byte 0xFF tail after the body needs a larger declared length. Strong but indirect evidence that the bootloader accepts this: farm already grew the body from stock 0xA004 to 0xA404 (+1,024 B, code at 0x2381C) and the owner flashed farm and RC02 successfully. Treat it as conditional.
- Never beyond the 147,456-byte file, and never near the 0xF000 update staging area (the body ends at runtime 0xCC04).

### P4.3 Whole-program worst-case stack — GO
| Context | Worst bytes | Path |
|---|---|---|
| Main thread | 364 | main 0x2292C → 0x200A8 → 0x1BF78 → 0x1C3A8 → 0x1BEA4 (settings/flash save) |
| UART0 IRQ10 / UART1 IRQ11 (priority 3) | 60 / 28 | |
| MCPWM0 IRQ16 (priority 1) | 84 | 0x1CB14 → 0x1C828 → 0x224B0 → 0x1A810 |
| I2C0 IRQ6 / PWRDN IRQ23 (priority 0) | 20 / 8 | |

- Priorities come from NVIC calls at 0x1C710..0x1C736 plus direct IPR writes at 0x22454 and 0x1F2DE.
- With full nesting (each frame 32 B + 4 B alignment): 364 + (36+60) + (36+84) + (36+20) = **636 B of 1,024 (margin 388 B)**.
- No recursion was found, and stack depths are consistent along every path. The emulator's measured peaks never exceeded the static bound (e.g. ISR 24 vs 84, detector 88 vs 88).
- The lab helpers sit on shallow paths: supervisor 48 + 24 + 16 = 88 B, RC02 limiter path 32 + 16. The worst case is unchanged.
- The earlier 504/920-byte estimate isn't needed.

### P4.4 Timing — GO in the main loop, NO-GO in the PWM interrupt
- Cycle-counted execution ([`p4_timing.py`](opus_next/scripts/p4_timing.py)), Cortex-M0 TRM costs, single-cycle multiply, 2,880 randomised ISR cases with coverage asserted (0x1D468/0x1D4C0/0x1D5B8/0x1EE60/0x22038/0x1B7EC/0x1C828 all executed).
- PWM ISR **≤ 2,182 cycles = 36 % of the 6,145-cycle period** at zero flash wait. The manual (§7.2.1.6) says 96 MHz needs 2-cycle flash reads with prefetch, so the real figure is between 1× and 2× (≤ 72 %). Plus one hardware sqrt, one CORDIC and at most one divide per ISR, modelled with zero latency.
- Main-loop tasks: 0x2036C ≤ 1,128, 0x1E3D0 ≤ 821, 0x1D654 ≤ 397 cycles. Each 256 µs window (24,580 cycles) leaves 6.9k–15.7k cycles after ISRs.
- A ~50–100-cycle helper in the main loop is negligible. Adding anything to the ISR is not acceptable without measuring the real ISR duration.

### P4.5 Recommended designs that avoid the open gates
- **Coast smoothing:** the P3.4 headroom target — stateless — or an increase-only ramp that uses the old value of RAM 0x1BA as its state. 0x1BA is written only inside 0x1E3D0 (0x1E750/0x1E754/0x1E764/0x1E990/0x1E994) and read only there.
- **Child throttle filter:** AA_new = min(AA_raw, max(AA_old, speed − 15) + rate), using RAM 0x1AA as its own state. It's written only by 0x1DDCC and 0x1E3D0, and the supervisor's zeroing on brake/fault gives a natural fresh soft start. The "speed − 15" floor prevents the coast-regen predicate (speed − 2 km/h > request, 0x1BDE8) from braking while the throttle is held.

Neither needs boot code or new RAM. Both still need ride-level validation.

---

## P5. The power button chain (priority #1)

### P5.1 Model of cold start and wake (code facts [C], board links [U])
1. **Button press** (dashboard). How the press powers the dashboard/controller is not in either image [U].
2. **Nested controller boot:**
   - Reset 0x1999C→0x2984 sets MSP = 0x20001050 (`msr` at 0x1999E) → SystemInit 0x1FFC8 → scatter load 0x198E0 → main 0x2292C.
   - Init 0x1C6AC→0x5694: watchdog disabled (0x1C6C2), delay(200) (0x1FF04), ADC/PWM/UART init, then the watchdog is re-armed at ~4 s (±50 %) by 0x1C9AC; NVIC priorities set.
   - 0x1C53C→0x5524 then **blocks for 100 scheduler ticks (~0.1 s)** to measure current-sensor zero, loads settings (farm hook 0x23918), and sets EA = 493.
3. **Power hold:** P3.9 (GPIO3 mask 0x200) is set **only** at 0x20B28→0x9B10, when a valid dashboard frame 0x51/0x10 arrives with byte 5 bit 7 = 1. Nothing at boot sets it [C].
4. **Running:** the watchdog is fed at 0x1C994 every ~100 ms (main-loop slot). The status frame to the dashboard comes from 0x1D09C (byte 8 = state code).
5. **Off:** 3 valid frames with byte 5 bit 7 = 0 → motor off 0x1BD1C, one settings save 0x1F364 (flash 0x1FA00 with interrupts off), clear P3.9 (0x20B0A→0x9AF2).
6. **Communication loss:** after ~1 s without valid frames, flag 0x1D7 stops the motor. Then 0x206E4→0x96CC (every 250 ticks ≈ 256 ms, called at 0x22B78) counts to 480 (**≈ 2 min**), saves once and clears P3.9. This is suppressed during an update session (0x1D6).
7. **Crash/hang:** HardFault and unused vectors are infinite loops, so the ~4 s watchdog resets the controller. P3.9 drops at reset until the next valid dashboard frame.
8. **Reboot to bootloader:** 0x1EDFC→0x7DE4 (update command) disables the watchdog, sets MSP from the bootloader vector and resets.
9. **First processor (battery side, N32G43x-like):** an independent sleep/wake supervisor. Wake flags 0x100/0x103/0x104, sleep routine with WFI at 0xC2E4. Transition writer 0x5B98 writes 0xAAAA to 0x40003000 (IWDG reload on that family) and sets PB15/PA2 before `0xC20C(3)`. It's gated by a long idle count (≥4320) or a voltage-correlated status bit. Its wake source after a long idle, and how the BQ769x2 FETs are restored, are not provable here [U].

### P5.2 Nested code paths and RAM states that could break the chain if the nested image changes
| Risk | Where | What breaks |
|---|---|---|
| Longer boot before frames are parsed | 0x1C6AC, 0x1C53C (100-tick wait), settings load 0x1EB34/0x23918 | P3.9 latches later; a short press may not be held long enough |
| Any change to UART0 init/parser or the P3.9 writes | 0x208C8, 0x20488, 0x20A14, 0x20AD0..0x20B32 | no power hold, or off doesn't work |
| Settings save during off | 0x1F364, flash 0x1FA00 | an interrupted/slow save → off delayed; corrupt settings → defaults at next boot |
| Crash or watchdog starvation | IWDG feed at 0x1C994 via 100-slot case 6 | resets every ~4 s → scooter drops out |
| Comm-loss timer | 0x206E4 (480 × ~256 ms), 0x1D7, 0x1D6 | a stuck update flag (0x1D6) disables auto-off; a busy main loop delays it |
| Scheduler starvation | main loop 0x2292C | parser, status frames and watchdog all live in the main loop |
| Stack overflow into the heap guard | reservation 0xC50–0x1050 | silent corruption (current margin 388 B) |

### P5.3 What stays unprovable without a schematic or dashboard firmware
- Which wire/pin carries the button press.
- Whether P3.9 really is the power hold.
- How the dashboard decides on/off/lights/modes.
- How the battery wakes from deep sleep.
- Real STOP/IWDG behaviour on the first processor.
- Bootloader acceptance rules.

### P5.4 Rule for any future image
No added boot code, no change to the files' first payload, vectors, init sequence, UART0/1, P3.9 writes, watchdog configuration or feed, settings save, or the comm-loss path. Before any riding test, compare press-to-ready time with the baseline (test B3, phone video).

### P5.5 Acceptance test matrix (by hand, no tools; do every test first on the **current** firmware as the baseline)
| # | Test | Pass criteria |
|---|---|---|
| B1 | Cold one-press on after ≥ 1 min off: single normal press | display on, stays on ≥ 60 s, no error code; 10/10 |
| B2 | **Shortest press**: find the shortest tap that turns it on (baseline) | the new firmware turns on with the same tap, 10/10 |
| B3 | Time from press to display/ready (phone video) | within ±0.2 s of baseline |
| B4 | Off: hold 2–3 s while stopped | off within baseline time; settings (mode, child profile) kept at next start; 10/10 |
| B5 | Light toggle: short press while on | toggles every time |
| B6 | Mode change: double press (and the 6-change child gesture, if used) | same behaviour as baseline |
| B7 | Auto standby/idle off: leave on, untouched | turns itself off after the same time as baseline; then B1 passes |
| B8 | Long idle: off for 24 h (and once for a week) | B1 passes first time |
| B9 | Low battery: at ≤ 20 % and again ≤ 10 % | B1 and B4 pass; any error code noted |
| B10 | After charger connect/disconnect, and after any naturally occurring error code | B1 and B4 pass |
| B11 | Ride 5 min, stop, B4 off, B1 on | passes 5/5 |

Any failure → stop, return to the last known-good firmware, and don't continue riding tests.

---

## P6. Display codes and the ~30 km/h beep

The controller's status byte 8 (prioritised state) matches the public Xiaomi error numbers **when read as hex digits**:

| Byte 8 | Controller meaning (code) | Public Xiaomi code | Match grade | Source |
|---|---|---|---|---|
| 0x10 | dashboard comms loss | E10 display↔controller communication | [S] | [fallman.tech list](https://fallman.tech/xiaomi-m365-error-codes/), [levyelectric](https://www.levyelectric.com/electric-scooter-error-codes/xiaomi) |
| 0x11 | latched PWM hardware fault (FAIL0_IF, manual tab. 14-42; set at 0x1CFF8) | E11 motor phase A / current fault | [L] | fallman.tech |
| 0x12 | current-offset calibration fault | E12 phase B current sensing | [L] | fallman.tech |
| 0x18 | Hall sequence | E18 motor (Hall) sensor | [S] | fallman.tech; Xiaomi |
| 0x21 | battery-side link timeout | E21 BMS communication | [S] | fallman.tech |
| 0x24 | high voltage (FE > 1075 ≈ 58 V, clears < 1037) | E24 system voltage | [S] | fallman.tech |
| 0x28 / 0x29 | power-stage self-test | E28 / E29 MOSFET | [S] | fallman.tech |
| 0x40 | temperature-sensor fault (0xB8) | E40 controller temperature sensor faulty/overheated | [S] | fallman.tech |
| 0x43 | peripheral probe | E43 "external battery" on some lists | [U] conflicting | [wheelyshop](https://www.wheelyshop.se/en/blogs/maintenance-advice/troubleshooting-error-codes-for-xiaomi-electric-scooters) |
| 0x45 | local thermal derate flag (C2 > 102.0 °C farm) | E45 "battery" on some lists | [U] conflicting | wheelyshop |

**Beep at ~30 km/h:** no controller output plays a sound. The only speed the controller sends is bytes 9–10.
- Xiaomi's 4 Pro manual documents beeps for cruise engage (long), cruise cancel (two), pre-activation and the motor-lock alarm ([manual PDF](https://wheelyshop.se/cdn/shop/files/Xiaomi_4_Pro_Nordic_Edition_Manual.pdf)). There's no over-speed beep there.
- E24 needs ~58 V, so it's unlikely.
- Leading hypothesis [L]: a dashboard-side threshold on the received speed (dashboard firmware not supplied).

To decide, note: whether a code shows during the beep; the displayed speed at the first beep each time; whether it repeats while above ~30 and stops below; whether it happens on flat ground if you ever reach 30; whether battery % changes the speed. I won't invent a way to make the dashboard play a child-mode tone.

---

## P7. Independent double-check of the newest findings
My own fixture ([`opus_emu.py`](opus_next/scripts/opus_emu.py), [`p7_rechecks.py`](opus_next/scripts/p7_rechecks.py)), not the earlier harness.

1. **Regen flatness and Hall injection — agree.**
   - In all four images at forced speeds 8.5–35 km/h (realised speed asserted): target 320, step 10, first DA drop at tick 110 = **22 supervisor visits**, the same as the earlier report. 7–8 km/h → target 0.
   - My first version of this test was wrong: it left RAM 0x210 stale, so it passed trivially. Fixed by running the real voltage task 0x22F38.
2. **54.0 V gate — agree, with a refinement.**
   - Executed edge: FE 999 → step 10, FE 1000 → step 0.
   - Independent anchor: the implied 30.7:1 divider is within 1 % of a standard 300k/10k.
   - Refinement: the closed loop gives a sharper charge dependence than the earlier illustrative table (P3.2), and at ≥ 53.5 V there's essentially no coast regen at all rather than "until much lower speed".
3. **Temperature sensor and caps — agree, plus two additions.**
   - The settled temperature matches (340800 − 213x)/100 within the filter's truncation band [f−7, f].
   - The caps were re-executed: stock min(560, 3193 − 3·C2) above 90.0 °C, farm min(560, 3620 − 3·C2) above 102.0 °C, 3 at ≥ 110.0 °C. Both lines are continuous with each image's Sport envelope at the entry point.
   - **New:** a *single* out-of-window reading sets C2 = 30.0 °C immediately (0x1D962→0x694A), and it then recovers by 1/8 per call.
   - **New:** sustained faults set 0xB8, which only the telemetry builder reads (0x1D224). It doesn't stop or derate the motor. A loose or failed controller temperature sensor therefore silently disables the local heat derate and shows only E40.
4. **Hold/cruise — agree on engagement.** It never engages with enable bit 0x16D = 0. With the bit set it engages after 5.3 s of steady throttle and holds the *request* (450), not the measured speed. I didn't re-derive every cancel path.
5. **Byte-8 chain / RAM 0x14 — agree.** My analyser finds exactly the same writers (0x14: 0x1C5B4, 0x1CFF8, 0x1DFB0; 0x1D6: 0x1BF4A, 0x201EA, 0x213E4, 0x22B92). 0x1CFF8 follows a read-and-clear of MCPWM0_EIF bit 4 = **FAIL0_IF** (hardware fault input), so "latched hardware PWM fault" is confirmed against the manual.
6. **The earlier CFG tool — sound for its stated result, not general.** Its weaknesses:
   - Linear-sweep decoding treats literal pools as code (boundary desync risk).
   - It assumes standard register clobbering at every call. The farm helper 0x2381C keeps r1, and the caller relies on that (0x1E028–0x1E072 stores to the 0x14C block), so the tool loses such stores.
   - Differing constants at a join collapse to "unknown".
   - Only the 0x21714 switch helper is handled (I found no other computed jumps).
   - Pointer stores are unresolved.

   For 0x14/0x1D6 its answer is reproduced exactly; for general "no writer" proofs use a value-set analysis like [`p4_mem.py`](opus_next/scripts/p4_mem.py).

**Could not reproduce or settle:** the actual ride cause without ride data; ground-speed calibration; the phase-current scale; dashboard behaviour; first-processor STOP/IWDG silicon behaviour; bootloader acceptance limits.

---

## Mistakes I made and corrected during this work (so the evidence can be trusted)
- Unicorn skips code hooks on already-translated blocks. My first cycle and branch counts missed routine 0x1DDCC. Fixed with `ctl_flush_tb()` after adding hooks, and the scripts now assert that coverage is non-zero.
- My first ISR timing fixture left the ISR enable byte 0x0C = 0, so it measured only the short path (361 cycles). Fixed: coverage of the full FOC path is now asserted, giving 2,182 cycles.
- My first plant had no winding inductance, which made the optional governor fire in a stiff-motor case. With L·di/dt that disappears.
- RAM 0x210 is computed by 0x22F38, which my first scheduler didn't call. My plant wrote the identical formula, so P1/P3 were unaffected; it's now executed.
- Failed pre-registered checks are kept visible: P1 onset window (20.9 km/h), P3 "toggles at ≥53 V", P3 spec ripple (`p3_regen.py` exits 1 by design).

## Files
- Scripts: `opus_emu.py` (fixture), `p1_closed_loop.py`, `p1_experiments.py`, `p1_svpwm.py`, `p1_battery_r_sensitivity.py`, `p2_calibration.py`, `p3_regen.py`, `p4_static.py`, `p4_mem.py`, `p4_stack_check.py`, `p4_ram_evidence.py`, `p4_timing.py`, `p7_rechecks.py`, `disw.py` (disassembly window), `run_all.sh`.
- Evidence: `P1_power_dip_evidence.json`, `P1_svpwm_evidence.json`, `P1_battery_r_sensitivity.json`, `P2_calibration.json`, `P3_regen_evidence.json`, `P4_static_<image>.json`, `P4_mem_<image>.json`, `P4_stack_farm.json`, `P4_ram_evidence.json`, `P4_timing_evidence.json`, `P7_rechecks_evidence.json`, and `*_log.txt` run logs.
- The firmware files are **not** copied into this repository; the scripts read them from the extracted project folder and verify their SHA-256 first.

A note on the child profile: Xiaomi's specification (quoted in the project's earlier power review) gives a rider age range of 16–50 and a 120 kg maximum load ([specs](https://www.mi.com/global/product/xiaomi-electric-scooter-5-max/specs/)). A gentler child profile reduces, but does not remove, that consideration.
