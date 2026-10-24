"""Offline design arithmetic and evidence gate. No hardware driver or repo adapter.

Python >=3.10, standard library only. Run from any directory.
The 4-note ratio example is a NEW design fixture, not recovered Dyletsky output.
"""
from pathlib import Path
import json, math

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output'
LABELS = ['C','C#','Db','D','D#','Eb','E','F','F#','Gb','G','G#','Ab','A','A#','Bb','B']

def require_measured_run(run):
    """Refuse a physical acceptance claim when provenance/calibration is absent."""
    needed = ['specimen_id','raw_audio_path','slow_csv_path','calibration_id',
              'sync_residual_s','water_temperature_C','cartridge_mass_g',
              'history_protocol','source_refs','validity_domain']
    missing = [k for k in needed if run.get(k) is None]
    if run.get('data_origin') != 'physical_measurement':
        missing.append('data_origin=physical_measurement')
    if run.get('clipping') is not False:
        missing.append('clipping=false')
    if missing:
        return {'accepted':False,'reason':'missing_or_invalid_evidence', 'fields':missing}
    return {'accepted':True,'meaning':'provenance fields present only; scientific acceptance is separate'}

def main():
    OUT.mkdir(exist_ok=True)
    L, diameter, rho = .4, .0005, 1150.
    mu = rho*math.pi*diameter**2/4
    base = 440*2**(-9/12)
    notes = [('C4',0,1),('D4',2,9/8),('E4',4,5/4),('G4',7,3/2)]
    rows = []
    for name, steps, ratio in notes:
        et = base*2**(steps/12)
        f = base*ratio
        cents = 1200*math.log2(f/et)
        rows.append({'spelling':name,'equal_temperament_Hz':et,'ratio_fixture_Hz':f,
                     'offset_cents':cents,'ideal_nylon_tension_N':mu*(2*L*f)**2})
    result = {'status':'DESIGN_ARITHMETIC_NOT_MEASURED',
              'assumptions':{'speaking_length_m':L,'nylon_diameter_m':diameter,
                  'assumed_density_kg_m3':rho,'linear_density_kg_m':mu,
                  'warning':'Measure linear density; flexible bridge, stretch and end corrections change pitch.'},
              'spelled_pitch_labels':LABELS,'physical_simultaneous_voices':4,'notes':rows,
              'clay_nominal_shear_strain_at_0p5_mm':.5/8,
              'water_nominal_volume_litre':160*100*80/1e6,
              'synthetic_record_gate':require_measured_run({'data_origin':'synthetic','clipping':False})}
    assert len(LABELS)==17 and len(set(LABELS))==17
    assert all(abs(base*r - row['ratio_fixture_Hz'])<1e-12 for (_,_,r),row in zip(notes,rows))
    assert not result['synthetic_record_gate']['accepted']
    (OUT/'design_arithmetic.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
