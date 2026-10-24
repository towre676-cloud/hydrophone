"""Compile a stationary engineering probe from actual recovered tuning targets."""
from array import array
import hashlib
import json
import math
from pathlib import Path
import sys
import wave
from .drive import _number
from .run import load_json

DEFAULT_CHANNELS = ['hydrophone_raw', 'bridge_acceleration_raw',
                    'drive_loopback_raw', 'sync_marker_raw']


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compile_probe(target_path, output_dir, *, sample_rate=48000, peak=.01,
                  plateau_s=8):
    """Write a stereo PCM16 command: OUT1 multitone, OUT2 silent.

    One second precedes/follows the eight-second stimulus. The fit excludes
    its 50 ms fades and another 950 ms at either edge. The user must check
    settling independently. Digital amplitude is deliberately NOT a travel
    or force limit. This function opens no devices.
    """
    source = Path(target_path).resolve()
    targets = load_json(source).get('calibration_targets')
    if not isinstance(targets, list) or not 1 <= len(targets) <= 16:
        raise ValueError('Need 1..16 explicit calibration_targets')
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or not 8000 <= sample_rate <= 96000:
        raise ValueError('sample_rate must be an integer in 8000..96000')
    amplitude = _number(peak, 'peak', positive=True)
    duration = _number(plateau_s, 'plateau_s', positive=True)
    if not 4 <= duration <= 58 or amplitude > .05:
        raise ValueError('Engineering preset requires 4..58 s plateau and digital peak <=0.05')
    frequencies = [_number(t.get('target_Hz'), 'target_Hz', positive=True) for t in targets]
    if len(set(frequencies)) != len(frequencies) or max(frequencies) >= sample_rate / 2:
        raise ValueError('Targets must be distinct and below Nyquist')
    total = round((duration + 2) * sample_rate)
    pcm = array('h')
    # Divide by the number of tones: triangle inequality bounds every sample.
    for frame in range(total):
        t = frame / sample_rate - 1
        value = 0.
        if 0 <= t < duration:
            fade = min(1., t / .05, (duration - t) / .05)
            envelope = .5 * (1 - math.cos(math.pi * max(0., fade)))
            value = amplitude / len(frequencies) * envelope * sum(math.sin(math.tau * f * t) for f in frequencies)
        pcm.extend((round(32767 * value), 0))
    if sys.byteorder != 'little':
        pcm.byteswap()
    root = Path(output_dir)
    if root.exists():
        raise ValueError('Probe output directory must be new; preserve previous commands')
    root.mkdir(parents=True)
    wav = root / 'drive_command.wav'
    with wave.open(str(wav), 'wb') as stream:
        stream.setparams((2, 2, sample_rate, total, 'NONE', 'not compressed'))
        stream.writeframes(pcm.tobytes())
    plan = {'schema': 'hydrophone.stationary-probe/1',
        'source_targets_sha256': sha256(source), 'source_targets_name': source.name,
        'targets': targets, 'frequencies_Hz': frequencies,
        'sample_rate_Hz': sample_rate, 'frames': total, 'output_channels': 2,
        'input_channel_map': DEFAULT_CHANNELS, 'digital_peak_limit': amplitude,
        'drive_command': {'path': wav.name, 'sha256': sha256(wav)},
        'stimulus_dac_window_s': [1., 1. + duration],
        'fit_dac_window_s': [2., duration], 'fade_s': .05,
        'engineering_only': True, 'physical_force_or_travel_limit_verified': False,
        'hardware_commands_issued': 0,
        'notes': ['OUT1 is common excitation; OUT2 is silent.',
                  'Do not equate musical audition envelopes with this stationary probe.',
                  'Window settling, mechanical travel and non-disturbance require measurements.',
                  'Map DAC fit window into ADC time using measured loopback timing before analysis.']}
    (root / 'probe.json').write_text(json.dumps(plan, indent=2, allow_nan=False) + '\n')
    return plan


def load_probe(path):
    path = Path(path).resolve()
    plan = load_json(path)
    if plan.get('schema') != 'hydrophone.stationary-probe/1':
        raise ValueError('Expected stationary-probe/1')
    record = plan['drive_command']
    name = record['path']
    if Path(name).is_absolute():
        raise ValueError('Probe WAV path must be relative')
    wav = (path.parent / name).resolve()
    if not wav.is_relative_to(path.parent) or not wav.is_file() or sha256(wav) != record['sha256']:
        raise ValueError('Probe WAV missing, outside directory, or SHA256 mismatch')
    with wave.open(str(wav), 'rb') as stream:
        if (stream.getsampwidth() != 2 or stream.getnchannels() != 2 or
            stream.getframerate() != plan['sample_rate_Hz'] or stream.getnframes() != plan['frames']):
            raise ValueError('Probe WAV format differs from plan')
        pcm = stream.readframes(stream.getnframes())
    if len(pcm) != 4 * plan['frames'] or not 8000 <= plan['sample_rate_Hz'] <= 96000 or not 0 < plan['frames'] <= 60 * plan['sample_rate_Hz']:
        raise ValueError('Truncated or over-budget probe')
    values = array('h'); values.frombytes(pcm)
    if sys.byteorder != 'little': values.byteswap()
    peak = _number(plan['digital_peak_limit'], 'digital_peak_limit', positive=True)
    if peak > .05 or max(abs(v) for v in values) > math.ceil(32767 * peak):
        raise ValueError('Command exceeds declared engineering digital peak')
    if any(values[1::2]):
        raise ValueError('OUT2 must remain silent in this preset')
    labels = plan['input_channel_map']
    if (not isinstance(labels, list) or not 1 <= len(labels) <= 16 or len(set(labels)) != len(labels)
        or any(not isinstance(s, str) or not s for s in labels)):
        raise ValueError('Need unique input channel labels')
    frequencies = plan['frequencies_Hz']
    if (not isinstance(frequencies, list) or not frequencies or len(set(frequencies)) != len(frequencies)
        or any(not 0 < _number(f, 'frequency') < plan['sample_rate_Hz']/2 for f in frequencies)):
        raise ValueError('Invalid analysis frequencies')
    a, b = plan['fit_dac_window_s']
    on, off = plan['stimulus_dac_window_s']
    if not 0 <= on < a < b < off <= plan['frames']/plan['sample_rate_Hz']:
        raise ValueError('Fit window must be strictly inside stimulus')
    return plan, pcm, wav
