"""Conditional SI conversion of *declared* calibrated complex tone phasors.

No calibration is inferred here. Exact Fraction arithmetic applies to the
decimal inputs supplied to this module; sensor validity and input error disks
must be established independently. No interpolation/extrapolation is allowed.
The statistical residual from instrument.analyze is not an input error bound.
"""
from __future__ import annotations

from fractions import Fraction as F
import math


UNITS = {"voltage": "V", "pressure": "Pa", "acceleration": "m/s^2",
         "force": "N", "displacement": "m"}
ROLE_QUANTITIES = {"drive_loopback": "voltage", "hydrophone": "pressure",
                   "bridge_acceleration": "acceleration", "dynamic_force": "force",
                   "bridge_displacement": "displacement"}


def _f(value):
    if value is None or isinstance(value, bool):
        raise ValueError("Finite decimal numeric input required")
    try:
        number = F(str(value))
        rendered = float(number)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError("Finite decimal numeric input required") from exc
    if not math.isfinite(rendered):
        raise ValueError("Input exceeds finite output range")
    return number


def _nonnegative(value):
    value = _f(value)
    if value < 0:
        raise ValueError("Error radii must be nonnegative")
    return value


def _z(value):
    return _f(value["real"]), _f(value["imag"])


def _divide(a, b):
    denominator = b[0]**2+b[1]**2
    if denominator == 0:
        raise ValueError("Complex denominator is zero")
    return ((a[0]*b[0]+a[1]*b[1])/denominator,
            (a[1]*b[0]-a[0]*b[1])/denominator)


def _record(z, error=None):
    real, imag = float(z[0]), float(z[1])
    if not math.isfinite(real) or not math.isfinite(imag):
        raise ValueError("SI result exceeds finite output range")
    result = {"real": real, "imag": imag,
              "exact_decimal_model": {"real": str(z[0]), "imag": str(z[1])},
              "amplitude_approximate": math.hypot(real, imag),
              "phase_rad_approximate": math.atan2(imag, real) if z != (0, 0) else None,
              "error_radius_abs_exact_decimal_model": None if error is None else str(error),
              "bound_status": "not_available" if error is None else "conditional_on_declared_deterministic_disks"}
    if not math.isfinite(result["amplitude_approximate"]):
        raise ValueError("SI result exceeds finite output range")
    return result


def _ratio_with_disk(numerator, denominator, numerator_error=None, denominator_error=None):
    nominal = _divide(numerator, denominator)
    error = None
    nr = None if numerator_error is None else _nonnegative(numerator_error)
    dr = None if denominator_error is None else _nonnegative(denominator_error)
    if nr is not None and dr is not None:
        # Conservative rational inequalities: |z| <= |Re z|+|Im z| and
        # |denominator_true| >= max(|Re d|,|Im d|)-declared_radius.
        lower = max(abs(denominator[0]), abs(denominator[1]))-dr
        if lower <= 0:
            raise ValueError("Denominator uncertainty does not exclude conservative zero bound")
        error = (nr+(abs(nominal[0])+abs(nominal[1]))*dr)/lower
    return nominal, error


