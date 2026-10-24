"""Conservative axial boss-motion witness from declared measured bounds.

No instrument is opened and no actuator command is emitted. Exact rational
arithmetic encloses the declared decimal model. Unknown spectral, transient,
drift, setup or amplitude-scaling terms block qualification. This module does
not infer those terms from a least-squares residual or instrument data sheet.
"""
from __future__ import annotations

import argparse
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path

PI_LOWER = F("3.14159265358979323846264338327950288419716939937510")
PI_UPPER = PI_LOWER+F(1,10**50)
REMAINDERS = ("in_band_non_tone_peak_m", "outside_measured_band_peak_m",
              "sub_band_and_equilibrium_drift_peak_m", "drive_on_off_transient_peak_m",
              "instrument_head_and_mount_motion_peak_m")


class Blocked(ValueError):
    pass


def number(value, label):
    if value is None or isinstance(value, bool):
        raise Blocked(label+" is unresolved")
    try:
        result = F(str(value))
        rendered = float(result)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
        raise Blocked(label+" must be a finite decimal number") from exc
    if not math.isfinite(rendered):
        raise Blocked(label+" exceeds finite output range")
    return result


def positive(value, label, *, zero=False):
    result = number(value, label)
    if result < 0 or (result == 0 and not zero):
        raise Blocked(label+" must be "+("nonnegative" if zero else "positive"))
    return result


def sqrt_upper(value):
    """Exact upper square-root enclosure with a rational 1e-24 grid."""
    if value < 0:
        raise Blocked("Negative squared amplitude")
    grid = 10**24
    scaled = (value.numerator*grid*grid+value.denominator-1)//value.denominator
    root = math.isqrt(scaled)
    if root*root < scaled:
        root += 1
    return F(root, grid)


def amplitude_upper(phasor, label):
    if not isinstance(phasor, dict):
        raise Blocked(label+" complex phasor is unresolved")
    re = number(phasor.get("real"), label+" real")
    im = number(phasor.get("imag"), label+" imag")
    error = positive(phasor.get("error_radius_abs"), label+" error radius", zero=True)
    return sqrt_upper(re*re+im*im)+error


def derive_boss_over_bridge(boss_displacement_m, bridge_acceleration_m_per_s2,
                           frequency_SI_Hz, frequency_error_Hz):
    """Derive R=boss/bridge displacement at one measured stationary frequency.

    Inputs must be calibrated, common-phase-origin SI phasors whose disks
    cover their complete measurement error. This point calculation does not
    establish R's applicability to a different amplitude, wet preload or time.
    """
    b=(number(boss_displacement_m.get("real"),"boss real"),
       number(boss_displacement_m.get("imag"),"boss imag"))
    a=(number(bridge_acceleration_m_per_s2.get("real"),"acceleration real"),
       number(bridge_acceleration_m_per_s2.get("imag"),"acceleration imag"))
    rb=positive(boss_displacement_m.get("error_radius_abs"),"boss error",zero=True)
    ra=positive(bridge_acceleration_m_per_s2.get("error_radius_abs"),"acceleration error",zero=True)
    f=positive(frequency_SI_Hz,"frequency");ef=positive(frequency_error_Hz,"frequency error",zero=True)
    if f-ef <= 0:
        raise Blocked("Transfer frequency uncertainty reaches DC")
    lower=max(abs(a[0]),abs(a[1]))-ra
    norm2=a[0]*a[0]+a[1]*a[1]
    if lower <= 0 or norm2 == 0:
        raise Blocked("Measured bridge acceleration denominator is unresolved")
    d=((b[0]*a[0]+b[1]*a[1])/norm2,
       (b[1]*a[0]-b[0]*a[1])/norm2)
    dabs=sqrt_upper(d[0]*d[0]+d[1]*d[1])
    rd=(rb+dabs*ra)/lower
    wm=(2*((PI_LOWER+PI_UPPER)/2)*f)**2
    wl=(2*PI_LOWER*(f-ef))**2
    wh=(2*PI_UPPER*(f+ef))**2
    nominal=(-wm*d[0],-wm*d[1])
    radius=wh*rd+dabs*max(wm-wl,wh-wm)
    return {"real":str(nominal[0]),"imag":str(nominal[1]),
            "error_radius_abs":str(radius),"SI_unit":"m/m",
            "frequency_SI_Hz":str(f),"frequency_error_Hz":str(ef),
            "status":"CONDITIONAL_MEASURED_POINT_RATIO_NOT_UNIFORM_DOMAIN_QUALIFICATION",
            "hardware_execution_enabled":False}


