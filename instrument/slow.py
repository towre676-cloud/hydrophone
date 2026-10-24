"""Descriptive features of a sampled, slow force/displacement record.

Work is signed work at the measured writer port, not identified clay
dissipation.  Error intervals concern the trapezoidal sampled path only;
unobserved motion between samples is not bounded by this module.
"""

from __future__ import annotations

import csv
from fractions import Fraction
import hashlib
import math
from pathlib import Path


def _number(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _nonnegative(value, name):
    if value is None:
        return None
    result = _number(value, name)
    if result < 0:
        raise ValueError(f"{name} must be nonnegative")
    return result


def _finite_result(value, name):
    if not math.isfinite(value):
        raise ValueError(f"{name} exceeds finite floating-point range")
    return value


def _sum(values, name):
    try:
        return _finite_result(math.fsum(values), name)
    except OverflowError as exc:
        raise ValueError(f"{name} exceeds finite floating-point range") from exc


def _mean(values):
    return _sum((x / len(values) for x in values), "sample mean")


def _outward_float(value, direction):
    """Round a rational endpoint outward, or reject an unrepresentable one."""
    try:
        result = _finite_result(float(value), "work enclosure endpoint")
    except OverflowError as exc:
        raise ValueError("work enclosure endpoint exceeds finite floating-point range") from exc
    exact_result = Fraction.from_float(result)
    if direction < 0 and exact_result > value:
        result = math.nextafter(result, -math.inf)
    elif direction > 0 and exact_result < value:
        result = math.nextafter(result, math.inf)
    return _finite_result(result, "work enclosure endpoint")


def _read_rows(path, time_column="time_s"):
    required = {time_column, "force_N", "displacement_m"}
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, strict=True)
        fields = reader.fieldnames
        if not fields or len(fields) != len(set(fields)):
            raise ValueError("CSV headers must be present and unique")
        if not required.issubset(fields):
            raise ValueError(f"CSV requires {time_column}, force_N and displacement_m")
        try:
            for line_number, raw in enumerate(reader, start=2):
                if None in raw or any(value is None for value in raw.values()):
                    raise ValueError(f"CSV row {line_number} has the wrong field count")
                row = {name: _number(raw[name], f"row {line_number} {name}")
                       for name in ("force_N", "displacement_m")}
                row["time_s"] = _number(raw[time_column], f"row {line_number} {time_column}")
                if time_column != "time_s":
                    row[time_column] = row["time_s"]
                if "temperature_C" in fields:
                    row["temperature_C"] = _number(
                        raw["temperature_C"], f"row {line_number} temperature_C"
                    )
                if "stage" in fields:
                    row["stage"] = raw["stage"]
                if rows and row["time_s"] <= rows[-1]["time_s"]:
                    raise ValueError("CSV timestamps must be strictly increasing")
                rows.append(row)
        except csv.Error as exc:
            raise ValueError(f"invalid CSV: {exc}") from exc
    if len(rows) < 2:
        raise ValueError("CSV needs at least two samples")
    return rows, "stage" in fields


def _stage(row):
    return row.get("stage", "").strip().casefold()


def _baseline(rows, stage_present):
    baseline_names = {"baseline", "baseline_before"}
    selected = []
    if stage_present and _stage(rows[0]) in baseline_names:
        for row in rows:
            if _stage(row) not in baseline_names:
                break
            selected.append(row)
    else:
        selected = [rows[0]]
    return {
        "selection": "contiguous_initial_baseline_stage"
        if stage_present and _stage(rows[0]) in baseline_names
        else "first_sample_only_no_baseline_stage_inferred",
        "sample_count": len(selected),
        "time_start_s": selected[0]["time_s"],
        "time_end_s": selected[-1]["time_s"],
        "force_mean_N": _mean([row["force_N"] for row in selected]),
        "displacement_mean_m": _mean([row["displacement_m"] for row in selected]),
        "raw_samples": [dict(row) for row in selected],
        "detrended": False,
    }


def _hold_segments(rows, stage_present, window):
    if window is not None:
        selected = [row for row in rows if window[0] <= row["time_s"] <= window[1]]
        return [(selected, list(window), "explicit_window")]
    if not stage_present:
        return []
    segments, current = [], []
    for row in rows:
        if _stage(row) == "hold":
            current.append(row)
        elif current:
            segments.append((current, None, "contiguous_hold_stage"))
            current = []
    if current:
        segments.append((current, None, "contiguous_hold_stage"))
    return segments