def validate_record(record, *, configuration_id, sample_rate_Hz, temperature_C):
    """Validate declarations and measured-frequency coverage, not authenticity."""
    if record.get("schema") != "hydrophone.calibration-record/1":
        raise ValueError("Unknown calibration schema")
    if record.get("frequency_axis") != "SI_Hz":
        raise ValueError("Calibration frequency axis must explicitly be SI_Hz")
    if record.get("status") != "measured_with_declared_scope":
        raise ValueError("Calibration record is not enabled; template/nominal specs cannot convert to SI")
    if record.get("evidence_type") not in ("physical_calibration_declared", "synthetic_demo"):
        raise ValueError("Calibration evidence type must be explicit")
    if not isinstance(record.get("calibration_id"), str) or not record["calibration_id"]:
        raise ValueError("Calibration identity is missing")
    if record.get("configuration_id") != configuration_id:
        raise ValueError("Calibration configuration differs from run")
    if _f(record["sample_rate_Hz"]) != _f(sample_rate_Hz):
        raise ValueError("Calibration sample rate differs from analysis")
    temperature = _f(temperature_C)
    bounds = record["valid_temperature_C"]
    if not _f(bounds[0]) <= temperature <= _f(bounds[1]):
        raise ValueError("Temperature lies outside calibration domain")
    channels = record.get("channels")
    if not isinstance(channels, list) or not channels:
        raise ValueError("Calibration channels are missing")
    seen, seen_roles = set(), set()
    for channel in channels:
        index = channel.get("analysis_channel")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0 or index in seen:
            raise ValueError("Calibration channel indices must be unique nonnegative integers")
        seen.add(index)
        quantity = channel.get("quantity")
        if not isinstance(quantity, str) or quantity not in UNITS or channel.get("SI_unit") != UNITS[quantity]:
            raise ValueError("Quantity and SI unit mismatch")
        role = channel.get("role")
        if not isinstance(role, str) or role not in ROLE_QUANTITIES or ROLE_QUANTITIES[role] != quantity or role in seen_roles:
            raise ValueError("Role/quantity mismatch or duplicate role; channels need distinct physical roles")
        seen_roles.add(role)
        if not channel.get("chain_id") or channel.get("phase_response_measured") is not True:
            raise ValueError("Complex conversion needs an identified chain and measured phase response")
        points = channel.get("points")
        if not isinstance(points, list) or not points:
            raise ValueError("Calibration frequency points are missing")
        frequencies = [_f(p["frequency_Hz"]) for p in points]
        if any(f <= 0 for f in frequencies) or len(set(frequencies)) != len(frequencies):
            raise ValueError("Calibration frequencies must be distinct and positive SI Hz")
        for point in points:
            _nonnegative(point.get("frequency_domain_halfwidth_Hz", 0))
            if _z(point["sensitivity_FS_per_SI"]) == (0, 0):
                raise ValueError("Sensitivity cannot be zero")
            if point.get("uncertainty_kind") not in ("deterministic_disk_declared", "expanded_uncertainty_declared", "unspecified"):
                raise ValueError("Calibration uncertainty kind is unknown")
            if point.get("uncertainty_kind") == "deterministic_disk_declared":
                _nonnegative(point["sensitivity_error_radius_abs_FS_per_SI"])
    return True


