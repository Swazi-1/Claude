"""P2 calibration table from executed code facts + independent anchors.
Run after p1_experiments.py / p1_svpwm.py:  MI5MAX_ROOT=<root> python p2_calibration.py OUTDIR
Assertions compare INDEPENDENT anchors and fail if they disagree beyond the stated bands."""
import json, math, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from opus_emu import M0, load_initial_ram, image
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '../evidence')
checks = []
def check(name, ok, detail=None):
    checks.append(dict(check=name, ok=bool(ok), detail=detail)); print(('OK   ' if ok else 'FAIL ') + name, detail if detail is not None else '')

# ADC front end (executed init 0x1C84C, manual 5.2.4 / 12.1.6 / 12.2.5.1)
m = M0('farm', load_initial_ram('farm')); m.u.mem_map(0x20000, 0x10000); m.u.mem_write(0x20000, b'\xff' * 0x10000)
m.call(0x1C84C, count=2_000_000)
gain0 = struct.unpack('<I', m.u.mem_read(0x40010464, 4))[0]; gain1 = struct.unpack('<I', m.u.mem_read(0x40010564, 4))[0]
chn0 = struct.unpack('<2I', m.u.mem_read(0x40010450, 8)); chn1 = struct.unpack('<2I', m.u.mem_read(0x40010550, 8))
m2 = M0('farm', load_initial_ram('farm')); m2.call(0x1D59C); afe0 = struct.unpack('<I', m2.u.mem_read(0x40000010, 4))[0]
check('ADC: DC-current slot (ADC0 DAT2) and voltage slot (ADC0 DAT3) use the +-3.6 V range; phase-current slots too',
      not (gain0 >> 2) & 1 and not (gain0 >> 3) & 1 and not gain0 & 3 and not gain1 & 1, dict(ADC0_GAIN=hex(gain0), ADC1_GAIN=hex(gain1),
      ADC0_CHN=[hex(x) for x in chn0], ADC1_CHN=[hex(x) for x in chn1], SYS_AFE_REG0=hex(afe0)))
counts_per_volt = 2048 / 3.6
opa_gain = (320e3 / 10e3, 320e3 / (10e3 + 2e3))          # RES_OPAx=00 -> 320k:10k, external R0 0..2k (manual 5.1.5)

# FE -> volts
k_fe_code = 8850 / 16384 / 10                               # volts per FE count from 0x210 decivolts
div_needed = (1 / k_fe_code) / counts_per_volt              # pin volts per bus volt -> 1/ratio
ratio = 1 / div_needed
check('FE scale: implied divider ratio is within 2 % of a standard 300k:10k (31:1) divider', abs(ratio / 31 - 1) < 0.02, round(ratio, 2))
anchors_V = dict(code_540_gate=54.0, mapper_100pct_FE1007=1007 * k_fe_code, charger_spec=54.6, owner_rest=54.15)

# DC -> battery amps
ev = json.loads((OUT / 'P1_power_dip_evidence.json').read_text())
steady = ev['B_forced_speed_plant']['steady']
mean_dc_farm = sum(r['DC'] for r in steady['farm'] if r['kmh'] <= 20) / len([r for r in steady['farm'] if r['kmh'] <= 20])
mean_dc_stock = sum(r['DC'] for r in steady['stock'] if r['kmh'] <= 20) / len([r for r in steady['stock'] if r['kmh'] <= 20])
k_owner = 20.41 / mean_dc_farm
k_xiaomi, k_xiaomi_err = (1000 / 54.6) / mean_dc_stock, (50 / 54.6) / mean_dc_stock
check('DC scale: owner anchor (20.41 A at farm EA 560) and Xiaomi anchor (1000+-50 W at 54.6 V, stock EA 493) agree within the Xiaomi tolerance',
      abs(k_owner - k_xiaomi) <= k_xiaomi_err + 0.0005, dict(mean_regulated_DC_farm=round(mean_dc_farm, 1), mean_regulated_DC_stock=round(mean_dc_stock, 1),
      k_owner=round(k_owner, 5), k_xiaomi=round(k_xiaomi, 5), k_xiaomi_err=round(k_xiaomi_err, 5)))
k_dc = (k_owner + k_xiaomi) / 2
reg = (mean_dc_farm / 560 + mean_dc_stock / 493) / 2     # executed closed loop: mean DC / EA
shunt_x_gain = 1 / (counts_per_volt * k_dc)
check('DC scale is physically plausible: implied shunt with OPA gain 26.7..32 lies in 1..3 milliohm',
      1e-3 <= shunt_x_gain / opa_gain[0] and shunt_x_gain / opa_gain[1] <= 3e-3,
      dict(shunt_mohm=[round(1e3 * shunt_x_gain / g, 2) for g in opa_gain]))

