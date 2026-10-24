"""Offline electrical loopback timing from three recorded command templates.

NumPy and SciPy are optional dependencies of this module's operation. The
alignment is an integer-sample correlation estimate with an operator-declared
error allowance, not a certified clock map or a mechanical delay measurement.
"""
from __future__ import annotations

import csv
from fractions import Fraction
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import wave

from .drive import _number
from .probe import load_probe, sha256
from .synchronize import fit_clock


def _recording(path, channel, rate):
    raw = Path(path).read_bytes()
    try:
        with wave.open(BytesIO(raw), 'rb') as stream:
            if stream.getsampwidth() != 2 or stream.getframerate() != rate:
                raise ValueError('Alignment requires PCM16 at the command sample rate')
            channels = stream.getnchannels()
            if isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel < channels:
                raise ValueError('Loopback channel is outside the recording')
            frames = stream.getnframes()
            pcm = stream.readframes(frames)
            if frames <= 0 or len(pcm) != frames * channels * 2:
                raise ValueError('Alignment recording is empty or truncated')
    except (wave.Error, EOFError) as exc:
        raise ValueError('Alignment requires a valid PCM16 recording') from exc
    return raw, pcm, channels, frames


def align_drive(probe_path, recorded_wav, output_dir, *, loopback_channel=2,
                min_delay_s=0.0, max_delay_s=0.25, declared_error_s=0.001,
                source_pick_error_s=0.0, audio_pick_error_s=None,
                min_peak_correlation=0.95, min_peak_margin=0.01):
    """Save ``markers.csv``, ``drive_clock.json`` and ``alignment.json``.

    OUT1 is matched against a separately recorded electrical loopback channel.
    Three templates center on stimulus onset, plateau midpoint and offset;
    the first and last include the known envelope and adjoining silence. The
    fit therefore brackets the stationary analysis window and stimulus edges.
    Templates are 0.30 s long. Every allowed lag must fit the recording.

    Select an independently plausible delay bracket before examining results.
    A template must have an interior positive-polarity correlation peak above
    ``min_peak_correlation`` and exceed every other local peak outside its
    central half-cycle by ``min_peak_margin``. A single periodic tone usually
    fails this ambiguity test. Narrowing a search bracket is an external prior,
    not new timing evidence. Inverted or strongly filtered paths reject.

    Markers retain exact sample-index/rate times without fractional-delay
    interpolation. Audio picking error defaults to one sample and cannot be
    declared below half a sample. This resolution floor is not a proved error
    bound: noise, analog filtering, interpolation between markers and sample
    clock calibration remain separate physical obligations.
    """
    plan, command_pcm, command_path = load_probe(probe_path)
    if plan.get('protocol_arm')=='reduced':
        raise ValueError('Reduced silent command has no waveform timing anchors; supply independently qualified clock evidence')
    root = Path(output_dir)
    if root.exists():
        raise ValueError('Alignment output directory must be new')
    rate = plan['sample_rate_Hz']
    lower = _number(min_delay_s, 'min_delay_s')
    upper = _number(max_delay_s, 'max_delay_s')
    error = _number(declared_error_s, 'declared_error_s', nonnegative=True)
    source_error = _number(source_pick_error_s, 'source_pick_error_s', nonnegative=True)
    pick_error = 1 / rate if audio_pick_error_s is None else _number(
        audio_pick_error_s, 'audio_pick_error_s', nonnegative=True)
    peak_floor = _number(min_peak_correlation, 'min_peak_correlation', positive=True)
    margin_floor = _number(min_peak_margin, 'min_peak_margin', positive=True)
    if not -1 <= lower < upper <= 1:
        raise ValueError('Declare a delay bracket within -1..1 s')
    if pick_error < .5 / rate:
        raise ValueError('Integer-sample alignment cannot declare sub-half-sample picking error')
    if not 0 < peak_floor <= 1 or not 0 < margin_floor <= 1:
        raise ValueError('Correlation and ambiguity thresholds must be in (0,1]')
    lag_first, lag_last = math.ceil(lower * rate), math.floor(upper * rate)
    if lag_last - lag_first < 2:
        raise ValueError('Delay bracket needs at least three sample positions')
    raw, recorded_pcm, channels, recorded_frames = _recording(recorded_wav, loopback_channel, rate)
    try:
        import numpy as np
        from scipy.signal import correlate, find_peaks
        import scipy
    except ImportError as exc:
        raise ValueError('Offline loopback alignment requires optional numpy and scipy') from exc
    command = np.frombuffer(command_pcm, dtype='<i2').reshape(-1, 2)[:, 0].astype(float) / 32768.
    recorded = np.frombuffer(recorded_pcm, dtype='<i2').reshape(-1, channels)[:, loopback_channel]
    if np.any((recorded == -32768) | (recorded == 32767)):
        raise ValueError('Loopback recording contains clipped rail codes')
    recorded = recorded.astype(float) / 32768.
    on, off = plan['stimulus_dac_window_s']
    anchors = [round(on * rate), round((on + off) * rate / 2), round(off * rate)]
    half_width = round(.15 * rate)
    exclusion = max(1, math.ceil(rate / (2 * max(plan['frequencies_Hz']))))
    diagnostics = []
    markers = []
    for anchor in anchors:
        first, last = anchor - half_width, anchor + half_width
        search_first, search_last = first + lag_first, last + lag_last
        if first < 0 or last > len(command) or search_first < 0 or search_last > recorded_frames:
            raise ValueError('A command template or its entire declared delay search leaves the recording')
        template = command[first:last]
        template = template - np.mean(template)
        energy = float(np.dot(template, template))
        size = len(template)
        if not math.isfinite(energy) or energy <= size * (2 / 32768.) ** 2:
            raise ValueError('Command template is zero or unresolved at PCM16 resolution')
        segment = recorded[search_first:search_last]
        numerator = correlate(segment, template, mode='valid', method='fft')
        cumulative = np.concatenate(([0.], np.cumsum(segment)))
        square_cumulative = np.concatenate(([0.], np.cumsum(segment * segment)))
        totals = cumulative[size:] - cumulative[:-size]
        squares = square_cumulative[size:] - square_cumulative[:-size]
        variances = np.maximum(0., squares - totals * totals / size)
        denominator = np.sqrt(energy * variances)
        correlations = np.full(len(numerator), -np.inf)
        resolved = variances > size * (2 / 32768.) ** 2
        correlations[resolved] = numerator[resolved] / denominator[resolved]
        if not np.any(np.isfinite(correlations)):
            raise ValueError('Electrical loopback template is zero or unresolved')
        best = int(np.argmax(correlations))
        peak = float(min(1., correlations[best]))
        if best in (0, len(correlations)-1):
            raise ValueError('Alignment peak reaches delay-search boundary; provide a wider justified bracket')
        if peak < peak_floor:
            raise ValueError('Electrical loopback correlation is below its declared acceptance threshold')
        others = list(find_peaks(correlations)[0]) + [0, len(correlations)-1]
        competitors = [float(correlations[i]) for i in others
                       if abs(int(i)-best) > exclusion and math.isfinite(float(correlations[i]))]
        runner_up = min(1., max(competitors, default=-1.))
        margin = peak - runner_up
        if margin < margin_floor:
            raise ValueError('Ambiguous electrical loopback timing: another correlation peak remains plausible')
        lag = lag_first + best
        source_time = Fraction(anchor, rate)
        audio_time = Fraction(anchor + lag, rate)
        markers.append((str(source_time), str(audio_time)))
        diagnostics.append({'source_anchor_frame': anchor, 'audio_anchor_frame': anchor + lag,
            'lag_frames': lag, 'lag_s': lag / rate, 'template_start_frame': first,
            'template_end_frame_exclusive': last, 'peak_correlation': peak,
            'highest_other_peak_correlation': runner_up, 'peak_margin': margin,
            'local_peak_exclusion_frames': exclusion,
            'loopback_window_rms_after_mean_removal_full_scale': math.sqrt(float(variances[best])/size)})
    root.mkdir(parents=True)
    marker_path = root/'markers.csv'
    with marker_path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['drive_time_s','audio_time_s'])
        writer.writerows(markers)
    clock = fit_clock(marker_path, source_key='drive_time_s', declared_error_s=error,
        source_pick_error_s=source_error, audio_pick_error_s=pick_error,
        method='Three positive-polarity electrical command-template correlation anchors; integer-sample timing')
    (root/'drive_clock.json').write_text(json.dumps(clock, indent=2, allow_nan=False)+'\n')
    receipt = {'schema':'hydrophone.drive-alignment/1',
        'status':'THREE_TEMPLATE_ANCHORS_FITTED_WITH_DECLARED_BOUND',
        'probe_sha256':sha256(probe_path), 'command_sha256':sha256(command_path),
        'recorded_wav_sha256':hashlib.sha256(raw).hexdigest(),
        'recorded_wav_name':Path(recorded_wav).name, 'loopback_channel':loopback_channel,
        'sample_rate_Hz':rate, 'delay_search_s':[lower,upper],
        'min_peak_correlation':peak_floor, 'min_peak_margin':margin_floor,
        'anchors':diagnostics, 'markers':{'path':marker_path.name,'sha256':sha256(marker_path)},
        'clock':{'path':'drive_clock.json','sha256':sha256(root/'drive_clock.json')},
        'software':{'numpy':np.__version__,'scipy':scipy.__version__},
        'hardware_commands_issued':0, 'physical_clock_bound_verified':False,
        'qualifications':['Electrical loopback timing is not mechanical force or propagation delay.',
            'Correlation thresholds diagnose ambiguity; they are not calibrated statistical confidence.',
            'Integer-sample markers do not establish fractional-sample precision.',
            'Clock interpolation, analog filtering, noise and sample-rate calibration require independent validation.',
            'A narrow delay bracket is prior information and must be justified before fitting.']}
    (root/'alignment.json').write_text(json.dumps(receipt, indent=2, allow_nan=False)+'\n')
    return receipt
