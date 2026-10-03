#!/usr/bin/env bash
# Re-run every analysis step. Read-only: nothing is written to firmware,
# nothing talks to a device, no flashable file is produced.
# Needs: Python 3.11+, capstone==5.0.9, unicorn==2.1.4
# Usage: MI5MAX_ROOT=/path/to/MI5Max_Opus_FromScratch bash scripts/run_all.sh
set -euo pipefail
: "${MI5MAX_ROOT:?set MI5MAX_ROOT to the unpacked package folder}"
cd "$(dirname "$0")"
python3 s01_layout_and_checksums.py
python3 s02_survey.py > ../evidence/s02_survey_stdout.txt
for img in stock rc02 v71; do python3 s03_disasm_dump.py "$img" mc; done
python3 s03_disasm_dump.py stock a
python3 s04_mc_initram.py
python3 s05_power_path.py > ../evidence/s05_power_path_stdout.txt
python3 s06_diff_context.py stock rc02
python3 s06_diff_context.py v71 rc02
python3 s07_progA_bq769x2.py
python3 s09_coverage.py > /dev/null
python3 s10_predictions.py > /dev/null
echo "done; results in ../evidence (large listings in ../evidence/generated, not committed)"