# q counts: only bounded
q_per_A = {f'{r} mohm': [round(counts_per_volt * g * r * 1e-3, 1) for g in opa_gain] for r in (1, 1.5, 2, 3)}
svp = json.loads((OUT / 'P1_svpwm_evidence.json').read_text())
table = [
    dict(quantity='speed A6 / 1AC (status bytes 9-10)', unit='0.1 km/h per count (speed = 224427/period/10)', grade='strong evidence',
         error='+-5..10 % against ground (wheel size/pole count not measured)', needs='GPS or wheel-revolution timing at steady speed'),
    dict(quantity='FE raw bus voltage', unit=f'{k_fe_code:.5f} V/count (54.0 V at FE 1000)', grade='strong evidence',
         error='+-1.5 % (BGP reference +-0.8 %, divider resistors +-1 %)', anchors=anchors_V, implied_divider=round(ratio, 2)),
    dict(quantity='0x210 converted voltage', unit='0.1 V per count (FE*8850>>14, file 0x22F46)', grade='confirmed arithmetic; volts strong evidence', error='as FE'),
    dict(quantity='DC (0xDC) battery-side current', unit=f'{k_dc:.4f} A/count', grade='strong evidence (two independent anchors)',
         error='+-5 %', note=f'regulated mean DC = {reg:.3f} x EA in the executed closed loop'),
    dict(quantity='EA/CA/C8 demand envelope', unit=f'battery current ~ {k_dc:.4f} x {reg:.3f} x EA A; watts = that x loaded bus volts', grade='strong evidence',
         examples=dict(EA560=f'{reg*560*k_dc:.1f} A ~ {reg*560*k_dc*50.9:.0f} W at 50.9 V', EA493=f'{reg*493*k_dc:.1f} A ~ {reg*493*k_dc*54.6:.0f} W at 54.6 V', EA274=f'{reg*274*k_dc:.1f} A'), error='+-6 %'),
    dict(quantity='Vq command DA / 140 / 11C', unit='1023 = line-line peak equal to bus (phase peak Vbus/sqrt3), executed SVPWM', grade='confirmed (code executed)',
         error='+-2 % dead-time', evidence=svp['result']),
    dict(quantity='0x1AE normalised back-EMF', unit='line-line back-EMF peak / FE x 1023 (file 0x1B7EC), written into 11C at flying start', grade='confirmed arithmetic; equal dividers assumed', error='unknown'),
    dict(quantity='q (0x132) / d (0x130) phase current', unit='counts per A peak = 569 x G x R_shunt', grade='cannot be calibrated without the phase shunt value and external R0',
         bounds=q_per_A, if_phase_shunt_equals_dc_shunt=round(counts_per_volt * shunt_x_gain, 1)),
    dict(quantity='q -> wheel force', unit='F = 1.5 x 3.6 x ke x Iq_peak (N); ke fitted 1.0..1.13 V per km/h (phase peak) under P1 hypothesis b',
         grade='likely interpretation (model-fitted)', example='~5.9 N per A peak; 1461 counts ~ 317 N if 27 counts/A'),
    dict(quantity='coast regen targets B4 91/160/320', unit='q-current targets (counts), farm Strong 320', grade='confirmed role; amps need q scale',
         example='at 27 counts/A: 3.4 / 5.9 / 11.9 A peak ~ 20 / 35 / 70 N'),
    dict(quantity='C2 local temperature', unit='0.1 degC (NTC line (340800-213x)/100, IIR 1/8)', grade='strong evidence', error='sensor placement unknown'),
    dict(quantity='0x328 remote temperature', unit='degC (sign-magnitude from BMS frame 0x74/0x44 byte 9)', grade='likely interpretation'),
    dict(quantity='BMS current (first image)', unit='raw x10 -> likely mA; 22000 trip = ~22 A for 80 calls (~8 s)', grade='likely interpretation'),
    dict(quantity='scheduler tick', unit='1.0241667 ms nominal (16 PWM periods of 64.01 us)', grade='confirmed configuration; wall time not measured', error='PLL accuracy; flag coalescing under load'),
]
res = dict(table=table, checks=checks)
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'P2_calibration.json').write_text(json.dumps(res, indent=1))
sys.exit(0 if all(c['ok'] for c in checks) else 1)
