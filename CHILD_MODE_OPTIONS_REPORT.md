# Xiaomi 5 Max: quicker ways to switch on speed-limit ("child") mode

Date: 2026-10-03. Research, reasoning and a test plan only. **Nothing was sent to the scooter, nothing was flashed, no file to flash and no scooter code was produced.**

Package check: `MI5Max_ChildMode_Options_2026-10-03.zip` SHA-256 = `99b0305a1585eb504d0912a31e6fe3f8cec1da8986e73002c1958ec1043ca196`. This **matches** the value in your prompt. You also attached a separate file, `04_V8_RC02_SPORT35_REVIEW_ONLY_NOT_FLASH_READY.bin` (SHA-256 `f1037de2…3abe1a`), which is not part of the package. Its hash matches the RC02 short hash (`f103…be1a`) in the earlier report. As your brief asked, I did **not** analyse it.

Evidence labels: **confirmed**, **strong evidence**, **likely**, **unknown**. "Official" means a Xiaomi page or manual. "Community" means a hobbyist write-up: useful, but not checked by Xiaomi and usually tested on a sibling model rather than a 5 Max.

---

## Summary

**What we now know**
- Xiaomi's app has three energy-recovery levels for the 5 Max: Low / Medium / High. Low is the default. **confirmed** (official)
- On Brightway-made scooters (the family the 5 Max belongs to), the app's values are **Weak = 0x1E (30), Middle = 0x3C (60), Strong = 0x5A (90)**. The dashboard passes the same 0x1E / 0x3C / 0x5A to the motor controller. **strong evidence** (two independent community sources; neither was measured on a 5 Max)
- So "Medium = 60, which switches your caps on" is very probably right. But it only works on the custom firmware: you say stock software ignores the value 60.
- Xiaomi has **no** official child mode, kids mode or app speed limit for the 5 Max. **strong evidence** (official FAQ and manual list none)
- Xiaomi's own instructions say **"Do not cycle through the riding modes when riding the scooter"**, and the button sits in the middle of the handlebar. **confirmed** (official)

**What we do not know**
- Which firmware is on your scooter right now. Everything about the Medium route depends on this.
- Whether your 5 Max's dashboard really sends exactly 60 for Medium, all the time. Xiaomi's 5 Max page says the scooter "automatically adjusts the energy recovery intensity" on hills. If the dashboard does that by changing this value, a check for "exactly 60" could fail. **unknown**
- The order in which a double press cycles the modes, and whether the six-press switch and the "Medium" switch cancel each other out.
- How the cap feels on a real ride, especially downhill. The cap stops the motor from pushing; it does not brake you to hold speed.

**What to do next**
1. Do the stationary and low-speed checks in Task 5 (about 20 minutes, flat empty area, standard mode D only, never above about 20 km/h).
2. If T3–T5 pass, use the recommendation in Task 6: **set Medium in the app while stopped, then power off and on (or double-press once)**. Use Strong to switch it off again.
3. Do not switch the cap on while riding (see Task 4). If you ever do, be below 15 km/h, on the flat.

---

## Task 1: Checking your reasoning

### Points that do not follow, or are stated too strongly
1. **"A second way to switch on the caps" exists only on custom firmware.** Section 2 says stock software ignores the value 60. So route (a) works only while your modified controller firmware is installed. The summary never says which firmware is on the scooter today (stock, farm, RC01 or RC02). This is the single biggest missing fact. (The six-press gesture may also be custom-firmware-only; the summary does not say.) **unknown**
2. **"30 / 60 / 90 appear to mean Low / Medium / Strong" can be upgraded, but not to "confirmed".** Two independent community sources agree (Task 2). Neither was captured on a 5 Max, so it is **strong evidence**, not confirmed.
3. **The simulated situation (riding in the top mode at ~30 km/h and then the cap switching on) probably cannot happen through the Medium route.** You say the cap only takes effect at a riding-mode change or at power-on. A mode change always *leaves* the mode you are in. So, assuming the usual cycle walking → D → S → walking (**unknown** for your scooter):
   - D → S with the cap on: S is capped at 20. If D's own limit is 20 or less, nothing slows down at all.
   - S → walking: the speed target drops to 6 because of the mode change itself, cap or no cap. That is normal mode-change behaviour, and Xiaomi says not to do it while riding.
   - walking → D: you are at 6 km/h or less, below the 15 km/h cap, so nothing happens.

   So the section 3 simulation is a **worst-case bound**, not the usual case. The only exception is if your firmware's D mode is faster than 20 km/h. **likely**, depends on the mode order and on D's speed in your firmware
