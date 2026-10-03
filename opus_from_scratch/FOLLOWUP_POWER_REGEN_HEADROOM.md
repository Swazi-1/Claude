# Follow-up: power button, regen conflict, voltage headroom, ride predictions, self-audit

Read-only analysis of the owner's files. No device contacted, no firmware written, no flashable file produced, no settings change suggested. Labels: **[C] confirmed** (bytes/executed code), **[S] strong**, **[L] likely**, **[U] unknown**.

Companion to `OPUS_FROM_SCRATCH_REPORT.md`. Reproduce with `scripts/run_all.sh`; the specific scripts are named per section. File hashes of this folder's deliverables are at the end.

---

## 1. Power button first — does anything differ between original and RC02?

**Answer: No. On every path that touches the power button, power-hold (P3.9), wake, sleep, power-off and the dashboard handshake, RC02 is byte-for-byte identical to the original, and no RC02 change can reach those paths through shared memory in a way that flips a decision.** Evidence: `scripts/s05_power_path.py` → `evidence/s05_power_path.json`.

**What I checked, and how it could have failed.**

1. **The whole battery-side program is identical.** File `0x1000–0x19223` (the processor that owns sleep/wake, the EXTI wake pins and the BQ769x2 FETs) is byte-for-byte the same in stock, v7.1, RC01 and RC02. A single changed byte there would have shown up. *(This check can fail; it did not.)* So every RC02 change is inside the **motor controller** only. **[C]**

2. **The motor-controller power path is identical.** I seeded the set of functions that touch the power/sleep hardware — any function that reads/writes **GPIO3 (P3.9 power-hold)**, the **SYS** clock/reset block, the **AON/IWDG** block, the **PWRDN** supply-low interrupt, the two **UART** interrupts, the **dashboard frame handler `0x99fc`** (which owns the stay-on bit → P3.9), and the **idle auto-off `0x96cc`** — then closed over everything they call. That is **68 functions**. I compared the bytes of every one of them, plus the literal-pool words they load, stock vs RC02: **all 68 identical.** The named anchors include `0x5694` (clock/watchdog bring-up), `0x5748` (GPIO3), `0x6634` (PWRDN ISR), `0x9470`/`0x9724` (UART0/1 ISRs), `0x99fc` and `0xa0ac` (handshake + P3.9 drive), `0x96cc` (10-min auto-off), `0x834c` (settings save). **[C]**

3. **No RC02 change can leak into the power path through RAM.** RC02's changed and new functions (`0x4db8, 0x5144, 0x5524, 0x663c, 0x6db4, 0x70f0, 0x8bf4, 0x8fc4, 0x9044, 0xc804, 0xc840, 0xc900, 0xc938`) touch many RAM bytes. I intersected "RAM read by a power-path function" with "RAM written by a changed/new function". Only four small groups overlap:

   | RAM | read by (power path) | written by (changed fn) | what it is |
   |---|---|---|---|
   | `0x2000001F` | `0x4fbc` | `0x663c` | supervisor "settings dirty / event" flag |
   | `0x200000E8–E9` | `0x99fc` | `0x5524` | a voltage/telemetry word echoed to the dashboard |
   | `0x20000144–149` | `0x99fc` | `0x5524`, `0x6db4` | speed/demand words echoed to the dashboard |
   | `0x2000034C–34F` | `0x4e8c` | `0x5524` | the flash-save signature `0x9A0D361F` |

   For each one I then checked the **actual store instructions**: every write to these addresses from `0x663c`, `0x5524` and `0x6db4` sits in **pre-existing, byte-identical code** (store sites `0x68c4`, `0x555c/5582/5586/558a/55f6`, `0x6eba/6ec0/6ec6`) — none is in a changed byte, and none differs stock↔RC02. And none of these four is the signal the power latch uses: the stay-on latch keys on the **dashboard frame `0x51/0x10` byte5-bit7** and on comms-loss, not on speed, voltage, the dirty flag or the save signature. So even where RC02 changes the *value* that flows through these variables, it cannot change whether the scooter powers on, holds on, sleeps or powers off. **[C]**

**How the one-press power actually works (so you can see why RC02 is irrelevant to it).** The motor controller holds itself powered by driving **P3.9** once it receives a valid dashboard frame `0x51` command `0x10` with **byte 5 bit 7 set** (`0x99fc`→`0xa0ac`); boot needs ~0.3 s before the first such frame; three valid frames with that bit **clear**, or a comms-loss timeout, run the shutdown (disable motor, save once, drop P3.9). The battery-side processor wakes from **EXTI edges on PB9/PA8/PB7** (or charger-present) and sleeps the N32 (STOP2/STANDBY) and the BQ769x2 (SLEEP/DEEPSLEEP) after an idle timeout. **[C for all of this.]**

