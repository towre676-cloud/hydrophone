"""Joint, stationary-window tone analysis of PCM16 multichannel WAV data.

The known-tone basis includes a DC term and centered linear trend. Scaled,
column-pivoted Householder QR avoids forming the normal equations. All sample
amplitudes are digital full-scale fractions, not pressure or calibrated volts.
Ratios are complex digital channel ratios; analog channel gain and phase,
driver response, fluid propagation, and sensor calibration remain uncorrected.

The model assumes one stationary linear response over the selected window.
Joint fitting limits leakage *between the supplied basis functions*; omitted
tones, changing amplitudes, nonlinear response, clock drift, and colored noise
can still bias it. Residual diagnostics are not certified error bounds.
"""
from __future__ import annotations

import hashlib
import io
import math
from pathlib import Path
import struct
import wave


class AnalysisError(ValueError):
    """The WAV or requested analysis does not satisfy the analysis contract."""


_CONDITION_LIMIT = 1.0e8
_MAX_TONES = 64
_LSB = 1.0 / 32768.0


def _backsolve(r, rhs):
    p = len(r)
    x = [0.0] * p
    for i in range(p - 1, -1, -1):
        x[i] = (rhs[i] - math.fsum(r[i][j] * x[j] for j in range(i + 1, p))) / r[i][i]
    return x


def _qr_fit(columns, channels):
    """Solve simultaneous RHS with scaled pivoted Householder QR.

    Return coefficients in original basis order, coefficient-noise factors,
    and the infinity condition number of the scaled triangular factor. A
    column's coefficient-noise factor is its standard error when the sample
    residual standard deviation is one (iid assumption, diagnostic only).
    """
    n, p = len(columns[0]), len(columns)
    scales = [math.sqrt(math.fsum(v * v for v in col)) for col in columns]
    if any(not math.isfinite(s) or s <= 1e-15 for s in scales):
        raise AnalysisError("Tone/trend basis has a zero or invalid column")
    a = [[v / scale for v in col] for col, scale in zip(columns, scales)]
    ys = [list(values) for values in channels]
    order = list(range(p))
    for k in range(p):
        pivot = max(range(k, p),
                    key=lambda j: math.fsum(a[j][i] ** 2 for i in range(k, n)))
        if pivot != k:
            a[k], a[pivot] = a[pivot], a[k]
            order[k], order[pivot] = order[pivot], order[k]
        norm = math.sqrt(math.fsum(a[k][i] ** 2 for i in range(k, n)))
        if not math.isfinite(norm) or norm <= 1e-12:
            raise AnalysisError("Tone/trend basis is rank deficient or ill-conditioned")
        alpha = -math.copysign(norm, a[k][k])
        v = a[k][k:]
        v[0] -= alpha
        vv = math.fsum(x * x for x in v)
        if vv <= 0.0 or not math.isfinite(vv):
            raise AnalysisError("QR reflector is singular")
        for j in range(k + 1, p):
            factor = 2.0 * math.fsum(v[i] * a[j][k + i] for i in range(n - k)) / vv
            for i, value in enumerate(v):
                a[j][k + i] -= factor * value
        for y in ys:
            factor = 2.0 * math.fsum(v[i] * y[k + i] for i in range(n - k)) / vv
            for i, value in enumerate(v):
                y[k + i] -= factor * value
        a[k][k] = alpha
        # The eliminated tail is unnecessary; clear it to avoid mistaking
        # reflector storage for the R factor in later diagnostics.
        a[k][k + 1:] = [0.0] * (n - k - 1)
    r = [[a[j][i] if j >= i else 0.0 for j in range(p)] for i in range(p)]
    inverse_columns = []
    for j in range(p):
        rhs = [0.0] * p
        rhs[j] = 1.0
        inverse_columns.append(_backsolve(r, rhs))
    r_norm = max(math.fsum(abs(v) for v in row) for row in r)
    inverse_norm = max(math.fsum(abs(inverse_columns[j][i]) for j in range(p))
                       for i in range(p))
    condition = r_norm * inverse_norm
    if not math.isfinite(condition) or condition > _CONDITION_LIMIT:
        raise AnalysisError("Tone/trend basis is ill-conditioned; lengthen the window or separate tones")
    factors = [0.0] * p
    for i, original in enumerate(order):
        factors[original] = math.sqrt(math.fsum(inverse_columns[j][i] ** 2 for j in range(p))) / scales[original]
    results = []
    for y in ys:
        xp = _backsolve(r, y[:p])
        beta = [0.0] * p
        for i, original in enumerate(order):
            beta[original] = xp[i] / scales[original]
        if any(not math.isfinite(v) for v in beta):
            raise AnalysisError("Non-finite fitted coefficient")
        results.append(beta)
    return results, factors, condition


