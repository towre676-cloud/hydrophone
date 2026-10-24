"""Synthetic end-to-end commissioning-file replay; no simulated clay claim."""
from array import array
import csv
from fractions import Fraction as F
import json
import math
from pathlib import Path
import sys
import wave
from .probe import compile_probe, sha256
from .synchronize import fit_clock
from .seal import seal_capture
from .run import analyze_run


def _write(path, value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def demo(output_dir, *, sample_rate=8000, target_path=None):
    root=Path(output_dir)
    if root.exists():
        raise ValueError('Bench demo directory must be new')
    root.mkdir(parents=True)
    if target_path is None:
        target_path=Path(__file__).resolve().parents[1]/'design/fusion_design/dyletsky/output/instrument_plan.json'
    plan=compile_probe(target_path,root/'capture',sample_rate=sample_rate,plateau_s=4)
    capture_root=root/'capture'
    # ADC time = 0.01 + 1.00002 * DAC time, purposefully nonzero offset/drift.
    offset,slope=.01,1.00002
    values=array('h')
    expected=[]
    for i,f in enumerate(plan['frequencies_Hz']):
        expected.append({'target_Hz':f,'adc_frequency_Hz':f/slope,
                         'gain':.4+.1*i,'phase_rad':-.3+.2*i})
    for frame in range(plan['frames']):
        t=frame/sample_rate
        source_t=(t-offset)/slope-1
        envelope=1. if .05 < source_t < 3.95 else 0.
        drive=response=reference=0.
        for tone in expected:
            phase=math.tau*tone['target_Hz']*source_t
            amplitude=.12/len(expected)*envelope
            drive+=amplitude*math.sin(phase)
            response+=amplitude*tone['gain']*math.sin(phase+tone['phase_rad'])
            reference+=amplitude*.8*math.sin(phase+.1)
        values.extend((round(32767*response),round(32767*reference),round(32767*drive),0))
    if sys.byteorder!='little':values.byteswap()
    audio=capture_root/'multichannel_audio.wav'
    with wave.open(str(audio),'wb') as stream:
        stream.setparams((4,2,sample_rate,plan['frames'],'NONE','not compressed'))
        stream.writeframes(values.tobytes())
    capture={'schema':'hydrophone.capture/1','status':'COMPLETE_NO_HOST_FLAGS',
        'capture_method':'SYNTHETIC_FILE_FIXTURE_NOT_A_DEVICE', 'missing_samples':0,
        'host_flags':[],'callback_error':None,'stream_error':None,
        'sample_rate_Hz':sample_rate,'channel_map':plan['input_channel_map'],
        'frames_received':plan['frames'],'frames_requested':plan['frames'],
        'probe_sha256':sha256(capture_root/'probe.json'),
        'raw_files':{role:{'path':name,'sha256':sha256(capture_root/name)} for role,name in
            [('multichannel_audio','multichannel_audio.wav'),('drive_command','drive_command.wav')]},
        'hardware_commands_issued':0}
    _write(capture_root/'capture.json',capture)
    for key,filename,clock_offset,clock_slope,error,source_error in [
        ('logger_time_s','logger',F('0.002'),F('1.0001'),'0.025','0.01'),
        ('drive_time_s','drive',F('0.01'),F('1.00002'),'0.00025','0.00001')]:
        csv_path=root/(filename+'_markers.csv')
        with csv_path.open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow([key,'audio_time_s'])
            for x in [F(0),F('2.5'),F('5.8')]:
                # Fraction strings preserve exact fixture marker declarations.
                writer.writerow([str(x),str(clock_offset+clock_slope*x)])
        clock=fit_clock(csv_path,source_key=key,declared_error_s=error,
            source_pick_error_s=source_error,audio_pick_error_s=str(F(1,sample_rate)),
            method='synthetic paired markers; no physical clock')
        _write(root/(filename+'_clock.json'),clock)
    slow=root/'slow.csv'
    with slow.open('w',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['logger_time_s','force_N','displacement_m','temperature_C','stage'])
        for i in range(301):
            writer.writerow([i/50,.1+.2*math.exp(-i/100),.0001,20,'hold'])
    metadata={'run_id':'synthetic-commissioning-join','specimen_id':'NO_PHYSICAL_SPECIMEN',
        'history_protocol':'synthetic file interface and clock replay only',
        'calibration_id':'NONE_SYNTHETIC','validity_domain':'synthetic signals, no mechanical model',
        'rod_state':'synthetic_not_applicable','data_origin':'synthetic',
        'gain_per_channel':[1,1,1,1],'drive_channel':'drive_loopback_raw',
        'response_channel':'hydrophone_raw','reference_channel':'bridge_acceleration_raw',
        'max_slow_gap_s':'0.020001','calibration':{'slow_declared':False},
        'slow_analysis':{'time_column':'logger_time_s'}}
    _write(root/'operator_metadata.json',metadata)
    sealed=seal_capture(capture_root/'capture.json',slow,root/'operator_metadata.json',
        root/'logger_clock.json',root/'drive_clock.json',root/'sealed')
    analysis=analyze_run(sealed['run_manifest'])
    errors=[]
    for actual,truth in zip(analysis['audio']['tones'],expected):
        ratio=actual['response_over_drive']
        reconstructed=complex(ratio['real'],ratio['imag'])
        desired=truth['gain']*complex(math.cos(truth['phase_rad']),math.sin(truth['phase_rad']))
        errors.append(abs(reconstructed-desired))
    _write(root/'analysis.json',analysis)
    result={'schema':'hydrophone.bench-replay/1','data_origin':'synthetic',
        'status':'PASS' if max(errors)<.002 else 'FAIL',
        'expected':expected,'max_complex_gain_error':max(errors),
        'nonzero_drive_drift_corrected':True,'raw_marker_replay_verified':True,
        'hardware_commands_issued':0,'physical_measurements_made':0,
        'physical_readiness_verified':False}
    _write(root/'summary.json',result)
    return result
