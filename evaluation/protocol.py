"""Versioned registration, deterministic randomization and single-action rows."""
from __future__ import annotations

from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import random


def canonical(value):
    def encode(x):
        if isinstance(x, F):
            return str(x)
        raise TypeError("Unsupported canonical experiment value")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False,
                      default=encode)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def implementation_hashes():
    root = Path(__file__).resolve().parents[1]
    paths = ["evaluation/" + n for n in ("protocol.py", "policies.py", "evaluate.py", "statistics.py", "render.py")]
    paths += ["computing/memory.py", "computing/acquisition.py", "computing/cli.py", "instrument/drive.py"]
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in paths}


def exact(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, F)):
        raise ValueError("Use exact integer or decimal/rational-string data")
    try:
        return F(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("Invalid finite exact number") from exc


def read_json(path):
    from computing.cli import _unique, _reject_constant
    # Frozen numerical coefficients must round-trip as JSON numbers.
    # Exact physical quantities use rational/decimal strings separately.
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique,
                      parse_constant=_reject_constant)


def validate_contract(contract):
    if not isinstance(contract, dict) or contract.get("schema") != "fusion.experiment/1":
        raise ValueError("Expected fusion.experiment/1")
    if contract["action_ids"] != ["hold", "raise5"] or contract["task"]["actions"] != {"hold": "0", "raise5": "5"}:
        raise ValueError("This evaluator implements the registered hold/raise5 task only")
    if exact(contract["task"]["target_Hz"]) <= 0:
        raise ValueError("Positive fixed target required")
    if contract["confirmation"]["planned_blocks"] < 1:
        raise ValueError("A fixed positive confirmation horizon is required")


def bind_contract(core, binding, origin):
    validate_contract(core)
    if origin not in {"synthetic", "physical_measurement"}:
        raise ValueError("Explicit origin required")
    if not isinstance(binding, dict):
        raise ValueError("Hardware binding must be an object")
    missing = [k for k in core["hardware_binding_required"] if binding.get(k) in (None, "", "PENDING")]
    if missing:
        raise ValueError("Contract not bound: " + ",".join(missing))
    limits = core["mechanical_qualification"]
    if not 0 < exact(binding["write_stroke_m"]) <= exact(limits["maximum_write_stroke_m"]):
        raise ValueError("Write stroke exceeds the independently qualified M03 ceiling")
    if not 0 < exact(binding["force_limit_N"]) <= exact(limits["maximum_write_force_N"]) or exact(binding["clock_error_bound_s"]) < 0:
        raise ValueError("Invalid qualified force/clock declarations")
    for key in ("drive_waveform_sha256", "reduced_drive_waveform_sha256"):
        waveform = binding[key]
        if not isinstance(waveform, str) or len(waveform) != 64 or any(c not in "0123456789abcdef" for c in waveform):
            raise ValueError("Each full/reduced drive command needs a SHA256")
    if binding["drive_waveform_sha256"] == binding["reduced_drive_waveform_sha256"]:
        raise ValueError("Full probe and reduced no-probe commands must differ")
    return {"schema": "fusion.bound-experiment/1", "core": core, "binding": binding,
            "data_origin": origin, "qualification": "DECLARATIONS_NOT_LAB_AUTHENTICATION"}


def schedule(core, blocks):
    rng = random.Random(core["confirmation"]["randomization_seed"])
    tickets = []
    for block in blocks:
        cells = [(c, h, p) for c in core["conditions"] for h in core["histories"] for p in core["policy_arms"]]
        rng.shuffle(cells)
        for order, (condition, history, policy) in enumerate(cells):
            tickets.append({"ticket_id": f"{block}:{order:02d}", "block_id": block, "order": order,
                            "condition": condition, "write_protocol": history, "policy_arm": policy})
    return tickets


def freeze(bound, development, blocks, timestamp=None):
    from .policies import fit_policies
    core = bound["core"]
    if len(blocks) != core["confirmation"]["planned_blocks"] or len(set(blocks)) != len(blocks):
        raise ValueError("Block schedule must match the predeclared fixed horizon")
    if any(r.get("cohort") != "development" for r in development):
        raise ValueError("Only development rows may fit frozen policies")
    if any(r.get("data_origin") != bound["data_origin"] for r in development):
        raise ValueError("Development origin differs from bound contract")
    fitted = fit_policies(development, core)
    registration = {"schema": "fusion.registration/1", "bound_contract": bound,
                    "bound_contract_sha256": digest(bound), "policies": fitted,
                    "policies_sha256": digest(fitted), "development_sha256": digest(development),
                    "development_cartridges": sorted({r["cartridge_id"] for r in development}),
                    "development_days": sorted({r["day_id"] for r in development}),
                    "implementation_sha256": implementation_hashes(),
                    "schedule": schedule(core, blocks),
                    "registered_utc": timestamp or datetime.now(timezone.utc).isoformat()}
    registration["schedule_sha256"] = digest(registration["schedule"])
    registration["registration_sha256"] = digest(registration)
    return registration


def validate_registration(registration):
    if not isinstance(registration, dict) or registration.get("schema") != "fusion.registration/1":
        raise ValueError("Expected a frozen fusion.registration/1")
    unsigned = {k: v for k, v in registration.items() if k != "registration_sha256"}
    if digest(unsigned) != registration.get("registration_sha256"):
        raise ValueError("Registration digest mismatch")
    if registration.get("implementation_sha256") != implementation_hashes():
        raise ValueError("Evaluator or probe implementation changed; replay the registered source revision")
    for key, field in (("bound_contract", "bound_contract_sha256"), ("policies", "policies_sha256"), ("schedule", "schedule_sha256")):
        if digest(registration[key]) != registration[field]:
            raise ValueError("Frozen " + key + " changed")
    bound = registration["bound_contract"]
    if bind_contract(bound["core"], bound["binding"], bound["data_origin"]) != bound:
        raise ValueError("Invalid bound contract")
    return bound["core"]


def pitch_loss_interval(row, core):
    """Deterministic error bounds stay separate from sampling uncertainty."""
    if row.get("outcome_status") != "completed":
        return F(1), F(1)
    center, error = exact(row["outcome_cents"]), exact(row["outcome_error_cents"])
    if error < 0 or error > exact(core["task"]["maximum_qualified_pitch_error_bound_cents"]):
        raise ValueError("Pitch uncertainty exceeds the qualified task bound")
    low, high = center - error, center + error
    threshold = exact(core["task"]["success_abs_cents"])
    if low >= -threshold and high <= threshold:
        return F(0), F(0)
    if high < -threshold or low > threshold:
        return F(1), F(1)
    return F(0), F(1)


def total_cost(row, core):
    costs = row["cost_s"]
    if set(costs) != set(core["cost_components_s"]):
        raise ValueError("All predeclared total-cost components are required")
    values = [exact(costs[k]) for k in core["cost_components_s"]]
    if any(v < 0 for v in values):
        raise ValueError("Negative recorded cost")
    return sum(values)