def convert_analysis(analysis, record, *, configuration_id, temperature_C,
                     phasor_error_bounds_full_scale=None,
                     adc_nominal_seconds_per_SI_second=None,
                     adc_timebase_factor_error_abs=None):
    """Convert matching calibrated channels from an analyze_tones result.

    Optional phasor_error_bounds_full_scale maps channel strings to frequency
    strings, e.g. {"1":{"300.0":"0.0001"}}. These must bound the complete
    complex fitted-phasor error, including model/fit/clock effects. Missing
    entries produce nominal SI values without deterministic bounds. No RMS
    diagnostic is silently promoted to a bound.

    A declared independent ADC timebase factor k and its error are required:
    t_ADC_nominal=k*t_SI, hence f_SI=k*f_fit. A DAC/ADC relative drift fit
    does not supply this absolute factor. Each sensitivity point's declared
    frequency-domain halfwidth must cover f_fit times the factor error.
    """
    if analysis.get("schema") != "hydrophone.stationary-tone-analysis/1":
        raise ValueError("Expected stationary-tone analysis")
    validate_record(record, configuration_id=configuration_id,
                    sample_rate_Hz=analysis["pcm"]["sample_rate_Hz"], temperature_C=temperature_C)
    if adc_nominal_seconds_per_SI_second is None or adc_timebase_factor_error_abs is None:
        raise ValueError("Independent ADC-to-SI timebase factor and its error are required")
    timebase = _f(adc_nominal_seconds_per_SI_second)
    timebase_error = _nonnegative(adc_timebase_factor_error_abs)
    if timebase-timebase_error <= 0:
        raise ValueError("ADC-to-SI timebase must remain positive under its error bound")
    converted = []
    for tone in analysis["tones"]:
        nominal_adc_frequency = _f(tone["frequency_Hz"])
        frequency = nominal_adc_frequency*timebase
        frequency_error = nominal_adc_frequency*timebase_error
        outputs = {}
        by_role = {}
        for channel in record["channels"]:
            key = str(channel["analysis_channel"])
            if key not in tone["channel_phasors_full_scale_peak"]:
                raise ValueError("Calibrated channel is absent from analyzed channels")
            points = [point for point in channel["points"] if _f(point["frequency_Hz"]) == frequency]
            if len(points) != 1:
                raise ValueError("Requested frequency has no exact calibration point; no interpolation allowed")
            point = points[0]
            if frequency_error > _nonnegative(point.get("frequency_domain_halfwidth_Hz", 0)):
                raise ValueError("ADC timebase uncertainty leaves sensitivity frequency domain")
            error = None
            if phasor_error_bounds_full_scale is not None:
                error = phasor_error_bounds_full_scale.get(key, {}).get(str(tone["frequency_Hz"]))
            sensitivity_error = (point["sensitivity_error_radius_abs_FS_per_SI"]
                                 if point.get("uncertainty_kind") == "deterministic_disk_declared" else None)
            nominal, radius = _ratio_with_disk(
                _z(tone["channel_phasors_full_scale_peak"][key]),
                _z(point["sensitivity_FS_per_SI"]), error, sensitivity_error)
            outputs[key] = {**_record(nominal, radius), "role": channel["role"],
                            "quantity": channel["quantity"], "SI_unit": channel["SI_unit"],
                            "chain_id": channel["chain_id"]}
            by_role[channel["role"]] = (nominal, radius, channel["SI_unit"])
        transfers = {}
        if "hydrophone" in by_role:
            numerator, nr, _ = by_role["hydrophone"]
            for denominator_role, name in (("drive_loopback", "pressure_per_drive_voltage"),
                                           ("bridge_acceleration", "pressure_per_bridge_acceleration"),
                                           ("dynamic_force", "pressure_per_measured_force")):
                if denominator_role in by_role:
                    denominator, dr, unit = by_role[denominator_role]
                    nominal, radius = _ratio_with_disk(numerator, denominator, nr, dr)
                    transfers[name] = {**_record(nominal, radius), "SI_unit": f"Pa/({unit})"}
        converted.append({"frequency_ADC_nominal_Hz": tone["frequency_Hz"],
                          "frequency_SI_Hz_exact_decimal_model": str(frequency),
                          "frequency_SI_error_Hz_exact_decimal_model": str(frequency_error),
                          "channels_SI": outputs,
                          "transfers": transfers})
    return {"schema": "hydrophone.conditional-si-tone-conversion/1",
            "evidence_type": record["evidence_type"],
            "calibration_id": record["calibration_id"],
            "configuration_id": configuration_id,
            "ADC_timebase_factor_declared_exact_decimal_model": str(timebase),
            "ADC_timebase_factor_error_declared_exact_decimal_model": str(timebase_error),
            "source_analysis_file_sha256": analysis.get("source_file_sha256"),
            "calibration_authenticity_verified": False,
            "calibration_domain_verified_beyond_declared_fields": False,
            "pressure_per_force_available": any("pressure_per_measured_force" in t["transfers"] for t in converted),
            "tones": converted,
            "limitations": ["SI values condition on supplied chain calibration and its stated setup.",
                "Electrical loopback is voltage, never actual mechanical force.",
                "ADC-to-SI timebase factor/error are independent declarations, not inferred from DAC/ADC relative drift.",
                "Conservative exact-decimal disk propagation covers declared errors only, not missing uncertainty sources.",
                "Approximate amplitude/phase fields are display arithmetic; no pressure/material model is inferred."]}


def convert_slow_sample(raw_value, *, zero_raw, scale_SI_per_raw, SI_unit,
                        raw_error_abs=None, zero_error_abs=None, scale_error_abs=None):
    """Affine slow-sensor conversion with optional exact rectangular enclosure.

    A zero recorded before a run must remain available; this helper does not
    continuously retare, remove drift or identify clay-only deformation.
    """
    if SI_unit not in ("N", "m"):
        raise ValueError("Slow conversion supports force N or displacement m")
    delta = _f(raw_value)-_f(zero_raw)
    scale = _f(scale_SI_per_raw)
    if scale == 0:
        raise ValueError("Slow sensor scale cannot be zero")
    nominal = delta*scale
    bounds = None
    if all(value is not None for value in (raw_error_abs, zero_error_abs, scale_error_abs)):
        de = _nonnegative(raw_error_abs)+_nonnegative(zero_error_abs)
        se = _nonnegative(scale_error_abs)
        corners = [(delta+d)*(scale+s) for d in (-de,de) for s in (-se,se)]
        bounds = [str(min(corners)), str(max(corners))]
    elif any(value is not None for value in (raw_error_abs, zero_error_abs, scale_error_abs)):
        raise ValueError("All three slow uncertainty terms are required for an enclosure")
    value = float(nominal)
    if not math.isfinite(value):
        raise ValueError("Slow SI result exceeds finite output range")
    return {"value_SI": value, "exact_decimal_model": str(nominal), "SI_unit": SI_unit,
            "conditional_interval_exact_decimal_model": bounds,
            "zero_raw_preserved": str(_f(zero_raw)),
            "interpretation": "measured sensor port only; fixture compliance and clay strain not identified"}