def _references(ids, available, label):
    if not isinstance(ids, list) or not ids or any(value not in available for value in ids):
        raise Blocked(label+" needs bound/source evidence IDs")


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or value == "REPLACE":
        raise Blocked(label+" is unresolved")
    return value


def _qualify(record, digital_peak, configuration_id, evidence_root):
    if record.get("schema") != "hydrophone.motion-qualification/1":
        raise Blocked("Unknown motion witness schema")
    if record.get("status") != "measurements_with_declared_bounds":
        raise Blocked("Motion measurements/bounds have not been supplied")
    evidence_type = record.get("evidence_type")
    if evidence_type not in ("physical_measurements_declared", "synthetic_demo"):
        raise Blocked("Motion evidence origin is unresolved")
    identity = _text(record.get("configuration_id"), "configuration_id")
    if configuration_id is None or configuration_id != identity:
        raise Blocked("Explicit current configuration_id must match witness")
    if record.get("target_port") != "boss_center_axial":
        raise Blocked("This witness covers axial boss-center motion only; whole-membrane qualification needs a separate spatial witness")
    sources = record.get("evidence_files")
    if not isinstance(sources, list) or not sources:
        raise Blocked("Raw motion/calibration evidence inventory is missing")
    available = set()
    for source in sources:
        sid = _text(source.get("id"), "evidence ID")
        digest = source.get("sha256")
        if sid in available or not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise Blocked("Evidence IDs/hashes must be unique valid declarations")
        available.add(sid)
        if evidence_type == "physical_measurements_declared":
            if evidence_root is None:
                raise Blocked("Physical witness needs its raw evidence directory for hash checks")
            root = Path(evidence_root).resolve()
            name = source.get("path")
            if not isinstance(name, str) or Path(name).is_absolute():
                raise Blocked("Physical evidence files need relative paths")
            path = (root/name).resolve()
            if not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise Blocked("Physical evidence path/hash check failed: "+str(name))
    conditions = record.get("conditions", {})
    for field in ("wet_equilibrium_id", "rod_engagement_id", "writer_engagement_id", "preload_state_id",
                  "sensor_mount_id", "frequency_timebase_calibration_id"):
        _text(conditions.get(field), field)
    for field in ("same_waveform_family", "same_configuration", "stationarity_checked",
                  "no_clipping_or_dropout", "bounds_include_projection_and_rotation"):
        if conditions.get(field) is not True:
            raise Blocked("Required condition unresolved: "+field)
    _references(conditions.get("evidence_ids"), available, "Condition checks")
    requested = record.get("probe_frequencies_SI_Hz")
    if not isinstance(requested, list) or not requested:
        raise Blocked("Probe frequency inventory is missing")
    requested = [positive(f, "probe frequency") for f in requested]
    if len(set(requested)) != len(requested):
        raise Blocked("Probe frequencies must be distinct")
    band = record.get("observed_motion_band_SI_Hz")
    if not isinstance(band,list) or len(band)!=2:
        raise Blocked("Observed motion bandwidth is unresolved")
    band_lo=positive(band[0],"observed band lower edge",zero=True)
    band_hi=positive(band[1],"observed band upper edge")
    if band_lo>=band_hi:
        raise Blocked("Observed motion band must have ordered edges")
    required=record.get("required_time_interval_SI_s")
    measured=record.get("measurement_time_interval_SI_s")
    if not isinstance(required,list) or len(required)!=2 or not isinstance(measured,list) or len(measured)!=2:
        raise Blocked("Required/measured motion time support is unresolved")
    rt0,rt1=[number(t,"required time boundary") for t in required]
    mt0,mt1=[number(t,"measured time boundary") for t in measured]
    te=positive(record.get("measurement_time_error_s"),"measurement time error",zero=True)
    if rt0>=rt1 or not mt0+te<=rt0<rt1<=mt1-te:
        raise Blocked("Conservative measured time support does not cover the requested full waveform")
    tones = record.get("tones")
    if not isinstance(tones, list):
        raise Blocked("Per-tone motion measurements are missing")
    found = [positive(t.get("frequency_SI_Hz"), "tone frequency") for t in tones]
    if len(set(found)) != len(found) or set(found) != set(requested):
        raise Blocked("Tone inventory must cover every probe frequency exactly once")
    tone_bounds = []
    for tone, frequency in zip(tones, found):
        _references(tone.get("evidence_ids"), available, "Tone "+str(frequency))
        ferr = positive(tone.get("frequency_error_Hz"), "frequency error", zero=True)
        low = frequency-ferr
        if low <= 0:
            raise Blocked("Frequency uncertainty reaches DC")
        if low<band_lo or frequency+ferr>band_hi:
            raise Blocked("Probe frequency uncertainty leaves observed motion band")
        mode = tone.get("mode")
        if mode == "direct_boss_displacement":
            upper = amplitude_upper(tone.get("boss_displacement_m"), "boss displacement")
            method = "direct displacement phasor plus disk radius"
        elif mode == "direct_boss_velocity":
            upper = amplitude_upper(tone.get("boss_velocity_m_per_s"), "boss velocity")/(2*PI_LOWER*low)
            method = "boss velocity / conservative lower angular frequency"
        elif mode == "bridge_acceleration_with_measured_transfer":
            acceleration = amplitude_upper(tone.get("bridge_acceleration_m_per_s2"), "bridge acceleration")
            transfer = tone.get("boss_over_bridge_displacement")
            ratio = amplitude_upper(transfer, "measured boss/bridge transfer")
            _references(tone.get("transfer_evidence_ids"), available, "Transfer")
            if tone.get("transfer_domain_covers_frequency_amplitude_preload") is not True:
                raise Blocked("Boss/bridge transfer validity domain is unresolved")
            upper = acceleration*ratio/(2*PI_LOWER*low)**2
            method = "(|a|+error)(|R|+error)/(2*pi_lower*(f-error))^2"
        else:
            raise Blocked("Unknown or unresolved motion measurement mode")
        tone_bounds.append({"frequency_SI_Hz": str(frequency),
                            "frequency_SI_Hz_display": float(frequency),
                            "axial_boss_peak_upper_m": str(upper),
                            "axial_boss_peak_upper_um_display": float(upper*10**6),
                            "method": method})
    remainder = F(0)
    remainder_results = {}
    for name in REMAINDERS:
        item = record.get("remainder_bounds", {}).get(name)
        if not isinstance(item, dict) or item.get("scope") != "uniform_over_declared_command_domain":
            raise Blocked(name+" is unbounded over the command domain")
        value = positive(item.get("bound_m"), name, zero=True)
        _references(item.get("evidence_ids"), available, name)
        remainder += value
        remainder_results[name] = str(value)
    limit = positive(record.get("boss_motion_limit_m"), "boss motion limit")
    if limit > F(".00001"):
        raise Blocked("Requested limit exceeds the M03 10-micrometre commissioning ceiling")
    reference = positive(record.get("reference_digital_peak"), "reference digital peak")
    if reference > 1:
        raise Blocked("Digital peak cannot exceed full scale")
    peak = reference if digital_peak is None else positive(digital_peak, "digital peak", zero=True)
    scaling = record.get("amplitude_scaling", {})
    mode = scaling.get("mode")
    base_sum = sum(F(t["axial_boss_peak_upper_m"]) for t in tone_bounds)
    max_peak = None
    if mode == "measured_reference_only":
        if peak != reference:
            raise Blocked("No amplitude-scaling witness: only the measured reference command is covered")
        total = base_sum+remainder
        if total <= limit:
            max_peak = reference
        scaling_error = F(0)
    elif mode == "uniform_linear_envelope_declared":
        _references(scaling.get("evidence_ids"), available, "Amplitude scaling")
        domain = scaling.get("digital_peak_domain")
        if not isinstance(domain, list) or len(domain) != 2:
            raise Blocked("Measured amplitude domain is unresolved")
        lo, hi = [positive(v, "amplitude domain", zero=True) for v in domain]
        if not 0 <= lo <= reference <= hi <= 1 or not lo <= peak <= hi:
            raise Blocked("Requested amplitude/reference lies outside validated command domain")
        scaling_error = positive(scaling.get("relative_gain_error_upper"), "uniform scaling error", zero=True)
        if scaling.get("covers_waveform_quantization_and_nonlinearity") is not True:
            raise Blocked("Amplitude scaling must include quantization and nonlinear changes")
        total = peak/reference*base_sum*(1+scaling_error)+remainder
        slope = base_sum*(1+scaling_error)/reference
        if remainder <= limit:
            candidate = hi if slope == 0 else min(hi, (limit-remainder)/slope)
            if candidate >= lo:
                max_peak = candidate
    else:
        raise Blocked("Amplitude scaling/reference-only mode is unresolved")
    within = total <= limit
    status = ("SYNTHETIC_WITHIN_LIMIT" if evidence_type == "synthetic_demo" else
              "WITHIN_LIMIT_CONDITIONAL_ON_DECLARED_EVIDENCE") if within else "EXCEEDS_DECLARED_MOTION_LIMIT"
    return {"schema": "hydrophone.motion-qualification-result/1", "status": status,
            "evidence_type": evidence_type, "configuration_id": identity,
            "target_port": "boss_center_axial", "whole_diaphragm_qualified": False,
            "observed_motion_band_SI_Hz":[str(band_lo),str(band_hi)],
            "qualified_time_interval_SI_s":[str(rt0),str(rt1)],
            "requested_digital_peak": str(peak), "reference_digital_peak": str(reference),
            "tone_bounds_at_reference": tone_bounds,
            "sum_tone_peak_bounds_at_reference_m": str(base_sum),
            "uniform_remainder_bounds_m": remainder_results,
            "sum_uniform_remainders_m": str(remainder),
            "uniform_scaling_relative_error_upper": str(scaling_error),
            "boss_motion_peak_upper_m": str(total), "boss_motion_limit_m": str(limit),
            "boss_motion_peak_upper_um_display": float(total*10**6),
            "boss_motion_limit_um_display": float(limit*10**6),
            "largest_supported_digital_peak_under_bound": None if max_peak is None else str(max_peak),
            "largest_supported_digital_peak_display": None if max_peak is None else float(max_peak),
            "within_declared_limit": within, "hardware_execution_enabled": False,
            "evidence_hashes_checked": evidence_type == "physical_measurements_declared",
            "evidence_authenticity_verified": False,
            "limitations": ["All physical errors and domain statements are supplied measurements/declarations, not inferred from this arithmetic.",
                "The triangle envelope includes supplied non-tone/out-of-band/drift/transient/head-motion bounds; an unknown bound must block.",
                "Phase cancellation is not used to enlarge the permitted peak.",
                "A boss-center witness does not bound the maximum elsewhere on the diaphragm.",
                "No actuator, displacement interlock, material law or retained-memory result is implemented."]}


