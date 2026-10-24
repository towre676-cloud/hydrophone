"""Compile actual full/reduced command files for the shared tuning experiment.

The two-second mathematical probe is embedded in a complete duplex timeline.
The last second is raw support padding, charged to reset overhead rather than
silently disappearing from the experiment's total-cost ledger.
"""
from array import array
import json
from functools import lru_cache
from pathlib import Path
import sys
import tempfile
import wave
from .probe import DEFAULT_CHANNELS, sha256


def _validate_v1_core(core):
    from evaluation.protocol import validate_contract,exact
    validate_contract(core)
    expected={'slow_feature_start':1,'slow_feature_end':2,'dyletsky_probe_start':2,
        'dyletsky_probe_end':4,'decision_deadline':5,'action_start':5,'action_end':17,
        'outcome_start':18,'outcome_end':20,'pitch_check_start':0,'pitch_check_end':1}
    timing=core['timing_s_relative_to_write_end'];settings=core['excitation']
    if (core.get('experiment_id')!='clay-history-tuning-v1' or
        any(exact(timing.get(k))!=value for k,value in expected.items()) or
        settings['sample_rate_Hz']!=48000 or exact(settings['duration_s'])!=2):
        raise ValueError('Episode compiler implements only the exact clay-history-tuning-v1 timeline')
    if len(settings['frequencies_Hz'])!=4 or exact(settings['frequencies_Hz'][2])!=exact(core['task']['target_Hz']):
        raise ValueError('The E4 target must match the third declared probe tone')


@lru_cache(maxsize=4)
def _registered_source_sha(core_canonical):
    from evaluation.render import render_probe
    with tempfile.TemporaryDirectory(prefix='registered-probe-') as temporary:
        result=render_probe(json.loads(core_canonical),Path(temporary)/'source.wav')
        return result['sha256']


