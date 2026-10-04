# Power-button test + flash checklist (V8.1 candidate)

Fill in the "Result" columns. Do the BEFORE test on the current firmware (V8 FINAL 600) first. Do the AFTER test with the same steps.

## Before flashing
- [ ] File size is 147,456 bytes
- [ ] SHA-256 is 9218c5ef58b78d39a172d6a85d5c046d5ff85e4bfaa3e644f1e04c20b4e2f63b
- [ ] Stock, RC02 and V8 FINAL 600 files are copied somewhere safe
- [ ] I know how to put V8 FINAL 600 back (method: ______________________)
- [ ] Scooter charged to 60 % or more; not plugged in during the flash
- [ ] BEFORE test below is done

## Power-button test (same steps before and after)
| Step | BEFORE (V8 600) | AFTER (V8.1) |
|---|---|---|
| 1. Scooter off, press power once: turns on right away? (yes/no, delay in seconds) | | |
| 2. Lights and display come on normally? | | |
| 3. Turn off the normal way: works? | | |
| 4. Repeat on/off 10 times: how many worked out of 10? | | |
| 5. Double-press changes riding mode? Lights on single press? | | |
| 6. Six mode changes while stopped: child mode toggles (only if you want to test it) | | |
| 7. With charger plugged in: powers on/off normally? | | |
| 8. After sitting 10 minutes off: turns on with one press? | | |
| 9. Anything odd (second press needed, flicker, delay)? | | |

If AFTER differs from BEFORE in any step: stop, do not ride, tell Claude the exact difference.

## While flashing
- Do not touch the scooter or the connection. No unplugging. Computer/phone must not sleep.
- If the tool shows an error: stop and write down the exact message. Do not retry blindly.

## After flashing
1. Power-button test (above).
2. Rear wheel off the ground: gentle throttle, check brake works.
3. App shows normal charge/voltage, no error codes.
4. Slow ride, check regen at low speed.
5. Sport at full throttle for a few seconds. Record below.

## Ride record (send to Claude)
| Item | Value |
|---|---|
| Charge level before | |
| Peak amps in app (Sport, full throttle) | expected about 22 A (25 A or more: tell Claude) |
| Peak watts in app | expected about 1.1 kW |
| Speed where current starts to drop | |
| Battery / controller / motor temperature before | |
| Battery / controller / motor temperature after | |
| Regen release at ~30 km/h: amps, and any delay? | |
| Anything odd (time, speed) | |

## If the power cuts out while riding
1. Let go of the throttle. 2. Wait 30 seconds. 3. Press power once. 4. Check the app for errors. 5. Still dead: plug in the charger for about a minute, then press power again. 6. Still dead: stop, do not keep trying, do not open the scooter, tell Claude what you see, hear and smell.
After it comes back: no full throttle right away; feel for hot parts; next time go back to V8 FINAL 600. Do not ride if there is a burning smell, something is very hot, or an app error will not clear.

## Revert
Flash V8 FINAL 600 (sha256 901ce6ce...df9) again with the same method.
