# Opus-next scripts and evidence

Companion files for [`../OPUS_NEXT_INVESTIGATION_REPORT.md`](../OPUS_NEXT_INVESTIGATION_REPORT.md).

- `scripts/` — analysis code (Python ≥ 3.11, `capstone==5.0.9`, `unicorn==2.1.4`). Read-only: no firmware is written, no file to flash is produced, nothing talks to a device.
- `evidence/` — JSON results and run logs produced by those scripts.

Reproduce everything:

```bash
pip install capstone==5.0.9 unicorn==2.1.4
export MI5MAX_ROOT=/path/to/MI5Max_Opus_Next_Investigation   # the extracted project ZIP
bash scripts/run_all.sh evidence
```

`opus_emu.py` refuses to run if any firmware SHA-256 differs from the project's canonical values. `p3_regen.py` exits 1 on purpose: one pre-registered expectation about the proposed regen taper failed, and that failure is part of the result.
