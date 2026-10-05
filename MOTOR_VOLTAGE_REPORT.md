# Motor-voltage limit of program B (Xiaomi 5 Max motor controller): analysis report

Date: 2026-10-05. Offline analysis only: nothing was built, flashed or sent to the scooter. Byte changes below are **proposals**, tested only inside the emulator.
Labels: **C** confirmed in code or by running the real code in the emulator, **S** strong, **L** likely, **U** unknown.
Image: `MI5Max_V10_BOOST648_CANDIDATE.bin` (sha256 `28dce28c9a0d…`). Every function on the voltage path (`ISR_MCPWM0`, `svpwm_output`, `d_axis_regulator`, Park/inverse Park, `calc_modulation_index`, `pwm_init`, `speed_loop`, `voltage_monitor`) is **byte-identical in all 9 images**, stock through V10 (C). Only `current_limiter_drive_cmd` differs between builds (the caps).
Tools I ran: capstone 5.0.9, unicorn 2.1.4 (Python 3.11), the project's `06_VIRTUAL_SCOOTER` (real firmware control code plus the fitted plant), and the official English LKS32MC07x User Manual v1.68 (downloaded; the project's `lks_manual.txt` has its Chinese text stripped). Scripts and raw results are in `motor_voltage/` (see the end).

---

## In plain words

* The controller already uses **all of the battery voltage** that clean (linear) PWM can give. The command range 0…1023 is the full range: at 1023 one motor wire is switched fully on, and another fully off, at the six points of each turn where that's needed. No software limit holds the voltage lower than the battery allows.
* A little is lost to the "dead time", a short safety pause between the two transistors of each phase. Near full voltage the code can't compensate for it. My emulation says this costs about 1–3 %, which explains most of the project's fitted `m_max` = 0.9755.
* So **more voltage can only come from a code change inside the 15.6 kHz motor interrupt**. Three ways exist: (1) skip the useless tiny pulses near 0 % and 100 %, worth about +2–3 %; (2) mild overmodulation, which slightly distorts the voltage waveform, worth about +4–6 %; (3) field weakening, a different control trick, worth much more but risky.
* What you'd feel from (1) or (2): **top speed about +0.7 to +1.5 km/h, and 20→30 km/h about 0.3–2 s quicker** depending on charge. Launches and hill climbs would **not** change, because the battery current cap limits those, not the voltage.
* **Field weakening** (pushing a "negative d-current") could add 4–10 km/h in the model. But it is a new control loop in the time-critical interrupt. It makes the motor's own generated voltage exceed the battery voltage. If the PWM ever switches off at that speed (over-voltage cut, fault, battery cut), the motor would brake hard on its own and could push the controller's supply voltage above safe levels. **I do not recommend it.**
* **Recommendation: not worth doing unless you accept a new, interrupt-level firmware change for about 1 km/h.** If you do go ahead, use only the "clean" version (option C below): it writes only PWM states the chip manual documents. Test it with the wheel lifted first, at about 50 % charge, before any ride.

## One-page summary