4. **The cap is a drive limit, not a speed governor.** The summary says the controller "stops driving and coasts". On a downhill, coasting means the speed can rise *above* the cap. There is only gentle regen, and from the earlier report (P3), almost none near full charge, when the battery is above about 53.5 V. "Holds about 20" is true only on the flat. **strong evidence** (from your own description plus the earlier P3 findings)
5. **The 56 % charge "unexplained slow-down" may have a known cause.** The earlier report (P3) found that coast regen gets much stronger as battery voltage falls (full from the moment you let go at ≤ 52 V). At 56 % charge, regen probably joins in once driving stops, so the speed sinks below the cap. **likely** (not re-simulated). If so, at lower charge the cap feels like "letting go of the throttle with recovery on", which is still gentle, but test it (T8).
6. **"Exactly 60" is fragile.** A check for equality fails if the dashboard ever sends 59, 61 or a changing value. Xiaomi says recovery is auto-adjusted on hills (Task 2). If that happens on the dashboard side, the cap might fail to switch on at a mode change made on a slope. **unknown**
7. **The six-press counter can be triggered by accident.** It counts mode changes at a standstill, so a rider who fiddles with the button while stopped could switch the cap *off* with six double presses. The summary does not say whether the count resets after riding off or after a pause. **unknown**
8. **Who rides matters.** Xiaomi's official rider range for the 5 Max is **16–50 years, 120–200 cm, ≤ 120 kg**, and the manual says "Do not ride with anyone else, including children". **confirmed** (official FAQ, user guide). A speed cap lowers the risk for a younger or lighter rider but does not make the scooter a children's product. Local minimum-age rules may also apply.
9. Small point: in walking mode the cap (6 km/h) equals walking mode's own limit, so the cap only changes anything in D (20 → 15) and S (→ 20). In practice, **"S with the cap" ≈ a normal D**. The real value of the cap is that the rider *cannot raise the speed by changing mode*. **confirmed** (from your numbers)

### What is solid
- The motor controller does not see button presses. The dashboard works them out and sends a mode value. **strong evidence**: community notes describe a mode value in the dashboard's control frame ([bastelpichi UART](https://wiki.bastelpichi.de/uart)), and the earlier report's frame `51 10 06 33 01 88 64 00 5A E1 AE` fits that layout (byte 8 = 0x5A = Strong; I re-added the checksum: 0x1E1 → E1, correct).
- Six double presses = six mode changes = two full laps of three modes, so you end in the same mode you started in. This fits the 3-mode description. **likely**
- The caps 6 / 15 / 20 are the same numbers as the regional profile you found on an Egypt page (6 / 15 / 20). This suggests the cap table may be Xiaomi's own regional table reused by the firmware. **unknown**: I did not re-check that page.

### The facts that matter most and are still unknown (in order)
1. Which controller firmware is on the scooter now.
2. The value your 5 Max dashboard actually sends for Medium, and whether it stays at 60 (hills, battery level, right after power-on).
3. Whether the "Medium" cap and the six-press cap are combined with OR (either one switches the cap on) or cancel each other out.
4. The order of the modes when you double-press.
5. What happens downhill with the cap on.

---

## Task 2: Public research

