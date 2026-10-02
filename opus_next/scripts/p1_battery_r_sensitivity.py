"""Sensitivity of the P1 voltage-limit onset to battery resistance (analytic model of
p1_experiments).  Run: MI5MAX_ROOT=<root> python p1_battery_r_sensitivity.py OUTDIR"""
import json, sys
from pathlib import Path
out = Path(sys.argv[1] if len(sys.argv) > 1 else '../evidence'); sys.argv = sys.argv[:1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import p1_experiments as E
from p1_closed_loop import PLANT
ib = PLANT['k_dc'] * 547
rows = []
base = dict(PLANT); base['ke'] = E.fit_ke(dict(base), 750, ib)
for R in (0.11, 0.161, 0.21):
    p = dict(PLANT, R_batt=R); p['ke'] = E.fit_ke(dict(p), 750, ib)
    on, top, _ = E.characterise(p, ib)
    on2, top2, _ = E.characterise(dict(base, R_batt=R), ib)
    rows.append(dict(R_batt=R, refit_ke=dict(onset=on, top=top), fixed_ke=dict(onset=on2, top=top2)))
ok = max(abs(r['fixed_ke']['onset'] - rows[1]['fixed_ke']['onset']) for r in rows) <= 0.6
(out / 'P1_battery_r_sensitivity.json').write_text(json.dumps(dict(rows=rows, ok=ok), indent=1))
print(json.dumps(rows, indent=1)); sys.exit(0 if ok else 1)
