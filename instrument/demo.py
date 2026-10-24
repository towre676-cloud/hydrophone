"""Reproducible synthetic raw-record demonstration using real Dyletsky targets."""
from __future__ import annotations
import csv, hashlib, json, math, random, struct, wave
from pathlib import Path
from .run import analyze_run, load_json

REPO=Path(__file__).resolve().parents[1]
SCORE=REPO/'design/fusion_design/dyletsky/output/instrument_score.json'

def demo(output_dir):
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    score=load_json(SCORE); targets=score['calibration_targets']
    freqs=[t['target_Hz'] for t in targets]
    gains=[.7,.4,.9,.55]; phases=[.3,-.5,.7,-.1]
    ref_gains=[.5,.6,.8,.7];ref_phases=[.1,.05,-.2,.3]
    rate=8192; duration=2.; noise=random.Random(20261024)
    pcm=bytearray()
    for i in range(int(rate*duration)):
        t=i/rate
        drive=sum(.04*math.cos(2*math.pi*f*t) for f in freqs)
        response=.013+.002*(t-1)+sum(.04*g*math.cos(2*math.pi*f*t+p) for f,g,p in zip(freqs,gains,phases))
        reference=-.009-.001*(t-1)+sum(.04*g*math.cos(2*math.pi*f*t+p) for f,g,p in zip(freqs,ref_gains,ref_phases))
        for sample in (drive,response,reference):
            sample+=noise.uniform(-1e-5,1e-5)
            assert abs(sample)<1
            pcm.extend(struct.pack('<h',round(sample*32767)))
    wav=out/'synthetic_channels.wav'
    with wave.open(str(wav),'wb') as w:
        w.setparams((3,2,rate,0,'NONE','not compressed'));w.writeframes(pcm)
    slow=out/'synthetic_slow.csv'
    with slow.open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['time_s','force_N','displacement_m','temperature_C','stage'])
        f_hold=1+math.exp(-1/.4)
        for i in range(401):
            t=i/100
            if t<1:x=.0002*t; force=.15+10000*x;stage='load'
            elif t<=2:x=.0002;force=.15+1+math.exp(-(t-1)/.4);stage='hold'
            elif t<=3:x=.0002*(3-t);force=.15+f_hold*x/.0002;stage='unload'
            else:x=0.;force=.15;stage='rest'
            w.writerow([t,force,x,20.,stage])
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    run={'schema':'hydrophone.signal-run/1','run_id':'dyletsky-four-target-synthetic-v1','data_origin':'synthetic',
         'specimen_id':'NO_PHYSICAL_SPECIMEN','history_protocol':'declared synthetic load/hold/unload/rest',
         'source_score_sha256':digest(SCORE),'rod_state':'synthetic_disconnected_write',
         'calibration':{'slow_declared':False,'pressure':None,'force':None},
         'clock_alignment':{'status':'synthetic construction only; no measured clock certificate'},
         'audio':{'path':wav.name,'sha256':digest(wav),'drive_channel':0,'response_channel':1,'reference_channel':2,
                  'frequencies_Hz':freqs,'start_s':0.,'end_s':duration},
         'slow':{'path':slow.name,'sha256':digest(slow),'displacement_closure_tolerance_m':1e-9,
                 'force_return_tolerance_N':1e-9,'hold_window_s':[1.,2.], 'max_hold_drift_m':1e-9,
                 'force_error_N':.01,'displacement_error_m':1e-6}}
    manifest=out/'run.json';manifest.write_text(json.dumps(run,indent=2)+'\n')
    result=analyze_run(manifest)
    errors=[]
    for tone,g,p in zip(result['audio']['tones'],gains,phases):
        ratio=tone['response_over_drive']; error=abs(complex(ratio['real'],ratio['imag'])-g*complex(math.cos(p),math.sin(p)))
        errors.append(error)
    if max(errors)>=.001:raise AssertionError('Synthetic complex gain recovery failed')
    result['synthetic_truth']={'response_gain':gains,'response_phase_rad':phases,
        'max_complex_gain_error':max(errors),'status':'known generated values, not physical truth'}
    (out/'analysis.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    summary={'schema':'hydrophone.instrument-demo-receipt/1','data_origin':'synthetic',
        'dyletsky_target_count':len(freqs),'frequencies_Hz':freqs,
        'max_complex_gain_error':max(errors),'source_audio_sha256':digest(wav),
        'source_slow_sha256':digest(slow),'hardware_execution_enabled':False,
        'physical_calibration_verified':False,'analysis_file':'analysis.json'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary
