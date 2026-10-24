#!/usr/bin/env python3
"""Live, conditional writer observations; no actuator commands or interlock.

Offline demonstration:
  python hardware/readout/writer_display.py --demo --output-dir results/readout_demo
Physical acquisition, only after installed calibration and timing qualification:
  python hardware/readout/writer_display.py --execute --identifier SERIAL \
    --calibration measured.json --context session.json --output-dir results/writer

The main thread owns the T7 capture. A separate display watchdog continues
showing STOP if a device read blocks. Native raw files are never rewritten.
"""
from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import threading
import time

ROLES = ("force", "position")
LIMITS = {"force": 5.0, "position": 0.00025}
RAW_COLUMNS = {"force": "raw_force_V", "position": "raw_displacement_V"}
UNITS = {"force": "N", "position": "m"}
SCAN_LIST = ["AIN0", "AIN2", "AIN4", "AIN6"]


def rational(value):
    """Exact arithmetic on supplied decimal representations, not sensor truth."""
    number(value, "decimal model value")
    return Fraction(str(value))


def outward(value, direction):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Interval exceeds finite display range")
    represented = Fraction.from_float(result)
    if direction < 0 and represented > value or direction > 0 and represented < value:
        result = math.nextafter(result, -math.inf if direction < 0 else math.inf)
    return result


def number(value, name):
    if value is None or isinstance(value, bool):
        raise ValueError(name + " must be finite")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(name + " must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(name + " must be finite")
    return result


def nonnegative(value, name):
    result = number(value, name)
    if rational(value) < 0:
        raise ValueError(name + " must be nonnegative")
    return result


def interval(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(name + " must have two endpoints")
    lo, hi = [number(x, name) for x in value]
    if rational(value[0]) > rational(value[1]):
        raise ValueError(name + " endpoints are reversed")
    return lo, hi


def identity(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + " is missing")
    return value


def evidence(value, name):
    if not isinstance(value, list) or not value:
        raise ValueError(name + " is missing")
    for item in value:
        identity(item, name)


def utc(value):
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("An explicit timezone-aware UTC timestamp is required") from exc
    if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
        raise ValueError("An explicit UTC timestamp is required")
    return result.astimezone(timezone.utc)


def utc_now():
    return datetime.now(timezone.utc)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def validate_calibration(record, context, *, now=None, allow_synthetic=False):
    """Check declarations and domains; this cannot authenticate physical evidence."""
    now = utc(now or utc_now())
    if record.get("schema") != "hydrophone.writer-calibration/1":
        raise ValueError("Unknown writer calibration schema")
    if record.get("status") != "measured_with_declared_scope":
        raise ValueError("Calibration is blocked/unmeasured")
    kind = record.get("evidence_type")
    if kind != "physical_calibration_declared" and not (allow_synthetic and kind == "synthetic_demo"):
        raise ValueError("Physical calibration evidence is required; synthetic records cannot operate hardware")
    identity(record.get("calibration_id"), "calibration_id")
    evidence(record.get("reference_evidence_ids"), "calibration reference evidence")
    if not utc(record.get("created_utc")) <= now <= utc(record.get("valid_until_utc")):
        raise ValueError("Calibration is outside its declared validity dates")
    if context.get("schema") != "hydrophone.writer-session/1":
        raise ValueError("Unknown writer session schema")
    identity(context.get("run_id"), "run_id")
    identity(context.get("operator_id"), "operator_id")
    evidence(context.get("identity_check_evidence_ids"), "installed identity checks")
    scope = record["scope"]
    for key in ("configuration_id", "adc_serial", "force_sensor_serial", "position_sensor_serial",
                "filter_configuration_id", "mechanics_revision", "operation"):
        if identity(scope.get(key), key) != context.get(key):
            raise ValueError("Installed session differs from calibration: " + key)
    if scope["operation"] != "bidirectional_quasistatic":
        raise ValueError("Only the qualified bidirectional quasistatic writer scope is supported")
    if set(scope.get("qualified_direction_scope", [])) != {"positive", "negative"}:
        raise ValueError("Both signed load directions require qualification")
    profile = scope.get("wiring_profile", "E01")
    expected_scan_list = SCAN_LIST + (["AIN8"] if profile == "E02" else [])
    if profile not in ("E01", "E02") or scope.get("scan_list") != expected_scan_list or scope.get("resolution_index") != 7 or scope.get("range_V") != 10:
        raise ValueError("Calibration does not match the T7 channel/range/resolution plan")
    if isinstance(scope.get("scans_per_read"), bool) or not isinstance(scope.get("scans_per_read"), int) or scope.get("scans_per_read") not in range(1, 11):
        raise ValueError("Calibration scans_per_read must be 1..10")
    if interval(scope.get("sample_rate_Hz_interval"), "sample-rate domain")[0] <= 0:
        raise ValueError("Sample-rate domain must be positive")
    if interval(scope.get("valid_excitation_V"), "excitation domain")[0] <= 0:
        raise ValueError("Excitation domain must be positive")
    temp = number(context.get("temperature_C"), "measured temperature")
    temp_error = nonnegative(context.get("temperature_error_C"), "temperature error")
    lo, hi = interval(scope.get("valid_temperature_C"), "temperature domain")
    temperature_exact = rational(context["temperature_C"])
    temperature_error_exact = rational(context["temperature_error_C"])
    if (temperature_exact-temperature_error_exact < rational(scope["valid_temperature_C"][0])
            or temperature_exact+temperature_error_exact > rational(scope["valid_temperature_C"][1])):
        raise ValueError("Temperature uncertainty leaves the calibrated domain")
    env_age = (now-utc(context.get("temperature_observed_utc"))).total_seconds()
    env_valid = number(scope.get("environment_valid_for_s"), "environment validity")
    if env_valid <= 0 or env_age < 0 or env_age > env_valid:
        raise ValueError("Measured temperature is stale or future dated")
    timing = record["timing"]
    if timing.get("scope") != "native_scan_clock_filtered_channels_not_simultaneous":
        raise ValueError("Native sequential scan/filter scope is required")
    for key in ("pairing_id", "clock_origin_evidence_id"):
        identity(timing.get(key), key)
    interval(timing.get("first_scan_offset_from_call_interval_s"), "first-scan clock-origin bounds")
    if interval(timing.get("host_seconds_per_logger_nominal_second_interval"), "clock-rate bounds")[0] <= 0:
        raise ValueError("Clock-rate bounds must remain positive")
    if number(timing.get("maximum_observation_age_s"), "maximum observation age") <= 0:
        raise ValueError("Maximum observation age must be positive")
    for role in ROLES:
        channel = record["channels"][role]
        if channel.get("raw_column") != RAW_COLUMNS[role] or channel.get("SI_unit") != UNITS[role]:
            raise ValueError("Raw/SI channel meaning differs: " + role)
        if channel.get("sensor_serial") != scope[role+"_sensor_serial"]:
            raise ValueError("Sensor serial differs: " + role)
        for key in ("chain_id", "sign_convention", "uniform_bound_justification_id"):
            identity(channel.get(key), role+" "+key)
        evidence(channel.get("reference_evidence_ids"), role+" reference evidence")
        if channel.get("uncertainty_kind") != "deterministic_bound_declared":
            raise ValueError("Live limits require a declared deterministic bound: " + role)
        zero = number(channel.get("zero_raw_V"), role+" raw zero")
        if number(channel.get("scale_SI_per_V"), role+" signed scale") == 0:
            raise ValueError("Signed calibration scale cannot be zero")
        raw_lo, raw_hi = interval(channel.get("raw_valid_V"), role+" raw domain")
        if not -10 < raw_lo <= zero <= raw_hi < 10 or raw_lo == raw_hi:
            raise ValueError("Raw domain/zero must lie strictly inside ADC rails")
        nonnegative(channel.get("raw_error_bound_V"), role+" raw error")
        si_lo, si_hi = interval(channel.get("valid_SI"), role+" SI domain")
        if not si_lo < 0 < si_hi:
            raise ValueError("Both signed SI directions require a nonzero domain")
        nonnegative(channel.get("total_error_SI"), role+" uniform full-chain error")
        path = timing["per_channel"][role]
        number(path.get("sample_offset_s"), role+" scan offset")
        for key in ("sample_offset_error_s", "filter_lag_bound_s", "max_abs_slew_SI_per_s"):
            nonnegative(path.get(key), role+" "+key)
        for key in ("filter_bound_evidence_id", "slew_bound_evidence_id"):
            identity(path.get(key), role+" "+key)
    return True


class WriterReadout:
    """Thread-safe T7 observer and conditional current-observation evaluator.

    STOP events after a row arrives latch until a new run/readout is created.
    A display-only tare never changes the absolute limit check or raw zero.
    """
    def __init__(self, calibration, context, *, clock=time.monotonic,
                 wall_clock=utc_now, allow_synthetic=False, output_dir=None):
        self.calibration, self.context = copy.deepcopy(calibration), copy.deepcopy(context)
        self.clock, self.wall_clock = clock, wall_clock
        self.allow_synthetic = allow_synthetic
        self.lock = threading.RLock()
        self.start = self.latest = self.end = None
        self.stream_qualified = False
        self.latest_row_issues = []
        self.last_index = None
        self.last_nominal = {}
        self.latched = []
        self.history = []
        self.tare = None
        self.rows = 0
        self.derivative = None
        self.derivative_writer = None
        self.output_dir = Path(output_dir) if output_dir is not None else None
        self.qualification_error = None
        try:
            validate_calibration(self.calibration, self.context, now=self.wall_clock(),
                                 allow_synthetic=allow_synthetic)
        except (ValueError, KeyError, TypeError) as exc:
            self.qualification_error = str(exc)
        if self.output_dir is not None:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            target = self.output_dir/"writer_observations.csv"
            if target.exists() or (self.output_dir/"writer_readout.json").exists():
                raise ValueError("Readout output exists; choose a fresh directory")
            self.derivative = target.open("x", newline="", encoding="utf-8")
            self.derivative_writer = csv.writer(self.derivative)
            self.derivative_writer.writerow(["sample_index", "logger_time_s", "raw_force_V",
                "raw_displacement_V", "raw_excitation_V", "raw_temperature_V", "force_N", "displacement_m",
                "force_current_error_N", "displacement_current_error_m", "force_age_upper_s",
                "position_age_upper_s", "status", "reasons", "calibration_id", "pairing_id"])

    def _latch(self, reason):
        if reason not in self.latched:
            self.latched.append(reason)
            self.history.append({"host_monotonic_s":self.clock(), "reason":reason})

    def observe(self, event):
        """Consume start/block/end hydrophone.t7-observation/1 events."""
        with self.lock:
            if event.get("schema") != "hydrophone.t7-observation/1":
                self._latch("UNKNOWN OBSERVER SCHEMA")
                return
            kind = event.get("kind")
            if kind == "start":
                if self.start is not None:
                    self._latch("DUPLICATE STREAM START")
                self.start = copy.deepcopy(event)
                self._check_start()
            elif kind == "block":
                if self.start is None or self.end is not None:
                    self._latch("BLOCK OUTSIDE ACTIVE STREAM")
                if event.get("device_scan_backlog") != 0 or event.get("ljm_scan_backlog") != 0:
                    self._latch("BUFFER BACKLOG: SAMPLE AGE NOT QUALIFIED")
                rows = event.get("rows")
                if not isinstance(rows, list) or not rows:
                    self._latch("EMPTY OR INVALID FRAME")
                    return
                for row in rows:
                    self._accept_row(row)
                if self.derivative is not None:
                    self.derivative.flush()
            elif kind == "end":
                self.end = copy.deepcopy(event)
                self._latch("ACQUISITION ENDED; STOP MANUAL WRITING")
            else:
                self._latch("UNKNOWN OBSERVER EVENT")

    __call__ = observe

    def _check_start(self):
        self.stream_qualified = False
        try:
            if self.qualification_error:
                return
            scope = self.calibration["scope"]
            if str(self.start.get("identifier")) != scope["adc_serial"]:
                raise ValueError("ADC SERIAL MISMATCH")
            info = self.start.get("device_info")
            if not isinstance(info, (list, tuple)) or len(info) < 3 or info[0] != 7 or str(info[2]) != scope["adc_serial"]:
                raise ValueError("ACTUAL DEVICE IDENTITY MISMATCH")
            lo, hi = interval(scope["sample_rate_Hz_interval"], "sample rate")
            if not rational(scope["sample_rate_Hz_interval"][0]) <= rational(self.start.get("actual_scan_rate_Hz")) <= rational(scope["sample_rate_Hz_interval"][1]):
                raise ValueError("ACTUAL SCAN RATE OUTSIDE CALIBRATION")
            cfg = self.start["configuration"]
            if cfg.get("wiring_profile", "E01") != scope.get("wiring_profile", "E01"):
                raise ValueError("ACTUAL WIRING PROFILE MISMATCH")
            for field in ("scan_list", "scans_per_read", "stream_resolution_index", "range_V"):
                target = "resolution_index" if field == "stream_resolution_index" else field
                if cfg.get(field) != scope[target]:
                    raise ValueError("ACTUAL STREAM SETTINGS MISMATCH: "+field)
            before = number(self.start.get("stream_start_host_before_s"), "start bracket before")
            after = number(self.start.get("stream_start_host_after_s"), "start bracket after")
            if before > after or after > self.clock():
                raise ValueError("STREAM START BRACKET INVALID")
            self.stream_qualified = True
        except (KeyError, TypeError, ValueError) as exc:
            self._latch(str(exc))

    def _accept_row(self, row):
        if not isinstance(row, dict):
            self._latch("INVALID NATIVE ROW")
            return
        self.latest = copy.deepcopy(row)
        self.latest_row_issues = []
        self.rows += 1
        try:
            index = row["sample_index"]
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                raise ValueError("INVALID SAMPLE INDEX")
            if self.last_index is None and index != 0 or self.last_index is not None and index != self.last_index+1:
                raise ValueError("NONCONTIGUOUS NATIVE SAMPLES")
            self.last_index = index
            rate = number(self.start["actual_scan_rate_Hz"], "actual rate")
            if not math.isclose(number(row["time_s"], "native sample time"), index/rate, rel_tol=1e-12, abs_tol=1e-10):
                raise ValueError("NATIVE SCAN INDEX/TIME MISMATCH")
            if row.get("row_has_gap") not in (False, 0, "0") or row.get("gap_channels") or row.get("invalid_channels"):
                raise ValueError("GAP OR INVALID ADC SAMPLE")
            columns = [*RAW_COLUMNS.values(), "raw_marker_V", "raw_excitation_V"]
            if self.calibration.get("scope", {}).get("wiring_profile") == "E02":
                columns.append("raw_temperature_V")
            for column in columns:
                value = number(row.get(column), column)
                if value == -9999 or abs(value) >= 10:
                    raise ValueError("GAP OR CLIPPED ADC VOLTAGE")
        except (KeyError, TypeError, ValueError) as exc:
            self.latest_row_issues.append(str(exc))
            self._latch(str(exc))
        result = self._evaluate(self.clock())
        # An observed between-sample jump can falsify a declared slew bound.
        # Passing this check cannot prove an unobserved continuous-time bound.
        for role, value in result["channels"].items():
            if value.get("nominal_SI") is None:
                continue
            previous = self.last_nominal.get(role)
            if previous and self.latest.get("time_s") is not None:
                dt = number(self.latest["time_s"], "native time")-previous[0]
                path = self.calibration["timing"]["per_channel"][role]
                allowance = rational(path["max_abs_slew_SI_per_s"])*rational(dt) + 2*rational(self.calibration["channels"][role]["total_error_SI"])
                if dt <= 0 or abs(rational(value["nominal_SI"])-rational(previous[1])) > allowance:
                    self._latch(role.upper()+" OBSERVED CHANGE EXCEEDS QUALIFIED SLEW")
            self.last_nominal[role] = (number(self.latest["time_s"], "native time"), value["nominal_SI"])
        result = self._evaluate(self.clock())
        self._record_row(result)

    def _evaluate(self, now):
        reasons = list(self.latched)
        calibration_in_scope = self.qualification_error is None
        if self.qualification_error:
            reasons.append("CALIBRATION UNQUALIFIED: "+self.qualification_error)
        else:
            try:
                validate_calibration(self.calibration, self.context, now=self.wall_clock(),
                                     allow_synthetic=self.allow_synthetic)
            except (ValueError, KeyError, TypeError) as exc:
                calibration_in_scope = False
                reasons.append("CALIBRATION/ENVIRONMENT EXPIRED: "+str(exc))
        result = {"schema":"hydrophone.writer-observation/1", "status":"STOP", "reasons":reasons,
                  "synthetic":self.calibration.get("evidence_type") == "synthetic_demo",
                  "physical_observation_qualified":False, "manual_write_permission_issued":False,
                  "channels":{}, "sample_index":None,
                  "logger_time_s":None, "host_monotonic_s":now,
                  "calibration_id":self.calibration.get("calibration_id"),
                  "pairing_id":self.calibration.get("timing", {}).get("pairing_id"),
                  "tare":copy.deepcopy(self.tare)}
        if self.start is None or self.latest is None:
            reasons.append("WAITING FOR NATIVE STREAM AND FIRST SAMPLE")
            return result
        result["sample_index"] = self.latest.get("sample_index")
        result["logger_time_s"] = self.latest.get("time_s")
        if self.qualification_error:
            return result
        try:
            excitation = number(self.latest.get("raw_excitation_V"), "bridge excitation")
            lo, hi = self.calibration["scope"]["valid_excitation_V"]
            excitation_in_scope = rational(lo) <= rational(excitation) <= rational(hi)
            if not excitation_in_scope:
                reasons.append("EXCITATION OUTSIDE CALIBRATED DOMAIN")
            elapsed = number(self.latest.get("time_s"), "native time")
            for role in ROLES:
                ch = self.calibration["channels"][role]
                path = self.calibration["timing"]["per_channel"][role]
                raw = number(self.latest.get(RAW_COLUMNS[role]), role+" voltage")
                nominal_exact = (rational(raw)-rational(ch["zero_raw_V"]))*rational(ch["scale_SI_per_V"])
                nominal = float(nominal_exact)
                if not math.isfinite(nominal):
                    raise ValueError("NONFINITE SI CONVERSION")
                timing = self.calibration["timing"]
                elapsed_exact = Fraction(self.latest["sample_index"])/rational(self.start["actual_scan_rate_Hz"])
                earliest_exact = (rational(self.start["stream_start_host_before_s"])
                    + rational(timing["first_scan_offset_from_call_interval_s"][0])
                    + elapsed_exact*rational(timing["host_seconds_per_logger_nominal_second_interval"][0])
                    + rational(path["sample_offset_s"])-rational(path["sample_offset_error_s"]))
                latest_exact = (rational(self.start["stream_start_host_after_s"])
                    + rational(timing["first_scan_offset_from_call_interval_s"][1])
                    + elapsed_exact*rational(timing["host_seconds_per_logger_nominal_second_interval"][1])
                    + rational(path["sample_offset_s"])+rational(path["sample_offset_error_s"]))
                earliest, latest = outward(earliest_exact,-1), outward(latest_exact,1)
                age_exact = rational(now)-earliest_exact
                if age_exact < 0:
                    reasons.append(role.upper()+" CLOCK MAP PLACES SAMPLE IN FUTURE")
                age_exact = max(Fraction(0), age_exact)
                age = outward(age_exact,1)
                if age_exact > rational(timing["maximum_observation_age_s"]):
                    reasons.append(role.upper()+" STALE OR OLD BUFFERED SAMPLE")
                error_exact = (rational(ch["total_error_SI"])
                    + rational(path["max_abs_slew_SI_per_s"])*(age_exact+rational(path["filter_lag_bound_s"])))
                rounding_error = abs(Fraction.from_float(nominal)-nominal_exact)
                uncertainty = outward(error_exact+rounding_error,1)
                if not math.isfinite(uncertainty):
                    raise ValueError("NONFINITE LIVE UNCERTAINTY")
                raw_lo, raw_hi = ch["raw_valid_V"]
                raw_ok = (rational(raw)-rational(ch["raw_error_bound_V"]) > rational(raw_lo)
                          and rational(raw)+rational(ch["raw_error_bound_V"]) < rational(raw_hi))
                if not raw_ok:
                    reasons.append(role.upper()+" RAW DOMAIN/HEADROOM UNQUALIFIED")
                lo, hi = ch["valid_SI"]
                domain_ok = rational(lo) <= nominal_exact-error_exact and nominal_exact+error_exact <= rational(hi)
                if not domain_ok:
                    reasons.append(role.upper()+" SI INTERVAL OUTSIDE CALIBRATION DOMAIN")
                if abs(nominal_exact)+error_exact >= rational(LIMITS[role]):
                    reasons.append(role.upper()+" UNCERTAINTY REACHES INITIAL LIMIT")
                result["channels"][role] = {"raw_V":raw, "nominal_SI":nominal,
                    "SI_unit":UNITS[role], "static_error_SI":outward(rational(ch["total_error_SI"]),1),
                    "current_error_SI":uncertainty,
                    "current_interval_SI":[outward(nominal_exact-error_exact,-1),outward(nominal_exact+error_exact,1)],
                    "limit_abs_SI":LIMITS[role], "sample_age_upper_s":age,
                    "sample_host_interval_s":[earliest,latest], "native_sample_offset_s":number(path["sample_offset_s"], "scan offset"),
                    "filter_lag_bound_s":outward(rational(path["filter_lag_bound_s"]),1),
                    "SI_domain_qualified":raw_ok and domain_ok and calibration_in_scope
                        and excitation_in_scope and self.stream_qualified and not self.latest_row_issues}
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            reasons.append("INVALID OR UNQUALIFIED FRAME: "+str(exc))
        if self.end is not None:
            reasons.append("ACQUISITION ENDED; STOP MANUAL WRITING")
        reasons[:] = list(dict.fromkeys(reasons))
        # Once a sample has arrived, STOP does not silently clear on later rows.
        for reason in reasons:
            self._latch(reason)
        if not reasons and len(result["channels"]) == 2:
            result["status"] = "WITHIN_DECLARED_LIMITS"
            result["physical_observation_qualified"] = not result["synthetic"]
        return result

    def snapshot(self, now=None):
        with self.lock:
            return copy.deepcopy(self._evaluate(self.clock() if now is None else number(now, "host time")))

    def set_display_tare(self, operator_note):
        """Save an informational relative reference; absolute safety limits stay fixed."""
        with self.lock:
            identity(operator_note, "explicit display-tare operator note")
            current = self._evaluate(self.clock())
            if current["status"] != "WITHIN_DECLARED_LIMITS":
                raise ValueError("Display tare requires a fresh qualified observation")
            self.tare = {"operator_note":operator_note, "host_monotonic_s":self.clock(),
                         "native_row":copy.deepcopy(self.latest),
                         "absolute_channels":copy.deepcopy(current["channels"]),
                         "calibration_id":current["calibration_id"],
                         "scope":"display-only; raw zero, calibrated SI and limit checks unchanged"}
            self.history.append({"display_tare":copy.deepcopy(self.tare)})

    def _record_row(self, result):
        if self.derivative_writer is None:
            return
        force, pos = [result["channels"].get(r, {}) for r in ROLES]
        def value(channel):
            return channel.get("nominal_SI", "") if channel.get("SI_domain_qualified") else ""
        self.derivative_writer.writerow([self.latest.get("sample_index"),self.latest.get("time_s"),
            self.latest.get("raw_force_V"),self.latest.get("raw_displacement_V"),self.latest.get("raw_excitation_V"),
            self.latest.get("raw_temperature_V", ""),
            value(force),value(pos),force.get("current_error_SI", ""),pos.get("current_error_SI", ""),
            force.get("sample_age_upper_s", ""),pos.get("sample_age_upper_s", ""),result["status"],
            " | ".join(result["reasons"]),result["calibration_id"],result["pairing_id"]])

    def close(self):
        with self.lock:
            if self.derivative is not None:
                self.derivative.flush()
                self.derivative.close()
                self.derivative = None
            result = {"schema":"hydrophone.writer-readout/1", "calibration":self.calibration,
                "calibration_canonical_sha256":digest(self.calibration), "session":self.context,
                "session_canonical_sha256":digest(self.context), "native_start":self.start,
                "native_end":self.end, "rows_seen":self.rows, "stop_and_tare_history":self.history,
                "final_observation":self.snapshot(), "motor_commands":0,
                "scope":"Conditional operator display; no hard realtime, force protection, interlock, deconvolution or automatic writing permission",
                "native_pairing":"Logger times and original voltages retained; sequential scan offsets/filter lag preserved, not shifted or interpolated",
                "uncertainty_rule":"uniform static error + qualified absolute slew bound*(upper sample age + filter lag bound)",
                "tare_policy":"Display-only reference; raw zero, absolute SI and limits remain unchanged"}
            if self.output_dir is not None:
                data = self.output_dir/"writer_observations.csv"
                result["derived_files"] = {data.name:{"sha256":hashlib.sha256(data.read_bytes()).hexdigest()}}
                (self.output_dir/"writer_readout.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
            return result


def render_terminal(state):
    label = "DEMO ONLY - NO PHYSICAL WRITING\n" if state["synthetic"] else ""
    label += "STOP - DO NOT ADVANCE WRITER" if state["status"] == "STOP" else "WITHIN DECLARED OBSERVATION LIMITS"
    lines = ["="*76, label, "="*76]
    for role, factor, unit in (("force",1,"N"),("position",1000,"mm")):
        channel = state["channels"].get(role)
        if channel is None:
            lines.append(role.upper()+": UNAVAILABLE / UNQUALIFIED")
        else:
            qualifier = "" if channel["SI_domain_qualified"] else "UNQUALIFIED NOMINAL "
            lines.append(f"{role.upper():8} {qualifier}{channel['nominal_SI']*factor:+.6f} +/- "
                         f"{channel['current_error_SI']*factor:.6f} {unit}    "
                         f"initial limit +/- {LIMITS[role]*factor:g} {unit}")
            lines.append(f"         sample age <= {channel['sample_age_upper_s']:.3f} s; "
                         f"filter lag bound {channel['filter_lag_bound_s']:.3f} s")
            if state.get("tare"):
                reference = state["tare"]["absolute_channels"][role]["nominal_SI"]
                lines.append(f"         display-only relative to tare: {(channel['nominal_SI']-reference)*factor:+.6f} {unit}; limits remain absolute")
    lines.extend(state["reasons"])
    lines.append("Delayed conditional observations; operator control only. No interlock.")
    return "\n".join(lines)


def _load_t7():
    target = Path(__file__).parents[1]/"electronics"/"t7_capture.py"
    spec = importlib.util.spec_from_file_location("hydrophone_t7_capture_for_readout", target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_demo(output_dir=None):
    """Finite offline trace: valid observation, display tare, then limit STOP."""
    folder = Path(__file__).parent
    record = json.loads((folder/"writer_calibration.synthetic.json").read_text())
    context = json.loads((folder/"writer_session.synthetic.json").read_text())
    context["temperature_observed_utc"] = utc_now().isoformat()
    t = [100.12]
    readout = WriterReadout(record, context, clock=lambda:t[0], allow_synthetic=True, output_dir=output_dir)
    readout.observe({"schema":"hydrophone.t7-observation/1", "kind":"start", "identifier":"SYNTHETIC_T7",
        "device_info":[7,1,"SYNTHETIC_T7",0,0,64], "actual_scan_rate_Hz":50,
        "configuration":{"scan_list":SCAN_LIST,"stream_resolution_index":7,"range_V":10,"scans_per_read":5},
        "stream_start_host_before_s":100., "stream_start_host_after_s":100.01})
    def row(index, force, position):
        return {"sample_index":index,"time_s":index/50,"raw_force_V":1.25+force/20,
                "raw_displacement_V":3+position/.001,"raw_marker_V":.05,"raw_excitation_V":2.5,
                "row_has_gap":False,"gap_channels":[],"invalid_channels":[]}
    scenes = []
    for i in range(20):
        t[0]=100.12+i/50
        # Slow normal evolution respects the synthetic slew bound.
        readout.observe({"schema":"hydrophone.t7-observation/1","kind":"block","host_monotonic_s":t[0],
            "device_scan_backlog":0,"ljm_scan_backlog":0,"rows":[row(i,i*.002,i*.00000005)]})
        if i==4:
            readout.set_display_tare("Synthetic display reference; absolute limits unchanged")
        if i==19:
            scenes.append(readout.snapshot())
    # A synthetic limit excursion must produce STOP, including uncertainty.
    t[0]=100.52
    readout.observe({"schema":"hydrophone.t7-observation/1","kind":"block","host_monotonic_s":t[0],
        "device_scan_backlog":0,"ljm_scan_backlog":0,"rows":[row(20,4.94,.000249)]})
    scenes.append(readout.snapshot())
    readout.observe({"schema":"hydrophone.t7-observation/1","kind":"end","receipt":{"status":"SYNTHETIC_DEMO_COMPLETED"}})
    readout.close()
    return scenes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--identifier")
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--context", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--profile", choices=("E01", "E02"), default="E01")
    args = parser.parse_args(argv)
    if args.demo and args.execute:
        parser.error("Choose offline demo or explicit hardware execution")
    if args.demo:
        for scene in run_demo(args.output_dir):
            print(render_terminal(scene)+"\n")
        return 0
    if not args.execute:
        print("STOP / OFFLINE. Use --demo for synthetic observations. Physical readout requires --execute, exact serial, measured calibration and installed session context.")
        return 0
    if not args.identifier or not args.calibration or not args.context or not args.output_dir:
        parser.error("--execute requires --identifier, --calibration, --context and --output-dir")
    try:
        record = json.loads(args.calibration.read_text())
        context = json.loads(args.context.read_text())
        validate_calibration(record, context)
        if str(args.identifier) != record["scope"]["adc_serial"]:
            raise ValueError("Selected T7 serial differs from installed calibration")
        if args.profile != record["scope"].get("wiring_profile", "E01"):
            raise ValueError("Selected wiring profile differs from installed calibration")
        # Capture validates limits before any SDK/device access.
        t7 = _load_t7()
        t7.configuration_plan(args.duration, record["scope"]["scans_per_read"], profile=args.profile)
        readout = WriterReadout(record, context, output_dir=args.output_dir/"readout")
        finished = threading.Event()
        def display_loop():
            while not finished.is_set():
                state = readout.snapshot()
                if sys.stdout.isatty():
                    print("\033[2J\033[H"+render_terminal(state), flush=True)
                else:
                    print(render_terminal(state), flush=True)
                finished.wait(.2)
        watchdog = threading.Thread(target=display_loop, name="writer-display-watchdog", daemon=True)
        watchdog.start()
        try:
            receipt = t7.capture(args.output_dir/"native", identifier=args.identifier, execute=True,
                duration_s=args.duration, scans_per_read=record["scope"]["scans_per_read"],
                observer=readout.observe, profile=args.profile)
        finally:
            finished.set()
            watchdog.join(timeout=1)
            report = readout.close()
        print(render_terminal(report["final_observation"]))
        stop_reasons = [item["reason"] for item in report["stop_and_tare_history"]
                        if "reason" in item and not item["reason"].startswith("ACQUISITION ENDED")]
        return 0 if (receipt["status"] == "CAPTURE_COMPLETED"
                     and not receipt.get("quality_requires_review") and not stop_reasons) else 2
    except (ValueError, KeyError, TypeError, OSError, ImportError) as exc:
        print("STOP / NOT STARTED: "+str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