def compile_episode_commands(core_path, output_dir):
    from evaluation.protocol import read_json, validate_contract, digest, exact
    from evaluation.render import render_probe
    core_path=Path(core_path).resolve();core=read_json(core_path)
    _validate_v1_core(core)
    timing=core['timing_s_relative_to_write_end'];settings=core['excitation']
    rate=settings['sample_rate_Hz']
    if (rate!=48000 or exact(timing['dyletsky_probe_start'])!=2 or
        exact(timing['dyletsky_probe_end'])!=4 or exact(timing['outcome_end'])!=20 or
        exact(settings['duration_s'])!=2):
        raise ValueError('Episode compiler implements the exact clay-history-tuning-v1 timeline')
    root=Path(output_dir)
    if root.exists():raise ValueError('Episode command output directory must be new')
    root.mkdir(parents=True)
    source=root/'source_probe.wav'
    render=render_probe(core,source)
    with wave.open(str(source),'rb') as stream:
        if stream.getparams()[:3]!=(1,2,rate) or stream.getnframes()!=2*rate:
            raise ValueError('Registered renderer produced an incompatible probe')
        source_pcm=stream.readframes(stream.getnframes())
    source_values=array('h');source_values.frombytes(source_pcm)
    if sys.byteorder!='little':source_values.byteswap()
    plans={}
    for arm in ('full','reduced'):
        folder=root/arm;folder.mkdir()
        (folder/'source_probe.wav').write_bytes(source.read_bytes())
        (folder/'experiment_core.json').write_bytes(core_path.read_bytes())
        values=array('h',[0])*(21*rate*2)
        if arm=='full':
            for i,value in enumerate(source_values):values[2*(2*rate+i)]=value
        if sys.byteorder!='little':values.byteswap()
        command=folder/'drive_command.wav'
        with wave.open(str(command),'wb') as stream:
            stream.setparams((2,2,rate,21*rate,'NONE','not compressed'))
            stream.writeframes(values.tobytes())
        plan={'schema':'hydrophone.episode-command/1','experiment_id':core['experiment_id'],
            'experiment_core_canonical_sha256':digest(core), 'protocol_arm':arm,
            'experiment_core':{'path':'experiment_core.json','sha256':sha256(core_path)},
            'source_probe':{'path':'source_probe.wav','sha256':sha256(source)},
            'source_targets_sha256':sha256(core_path),
            'source_targets_name':core_path.name,
            'sample_rate_Hz':rate,'frames':21*rate,'output_channels':2,
            'input_channel_map':DEFAULT_CHANNELS,
            'frequencies_Hz':[float(exact(f)) for f in settings['frequencies_Hz']],
            'digital_peak_limit':float(exact(settings['normalized_pcm_peak'])),
            'drive_command':{'path':command.name,'sha256':sha256(command)},
            'stimulus_dac_window_s':[2.,4.],
            'actual_stimulus_present':arm=='full',
            'fit_dac_window_s':[2.1,3.9], 'fade_s':.005,
            'task_epoch_window_s':[0.,20.], 'record_support_window_s':[0.,21.],
            'tail_cost':{'duration_s':'1','component':'reset_s',
                'rule':'Charge at least one second of reset overhead; task endpoint remains 20 s.'},
            'manual_pitch_pluck_epochs_s':[0,18],
            'physical_force_or_travel_limit_verified':False,'hardware_commands_issued':0,
            'notes':['OUT1 is excitation only; OUT2 is silent. Pitch plucks are separately qualified manual events.',
                'stimulus_dac_window_s is the assigned probe slot; the reduced command is silent throughout.',
                'Register this complete command hash, not the two-second source-probe hash.',
                'The support tail is real acquisition/reset cost, not a wall-clock saving.',
                'Reduced silence has no waveform clock anchors; it needs a separately qualified clock/epoch mapping.']}
        (folder/'probe.json').write_text(json.dumps(plan,indent=2,allow_nan=False)+'\n')
        plans[arm]={'plan_path':str(folder/'probe.json'),'drive_waveform_sha256':sha256(command)}
    result={'schema':'hydrophone.episode-commands/1','experiment_core_sha256':digest(core),
        'source_probe_sha256':render['sha256'],'commands':plans,
        'hardware_commands_issued':0,'physical_readiness_verified':False}
    (root/'commands.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def validate_episode_payload(plan,pcm,folder):
    """Bind slot, padding and omission to actual command bytes before capture."""
    from evaluation.protocol import read_json,digest,exact,canonical
    from .run import _bound_file
    source=_bound_file(folder,plan['source_probe'])
    core_file=_bound_file(folder,plan['experiment_core'])
    core=read_json(core_file)
    _validate_v1_core(core)
    if digest(core)!=plan['experiment_core_canonical_sha256']:
        raise ValueError('Episode core canonical digest mismatch')
    if sha256(source)!=_registered_source_sha(canonical(core)):
        raise ValueError('Source waveform differs from independently replayed registered renderer')
    rate=plan['sample_rate_Hz']
    if (rate!=48000 or plan['frames']!=21*rate or plan['fit_dac_window_s']!=[2.1,3.9] or
        plan['stimulus_dac_window_s']!=[2,4] or plan.get('protocol_arm') not in ('full','reduced')):
        raise ValueError('Episode timeline differs from the shared task')
    if plan['frequencies_Hz']!=[float(exact(f)) for f in core['excitation']['frequencies_Hz']]:
        raise ValueError('Episode frequencies differ from task core')
    if plan['digital_peak_limit']!=float(exact(core['excitation']['normalized_pcm_peak'])):
        raise ValueError('Episode digital peak differs from registered core')
    with wave.open(str(source),'rb') as stream:
        if (stream.getnchannels(),stream.getsampwidth(),stream.getframerate(),stream.getnframes())!=(1,2,rate,2*rate):
            raise ValueError('Source probe format differs from the task')
        source_pcm=stream.readframes(2*rate)
    if len(source_pcm)!=4*rate:raise ValueError('Truncated source probe')
    command=array('h');command.frombytes(pcm)
    expected=array('h',[0])*(21*rate*2)
    tones=array('h');tones.frombytes(source_pcm)
    if sys.byteorder!='little':command.byteswap();tones.byteswap()
    if plan['protocol_arm']=='full':
        for i,value in enumerate(tones):expected[2*(2*rate+i)]=value
    if command!=expected or plan.get('actual_stimulus_present')!=(plan['protocol_arm']=='full'):
        raise ValueError('Actual episode command violates assigned probe presence/omission or timeline')
