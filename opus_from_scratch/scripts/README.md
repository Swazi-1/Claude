# Scripts (read-only analysis)

Python 3.11+, `capstone==5.0.9`, `unicorn==2.1.4`. Set `MI5MAX_ROOT` to the unpacked
`MI5Max_Opus_FromScratch` folder. Every script checks each image's SHA-256 first
(`fwlib.IMAGES`) and stops on a mismatch. Run everything with `bash run_all.sh`.

| script | what it does | output |
|---|---|---|
| fwlib.py | image loading + hash check, address maps (battery side: runtime = file + 0x08002000; motor controller: runtime = file − 0x17018), disassembly, function discovery (follows calls, switch tables, `ldr rX,=f; bx rX`), simple constant-address tracker | – |
| s01_layout_and_checksums.py | data regions, header fields, CRC-16/XMODEM (file 0x19800..end) and CRC-32/MPEG-2 (motor-controller body) for all 4 images, which regions differ | evidence/s01_layout_and_checksums.json |
| s02_survey.py | function discovery and hardware-register survey for both programs | evidence/s02_peripherals_*.txt, generated/s02_functions_*.json |
| s03_disasm_dump.py | annotated listing + RAM/peripheral cross-reference | generated/asm_*.txt, generated/xref_*.json |
| s04_mc_initram.py | emulates only the C-runtime RAM initialisation; compares with package work/default_initial_ram.bin | generated/s04_mc_initram_*.bin (printed comparison) |
| s05_power_path.py | power-button / power-hold / sleep / handshake path: byte identity stock vs RC02 and RAM data-flow overlap | evidence/s05_power_path.json, s05_power_path_stdout.txt |
| s06_diff_context.py | side-by-side listing of every changed region (for the owner's own review) | generated/s06_diff_*.md |
| s07_progA_bq769x2.py | battery-side program: every call into the BQ769x2-style I2C helpers with recovered constant arguments, named from the TI manual | evidence/s07_progA_bq769x2_calls.md |
| s09_coverage.py | mapped vs understood bytes per region | evidence/s09_coverage.md |
| s10_predictions.py | ride predictions from code facts + owner's sag measurement (no fitted motor constant) | evidence/s10_predictions.md |

Large generated files (full listings, cross-references, diff context) are written to
`evidence/generated/`, which is git-ignored because it reproduces the firmware almost
completely; re-create it locally with `run_all.sh`.

Limits of the tooling (so you know which checks could fail and which could not):
- The constant-address tracker is linear within a function and ignores register-offset
  accesses (`[rX, rY]`). It can miss writers. For the power-path question the overlaps it
  found were checked by hand, and the RC02 record words at 0x20000498..A7 (register-offset
  accesses) were traced manually.
- Function discovery misses code reached only through computed jumps it cannot resolve;
  "mapped" percentages are therefore lower bounds.