**What I could not trace.** The **physical button → dashboard → MCU wiring** is not in these files (no dashboard or bootloader firmware), so I cannot name which pin or frame your single press ultimately drives, only that it reaches the controller as that `0x51/0x10` stay-on bit and/or a battery-side EXTI edge, and that **RC02 changes none of the code on either side of that path.** **[U for the wiring; C for the no-change claim.]**

---

## 2. Regen: SOC rule vs 54.0 V gate — which do the bytes support?

Your note: regen only stops above ~90–95 %, same as the original; a 54.0 V battery-voltage gate would also fit. **The bytes contain all three mechanisms, and they are complementary, not competing — but the one that best matches "fails at 90–100 %, same as stock" is the voltage gate.** All three are byte-identical in stock/v7.1/RC01/RC02. Evidence: motor-controller functions `0x73b8` (coast), `0x4db8` (depth), `0x6c98` (E‑ABS); constants confirmed numerically in `scripts/s10_predictions.py` header and the disassembly.

| Mechanism | Where | Trigger | Effect | Label |
|---|---|---|---|---|
| **Coast voltage gate** | `0x7714`/`0x7718`, raw 1000 | controller battery-V reading **≥ 54.0 V** | coast-regen braking step **zeroed** | [C] value / [S] that it's 54.0 V |
| **Coast depth cap (SOC)** | `0x4df6`, `[0x200008CB]` | **BMS SOC ≥ 90 %** | Strong depth → Medium (not zero) | [C] value / [S] % |
| **E‑ABS cutoff (SOC)** | `0x6d2a`, `[0x200000F3]` | **charge ≥ 95 %** | brake-lever regen **disabled** | [C] value / [S] % |

**Which the bytes support better, and why it matters.** The owner symptom is "regen does **not work** at 90–100 %". The **SOC depth cap at 90 % does not stop regen** — it only steps Strong down to Medium, so by itself it predicts *weaker but present* regen from 90 %. The **54.0 V coast gate stops coast regen entirely** whenever the pack reads ≥ 54.0 V, which a pack above ~90–95 % does at rest and during light coasting. So "doesn't work near full" is the **gate's** signature, with the 95 % E‑ABS cutoff removing brake-lever regen on top. The SOC cap explains the "a bit weak even in the 85–90 % band" part. **[S]**

**What each would look like in a ride (so you can tell them apart):**

| Observation | 54.0 V voltage gate predicts | SOC-only rule predicts |
|---|---|---|
| Cut-off vs **charge** | coast regen returns only once terminal V sags below 54.0 V — depends on load and sag, not a clean % | clean switch at a fixed % regardless of voltage |
| **Load / speed dependence** | strong: faster coast → more regen current → terminal V hits 54.0 V sooner → regen chokes earlier; this is your **downhill delay** (weak at 30, bites at 22–25 as V/▼speed drop) | none: a % rule gives the same behaviour at any speed |
| **Temperature dependence** | indirect: cold raises internal resistance, so a given regen current lifts terminal V more → gate bites a touch earlier | none |
| Near 100 % on a **downhill** | almost no regen until speed/charge fall enough for V to drop under 54.0 V | regen present but capped (if SOC < cutoff) |

The **voltage gate uniquely predicts the load/speed-dependent downhill delay you describe**; a pure SOC rule cannot produce it. That, plus "fails at 90–100 %", is why the bytes favour the gate as the operative cause, with the two SOC rules shaping the edges. **[S]**

**Calibration caveat [U]:** the controller's battery-voltage reading and the app's battery voltage are **different sensors**; a few-tenths-of-a-volt offset between them is possible and unmeasured, so "54.0 V" is the controller's internal gate, which may read slightly differently on the app.

---

## 3. Voltage headroom without the circular fit

Your point is fair: the earlier saturation model fitted a motor constant `ke` to one ~7xx W reading, so "it matches" was partly built in. Here is the separation.

**What the code confirms, with no fit [C]:**
- The q-axis (torque) is a **voltage command**; the d-axis current reference is **held at zero** — there is **no field weakening** anywhere in the drive path (searched the current/FOC functions `0x5afc`, `0x642c/0x6450/0x64a8`, `0x65a0`, `0x8bf4`; d-ref is literally 0). **[C]**
- Therefore the maximum achievable motor current falls once back-EMF approaches the available phase voltage, and the available phase voltage is set by the **battery voltage** (minus IR drop). This is a structural fact of the code, independent of any constant.
- The Sport **current/demand ceiling is 560 counts** and your measured plateau was **20.35 A** — so at the dip you were at or near the ceiling, i.e. current was not being left on the table by a low ceiling. **[C ceiling; owner-measured amps]**