def qualify_motion(record, *, digital_peak=None, configuration_id=None, evidence_root=None):
    """Return an explicit BLOCKED result for incomplete/unusable records."""
    try:
        return _qualify(record, digital_peak, configuration_id, evidence_root)
    except (Blocked, KeyError, TypeError, IndexError, ZeroDivisionError, AttributeError, OSError, OverflowError) as exc:
        return {"schema": "hydrophone.motion-qualification-result/1", "status": "BLOCKED",
                "reasons": [str(exc)], "within_declared_limit": False,
                "largest_supported_digital_peak_under_bound": None,
                "hardware_execution_enabled": False, "evidence_hashes_checked":False,
                "evidence_authenticity_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument("--configuration-id", required=True)
    parser.add_argument("--digital-peak")
    parser.add_argument("--derive-transfer",action="store_true",
                        help="Read boss/bridge-transfer-input/1 and compute per-point R disks")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = args.record.read_bytes()
    record = json.loads(data, parse_constant=lambda x: (_ for _ in ()).throw(ValueError("Nonfinite JSON "+x)))
    if args.derive_transfer:
        if record.get("schema") != "hydrophone.boss-bridge-transfer-input/1" or record.get("configuration_id") != args.configuration_id:
            raise ValueError("Transfer input schema/configuration mismatch")
        if record.get("evidence_type") not in ("physical_measurements_declared","synthetic_demo"):
            raise ValueError("Transfer input evidence origin must be explicit")
        result={"schema":"hydrophone.boss-bridge-transfer-result/1",
                "evidence_type":record["evidence_type"],"configuration_id":args.configuration_id,
                "points":[derive_boss_over_bridge(p['boss_displacement_m'],p['bridge_acceleration_m_per_s2'],
                                                  p['frequency_SI_Hz'],p['frequency_error_Hz'])
                          for p in record['points']],
                "domain_qualified":False,"hardware_execution_enabled":False}
    else:
        result = qualify_motion(record, digital_peak=args.digital_peak, configuration_id=args.configuration_id,
                                evidence_root=args.record.resolve().parent)
    result["source_record_sha256"] = hashlib.sha256(data).hexdigest()
    encoded = json.dumps(result, indent=2, allow_nan=False)+"\n"
    if args.output:
        if args.output.exists():
            raise ValueError("Output already exists; preserve prior qualification receipts")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    if args.output:
        print(json.dumps({"status":result.get("status","TRANSFER_POINTS_COMPUTED"),
                          "boss_motion_peak_upper_um_display":result.get("boss_motion_peak_upper_um_display"),
                          "largest_supported_digital_peak_display":result.get("largest_supported_digital_peak_display"),
                          "hardware_execution_enabled":False}))
    else:
        print(encoded, end="")
    return 0 if args.derive_transfer or result.get("within_declared_limit") else 2


if __name__ == "__main__":
    raise SystemExit(main())