def _complex_record(value):
    amplitude = abs(value)
    return {"real": value.real, "imag": value.imag, "amplitude": amplitude,
            "phase_rad": math.atan2(value.imag, value.real) if amplitude > 1e-15 else None,
            "phase_deg": math.degrees(math.atan2(value.imag, value.real)) if amplitude > 1e-15 else None}


def _validate_channel(channel, count, label):
    if isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel < count:
        raise AnalysisError(f"{label} must be an integer channel index from 0 to {count - 1}")


def _finite_time(value, name):
    if isinstance(value, bool):
        raise AnalysisError(f"{name} must be finite seconds")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AnalysisError(f"{name} must be finite seconds") from exc
    if not math.isfinite(result):
        raise AnalysisError(f"{name} must be finite seconds")
    return result


def analyze_tones(wav_path, *, drive_channel=0, response_channel=1,
                  reference_channel=None, frequencies_Hz, start_s=0, end_s=None):
    """Fit known tones jointly and return uncalibrated complex channel ratios.

    PCM16 little-endian uncompressed WAV only. At most 64 distinct frequencies
    are accepted, each strictly between DC and Nyquist. The half-open requested
    interval selects sample timestamps t with start_s <= t < end_s; omitted
    end_s selects through the WAV's final sample. Selected samples on every
    used channel must avoid the two PCM16 rail codes. Every requested tone
    needs a resolved drive amplitude; an optional reference needs one too.

    A resolved denominator exceeds both one PCM16 LSB and five times its
    fitted two-coefficient iid residual diagnostic. This is a conditioning
    guard, not a statistical or physical accuracy guarantee.
    """
    path = Path(wav_path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AnalysisError(f"Cannot read WAV: {exc}") from exc
    try:
        with wave.open(io.BytesIO(raw), "rb") as source:
            channel_count = source.getnchannels()
            rate = source.getframerate()
            frame_count = source.getnframes()
            if source.getsampwidth() != 2 or source.getcomptype() != "NONE":
                raise AnalysisError("Only uncompressed PCM16 WAV is supported")
            if channel_count < 1 or rate <= 0 or frame_count <= 0:
                raise AnalysisError("WAV needs positive channels, sample rate and frame count")
            _validate_channel(drive_channel, channel_count, "drive_channel")
            _validate_channel(response_channel, channel_count, "response_channel")
            if drive_channel == response_channel:
                raise AnalysisError("Drive and response channels must be distinct")
            if reference_channel is not None:
                _validate_channel(reference_channel, channel_count, "reference_channel")
                if reference_channel in (drive_channel, response_channel):
                    raise AnalysisError("Reference, drive and response channels must be distinct")
            start = _finite_time(start_s, "start_s")
            duration = frame_count / rate
            end = duration if end_s is None else _finite_time(end_s, "end_s")
            if start < 0 or end <= start or end > duration or start >= duration:
                raise AnalysisError("Window must satisfy 0 <= start_s < end_s <= WAV duration")
            # Subtract only floating-point roundoff at integer sample boundaries.
            first = math.ceil(start * rate - 1e-12)
            stop = min(frame_count, math.ceil(end * rate - 1e-12))
            samples = stop - first
            if not isinstance(frequencies_Hz, (list, tuple)) or not frequencies_Hz:
                raise AnalysisError("frequencies_Hz must be a nonempty list or tuple")
            if len(frequencies_Hz) > _MAX_TONES:
                raise AnalysisError("At most 64 tones are supported by this small-basis analysis")
            frequencies = []
            for frequency in frequencies_Hz:
                if isinstance(frequency, bool):
                    raise AnalysisError("Tone frequencies must be finite, positive and below Nyquist")
                try:
                    frequency = float(frequency)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise AnalysisError("Tone frequencies must be finite numbers") from exc
                if not math.isfinite(frequency) or not 0 < frequency < rate / 2:
                    raise AnalysisError("Tone frequencies must be finite, positive and below Nyquist")
                frequencies.append(frequency)
            if len(set(frequencies)) != len(frequencies):
                raise AnalysisError("Tone frequencies must be distinct")
            basis_size = 2 + 2 * len(frequencies)
            if samples < max(16, basis_size + 2):
                raise AnalysisError("Window is too short for the tone/trend basis and residual diagnostics")
            source.setpos(first)
            pcm = source.readframes(samples)
            if len(pcm) != samples * channel_count * 2:
                raise AnalysisError("WAV PCM data is truncated relative to its header")
    except AnalysisError:
        raise
    except (wave.Error, EOFError, struct.error, OSError) as exc:
        raise AnalysisError(f"Invalid PCM WAV: {exc}") from exc

    used = sorted({drive_channel, response_channel} |
                  ({reference_channel} if reference_channel is not None else set()))
    signals = {channel: [] for channel in used}
    clips = {channel: 0 for channel in used}
    for frame in struct.iter_unpack("<" + "h" * channel_count, pcm):
        for channel in used:
            value = frame[channel]
            clips[channel] += value in (-32768, 32767)
            signals[channel].append(value / 32768.0)
    if any(clips.values()):
        channels_with_clipping = [channel for channel, count in clips.items() if count]
        raise AnalysisError(f"Clipping rail codes found on used channels {channels_with_clipping}")

    midpoint = (samples - 1) / 2.0
    centered_times = [(i - midpoint) / rate for i in range(samples)]
    halfspan = midpoint / rate
    columns = [[1.0] * samples, [t / halfspan for t in centered_times]]
    for frequency in frequencies:
        columns.append([math.cos(2 * math.pi * frequency * t) for t in centered_times])
        columns.append([math.sin(2 * math.pi * frequency * t) for t in centered_times])
    coefficients, noise_factors, condition = _qr_fit(columns, [signals[c] for c in used])
    fitted = {}
    for channel, beta in zip(used, coefficients):
        values = signals[channel]
        residual = [value - math.fsum(beta[j] * columns[j][i] for j in range(basis_size))
                    for i, value in enumerate(values)]
        rss = math.fsum(v * v for v in residual)
        sigma = math.sqrt(rss / (samples - basis_size))
        fitted[channel] = {
            "channel_index": channel,
            "coefficients": beta,
            "dc_at_window_midpoint_full_scale": beta[0],
            "linear_trend_full_scale_per_s": beta[1] / halfspan,
            "signal_rms_full_scale": math.sqrt(math.fsum(v * v for v in values) / samples),
            "residual_rms_full_scale": math.sqrt(rss / samples),
            "residual_std_dof_adjusted_full_scale": sigma,
            "residual_degrees_of_freedom": samples - basis_size,
            "rail_sample_count": clips[channel],
        }
    tones = []
    for j, frequency in enumerate(frequencies):
        phasors, thresholds = {}, {}
        for channel in used:
            fit = fitted[channel]
            beta = fit["coefficients"]
            phasors[channel] = complex(beta[2 + 2*j], -beta[3 + 2*j])
            coefficient_uncertainty = fit["residual_std_dof_adjusted_full_scale"] * math.hypot(
                noise_factors[2 + 2*j], noise_factors[3 + 2*j])
            thresholds[channel] = max(_LSB, 5 * coefficient_uncertainty)
        if abs(phasors[drive_channel]) <= thresholds[drive_channel]:
            raise AnalysisError(f"Drive tone at {frequency:g} Hz is zero or unresolved")
        if reference_channel is not None and abs(phasors[reference_channel]) <= thresholds[reference_channel]:
            raise AnalysisError(f"Reference tone at {frequency:g} Hz is zero or unresolved")
        record = {
            "frequency_Hz": frequency,
            "channel_phasors_full_scale_peak": {str(c): _complex_record(phasors[c]) for c in used},
            "denominator_resolution_threshold_full_scale": {str(c): thresholds[c] for c in used},
            "response_over_drive": _complex_record(phasors[response_channel] / phasors[drive_channel]),
        }
        if reference_channel is not None:
            record["reference_over_drive"] = _complex_record(phasors[reference_channel] / phasors[drive_channel])
            record["response_over_reference"] = _complex_record(phasors[response_channel] / phasors[reference_channel])
        tones.append(record)
    for fit in fitted.values():
        del fit["coefficients"]
    result = {
        "schema": "hydrophone.stationary-tone-analysis/1",
        "evidence_status": "ANALYSIS_OF_SUPPLIED_PCM_NOT_SENSOR_CALIBRATION",
        "source_name": path.name,
        "source_file_sha256": hashlib.sha256(raw).hexdigest(),
        "selected_pcm_sha256": hashlib.sha256(pcm).hexdigest(),
        "pcm": {"sample_width_bits": 16, "sample_rate_Hz": rate,
                "channel_count": channel_count, "source_frame_count": frame_count},
        "window": {"start_frame_inclusive": first, "end_frame_exclusive": stop,
                   "sample_count": samples, "first_sample_time_s": first / rate,
                   "last_sample_time_s": (stop - 1) / rate,
                   "phase_origin_time_s": (first + midpoint) / rate},
        "channel_map": {"drive": drive_channel, "response": response_channel,
                        "reference": reference_channel, "used_channels": used},
        "fit": {"method": "scaled_column_pivoted_Householder_QR",
                "basis": "DC + centered linear trend + joint cosine/sine pairs at known frequencies",
                "basis_columns": basis_size,
                "scaled_R_infinity_condition_number": condition,
                "condition_rejection_threshold": _CONDITION_LIMIT,
                "clipping_policy": "reject either PCM16 rail code on any used channel"},
        "units": {"amplitude": "digital full-scale fraction, peak phasor amplitude",
                  "ratios": "dimensionless digital channel amplitude ratios, uncalibrated",
                  "phase": "response phase relative to denominator channel; radians and degrees",
                  "calibration": "No pressure, material parameter, voltage or actuator calibration supplied"},
        "channels": {str(c): fitted[c] for c in used},
        "tones": tones,
        "assumptions": [
            "One stationary, common-clock observation window with known frequencies and linear superposition.",
            "All supplied tones are fitted jointly with DC and trend; omitted tones and time variation may bias the fit.",
            "Residuals combine noise, quantization and model mismatch and are not certified physical error bounds.",
            "Coefficient-noise thresholds use an iid residual diagnostic solely to reject unresolved denominators.",
            "Channel gain/phase, driver, propagation and sensor responses remain in the reported digital ratios.",
        ],
    }
    # Explicitly enforce JSON-safe finite numbers before returning to callers.
    def check_finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise AnalysisError("Analysis produced a non-finite value")
        if isinstance(item, dict):
            for value in item.values():
                check_finite(value)
        elif isinstance(item, (list, tuple)):
            for value in item:
                check_finite(value)
    check_finite(result)
    return result