**What is only model [L]:** the exact speed of roll-off needs the motor constant (V per km/h of back-EMF), which the files do not give. So instead of fitting `ke` to a watt reading, I use **only a ratio that cancels it**: the onset speed scales with the loaded battery voltage. Using your own sag (54.15 → 51.14 V at 20.35 A ⇒ 0.148 Ω) and **no absolute speed fit**, the onset at other rest voltages is `onset(V) = onset(54.15 V) × V_loaded(V) / 51.14`. The only place an absolute speed enters is your **recalled** 20–22 km/h at 54.15 V, and that anchor is quoted as recalled, not measured — the *ratios* in §4 do not depend on it. `scripts/s10_predictions.py` → `evidence/s10_predictions.md`.

**The first limiter that could bind below 25 km/h, and what would show I'm wrong.** Ranked by what the code supports:
1. **Voltage headroom (no field weakening)** — the structural one above. **[C structure / L operative]**
2. **The phase-current / modulation limiter** `0x8bf4`+`0x1d654`: lowers the drive command when battery DC current exceeds the demand envelope *or* q-current exceeds **1461 counts**. If this binds first, current clamps at a **fixed count regardless of voltage**, so the fade speed would **not** drop at lower charge. **[C it exists / U whether it binds first]**
3. **Battery-side remote current cap** arriving over UART (Task 4) — a BMS-driven ceiling independent of controller voltage.

**Falsifier for the voltage-headroom explanation:** if the watt-drop speed **stays at 23–25 km/h at 48 V rest** (within your ±1.5 km/h voice-read noise), voltage headroom is *not* the operative limiter and it is a fixed speed/current limit (candidate 2 or 3). If instead the onset **drops to ~17–20 km/h at 48 V**, headroom is confirmed and a fixed limit is ruled out.

---

## 4. Numeric predictions for your rides

Full-throttle, Sport, flat, median of ≥2 runs per level; dashboard speed read by voice (±1.5 km/h). Generated by `scripts/s10_predictions.py` from code facts + your 2026-10-03 sag (0.148 Ω). The **ratio column is the real test** — it does not use the recalled speed anchor.

**(A) Where power starts to fall (voltage-headroom hypothesis).** Battery-current ceiling ≈ 20.4 A; loaded V at the ceiling = rest − 20.4 A × 0.148 Ω.

| Rest voltage | Loaded V at 20.4 A | Onset ratio vs the 54.15 V run | Onset if the 20–22 km/h anchor holds | Peak electrical power |
|---|---|---|---|---|
| 54 V (~100 %) | 51.0 V | 1.00 | 19.9–21.9 km/h | ~1040 W |
| 50 V (~50 %) | 47.0 V | 0.92 | 18.4–20.2 km/h | ~960 W |
| 48 V (~30 %) | 45.0 V | 0.88 | 17.6–19.4 km/h | ~915 W |
| 46 V (~low) | 43.0 V | 0.84 | 16.8–18.5 km/h | ~875 W |

Internal resistance rises at low charge and in the cold, pushing the low-voltage onsets a little lower still.

**Failure threshold (one number):** at **48 V rest**, if the median watt-drop speed is **≥ 23 km/h**, the voltage-headroom hypothesis has failed — the limiter is speed/current-fixed, not voltage. (Equivalently: a drop of less than ~3 km/h in onset between 54 V and 48 V refutes headroom, given your ±1.5 km/h noise and 2+ runs.)

**(B) Coast regen onset (54.0 V gate).** Max coast-regen current before the reading reaches 54.0 V = (54.0 − open-circuit V)/0.148 Ω:

| Open-circuit V | Coast regen current the gate allows |
|---|---|
| ≥ 54.0 V | ~0 A (gate shut) |
| 53.6 V | ~2.7 A |
| 53.4 V | ~4.1 A |
| 53.0 V | ~6.8 A |
| ≤ 52 V | not gate-limited (other limits apply) |

**Regen failure threshold:** if, at a rest voltage **below ~53 V**, coast regen is still absent on a downhill, the 54.0 V gate is **not** the controlling mechanism and something else suppresses regen.

**Most valuable single measurement:** the **~30 % / ~48 V full-throttle Sport run** in (A). It is the one that cleanly separates the two power-fade hypotheses; everything else refines. Record rest voltage, then watts/amps/volts and the dashboard speed at the first sustained watt-drop. Second most valuable: a **coast-down from ~30 km/h at ~53 V** reading the speed where regen first bites, to test the gate in (B).

---

## 5. Self-audit — the 5 statements I'm least sure of