### Official (Xiaomi)
| Finding | Label | Source |
|---|---|---|
| 5 Max: recovery intensity can be set to **low, medium, high** in the Xiaomi Home app; **default low**; Xiaomi recommends low | confirmed | [5 Max FAQ](https://www.mi.com/global/support/faq/details/KA-503885/) Q6; [5 Max energy recovery FAQ](https://www.mi.com/my/support/faq/details/KA-509200/) |
| App path on the sibling 4 Pro (2nd Gen): three-dot menu → **[Energy recovery intensity]** | confirmed for 4 Pro 2nd Gen; likely the same on 5 Max | [4 Pro 2nd Gen FAQ](https://www.mi.com/uk/support/faq/details/KA-235666) |
| 5 Max: "While going uphill and downhill, the scooter **automatically adjusts the energy recovery intensity**" | confirmed that Xiaomi says it; unknown which part does it and whether it changes the value sent | [5 Max product page](https://www.mi.com/global/product/xiaomi-electric-scooter-5-max/) |
| Modes: walking 6, D 20, S 25 km/h (the FAQ also names "S+"); "Press the power button twice to cycle"; **"Do not cycle through the riding modes when riding"**; speeds vary by country | confirmed | [5 Max FAQ](https://www.mi.com/global/support/faq/details/KA-503885/) Q23; [ride FAQ](https://www.mi.com/global/support/faq/details/KA-509197/) |
| Button is "at the bottom of the display"; one press = lights, double press = mode, hold 2–3 s = off. Walking mode: **taillight blinks red** | confirmed | [product page](https://www.mi.com/global/product/xiaomi-electric-scooter-5-max/); [user guide PDF](https://cdn.azams0.fds.api.mi-img.com/xiaomi-b2c-i18n-upload/User-Guide-Upload-mi.com/Personal_Care/60559-Xiaomi-Electric-Scooter5-Max-UserGuide-GL.pdf) |
| App functions listed: lock motor, TCS on/off, auto headlight, tail light, ambient light, firmware update. **No speed-limit or child setting is listed** | strong evidence (absence in official lists) | [5 Max FAQ](https://www.mi.com/global/support/faq/details/KA-503885/) Q15, Q26; user guide |
| **Lock motor** (app only): buttons stop working, alarm when moved | confirmed | [5 Max FAQ](https://www.mi.com/global/support/faq/details/KA-503885/) Q15 |
| Before activation in the app, the scooter beeps and is limited to 10 km/h; the limit is lifted after activation | confirmed | [activation FAQ (FR)](https://www.mi.com/fr/support/faq/details/KA-730454/); user guide |
| Rider age 16–50, 120–200 cm, ≤ 120 kg; "Do not use mobile phone… when operating"; "Do not ride with anyone else, including children" | confirmed | [5 Max FAQ](https://www.mi.com/global/support/faq/details/KA-503885/) Q2; user guide |

### Community (not official)
| Finding | Label | Source and reliability |
|---|---|---|
| Brightway dashboard → controller control frame `51 10 06 B3 B4 B5 TH BR B8 SUM AE`; **B8 = "Regen strength; stock uses 0x1E / 0x3C / 0x5A"** | strong evidence | [bastelpichi UART](https://wiki.bastelpichi.de/uart). Community wiki, open source. Lists "3 Lite, 4 Pro 2nd" as typical Brightway; does not say which value is Medium, but the order fits Low / Medium / Strong |
| App/dashboard register 0x0A `ENERGY_RECOVERY_INTENSITY [Weak=1E, Middle=3C, Strong=5A]` | strong evidence (for the 3 Lite) | [RoboCoffee, "Hacking Brightway scooters", 22 Feb 2023](https://robocoffee.de/?p=436). Independent researcher, measured on a **3 Lite**. The same register list has CRUISE_CONTROL and LOCK but **no speed-limit register** |
| 5 Max, 5, 5 Pro, 4 Pro 2nd Gen and 4 Ultra are Brightway; Pro 2 and 4 Pro (1st gen) are Ninebot-based, so their protocol notes do **not** transfer | strong evidence | [bastelpichi compatibility](https://wiki.bastelpichi.de/compatibility), [Brightway guide](https://wiki.bastelpichi.de/brightway) (community) |
| On the 4 Pro 2nd Gen the dashboard's Bluetooth chip is **locked with a password** against debug access | strong evidence (for that model) | [RoboCoffee, 29 Oct 2024](https://robocoffee.de/?p=897) (community) |
| On a different dialect (LEQI, e.g. 5 Elite) the controller "may cap mid [regen] if pack metric > 89" | likely, but only an **analogy**: a different maker and protocol | [bastelpichi UART](https://wiki.bastelpichi.de/uart). It shows that "Medium" handling can depend on battery level on some scooters; whether the 5 Max does this is unknown |

**Your specific question: 0/1/2 or 30/60/90?** On Brightway scooters it is **30 / 60 / 90 (0x1E / 0x3C / 0x5A)**. **strong evidence**, from two independent community sources, neither measured on a 5 Max.
**Does the dashboard filter it?** **unknown.** No source describes dashboard filtering. Xiaomi's "automatically adjusts… uphill and downhill" is the one hint that the value might change during a ride.

**Not used:** several search results claimed the Mi Home app lets parents "set a maximum speed limit" on Xiaomi scooters. They came from low-quality, apparently auto-generated sites and contradict Xiaomi's own FAQ, so I ignored them.

---

## Task 3: Realistic options, ranked

Ranked by: likely to work × simple × safe.

| # | Option | Status | Touches power button / wake / lights? |
|---|---|---|---|
| 1 | **(a) Medium recovery in the app, then one mode change or a power cycle, done while stopped** | likely; needs tests T3–T5 | No. Normal app setting plus a normal double press or a normal off/on |
| 2 | **(b) Six double presses while stopped** | confirmed works today | No. Uses the normal mode gesture |
| 3 | **(c) Walking mode as a manual limit** | confirmed (official) | No |
| 4 | **(d) Other app/settings routes** | none found | Lock motor: no, but see the warning |
| 5 | **(f) Change the gesture in the controller firmware** (e.g. fewer presses) | not designed; out of scope | **Flag:** any controller firmware change risks boot and power-hold timing (earlier report P5) |
| 6 | **(e) Anything on the dashboard side** | impractical | **Flag first: yes.** The dashboard decodes the button, power on/off, wake and lights |

### (a) Medium recovery + one mode change (or power-on)
- **What would have to be true:** the custom firmware with the "byte = 60" check is installed; the 5 Max dashboard sends 60 for Medium, from power-on and steadily; the check runs at a mode change and at power-on (confirmed only in simulation).
- **Missing evidence:** a real ride showing ~15 km/h in D after setting Medium (T4/T5); behaviour on hills; how it interacts with the six-press switch (T6).
- **What could go wrong:** nothing happens (wrong firmware or different value), so you are no worse off. It might work on the flat but not after a mode change on a hill (auto-adjust). It feels different when you let go of the throttle: Medium regen is stronger than Low, weaker than your usual Strong. You might forget that "Medium = cap" and wonder why your own scooter is slow.
- **Reversible:** fully. Set Strong (or Low), then power-cycle or change mode.
- **Bonus:** a rider cannot undo it with the button, because changing it needs the paired app. Check this in T6.
- **Without stopping?** Technically it applies at the next mode change. But changing mode while riding is against Xiaomi's instructions, takes a hand off the bar, and using a phone while riding is also against them. Treat it as a **standstill** method.

### (b) Six double presses while stopped (today's method)
- **True today:** confirmed by you and by the simulation.
- **Missing:** whether the counter resets after riding or after a pause. If it does not, a fiddling rider could switch it off.
- **Could go wrong:** it is slow (12 presses); a wrong count leaves you in a different mode; no indicator (as far as I know) shows the cap is on.
- **Reversible:** six more presses.

### (c) Walking mode
- **What is true:** an official 6 km/h mode; the taillight blinks red so you can see it from behind. **confirmed**
- **Problems:** 6 km/h is barely faster than a walk. The rider can leave it with one double press, so it is not a lock. Throttle normally needs a push-off to about 5 km/h first (official), so it may feel awkward.
- **Use it for:** first minutes on the scooter, crowded places.

### (d) App or settings routes
- **No official speed-limit or child setting** for the 5 Max. **strong evidence**
- **Lock motor:** this is not a speed limit. What it does while someone is riding is **unknown**, and it could be abrupt. **Never use it as a remote "slow down" on a moving rider.**
- **The pre-activation 10 km/h limit:** not a usable route. Getting it back would mean resetting and unpairing (a button-plus-throttle reset gesture) and living with constant beeping. Not recommended.
- **Low recovery** does not switch the cap on (per your simulation). Xiaomi recommends Low for beginners.

### (f) Controller-firmware gesture change (mentioned only)
For example: fewer standstill mode changes (3 still returns to the same mode), or "mode change while the brake lever is held". This would still only use values the controller already receives (mode, brake). I have **not** designed it, as your rules require. The earlier report found any controller change can affect the ~0.3 s boot and the power-hold behaviour behind one-press start (P5), so this needs the full power-button baseline (B1–B11) before and after.

### (e) Dashboard side
The dashboard firmware is not available. On the sibling 4 Pro 2nd Gen its chip is password-locked (community). It owns the power button, wake and lights. **Highest risk to your one-press power button. Not recommended.**

---

## Task 4: Is it OK to switch the cap on while riding?

**Short answer:** on flat ground, below the cap speed, yes: you would feel nothing. Above the cap, the simulation says it is gentle (like letting go of the throttle). But the trigger is a mode change, Xiaomi says not to change mode while riding, and pressing the button takes a hand off the bar. **Do it stopped.** If you ever do it moving, be under 15 km/h, on the flat, going straight.

### What the rider would feel (from your simulation, flat road, ~30 km/h start)
- 2–3 s: nothing obvious. The motor still pushes while its speed target slides down about 5 km/h each second.
- Then the throttle seems to "go dead": the scooter coasts. Speed falls by about 1 km/h each second or less (about 0.03 g), with only small regen (4–5 A).
- About 20 km/h after 10–14 s, then it holds (at full charge).

**My own rough check:** air drag plus rolling resistance for 100 kg at 20–30 km/h gives about 0.25–0.37 m/s², i.e. 0.9–1.35 km/h per second. The simulated 10–14 s to drop from 30 to 20 km/h fits plain coasting, so the numbers hang together. **likely**. A lighter rider slows a bit faster (around 1.5–2 km/h per second for ~65 kg in total), which is still like coasting a bicycle.

### What matters
| Condition | Effect | Label |
|---|---|---|
| **Speed vs cap** | Below the new cap: nothing happens. Far above it: a longer coast. Because the cap only applies at a mode change, the "far above" case probably needs D faster than 20 or an S → walking change (see Task 1, point 3) | likely |
| **Downhill** | The cap stops the motor pushing but **does not hold speed**. Regen is gentle, and near full charge almost absent (earlier P3). The rider must brake | strong evidence |
| **Uphill** | When pushing stops, the scooter slows faster (on a 10 % slope about 1 m/s² ≈ 3.5 km/h per second). The controller should push again once speed falls below its target | likely |
| **Charge level** | At lower charge, regen when coasting is stronger, so expect it to sink below the cap a bit (the 56 % effect). Near full: no regen, pure coast | likely |
| **Hills + "exactly 60"** | If recovery is auto-adjusted on slopes, a mode change made on a hill might not switch the cap on | unknown |

### How far to trust the simulation
- **Trust most:** the controller's own logic (real code was run): the target ramp, cutting drive, no hard braking command. First ~10 s on the flat.
- **Trust less:** anything that depends on the motor, battery and rider model (assumed values, not checked against a ride), what happens after the first 10 s, and other charge levels.
- **Not covered:** slopes, a light rider, what the dashboard does, and which recovery level the simulation used. Moving activation can only come through Medium, so it should be run with 60.

---

## Task 5: A test plan you can do yourself

**Setup:** flat, empty, dry, straight area (a car park). Helmet. Charge 60–90 %. Tyres at 45–50 psi. Use **D mode as the "meter"**: no cap ≈ 20 km/h top speed, cap on ≈ 15 km/h. You never need S or more than ~20 km/h. Do all app changes and button presses **while stopped**, foot down. Read the speed on the dashboard. Write down the result of each step.

| Step | What you do | No cap | Cap on | What it tells you |
|---|---|---|---|---|
| T0 | In the app, note the firmware versions shown, and the current recovery level (should be Strong) | – | – | Which firmware is installed (key unknown #1). Keep the note |
| T1 | **Baseline.** Cap off (if unsure: check in T1 itself). In D, full throttle on the flat until the speed stops rising | ~20 | ~15 | Your "off" reading. If ~15, the cap is already on: do six double presses while stopped and repeat |
| T2 | **Mode order.** While stopped, double-press once at a time and note each mode (walking shows a blinking red taillight). Go back to D | – | – | Mode order (unknown #4). Needed to read Task 1 point 3 |
| T3 | Stopped. App: set recovery to **Medium**. **Do not press the button.** Ride D, full throttle | ~20 expected | ~15 | ~20 = matches "setting alone does nothing". ~15 = the value acts straight away (new information) |
| T4 | Stopped. Double-press until you are back in D (a full lap). Ride D | ~20 | **~15 expected** | **~15 = route (a) works.** ~20 = Medium is not 60 on your dashboard, it is filtered, the firmware lacks the check, or the trigger is different. Stop here; route (a) is not usable |
| T5 | Power off (hold 2–3 s), wait 5 s, power on with one press. Check one-press start still works. Ride D | ~20 | **~15 expected** | ~15 = it survives power-on (key for "set and forget"). ~20 = only works after a mode change |
| T6 | With Medium still set: while stopped, do the **six double presses**. Ride D. Then six more to undo | – | – | Still ~15 = OR (the rider cannot remove it with the button). ~20 = the two switches cancel out: write it down |
| T7 | **Switch off.** Stopped. App: set **Strong**. Power off/on. Ride D | **~20 expected** | ~15 | Confirms the way out. Repeat with **Low** (expect ~20) |
| T8 | (Only if T4–T5 passed) Medium set and cap applied. In D on the flat, full throttle until it settles; then **release** the throttle | holds ~15 | – | Feel the coast and regen at Medium. Repeat at lower charge another day (the 56 % effect) |
| T9 | (Optional, only if T4–T5 passed.) Cap off, Medium set, **in D at a steady 10–12 km/h** (below every cap), on the flat, going straight: one double press (→ next mode). Then gently ride on | no slowdown | stops at the new mode's cap | The safe "switch on while moving" case: you are below the cap, so nothing changes. **Skip it if you are not comfortable taking a hand off the bar** |
| T10 | (Optional) A gentle, short, known slope with the cap on: ride down without throttle, covering the brake | – | – | See whether speed goes above the cap downhill. Brake if it passes ~15 |

**Stop rules:** any jerk, a code on the display, an odd beep, or the scooter not powering on with one press → stop, set Strong, power-cycle, and write down what happened.

**How to switch it off again:**
- Medium route: app → **Strong** (or Low), then power off/on (or one double press).
- Six-press route: six double presses while stopped.
- If unsure: do both, then check top speed in D (~20 = off).

---

## Task 6: Recommendation

**Simplest approach, most likely to work and safest: set energy recovery to Medium in the app while the scooter is stopped, then turn the scooter off and on (or double-press once).** Switch it off with Strong plus off/on.

Why:
- It is one app tap plus a normal action. No new gesture, nothing near the power-button path.
- It stays on, and the rider cannot remove it with the button (if T6 shows OR).
- Fully reversible, and if it fails, nothing happens.
- It depends on the custom firmware and on T4/T5 passing. **likely**, not confirmed.

**Until T4/T5 pass, keep using the six double presses**: it is the method that is **confirmed** to work.

**Do not** try to switch it on while riding: it needs a mode change (against Xiaomi's instructions, and a hand off the bar), and there is no real benefit. "S with the cap" is about the same as a normal D. If you just want a lower speed for one ride, put the scooter in D, or walking for the very first minutes.

**Always remember:** the cap stops pushing; it does not brake. On a downhill the rider must brake. And Xiaomi's official rider range is 16–50 years.

### What I could not determine
- Which firmware is on the scooter now (only you can check: T0).
- A 5 Max measurement of the Medium value. My two sources are a 3 Lite and a general Brightway note.
- Whether the dashboard changes the recovery value on hills or by battery level (Xiaomi's "automatically adjusts" claim; no technical source).
- The mode order, the six-press counter's reset rules, and how the two switches interact (T2, T6).
- Real-ride behaviour of the cap, especially downhill and at lower charge. I could not re-run the simulation: there is no firmware in the package, and I did not analyse the separately attached `.bin`, as you asked.
- The Egypt 6/15/20 page you cited: I did not re-check it.
- Some Xiaomi pages blocked the normal fetch tool. I read them by downloading the page directly; the quotes above come from those downloads.
