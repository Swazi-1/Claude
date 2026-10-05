# Motor-voltage study (program B), scripts and evidence

Report: [`../MOTOR_VOLTAGE_REPORT.md`](../MOTOR_VOLTAGE_REPORT.md). Offline only; nothing built or flashed.

Run (Python 3.11+, `pip install capstone unicorn numpy`):
```
export MI5MAX_ROOT=<extracted MI5Max_project folder>
cd scripts
python e1_svpwm_sweep.py ../evidence
python e2_svpwm_edges.py ../evidence
python e3_deadtime_fundamental.py ../evidence
python e3b_options_fundamental.py ../evidence
python e5_scale_patch.py ../evidence
python e4_vscooter_variants.py ../evidence      # ~6 min, uses 06_VIRTUAL_SCOOTER
python e4b_sensitivity.py ../evidence           # ~4 min
```
The scripts check the firmware hashes before running. Firmware images are not in this repository.
