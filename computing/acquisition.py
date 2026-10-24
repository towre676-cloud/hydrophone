"""Inspect PCM WAV + slow CSV acquisition files; no laboratory authentication.

Audits actual bytes and timestamps. Calibration validity, synchronization
accuracy, physical origin, model applicability, and actuator readiness are
separate obligations. Raw hydrophone volts are not converted to pascals.
"""
from __future__ import annotations

import csv
from fractions import Fraction as F
import hashlib
from pathlib import Path
import wave


def _sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _number(value, label):
    if isinstance(value, bool):
        raise ValueError(label + " must be a finite exact number")
    try:
        return F(str(value))
    except (ValueError, ZeroDivisionError, TypeError) as exc:
        raise ValueError(label + " must be a finite exact number") from exc


def _file(root, record):
    if not isinstance(record, dict) or not record.get("path"):
        raise ValueError("A raw-file record needs a path")
    path = (root / record["path"]).resolve()
    actual = _sha(path)
    expected = record.get("sha256")
    if expected is None or actual != expected:
        raise ValueError("Raw-file digest missing or mismatched: " + record["path"])
    return path, actual


def _wav(path):
    try:
        with wave.open(str(path), "rb") as stream:
            channels, width, rate, frames = (stream.getnchannels(), stream.getsampwidth(),
                                             stream.getframerate(), stream.getnframes())
            if width not in (2, 3, 4) or frames <= 0 or rate <= 0:
                raise ValueError("Only nonempty16/24/32-bit integer PCM recordings are supported")
            clip_counts = [0] * channels
            limit, byte_count = 2 ** (8 * width - 1), 0
            while data := stream.readframes(8192):
                byte_count += len(data)
                if len(data) % (channels * width):
                    raise ValueError("Incomplete WAV frame")
                for i in range(0, len(data), width):
                    value = int.from_bytes(data[i:i + width], "little", signed=True)
                    if value in (-limit, limit - 1):
                        clip_counts[(i // width) % channels] += 1
            if byte_count != frames * channels * width:
                raise ValueError("Incomplete WAV payload")
    except (wave.Error, EOFError) as exc:
        raise ValueError("Invalid or unsupported PCM WAV: " + str(exc)) from exc
    return {"channels": channels, "sample_rate_Hz": rate, "frames": frames,
            "sample_width_bytes": width, "duration_s": str(F(frames, rate)),
            "full_scale_sample_counts": clip_counts}


def audit_run(manifest_path):
    from .cli import load_json
    path = Path(manifest_path).resolve()
    run = load_json(path)
    if not isinstance(run, dict):
        raise ValueError("The run manifest must be a JSON object")
    if run.get("schema") != "fusion.run/1":
        raise ValueError("Expected fusion.run/1")
    if run.get("data_origin") not in {"synthetic", "physical_measurement"}:
        raise ValueError("Origin must be explicitly declared")
    for key in ("run_id", "specimen_id", "history_protocol", "calibration_id", "validity_domain"):
        if not run.get(key):
            raise ValueError("Missing declared run metadata: " + key)
    raw = run["raw_files"]
    audio_path, audio_sha = _file(path.parent, raw["multichannel_audio"])
    slow_path, slow_sha = _file(path.parent, raw["slow_force_displacement"])
    drive_path, drive_sha = _file(path.parent, raw["drive_command"])
    audio, drive = _wav(audio_path), _wav(drive_path)
    if audio["sample_rate_Hz"] != run["audio"]["sample_rate_Hz"]:
        raise ValueError("Declared audio sample rate disagrees with WAV")
    mapping = run["audio"]["channel_map"]
    if (not isinstance(mapping, list) or len(mapping) != audio["channels"]
            or any(not isinstance(x, str) or not x for x in mapping)
            or len(set(mapping)) != len(mapping)):
        raise ValueError("Channel map must label every channel exactly once")
    gains = run["audio"]["gain_per_channel"]
    if (not isinstance(gains, list) or len(gains) != audio["channels"]
            or any(_number(g, "gain") <= 0 for g in gains)):
        raise ValueError("Each audio channel needs a positive declared gain")
    slow = []
    with slow_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("Slow CSV has missing or duplicate columns")
        required = {"logger_time_s", "force_N", "displacement_m"}
        if not required <= set(reader.fieldnames):
            raise ValueError("Slow CSV requires time,force_N,displacement_m")
        for row in reader:
            slow.append({key: _number(row[key], key) for key in required})
    if len(slow) < 2 or any(a["logger_time_s"] >= b["logger_time_s"] for a, b in zip(slow, slow[1:])):
        raise ValueError("Slow sample times must be strictly increasing with at least two rows")
    sync = run["sync"]
    offset = _number(sync["offset_s"], "clock offset")
    drift = _number(sync["drift_rate"], "clock drift")
    residual = _number(sync["sync_residual_s"], "clock residual")
    if residual < 0 or 1 + drift <= 0 or not sync.get("method"):
        raise ValueError("Invalid declared clock map")
    start = offset + (1 + drift) * slow[0]["logger_time_s"]
    end = offset + (1 + drift) * slow[-1]["logger_time_s"]
    duration = F(audio["duration_s"])
    overlap = max(F(0), min(duration, end - residual) - max(F(0), start + residual))
    if overlap <= 0:
        raise ValueError("No conservative common time interval under declared clock map")
    missing = run["audio"].get("missing_samples")
    if isinstance(missing, bool) or not isinstance(missing, int) or missing < 0:
        raise ValueError("Missing-sample count must be declared as a nonnegative integer")
    quality = "RECORDED_DATA_CHECKS_PASSED"
    drive_alignment = {"status": "UNVERIFIED_NO_DRIVE_CLOCK_MAP"}
    drive_clock = sync.get("drive_to_audio")
    if drive_clock is not None:
        drive_offset = _number(drive_clock["offset_s"], "drive offset")
        drive_drift = _number(drive_clock["drift_rate"], "drive drift")
        drive_error = _number(drive_clock["sync_residual_s"], "drive clock residual")
        if drive_error < 0 or 1 + drive_drift <= 0 or not drive_clock.get("method"):
            raise ValueError("Invalid drive-to-audio clock map")
        drive_start = drive_offset + drive_error
        drive_end = drive_offset + (1 + drive_drift) * F(drive["duration_s"]) - drive_error
        drive_overlap = max(F(0), min(duration, drive_end) - max(F(0), drive_start))
        if drive_overlap <= 0:
            raise ValueError("No declared drive/audio time overlap")
        drive_alignment = {"status": "DECLARED_CLOCK_OVERLAP_ONLY", "overlap_s": str(drive_overlap)}
    if (any(audio["full_scale_sample_counts"]) or any(drive["full_scale_sample_counts"])
            or missing or drive_clock is None):
        quality = "RECORDING_QUALITY_REQUIRES_REVIEW"
    return {"status": quality, "run_id": run["run_id"], "declared_origin": run["data_origin"],
            "audio": audio, "drive_command": drive, "slow_rows": len(slow),
            "slow_force_range_N": [str(min(r["force_N"] for r in slow)), str(max(r["force_N"] for r in slow))],
            "declared_clock_common_interval_length_s": str(overlap),
            "drive_temporal_alignment": drive_alignment,
            "sha256": {"multichannel_audio": audio_sha, "slow_force_displacement": slow_sha,
                       "drive_command": drive_sha},
            "qualification": "BYTE_AND_METADATA_CHECKS_ONLY_NOT_PHYSICAL_AUTHENTICATION",
            "physical_readiness": False, "hardware_commands_issued": 0}