| question | answer | label |
|---|---|---|
| Can the max motor voltage be raised? | Yes, but only by changing code in the PWM interrupt path (`svpwm_output` B:1EE60, plus the clamps). No constant-only change raises the *linear* limit, because 1023 already is the linear limit. | C |
| How much? | Pulse dropping (C1): about +2.8 % fundamental, almost no distortion. Overmodulation clamped to documented states (C2): +4.2 % at \|V\| 1050, +5.7 % at 1100, +6.7 % at 1182, with 5th/7th harmonics of 1–4.6 %. Field weakening: far more (model), with high risk. | C (PWM arithmetic) / S (dead-time model) |
| What does it buy? | Model, owner's usual stretch (2° down, 75 %): top 30.1 → 30.8 / 31.2 / 31.6 km/h for +2.5 / +4 / +5.5 %; 3→30 km/h 7.65 → 5.86 / 5.47 / 5.21 s. At 97 %: top 31.5 → 33.0 km/h, 3→30 km/h 5.30 → 4.70 s. 0→20 km/h unchanged (2.21 s). | S (model) |
| Risk | Low to moderate for C1/C2: no new protection gap, current sampling loss grows from 3 % to 7–11 % of angles, battery-chip rules still hold, cable/heat unchanged on climbs. Option A/B (constants only) write a compare state the manual does not document (TH1 > TH). Field weakening: high. | S / U |
| **Recommendation** | **Only with conditions:** use C1 (pulse dropping) alone, or C1 + C2 capped at \|V\| ≈ 1100. Emulator checks first (section 8), then a lifted-wheel test at about 50 % charge. **Do not** do field weakening, and **do not** raise the shared literal at B:1D918 (it is also the over-voltage trip). | – |
| Single most important unknown | Whether the predicted gain exists on the real inverter: the real dead-time loss near 100 % duty (it depends on the transistors' actual switching). The fitted 0.9755 is consistent with it, but a fit can't prove it. A lifted-wheel no-load speed test, stock vs patched, settles it without an oscilloscope. | U |
| Confidence | Code facts: high. Size of the gain: medium (it rests on the fitted plant and an idealised dead-time model). Field-weakening numbers: low (they depend on the fitted reactance `xl`). | – |

**Contradictions with the brief (prominent):**
1. **The d-axis regulator also clamps the q-voltage to a circle**: `|vq| ≤ sqrt(1023² − vd²)` (B:1D60A–1D636, constant 0xFF801 = 1023² at B:1D648). The brief lists only the ±920 clamp on vd. So 1023 is a limit on the **vector length**, not only on `vq` (C).
2. **0xDDB3 is not the voltage scale.** 0xDDB3/32768 = 1.7320 = √3. It is used only to split the plane into the six sectors. The voltage-to-duty gain is the constant 1536/1024 = 1.5 (`movs #3; lsls #9`, then `asrs #10`) at B:1EE9E, B:1EEA6/AA and B:1EEB0 (C).
3. **The 1023 literal at B:1D918 is shared** by the governor clamp (B:1D864) and the **over-voltage trip** (B:1D8CC: `0x3FF + 0x34 = 1075`). Raising that literal would also raise the over-voltage cut-off. Any patch must leave it alone (C).
4. `m_max` = 0.9755 is *not* a firmware number, as the brief says. But it is explainable: the real PWM, including dead time, gives 0.972–0.995 of Vbus/√3 at 1023 (S). The brief's sentence "(no field weakening) … voltage-commanded" is correct (C).

---

## 1. The voltage path, end to end (C unless marked)

| # | step | address | formula / action | limit |
|---|---|---|---|---|
| 1 | requested speed → `drive_cmd_target` (RAM 0xDA) | `speed_loop` B:1E3D0 (every 5.12 ms) | +`speed_step` per visit, or ±1 per cadence | `≥ 1023` blocks increments (literal B:1E860, used at B:1E6CC); final clamp ±1023 at B:1EAC2–1EADA (literal B:1EB20, shared with the brake path at B:1E9C0/1E9D8) |
| 2 | `drive_cmd_target` → `drive_cmd` (RAM 0x140) | `current_limiter_drive_cmd` B:1D654 (3.9 kHz) | `slew_toward(drive_cmd, target, 3)` at B:1D880; when the limiter clamps (DC current > `env_applied`, or `i_q` > 1461), `drive_cmd` is pulled down and copied back into the target (B:1D892) | governor path `< 1023` (literal B:1D918 – shared with the over-voltage trip!) |
| 3 | `drive_cmd` → `vq_like` (RAM 0x11C) | `ISR_MCPWM0` B:1CB14, state 2 (B:1CD56–1CD8E), 15.625 kHz | `vq_like` = `drive_cmd` while the limiter clamps, else ±1 per interrupt | none of its own |
| 4 | d-axis: `vd_like` (RAM 0x11E) | `d_axis_regulator` B:1D5B8, only when the current sample is valid | `vd += (−i_d)>>3 + 2·(i_d,prev − i_d)`, clamp ±920 (0x398, literal B:1D640), then float biquad (RAM 0x420); **then `vq` clamped to ±sqrt(1023² − vd²)** (B:1D60A–1D636) | **vector length ≤ 1023** |
| 5 | inverse Park | `inverse_park` B:1D468 | `vα = (cos·vd − sin·vq)>>15`, `vβ = (cos·vq + sin·vd)>>15` (CORDIC/DSP sin-cos) | none |
| 6 | sector | `svpwm_output` B:1EE60 | `x = vα·0xDDB3>>15` (= √3·vα); `r1 = (x − vβ)/2`, `r3 = −(x + vβ)/2`; sector bits (vβ>0)+2(r1>0)+4(r3>0) → RAM 0x118 | – |
| 7 | duty | same, B:1EE9C–1EF1A | three components ×1536>>10 (= ×1.5); per sector `t = 1536 ± …` (switch table after `bl lib_switch8_helper` at B:1EEBA) | **no clamp** on t |
| 8 | dead-time compensation | B:1EFB4–1F0B6 (per phase) | i > 120 counts: TH0 = −(t+76), TH1 = t; i < −120: TH0 = −t, TH1 = max(t−76, 0); otherwise linear, c = i·76/120/2: TH0 = min(−(t+c), 0), TH1 = max(t+c, 0) | only "≤ 0 / ≥ 0" clamps |
| 9 | sampling flags for the next period | B:1F0C4–1F0DA | phase valid if t < 0x57<<5 = **2784** | – |
| 10 | hardware | `pwm_init` B:1D034 | TCLK = 0x44 (counter on, clock on, DIV = 0 → 96 MHz); TH0 = 0xC00: counter −3072…+3072, **64.0 µs = 15.625 kHz**; DTH = 0x4C = **76 counts = 0.79 µs**; SDCFG = 0x10 (shadow load at t0 = period start: new duties act one period later); TMR2 = 0xF473 = **−2957** (ADC trigger 115 counts = 1.2 µs after period start); FAIL012 = 0x110 (hardware fault input → outputs off) | – |

**Full scale (C, emulator, E1/E2).** With zero current, |V| = 1023 gives a top-phase half on-time t = 3071–3072 at the vertex angles, so 100 % duty. The bottom phase gets t = 0–8 (0 %), and the fundamental is 0.999 × Vbus/√3. So **1023 is the edge of linear SVPWM** (the circle inside the hexagon). |V| = 500 gives 0.488, which is linear.

**Pulse widths (C from the manual + code).** On-time of a phase = 2t counts (out of 6144) at zero current. Per manual §14.1.4.1, the high side switches on at TH0 + DTH and off at TH1, and the low side switches on DTH after TH1. Manual §14.1.3: **TH0 ≥ TH1 → constant 0 % (low side on, no dead time); TH0 = −TH and TH1 = +TH → constant 100 % (no dead time).** At 1023 the top phase has t ≈ 3064–3071, so it switches off for 2–16 counts per period. That gap is shorter than the dead time, so the low side never actually turns on, but the phase still drops to the low diode for about the dead time (with positive current). The bottom phase has on-times of 0–16 counts, shorter than the dead time. These near-rail pulses are where voltage is lost (section 2).

**`calc_modulation_index` B:1B7EC (C).** It measures the back-EMF while the PWM is off: `phase_v_mag = sqrt((vc−va)² + ((2vb−vc−va)·0x49E7>>15)²)` (0x49E7/32768 = 1/√3, i.e. the line-line vector length). Then `mod_index = phase_v_mag·1023/vbus_raw`, clamped to 1023 (literal B:1B884). Users: `ISR_MCPWM0` state 1 (flying start: `vq_like = mod_index`, B:1CE22) and the start of `speed_loop` (`drive_cmd_target = mod_index` when the run latch is off, B:1E688 and B:1EADE). It is a re-engage helper, not a limiter. It confirms that 1023 means "line-line peak = Vbus".

## 2. Where does the maximum come from?

* **(a) Software clamps**: 1023 on `drive_cmd_target` (speed loop), and 1023² on the vector length (d-regulator). Both sit **exactly at** the linear SVPWM limit, not below it (C).
* **(b) SVPWM linear limit**: the binding one. The firmware stops at the inscribed circle (|V| = Vbus/√3) and never overmodulates in stock (C, E1: no inverted compare pairs and no TH1 > TH at ≤ 1023).
* **(c) Hardware**: the dead time limits what reaches the motor. I ran the real `svpwm_output` at 1023 with phase currents of 60–1200 counts and lags of 0–40°, and applied the manual's bridge timing (E3). Result: **0.987–0.995 × Vbus/√3 with the firmware's compensation, 0.972–0.978 if the compensation did nothing** (S: the idealised model ignores switching transients). The loss happens because at the top of the waveform the compensation would need TH0 = −(t+76) ≤ −3148, beyond the counter, so it can't act; and at the bottom TH1 = t − 76 is clamped to 0.
* **Reproducing `m_max` = 0.9755**: not exactly. The code plus PWM timing gives a band of 0.972–0.995 that contains it (S). The rest is lumped in the fit (battery-to-controller wiring drop, imperfect compensation, correlation with `ke`) (L). It **cannot** be a hidden software clamp: none exists below the linear limit (C).
* **Distance to the hexagon:** |V| = 1023 touches the hexagon only at its six vertices (30°, 90°, …). The hexagon reaches 1182 (= 1023·2/√3) at the vertices, so there is 0–15.5 % unused room between the circle and the hexagon, depending on angle. Using it is overmodulation (low-order harmonics).

## 3. Is there headroom, and where?

**(i) Clamps below the physical limit:** none (C). Every 1023 clamp equals the linear SVPWM limit. The ±920 clamp on vd is a different axis; it costs vq room only when |vd| is large, through the circle `sqrt(1023² − vd²)` (for example |vd| = 300 leaves 978, −4.4 %).

**(ii) Above the linear region (C, E1/E2):** the code neither clips the vector length nor clips each axis inside `svpwm_output`. It computes `t` linearly beyond 0…3072. What reaches the registers:
* the high side of the top phase: TH1 = t > +3072 (outside the counter). It first appears at |V| ≈ 1024 with zero current; at 1050, 150 of 1080 phase-angles. **This state is not described in the manual (U).** The stock firmware already writes TH0 < −3072 (the other edge, by the compensation; 212 of 1080 phase-angles at 1023 with current), and the scooter runs at full voltage every ride, so out-of-range edges are evidently handled gracefully (S).
* the bottom phase: t < 0 gives an **inverted pair (TH0 > TH1)**. At 1050 and above with current this happens on 78–318 of 1080 phase-angles. Per manual §14.1.3 that is a **clean 0 %** (C, manual). That's the right answer for the bottom phase, so inversion is harmless.
* So raising only the clamps gives a crude overmodulation that the hardware very probably handles. But it relies on one undocumented state (TH1 > TH), which is why option C below clamps explicitly.

**(iii) Current reconstruction near 100 % (C, code + emulator).** The ADC fires at count −2957 (TMR2). A phase is sampled only if its t < 2784 (B:1F0C4: the low side stays on until count ≤ −2784, which leaves 173 counts = 1.8 µs for the 3 Msps ADC conversions). `ISR_MCPWM0` picks a fixed phase pair from the previous sector (sector 4/6/0 → A+B, 2/3 → B+C, 1/5 → A+C, B:1CBB6–1CCB4). That pair is **always the two lowest duties** (E2; the only exception is an exact tie at 300°, which is harmless). It also requires |raw| < 0x708 = 1800. If either phase of the pair is invalid, `phase_sample_valid = 0`. Clarke/Park and the d-regulator are then **skipped**: `i_d`/`i_q` keep their old values, `vd` is frozen, and the vq circle clamp is not applied that period (B:1CD90–1CDC4).

| \|V\| | angles without a current sample | worst middle-phase t |
|---|---|---|
| 900 | 0 % | 2706 |
| 1000 | 2.5 % | 2836 |
| **1023 (stock)** | **3.3 %** (about ±1° around each sector boundary) | 2865 |
| 1050 | 4.2 % | 2901 |
| 1100 | 7.5 % | 2966 |
| 1182 | 10.8 % | 3072 |
| 1300 | 14.2 % | 3225 |

Consequences of a larger vector: short windows (6 per electrical turn) in which the measured `i_q` is up to one sample period old. `current_limiter_drive_cmd` reads `i_q` at 3.9 kHz and filters it (`i_q_filt += (i_q − i_q_filt)/20`). The "`i_q` > 1461" bound and the regen bound −1826 therefore react up to a few hundred microseconds late (L: harmless at 7–11 % loss, worse in deep overmodulation). The **battery-current limiter uses its own DC shunt channel** (ring 0x48, B:1D65C) and the **hardware over-current comparator** (CMP0, DAC0 = 203, FAIL012) does not depend on phase sampling. Both stay fully effective (C for the code path; which signal feeds the comparator is L).

## 4. Options for a higher maximum voltage

Gains below are the voltage fundamental relative to stock from E3/E3b (dead time included, current 600 counts lagging 20°), and the ride effect from the virtual scooter (E4, real V10 control code, boost on, chip rules on, **owner's 2° downhill stretch at 75 %** unless noted). Baseline: top 30.1 km/h, 3→20 km/h 2.21 s, 3→30 km/h 7.65 s, battery 10.6 A at 28 km/h.

### Option A: raise the software clamps (constants only)
* **Change (proposal):** literal B:1E860 `ff 03 00 00` → `4c 04 00 00` (1100); literal B:1EB20 `ff 03 00 00` → `4c 04 00 00` (this also moves the brake-path ±1023 clamps at B:1E9C0/1E9D8 to ±1100); literal B:1D648 `01 f8 0f 00` → `90 76 12 00` (1100² = 1,210,000). **Do not touch B:1D918** (over-voltage trip) or B:1B884 (flying start). Recompute the image CRCs with `fw_image_tool.py recrc`.
* **Gain:** +4.0 % (ideal, E1) to about +5 % (with dead time). Ride: top about +1.1 km/h, 3→30 km/h about 5.5 s (+4 % row of E4).
* **Touches:** overmodulation with uncontrolled compare values; TH1 > TH (undocumented); current sample loss 7.5 %; the regen/brake path gets 7.5 % more negative range.
* **Failure modes:** undocumented hardware state at the top phase (U); 5th/7th harmonics about 2–3 % (but see the note on harmonic current below); brief stale `i_q`.
* **Verdict:** simplest, but it relies on an undocumented state. Not recommended in this form.

### Option B: change the vq_like-to-duty scale (4 half-words, tested in the emulator)
* **Change (proposal, E5):** the three multiplier sites in `svpwm_output` (1536 = 3<<9 → 1600 = 200<<3): B:1EE9E `03 21 49 02` → `c8 21 c9 00` (`movs r1,#200; lsls r1,r1,#3`); B:1EEA6 `03 22` → `c8 22` and B:1EEAA `52 02` → `d2 00`; B:1EEB0 `03 23 5b 02` → `c8 23 db 00`. The four "centre" sites that also build 1536 (B:1EEC8, 1EEDE, 1EEF4, 1EF08) must **not** change. Emulator: centre still 1536, swing ×1.0426, 100 % first reached at |V| = 982.
* **Gain:** +4.2 % at the same command. Everything above 982 is overmodulation, just as in A.
* **Touches:** every voltage in the drive is 4.2 % larger for the same `vq_like`. The flying start (`mod_index`) re-engages 4 % "hot", a small current blip at re-engagement (L). The speed loop and limiter close their loops around it (C: they are feedback loops).
* **Failure modes:** the same as A (TH1 > TH, sample loss 7 %), plus the re-engage blip.
* **Verdict:** fewer bytes than A, same undocumented state. Not recommended alone.

### Option C: clean overmodulation (recommended form if anything is done)
New code, called once at the end of `svpwm_output`. It needs a trampoline: replace `ldr r0,[pc,#0x24]; strh r4,[r0,#0x1c]` at B:1F0B8 (`09 48 84 83`) with a `bl` to a routine in the 0xFF padding after the V10 hook. The routine first does those two instructions, then post-processes each phase pair, reading back MCPWM0_TH00…TH21 (RW registers, 16-bit: sign-extend):

```
for each phase n (TH0 at 0x40010C00+8n, TH1 at +4):
    th0 = sxth(TH0); th1 = sxth(TH1)
    if th0 >= th1:                 TH0 = TH1 = 0         ; inverted -> documented 0 %
    else:
        th0 = max(th0, -3072); th1 = min(th1, 3072)      ; keep inside the counter
        on = th1 - th0
        if on >= 6144 - 152:       TH0 = -3072; TH1 = 3072 ; C1: documented 100 %, no dead time
        elif on <= 152:            TH0 = TH1 = 0           ; C1: documented 0 %, no dead time
        else:                      TH0 = th0;  TH1 = th1
```
About 3 × 15 = 45 Thumb instructions, roughly 0.5–0.7 µs per interrupt out of 64 µs (L; measure it in the emulator, see section 8). The sampling flags are unchanged: the top phase is never sampled, and a bottom phase at a clean 0 % has its low side on for the whole period, which is better for sampling.

* **C1 = pulse dropping only** (no clamp change): **+2.8 %** (E3b: 0.9884 → 1.0161); 5th/7th harmonics 0.31 %/0.53 % (stock 0.66 %/0.38 %). It removes the near-rail pulses that cost a dead time each. Sampling loss unchanged (3.3 %). Ride: like the +2.5 % row, **top +0.7 km/h, 3→30 km/h 7.65 → about 5.9 s at 75 %, 5.30 → 4.96 s at 97 %**.
* **C2 = C1 + clamps raised to 1100** (option A's three literals, or option B's scale): **+5.7 %** (E3b: 1.0446/0.9884). 5th 2.7 %, 7th 2.05 %. Sampling loss 7.5 %. Ride: like the +5.5 % row, **top 30.1 → 31.6 km/h, 3→30 km/h 7.65 → 5.21 s at 75 %; at 97 %: 31.5 → 33.0 km/h, 5.30 → 4.70 s**.
* At 1182 the gain is +6.7 % with 4.6 % 5th harmonic; beyond that, gains are tiny (1300: +7.6 %, 1500: +8.6 %) and harmonics grow. **Cap at 1100.**
* **Harmonic current (L):** this motor's fitted reactance is large (0.5 Ω at 30 km/h at the fundamental, so 2.5 Ω for the 5th). A 2.7 % 5th harmonic (about 0.8 V) drives only about 0.3 A. Torque ripple and extra heat from overmodulation should therefore be small.
* **Failure modes:** a bug in new interrupt code (shoot-through is still prevented by the hardware dead time and the documented states, C from the manual); bootstrap gate drive at 100 % for longer stretches. The stock firmware already holds the top phase effectively on through the vertices (its off-gap is shorter than the dead time), so the low side doesn't switch there in stock either; worst case at 30 km/h is about 0.4 ms continuous (L, gate-driver type not known).

### Option D: field weakening (id < 0), for completeness
* **Feasibility, physics:** with the fitted plant, characteristic current = ke/xl = 0.9306/0.01675 = **55.6 A peak** (39 A rms). That is within the range of the phase-current bound (1461 counts = 54–100 A, scale U). So FW is very effective *in the model*. E4: id = −10 A gives top 30.1 → 35.4 km/h, 3→30 km/h 4.63 s; id = −20 A gives 41.7 km/h (75 %, 2° down); 97 % flat 29.8 → 34.3 / 39.3 km/h. With `xl` halved (E4b): still 32.7 / 35.5 km/h. **The size of the gain rests entirely on the fitted `xl` (U)**; the direction does not.
* **Code:** the regulator's error is hard-wired to `−i_d` (B:1D5BC–1D5C6). FW needs an id reference (`err = id_ref − i_d`) and an outer law deciding id_ref from voltage saturation. That's new code in the interrupt, plus a RAM cell outside the ±62-byte reach of `r4` (0x118). It also has to handle the frozen regulator when samples are invalid.
* **Costs:** copper loss 1.5·R·id² = 16 W at −10 A, 65 W at −20 A, even with no torque. Battery current at 28–30 km/h rises from 3–11 A to 19–23 A, sitting on the cap for long stretches (16 AWG cable, `V10_IDEA_680_ANALYSIS.md` §8).
* **Main hazard (S):** above about 36 km/h the line-line back-EMF (√3·0.93·v) exceeds 58 V. Any PWM shutdown at that speed — the controller's own over-voltage trip at 58.07 V (B:1D8CC), a fault, the battery chip opening, dashboard loss — turns the motor into an uncontrolled generator through the transistor body diodes. That means sudden braking torque, plus bus over-voltage if the battery's charge FET is open.
* **Verdict: do not implement.**

## 5. Generator side (steep full-throttle descents)

* **Code facts (C):** `vbus_regen_limit` = 1001 counts = 54.07 V (B:1FFDC; `current_limiter_drive_cmd` stops braking drive above it, B:1D794). Over-voltage cut: `vbus_raw` > 1075 = **58.07 V**, checked at 3.9 kHz in the limiter (B:1D8C6–1D8DE) and in `voltage_monitor` (B:22F64). It sets `flag_highv`, clears `run_latch` and turns the PWM off (MOE off). It clears below 1037 = 56.0 V. The ISR does not re-arm while `flag_highv` is set (B:1CDD4).
* **What changes with a higher voltage limit (S):** the speed at which the scooter stops being driven and starts generating rises by the same percentage, about +0.7 km/h (C1) or +1.5 km/h (C2). At the descent equilibrium the regen current is set by the slope, not by the voltage limit, so the regen current and pack voltage at equilibrium hardly change. The speed is about 2–6 % higher.
* **Worse or better?** Slightly **worse**. The descent speed is a bit higher, so if the PWM does switch off (for example the 58.07 V trip at 100 % charge, which the model's 56–58 V estimate puts close), the uncontrolled diode current starts from a higher back-EMF. For C1/C2 the shift is small next to what descents already do: 37.8 km/h on 11° in the model is a back-EMF of 61 V, already above the 58.07 V trip. With field weakening it would be much worse (section 4D).
* **Advice regardless of any patch:** avoid long full-throttle descents above about 90 % charge (the project's earlier advice stands).

## 6. Battery-current cap and the chip rules

* The voltage limit binds only above roughly 22–24 km/h. Below that, the cap (`env_applied` 600/648 counts) binds (C for the logic, S for the speed).
* E4 with the **real** program-A latch: battery peak 23.7 A in every C1/C2 case (the 648 boost), the same as stock. Battery current at 25 / 28 / 30 km/h (97 %, flat): stock 21.0 / 14.0 / 9.1 A; +2.5 %: 22.9 / 16.1 / 10.8 A; +5.5 %: 23.3 / 18.5 / 13.6 A. **No chip trip in any run** (S). More voltage keeps the scooter on the cap about 1 km/h longer, so the time at ≥ 22 A per launch grows a little, but the boost guard/dip logic is unchanged.
* Climbs: unchanged. At 18 km/h on 7.5° the scooter is current-limited, not voltage-limited.
* Field weakening (−10/−20 A): 20–23 A continuously at 28–30 km/h. That is right at the 22 A/10 s rule if the chip reads 1–2 % high (L). Another reason against it.

## 7. Top speed and mechanics

* Expected top speed (model): C1 about +0.7 km/h, C2 about +1.5 km/h; at 100 % on your stretch, roughly 33 → 34 km/h. Rule of thumb from the model: **about +0.27 km/h per % of voltage** (the brief's "+1 km/h per 3 %" is about right).
* Other limits (from code where possible): Sport target 45.0 km/h (the speed loop starts trimming at the requested speed −0.3 km/h, B:1E712); **no over-speed fault in program B was found** in the paths read (speed loop, limiter, voltage monitor, region defaults; "not found"). `region_config_defaults` contains no speed constant near 30–35 km/h (C; `ctrl_450` = 0x1D4C0 = 120000 has an unknown meaning, U). The dashboard beep above 30 km/h and anything the dashboard does with speed: U (no dashboard firmware). Brakes, tyres and frame are outside the code: the 5 Max is built for its stock top speed; 1–2 km/h more is not a structural concern, but braking distance grows with v².

## 8. Verification plan (before any hardware use)

**In the emulator (Unicorn, real code):**
1. Apply the proposed bytes **only in the emulated flash**. Regression-diff the image: only the intended bytes and CRCs may change.
2. Run the **real `ISR_MCPWM0`** (not done in this study; I ran `svpwm_output`, `d_axis_regulator`'s constants and the main-loop functions). Feed synthetic ADC rings, hall states and `elec_angle` over 720 angles × |V| ∈ {900…1100} × currents. Check: no write outside {−3072…3072}; only the documented 100 %/0 % specials; `phase_sample_valid` share matches E2; `i_q` stays consistent; the stall/limiter paths are unchanged.
3. Count cycles of the patched ISR path (Unicorn code hook): it must stay well under 6144 cycles per period with the main loop still getting time. Compare with stock.
4. Closed loop: `06_VIRTUAL_SCOOTER` launches, the 600 m climb and the descent study must give the same chip-latch and limiter behaviour as stock.

**On the hardware (in this order, owner, no oscilloscope):**
1. Stock baseline: wheel lifted, **about 50 % charge**, Sport, full throttle for 10 s. Read the steady no-load speed and pack voltage in the app. Repeat 3×. (no-load speed ≈ m·Vbus/(√3·ke), so the ratio tells you the real gain.)
2. Patched (C1 first), the same test. Expected: no-load speed +2–3 % at the same voltage. Listen for new noise.
3. Stop criteria at any step: any error code or cut-out, a new whine or vibration, controller temperature (app) rising more than 5 °C above the stock run, lifted-wheel battery current more than 1 A higher than stock at the same speed, any jerk at throttle on/off. Roll back to V10 / V8.2.1 at once.
4. Then a short flat ride at 50–70 % charge, no descents: top speed and amps at 25/28 km/h against the stock numbers. Only after that a normal ride, still avoiding long full-throttle descents above 90 % charge.
5. C2 (clamps to 1100) only after C1 has passed everything above.

---

## Constants and addresses relevant to the voltage limit

| name | address (B:file) | value | meaning | label |
|---|---|---|---|---|
| drive cap (speed loop increment) | literal B:1E860, used at B:1E6CC | 0x3FF = 1023 | `drive_cmd_target` stops rising | C |
| drive clamp (speed loop end, brake path) | literal B:1EB20, used at B:1E9C0, 1E9D8, 1EAC6 | 0x3FF | ±1023 final clamp; also the brake ±40 step limits | C |
| governor clamp **and** OV trip | literal B:1D918, used at B:1D864 and B:1D8CC | 0x3FF (+0x34 = 1075) | **shared**: governor `drive_cmd` < 1023 and `vbus_raw` > 1075 → PWM off | C |
| vector circle | literal B:1D648, used at B:1D614 | 0xFF801 = 1023² | \|vq\| ≤ sqrt(1023² − vd²) | C |
| vd clamp | literal B:1D640, used at B:1D5E2 | 0xFFFFFC68 = −920 (and +920) | d-axis voltage limit | C |
| sector scale | literal B:1F0E4, used at B:1EE68 | 0xDDB3 = √3·32768 | sector geometry only | C |
| SVPWM gain | B:1EE9E, B:1EEA6/1EEAA, B:1EEB0 | 3<<9 = 1536, then >>10 | ×1.5 (1023 → 1534.5 counts swing) | C |
| SVPWM centre | B:1EEC8, 1EEDE, 1EEF4, 1EF08 | 1536 | 50 % duty | C |
| dead-time comp | B:1EFB4… (`#0x78`, `#0x4c`) | 120 counts / 76 counts | full comp above \|i\| = 120 | C |
| sample-valid limit | B:1F0C4 | 0x57<<5 = 2784 | phase current measurable if t < 2784 | C |
| ADC raw validity | ISR B:1CBE2… | ±0x708 = 1800 | sample rejected outside | C |
| PWM period | `pwm_init` B:1D050 | TH0 = 0xC00 = 3072 | −3072…+3072 at 96 MHz, 64 µs | C |
| dead time | B:1D06E… (DTH00/01/10/11) | 0x4C = 76 | 0.79 µs | C |
| ADC trigger | B:1D054/1D058 (literal) | TMR2 = 0xF473 = −2957 | 1.2 µs after period start | C |
| clock | B:1D03E/1D042 | TCLK = 0x44 | 96 MHz, counter 0 on | C |
| shadow load | B:1D06A/1D06C, SDCFG = 0x10 | update at t0 | new duties act next period | C (manual) |
| mod_index clamp | literal B:1B884, used at B:1B858 | 1023 | flying-start command | C |
| phase current bound | literal B:1D8F4 | 0x5B5 = 1461 | limiter acts above it | C |
| regen voltage limit | RAM 0x454 (B:1FFDC) | 1001 = 54.07 V | stops braking drive | C |
| over-voltage cut | B:1D8CC, B:22F64 | 1075 = 58.07 V, clear < 1037 = 56.0 V | PWM off | C |
| under-voltage | B:22F4x | < 603 = 32.6 V off; < 743 = 40.1 V warning | – | C |
| HW over-current | `dac_init` B:1BBA6 | DAC0 = 203 (self-test 51) | CMP → FAIL → outputs off | C (input signal L) |

## Contradictions with the project documents
1. Brief section 2 omits the **vq circle clamp** (`sqrt(1023² − vd²)`) in `d_axis_regulator` (it is in the function catalog). (C)
2. Brief: "svpwm_output (… scale 0xDDB3)". 0xDDB3 is √3 for the sector split; the gain is 1.5 at three other sites. (C)
3. "`m_max` … not derived from code": correct, but the code plus PWM timing gives 0.972–0.995, so 0.9755 is physically plausible and not a model artefact only. (S)
4. `V10_IDEA_680_ANALYSIS.md` §5 calls the limit "the maximum voltage command and the PWM scaling" and "not a constants-only change". Partly wrong: constants **can** raise it (options A/B), but only into overmodulation, and safely only with code (option C). (C/S)
5. `02_PROGRAM_B_MOTOR_CONTROLLER.md` says the over-voltage check (> 1075) is in `voltage_monitor` (195 Hz). It is **also** in `current_limiter_drive_cmd` at 3.9 kHz, which is the fast one that switches the PWM off. (C)
6. I reproduced the §5 table to within 0.02 s (5.30 / 4.96 / 4.70 s against 5.32 / 4.98 / 4.72 s). No contradiction.

## Unknowns and how to resolve them
| unknown | why it matters | how to resolve |
|---|---|---|
| real dead-time loss near 100 % (so the real gain of C1) | size of the benefit | lifted-wheel no-load speed, stock vs patched, at the same pack voltage (app) |
| MCPWM behaviour for TH1 > +TH (options A/B) | undocumented state | avoid it (option C); or an oscilloscope on a phase |
| gate driver type (bootstrap or not) | long 100 % stretches | board photo / driver IC marking; stock already does near-100 % |
| motor inductance (`xl` fitted) | field weakening size | not needed if FW is rejected; an LCR meter across two phases |
| phase-current scale (14–27 counts/A) | i_q bound in amps | the coast-down test already proposed in FINDINGS.md §6 |
| ISR cycle budget with new code | time-critical interrupt | Unicorn cycle count (section 8, step 3) |
| controller's capacitor/FET voltage ratings | generator-side risk | board photo of the capacitor and FET markings |
| dashboard speed behaviour (beep > 30) | top-speed use | not resolvable from these images |
| meaning of `ctrl_450` = 120000 | possible hidden limit | code reading of its users |

## What I ran (all in `motor_voltage/`)
* `scripts/mv_emu.py`: minimal Unicorn Cortex-M0 fixture for program B (hash-checked image, DSP divider/sqrt/sin-cos model).
* `e1_svpwm_sweep.py` → `evidence/E1_svpwm_sweep.json`: real `svpwm_output`, |V| 500–1600 × 360 angles, ideal fundamental, sample loss.
* `e2_svpwm_edges.py` → `E2_svpwm_edges.json`: out-of-range and inverted compare pairs, the ISR phase-pair rule.
* `e3_deadtime_fundamental.py` → `E3_deadtime_fundamental.json`: 1023 with dead time, currents 0–1200 counts, lag 0–40°.
* `e3b_options_fundamental.py` → `E3b_options_fundamental.json`: stock vs pulse dropping vs clamped overmodulation, with harmonics.
* `e4_vscooter_variants.py`, `e4b_sensitivity.py` → `E4_vscooter_variants.json`, `E4b_sensitivity.json`: virtual scooter (real V10 control code) with voltage gain or field weakening; reproduction of the project's §5; `xl` sensitivity.
* `e5_scale_patch.py` → `E5_scale_patch.json`: option B bytes disassembled and run in the emulator.
* Run with `MI5MAX_ROOT=<extracted MI5Max_project>`. Firmware images are not copied into this repository.
* Not run: the full `ISR_MCPWM0` in the emulator (its sampling logic was read from the disassembly), and no hardware anything.