1. **"The 23–25 km/h fade is voltage headroom (no field weakening)."** Confidence: the no-field-weakening *structure* is [C]; that it is the *operative* limiter at your dip is [L]. **How to prove it wrong:** the 48 V run in §4 — if onset stays ≥ 23 km/h, this is wrong and it's a fixed speed/current limit.
2. **"27.5 counts per amp" (and the whole amps axis).** From a single owner ride (560 ↔ 20.35 A); [L]. **Prove it wrong:** log app amps at a known steady demand at two different throttles; if amps/count isn't ~27.5, every amp figure here shifts.
3. **"The 54.0 V coast gate is the main reason regen fails near full."** [S]. **Prove it wrong:** a downhill below ~53 V rest with still-absent coast regen (§4B) would show the gate isn't controlling; or an app-vs-controller voltage offset large enough to move the effective gate.
4. **"RC02 cannot affect the power button / sleep / wake."** [C by the identity + data-flow checks]. **Prove it wrong:** find a power-path function I did not seed that (a) reads a RAM byte a changed RC02 function writes in *changed* code and (b) uses it in the P3.9 or sleep decision. My seed set was the GPIO3/SYS/AON/PWRDN/UART/`0x99fc`/`0x96cc` closure (68 functions); a reachable path outside it would break the claim. I consider this low-risk but not zero.
5. **"Battery-side temperature/SOC reach the controller only as UART telemetry (RAM `0x328`, the SOC set), not local controller sensors."** [C for the UART `0x74` decoder and the write to `0x328`]; [L] that *no* local controller channel also feeds the remote cap. **Prove it wrong:** a local ADC path writing `0x328`/the SOC bytes that my constant-tracker missed (it ignores register-offset `[rX,rY]` stores).

**Secondary uncertainties worth stating:** the exact volts-per-count (anchored to the charger/gate, not measured); the thermal derate entry (102.0 °C) is a prior-work value I cross-checked via the 560/K pairing, not re-derived end-to-end; "seconds" from scheduler ticks are nominal (~5.12 ms/slot, not re-measured).

**What I could not finish.** Absolute phase-current/motor-constant/volts-per-count calibration (needs a measured point); the BQ769x2 hard trip thresholds (in the chip's data memory, not plaintext here); the physical button wiring and all dashboard-side behaviour (firmware not in the package); deep reading of the battery-side program (~5 % of bodies read); a measured scheduler tick.

---

### Deliverable file hashes (this folder)

Computed at write time; regenerate with `sha256sum`.

```
65102c0126263fb1f88dc88a7998134d8797da6439078afbcd068bbf28032d6e  OPUS_FROM_SCRATCH_REPORT.md
3b5fa0f747ad2fb714e7c20dca9e44f211df18763af5d1ef635698b29e8c2913  evidence/s00_public_sources.md
475cd99bd4ee75da2687e2bcc61d72e784c7183823912117c05480ab5b11c138  evidence/s09_coverage.md
ddb7bc7e3f1a4f7364dbef3054ce10704f68b962e42e7b3ca97d8375cda7e2fb  evidence/s10_predictions.md
a750b1e813c58595bf461de40a17c29e3b1b0da61d28070c83992b26aa3527cc  evidence/s05_power_path.json
452eddf663de91234b89cf8d5e1891a872af466dcb7ccd5071fab01a5d2c591f  evidence/s07_progA_bq769x2_calls.md
265b65aa65794f71a760e2a8c0c3343c2a496f4aa8cc0526e73a6a903c670752  evidence/s01_layout_and_checksums.json
d5609c175680676f955dd4a486fe02f7b84b9cd77a134981676e4fdd96efe0bd  scripts/fwlib.py
b69cc65bd8e73d9834beaf81dbacdb949aad48689d6c6bcb6c3b48e4ba5a5dd7  scripts/s01_layout_and_checksums.py
59c02f4a85dd8a6f446f5124178c400e4643a638a876f1edb61550cbcd42b70c  scripts/s02_survey.py
dbdfe34ce96e983d41d234450df23892d45c694df158ee0938e47ed651ff411c  scripts/s03_disasm_dump.py
d9d7da46b6ab65f0959ab98263e40ae48b2e274bf7797dd353b296dd42cb24dd  scripts/s04_mc_initram.py
06083165b837eb021f5c40963c3417dc1b81677f5749bfe6bedcdac251e13643  scripts/s05_power_path.py
d649f761ae0323b6a28df6891b3762e1ca61dfb6d86ae6182ef739db0dc950d7  scripts/s06_diff_context.py
ceae70276f87ad65970a6cb28fa1f4fcbb575cf47b0ac0c2a7f08694b8f33798  scripts/s07_progA_bq769x2.py
a6311473ca520816e8ba330153330b75fef4305a2795df6578ba24cff574177e  scripts/s09_coverage.py
aff7c33fb0d65bb0ca5f3c934c6de1f6e4e486170af1469cc4b3bc6915a6a752  scripts/s10_predictions.py
5339638d942aadea3053d626e36c8492edf5a6fd89b7fa130b45011bc12ba3ae  scripts/run_all.sh
```