def _hold_features(selected, requested_window, selection, rows, stage_present,
                   drift_tolerance, force_error, baseline):
    reasons = []
    if requested_window is not None and (
        requested_window[0] < rows[0]["time_s"]
        or requested_window[1] > rows[-1]["time_s"]
    ):
        reasons.append("requested_window_outside_record")
    if len(selected) < 5:
        reasons.append("fewer_than_five_hold_samples")
    if stage_present and any(_stage(row) != "hold" for row in selected):
        reasons.append("selected_samples_not_all_labelled_hold")
    result = {
        "selection": selection,
        "requested_window_s": requested_window,
        "sample_count": len(selected),
        "eligible": False,
        "reasons": reasons,
        "raw_start": dict(selected[0]) if selected else None,
        "raw_end": dict(selected[-1]) if selected else None,
        "baseline_force_N": baseline["force_mean_N"],
        "features": None,
    }
    if not selected:
        return result
    duration = _finite_result(selected[-1]["time_s"] - selected[0]["time_s"],
                              "hold duration")
    positions = [row["displacement_m"] for row in selected]
    drift = _finite_result(max(positions) - min(positions), "hold displacement range")
    result.update({
        "time_start_s": selected[0]["time_s"],
        "time_end_s": selected[-1]["time_s"],
        "duration_s": duration,
        "elapsed_from_record_start_s": selected[0]["time_s"] - rows[0]["time_s"],
        "displacement_range_m": drift,
        "max_hold_drift_m": drift_tolerance,
    })
    if duration <= 0:
        reasons.append("nonpositive_hold_duration")
    if drift_tolerance is None:
        reasons.append("hold_displacement_tolerance_not_declared")
    elif drift > drift_tolerance:
        reasons.append("hold_displacement_drift_exceeds_tolerance")
    if reasons:
        return result
    block = max(1, len(selected) // 5)
    first_force = _mean([row["force_N"] for row in selected[:block]])
    last_force = _mean([row["force_N"] for row in selected[-block:]])
    amplitude = _finite_result(first_force - baseline["force_mean_N"],
                               "baseline-relative hold force")
    if force_error is None:
        fraction, fraction_status = None, "force_error_bound_not_declared"
    elif abs(amplitude) <= 2 * force_error:
        fraction, fraction_status = None, "baseline_relative_force_not_resolved"
    else:
        fraction = _finite_result((first_force - last_force) / amplitude,
                                  "relaxation fraction")
        fraction_status = "descriptive_ratio_with_resolved_denominator"
    result["eligible"] = True
    result["features"] = {
        "endpoint_block_samples": block,
        "first_block_force_mean_N": first_force,
        "last_block_force_mean_N": last_force,
        "force_drop_N": _finite_result(first_force - last_force, "hold force drop"),
        "baseline_relative_start_force_N": amplitude,
        "relaxation_fraction": fraction,
        "relaxation_fraction_status": fraction_status,
        "interpretation": "descriptive_force_change_during_declared_displacement_hold",
        "relaxation_time_identified": False,
    }
    return result


def analyze_slow(csv_path, *, displacement_closure_tolerance_m=None,
                 force_return_tolerance_N=None, hold_window_s=None,
                 max_hold_drift_m=None, force_error_N=None,
                 displacement_error_m=None, rod_state="unknown",
                 calibration_declared=False, time_column="time_s"):
    """Read strict CSV and describe work, closure and declared hold intervals.

    Optional tolerances/errors are uniform nonnegative absolute bounds in the
    named units. ``None`` means unknown, never an invented zero tolerance.
    ``hold_window_s`` is an inclusive (start, end) pair; when a stage column
    exists every selected sample must also be labelled ``hold``. Without an
    explicit window only contiguous ``hold`` stages are considered.
    """
    x_tolerance = _nonnegative(displacement_closure_tolerance_m,
                              "displacement_closure_tolerance_m")
    f_tolerance = _nonnegative(force_return_tolerance_N, "force_return_tolerance_N")
    drift_tolerance = _nonnegative(max_hold_drift_m, "max_hold_drift_m")
    e_force = _nonnegative(force_error_N, "force_error_N")
    e_position = _nonnegative(displacement_error_m, "displacement_error_m")
    if not isinstance(calibration_declared, bool):
        raise ValueError("calibration_declared must be a boolean")
    if not isinstance(rod_state, str) or not rod_state.strip():
        raise ValueError("rod_state must be a nonempty declaration")
    window = None
    if hold_window_s is not None:
        if not isinstance(hold_window_s, (tuple, list)) or len(hold_window_s) != 2:
            raise ValueError("hold_window_s must be a (start, end) pair")
        window = tuple(_number(value, "hold_window_s") for value in hold_window_s)
        if window[1] <= window[0]:
            raise ValueError("hold_window_s must have end greater than start")
    path = Path(csv_path)
    if time_column not in ("time_s", "logger_time_s"):
        raise ValueError("time_column must be time_s or logger_time_s")
    rows, stage_present = _read_rows(path, time_column)
    baseline = _baseline(rows, stage_present)
    segments = list(zip(rows, rows[1:]))
    gaps = [_finite_result(b["time_s"] - a["time_s"], "sample gap")
            for a, b in segments]
    delta_positions = [_finite_result(b["displacement_m"] - a["displacement_m"],
                                     "sample displacement difference")
                       for a, b in segments]
    mean_forces = [0.5 * a["force_N"] + 0.5 * b["force_N"] for a, b in segments]
    work = _sum((force * dx for force, dx in zip(mean_forces, delta_positions)),
                "sampled path work")
    error_bound, work_interval = None, None
    if e_force is not None and e_position is not None:
        # Exact rationals of the parsed binary samples avoid rounding an outer
        # bound inward. CSV decimal-to-binary conversion is a declared part of
        # the sample semantics, not a sensor-calibration uncertainty model.
        q_force, q_position = Fraction.from_float(e_force), Fraction.from_float(e_position)
        exact_work, exact_error = Fraction(0), Fraction(0)
        for before, after in segments:
            force = (Fraction.from_float(before["force_N"])
                     + Fraction.from_float(after["force_N"])) / 2
            dx = (Fraction.from_float(after["displacement_m"])
                  - Fraction.from_float(before["displacement_m"]))
            exact_work += force * dx
            exact_error += (q_force * abs(dx) + 2 * q_position * abs(force)
                            + 2 * q_force * q_position)
        # Report a symmetric error radius about the displayed nominal value,
        # including its final floating-point rounding, and sharper endpoints.
        error_bound = _outward_float(
            exact_error + abs(exact_work - Fraction.from_float(work)), 1)
        work_interval = [_outward_float(exact_work - exact_error, -1),
                         _outward_float(exact_work + exact_error, 1)]
    delta_x = _finite_result(rows[-1]["displacement_m"] - rows[0]["displacement_m"],
                             "endpoint displacement difference")
    delta_force = _finite_result(rows[-1]["force_N"] - rows[0]["force_N"],
                                 "endpoint force difference")
    holds = [_hold_features(selected, requested, selection, rows, stage_present,
                            drift_tolerance, e_force, baseline)
             for selected, requested, selection in
             _hold_segments(rows, stage_present, window)]
    return {
        "schema": "fusion.slow-features/1",
        "source_csv": str(path.resolve()),
        "source_time_column": time_column,
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "sample_count": len(rows),
        "raw_start": dict(rows[0]),
        "raw_end": dict(rows[-1]),
        "baseline": baseline,
        "timestamps": {
            "start_s": rows[0]["time_s"],
            "end_s": rows[-1]["time_s"],
            "duration_s": _finite_result(rows[-1]["time_s"] - rows[0]["time_s"],
                                          "record duration"),
            "max_sample_gap_s": max(gaps),
            "strictly_increasing": True,
        },
        "work": {
            "sampled_path_work_J": work,
            "quantity": "signed_measured_writer_port_work_not_clay_dissipation",
            "method": "trapezoidal_force_displacement_in_time_order",
            "sign_convention": "force_on_specimen_positive_along_positive_displacement_must_be_verified",
            "force_error_N": e_force,
            "displacement_error_m": e_position,
            "sampled_path_error_bound_J": error_bound,
            "sampled_path_interval_J": work_interval,
            "sample_value_semantics": "finite_parsed_binary_float_samples",
            "interval_arithmetic": "rational_sample_bound_with_outward_rounded_float_endpoints"
            if work_interval is not None else "error_bounds_not_declared",
            "error_bound_scope": "uniform_sample_errors_only_interpolation_and_undersampling_excluded",
            "between_sample_path_error_bounded": False,
            "dissipation_identified": False,
        },
        "closure": {
            "endpoint_displacement_change_m": delta_x,
            "endpoint_force_change_N": delta_force,
            "displacement_closure_tolerance_m": x_tolerance,
            "force_return_tolerance_N": f_tolerance,
            "geometric_loop_closed": abs(delta_x) <= x_tolerance
            if x_tolerance is not None else None,
            "force_returned": abs(delta_force) <= f_tolerance
            if f_tolerance is not None else None,
            "scope": "observed_endpoints_only_not_a_thermodynamic_closure_test",
            "internal_state_returned": None,
        },
        "hold_analysis": {
            "selection": "explicit_window" if window is not None
            else "declared_hold_stages" if stage_present
            else "no_declared_hold_stage_or_window",
            "windows": holds,
            "eligible_window_count": sum(item["eligible"] for item in holds),
        },
        "rod_state": rod_state,
        "calibration_declared": calibration_declared,
        "calibration_verified": False,
        "interpretation_status": "calibration_declared_not_independently_verified"
        if calibration_declared else "declared_units_only",
        "physical_readiness": False,
        "limitations": [
            "No material law, relaxation time, modulus, memory identity or dissipation is identified.",
            "Force/displacement calibration, sign, fixture loading and clock provenance are declarations.",
            "A geometric loop can exchange stored internal energy even when force also returns.",
            "Writer-port work includes fixture forces; rod and other coupling states must be controlled.",
        ],
    }
