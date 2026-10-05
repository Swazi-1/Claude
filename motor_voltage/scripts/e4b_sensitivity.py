"""E4b: cross-check against V10_IDEA_680_ANALYSIS section 5 (97 %, 2 deg downhill) and the sensitivity of the
field-weakening gain to the fitted reactance xl (halved, other parameters unchanged, so the baseline moves too)."""
import json, os, sys
from dataclasses import replace
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import e4_vscooter_variants as E
from calibrate import load_params
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '../evidence')
res = []
for c in (dict(), dict(k_om=1.025), dict(k_om=1.055), dict(id_fw=10), dict(id_fw=20)):
    r = E.launch(soc=97, slope=-2.0, **c); r['xl_scale'] = 1.0; res.append(r); print(json.dumps(r), flush=True)
base = load_params()
orig = E.load_params
E.load_params = lambda: replace(base, xl=base.xl * 0.5)
for c in (dict(), dict(k_om=1.055), dict(id_fw=10), dict(id_fw=20)):
    r = E.launch(soc=75, slope=-2.0, **c); r['xl_scale'] = 0.5; res.append(r); print(json.dumps(r), flush=True)
(OUT / 'E4b_sensitivity.json').write_text(json.dumps(res, indent=1))
