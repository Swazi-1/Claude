#!/usr/bin/env bash
# Reproduce every Opus-next experiment.  Usage:
#   MI5MAX_ROOT=/path/to/MI5Max_Opus_Next_Investigation bash run_all.sh [OUTDIR]
# Needs Python 3.11+ with capstone==5.0.9 and unicorn==2.1.4.  Read-only: no firmware is written, no device I/O.
set -u
OUT="${1:-../evidence}"
cd "$(dirname "$0")"
: "${MI5MAX_ROOT:?set MI5MAX_ROOT to the extracted project folder}"
status=0
run() { echo "== $*"; python3 "$@" > "$OUT/$(basename "$1" .py)_log.txt" 2>&1; rc=$?; echo "   exit=$rc"; echo "exit=$rc" >> "$OUT/$(basename "$1" .py)_log.txt"; [ $rc -eq 0 ] || status=1; }
run p1_experiments.py "$OUT"
run p1_svpwm.py "$OUT"
run p1_battery_r_sensitivity.py "$OUT"
run p2_calibration.py "$OUT"
run p3_regen.py "$OUT"          # expected to exit 1: one pre-registered expectation about the regen SPEC fails (see report)
for im in stock farm rc01 rc02; do python3 p4_static.py $im "$OUT" > "$OUT/p4_static_${im}_log.txt" 2>&1; done
run p4_stack_check.py farm "$OUT"
run p4_ram_evidence.py "$OUT"
run p4_timing.py "$OUT"
run p7_rechecks.py "$OUT"
exit $status
