"""Deterministic offline common-exciter waveforms from fusion.score/1.

This module renders software commands only. A normalized DAC sample is not a
force, displacement, pressure, or calibrated actuator setting. Source spelling
and event metadata survive in the returned manifest. The source choir's timbre,
pan, vibrato and room are not simulated: each event becomes one sinusoid with
a short raised-cosine fade, mixed into one channel.
"""
from __future__ import annotations

from array import array
import copy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import sys
import wave


def _number(value, name, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise ValueError(f"{name} must be a finite number") from None
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    if positive and result <= 0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and result < 0:
        raise ValueError(f"{name} must be nonnegative")
    return result


def _event_alias(event, primary, alternate, default=None):
    if primary in event and alternate in event and event[primary] != event[alternate]:
        raise ValueError(f"Conflicting {primary}/{alternate} event fields")
    return event[primary] if primary in event else event.get(alternate, default)


def render_score(score: dict, output_wav, *, sample_rate=48000, peak=0.2,
                 max_duration_s=120.0) -> dict:
    """Render a score to deterministic little-endian PCM16 mono WAV.

    Event keys are ``target_Hz``, ``start_s`` and ``duration_s``. The
    parallel workbench aliases ``onset_s`` and ``amplitude`` are supported;
    conflicting dual declarations are rejected, and voice numbering is retained. Optional
    ``source_amplitude`` is a finite nonnegative relative mixing weight,
    defaulting to one. Source ``pan`` fields are preserved but do not position
    this common mono command. Every event starts with zero oscillator phase at
    its declared start time. Its attack/release fade is 5 ms or half the event
    duration, whichever is shorter.

    At least one event is required. Frequencies must be strictly below Nyquist;
    starts must be nonnegative and ends at or below ``max_duration_s``. All
    validation precedes file writing. The complete mix is normalized once to
    ``peak`` in (0,1], then quantized with ties-to-even rounding against positive
    full scale 32767. PCM peak may differ by half a least-significant bit. An
    entirely silent mix stays silent, with normalization gain zero.

    Returned metadata explicitly disables hardware execution. This function
    never opens an audio device or issues an actuator command.
    """
    if not isinstance(score, dict) or score.get("schema") != "fusion.score/1":
        raise ValueError("a fusion.score/1 object is required")
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or sample_rate <= 0:
        raise ValueError("sample_rate must be a positive integer")
    # PCM WAV's sample-rate and byte-rate fields are unsigned 32-bit integers.
    if sample_rate > (2**32 - 1)//2:
        raise ValueError("sample_rate exceeds the PCM WAV byte-rate field")
    target_peak = _number(peak, "peak", positive=True)
    if target_peak > 1:
        raise ValueError("peak must not exceed digital full scale one")
    _number(max_duration_s, "max_duration_s", positive=True)
    duration_limit = Fraction(str(max_duration_s))
    events = score.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("score.events must be a nonempty list")
    try:
        canonical = json.dumps(score, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError):
        raise ValueError("score metadata must contain finite JSON values") from None

    prepared = []
    end_time = Fraction(0)
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(f"event {index} must be an object")
        freq = _number(event.get("target_Hz"), f"event {index} target_Hz", positive=True)
        if freq >= sample_rate/2:
            raise ValueError(f"event {index} target_Hz must be below Nyquist")
        start_value = _event_alias(event, "start_s", "onset_s")
        start = _number(start_value, f"event {index} start_s/onset_s", nonnegative=True)
        duration = _number(event.get("duration_s"), f"event {index} duration_s", positive=True)
        # Count frames using the declared decimal times. This avoids an extra
        # frame from binary64 additions such as 0.02+0.1=0.12000000000000001.
        exact_start = Fraction(str(start_value))
        exact_stop = exact_start + Fraction(str(event['duration_s']))
        if exact_stop > duration_limit:
            raise ValueError(f"event {index} ends after max_duration_s")
        amplitude = _number(_event_alias(event, "source_amplitude", "amplitude", 1.0),
                            f"event {index} source_amplitude", nonnegative=True)
        prepared.append((freq, start, duration, exact_start, exact_stop, amplitude))
        end_time = max(end_time, exact_stop)

    frames = math.ceil(end_time*sample_rate)
    # WAV RIFF sizes are 32-bit; reject before allocation or writing.
    if frames > (2**32 - 1 - 36)//2:
        raise ValueError("render exceeds the PCM WAV RIFF size field")
    mixed = array("d", [0.0])*frames
    rendering = []
    # Relative scaling before mixing prevents finite but huge source weights
    # from overflowing a superposition. It cancels out in final normalization.
    amplitude_scale = max((p[5] for p in prepared), default=0.0)
    divisor = amplitude_scale if amplitude_scale else 1.0
    for index, (freq, start, duration, exact_start, exact_stop, amplitude) in enumerate(prepared):
        first = min(frames, math.ceil(exact_start*sample_rate))
        last = min(frames, math.ceil(exact_stop*sample_rate))
        fade = min(0.005, duration/2)
        weight = amplitude/divisor
        for frame in range(first, last):
            elapsed = frame/sample_rate-start
            # Guard the ideal time interval at floating-point boundaries.
            if elapsed < 0 or elapsed >= duration:
                continue
            envelope = 1.0
            if elapsed < fade:
                envelope *= 0.5*(1-math.cos(math.pi*elapsed/fade))
            remaining = duration-elapsed
            if remaining < fade:
                envelope *= 0.5*(1-math.cos(math.pi*remaining/fade))
            mixed[frame] += weight*envelope*math.sin(math.tau*freq*elapsed)
        rendering.append({"source_event_index":index,
                          "first_sample_frame":first,
                          "end_sample_frame_exclusive":last,
                          "relative_source_amplitude":amplitude,
                          "fade_duration_s":fade})

    mixed_peak = max((abs(v) for v in mixed), default=0.0)
    # Gain is represented as two factors so all finite input weights remain
    # representable, even when their raw superposition would overflow binary64.
    scaled_gain = target_peak/mixed_peak if mixed_peak else 0.0
    normalization_gain = scaled_gain/divisor if amplitude_scale else 0.0
    if not math.isfinite(normalization_gain):
        raise ValueError("required normalization gain is not finite")
    pcm = array("h")
    clipping_count = 0
    for value in mixed:
        sample = round(value*scaled_gain*32767)
        if not -32767 <= sample <= 32767:
            clipping_count += 1
            raise ValueError("internal normalization exceeded PCM full scale")
        pcm.append(sample)
    if sys.byteorder != "little":
        pcm.byteswap()
    output = Path(output_wav)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(pcm.tobytes())
    byte_hash = hashlib.sha256(output.read_bytes()).hexdigest()
    pcm_peak = max((abs(v) for v in mixed), default=0.0)*scaled_gain
    # Quantized peak is independent of host endian order.
    quantized_peak = round(pcm_peak*32767)/32767 if pcm_peak else 0.0
    return {
        "schema":"fusion.drive/1",
        "data_origin":"software_rendered_command",
        "physical_readiness":False,
        "hardware_execution_enabled":False,
        "hardware_commands_issued":0,
        "output_wav":str(output),
        "sha256":byte_hash,
        "source_score_sha256":hashlib.sha256(canonical).hexdigest(),
        "source_event_count":len(events),
        "sample_rate_Hz":sample_rate,
        "channels":1,
        "pcm_bits":16,
        "sample_frames":frames,
        "duration_s":frames/sample_rate,
        "declared_peak_full_scale":target_peak,
        "actual_peak_full_scale":quantized_peak,
        "normalization_gain":normalization_gain,
        "normalization_gain_convention":"gain against the unscaled source-amplitude sum",
        "mixing_amplitude_divisor":divisor,
        "scaled_mix_peak_before_normalization":mixed_peak,
        "clipping_count":clipping_count,
        "command_units":"normalized digital amplitude; not force, displacement or pressure",
        "rendering":"sinusoidal source events, raised-cosine fades, one global normalization, one shared mono exciter input",
        "phase_convention":"zero oscillator phase at each declared event start",
        "source_audio_effects_rendered":False,
        "source_pan_applied":False,
        "source_score_metadata":copy.deepcopy({k:v for k,v in score.items() if k!="events"}),
        "events":copy.deepcopy(events),
        "event_rendering":rendering,
    }
