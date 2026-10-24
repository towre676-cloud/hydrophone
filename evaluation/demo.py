"""Positive, no-task-coupling, and unobservable synthetic evaluations.

The positive fixture STIPULATES a retained-state-to-future-pitch coupling.
It is not a prediction derived from the linear SLS model. All episodes
are declared synthetic and supply only the actually selected action.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

from .protocol import bind_contract, freeze, digest
from .policies import choose_action
from .evaluate import evaluate


def synthetic_binding():
    return {"calibration_id": "SYNTHETIC_CALIBRATION", "pitch_bound_validation_id": "SYNTHETIC_PITCH_BOUND",
            "synchronization_validation_id": "SYNTHETIC_CLOCK", "write_stroke_m": "0.0002",
            "force_limit_N": "1", "drive_transfer_validation_id": "SYNTHETIC_DRIVE",
            "raw_feature_extractor_revision": "SYNTHETIC_EXTRACTOR", "rod_reference_matching_id": "SYNTHETIC_REFERENCE",
            "action_qualification_id": "SYNTHETIC_ACTION", "clock_error_bound_s": "0.001",
            "drive_waveform_sha256": "0" * 64, "reduced_drive_waveform_sha256": "1" * 64,
            "dynamic_read_validation_id": "SYNTHETIC_DYNAMIC_READ",
            "pitch_probe_qualification_id": "SYNTHETIC_PITCH_PROBE"}


def features(history, condition, latent):
    return {"pre_pitch_cents": "0", "temperature_C": "20", "displacement_m": "0.001",
            "condition_code": str({"connected_clay": 0, "rod_disconnected_clay": 1, "reference_cartridge": 2}[condition]),
            "write_code": str(int(history == "H1")), "slow_force_N": "0.42" if latent else "0.18",
            "relaxation_N": "0.03" if latent else "0.01", "bridge_feature": "2" if latent else "1",
            "water_feature": "0" if condition == "rod_disconnected_clay" else ("2" if latent else "1")}


def future_error(mode, condition, latent, action):
    if condition == "reference_cartridge" or mode == "no_task_coupling":
        drift = 0
    else:
        drift = -5 if latent else 0
    return str(drift + (5 if action == "raise5" else 0))


def make_development(core, mode):
    rows = []
    for block in range(8):
        for condition in core["conditions"]:
            for history in core["histories"]:
                for latent in (0, 1):
                    for action in core["action_ids"]:
                        f = features(history, condition, latent)
                        if mode == "unobservable":
                            f["slow_force_N"], f["relaxation_N"], f["bridge_feature"], f["water_feature"] = "0.3", "0.02", "1.5", "1.5"
                        rows.append({"cohort": "development", "data_origin": "synthetic", "cartridge_id": f"dev-cartridge-{block}",
                                     "day_id": f"dev-day-{block}", "action": action, "features": f,
                                     "outcome_cents": future_error(mode, condition, latent, action), "outcome_error_cents": "0.25"})
    return rows


def make_confirmation(registration, mode):
    core = registration["bound_contract"]["core"]
    rows = []
    for ticket in registration["schedule"]:
        block = int(ticket["block_id"].split("-")[-1])
        latent = block % 2 if mode == "observable_nuisance" else (block + int(ticket["write_protocol"] == "H1")) % 2
        f = features(ticket["write_protocol"], ticket["condition"], latent)
        if mode == "unobservable":
            f["slow_force_N"], f["relaxation_N"], f["bridge_feature"], f["water_feature"] = "0.3", "0.02", "1.5", "1.5"
        if ticket["policy_arm"] == "fusion_reduced":
            del f["bridge_feature"], f["water_feature"]
        action = choose_action(registration["policies"], ticket["policy_arm"], {"features": f})
        if action == "ABSTAIN":
            action = "hold"
        token = ticket["ticket_id"]
        # Waiting replaces an omitted probe so the scored epoch stays fixed.
        # That preserves causal timing and deliberately prevents a fictitious
        # total-wall-clock saving in this first controlled experiment.
        reduced = ticket["policy_arm"] == "fusion_reduced"
        date = (datetime(2026, 10, 25, 12, tzinfo=timezone.utc) + timedelta(days=block, seconds=60 * ticket["order"]))
        row = {**ticket, "performed_order": ticket["order"], "cohort": "confirmation",
               "registration_sha256": registration["registration_sha256"], "data_origin": "synthetic",
               "preparation_id": "fresh-" + token, "run_id": "run-" + token,
               "day_id": date.date().isoformat(),
               "cartridge_id": (f"reference-cartridge-{block}" if ticket["condition"] == "reference_cartridge"
                                else f"confirmation-cartridge-{block}"),
               "acquired_utc": date.isoformat(), "target_Hz": core["task"]["target_Hz"],
               "calibration_id": "SYNTHETIC_CALIBRATION", "pitch_bound_validation_id": "SYNTHETIC_PITCH_BOUND",
               "raw_feature_extractor_revision": "SYNTHETIC_EXTRACTOR", "synchronization_validation_id": "SYNTHETIC_CLOCK",
               "action_qualification_id": "SYNTHETIC_ACTION",
               "raw_run_sha256": digest({"raw": token}), "pre_feature_sha256": digest({"pre": token}),
               "outcome_record_sha256": digest({"post": token}), "feature_end_s": "2" if reduced else "4", "decision_time_s": "4.5",
               "action_start_s": "5", "action_end_s": "17", "outcome_start_s": "18", "outcome_end_s": "20",
               "features": f, "action": action, "realized_action_cents": "5" if action == "raise5" else "0",
               "realized_action_error_cents": "0.1",
               "outcome_status": "completed", "outcome_cents": future_error(mode, ticket["condition"], latent, action),
               "outcome_error_cents": "0.25", "acquired_protocols": core["reduced_protocols"] if reduced else core["full_protocols"],
               "cost_s": {"preparation_s": "21", "reset_s": "2", "calibration_share_s": "1",
                          "acquisition_s": "2" if reduced else "4", "waiting_s": "3.5" if reduced else "1.5",
                          "compute_s": "0.5", "retune_s": "12", "verification_s": "2"}}
        rows.append(row)
    return rows


def run_demo(contract_path, output):
    from .protocol import read_json
    core = read_json(contract_path)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    summaries = {}
    for mode in ("coupled", "no_task_coupling", "unobservable", "observable_nuisance"):
        development = make_development(core, mode)
        bound = bind_contract(core, synthetic_binding(), "synthetic")
        registration = freeze(bound, development, [f"block-{i}" for i in range(core["confirmation"]["planned_blocks"])],
                              timestamp="2026-10-24T12:00:00+00:00")
        confirmation = make_confirmation(registration, mode)
        result = evaluate(registration, confirmation)
        (output / (mode + "_result.json")).write_text(json.dumps(result, indent=2) + "\n")
        summaries[mode] = {k: result[k] for k in ("status", "material_information", "cost_reduction", "physical_claim", "episodes")}
    if summaries["coupled"]["material_information"] != "USEFUL_WITHIN_DECLARED_CONFIRMATION_DESIGN":
        raise AssertionError("Stipulated useful-coupling fixture did not exercise positive verdict")
    if any(summaries[m]["material_information"] != "NOT_DEMONSTRATED" for m in ("no_task_coupling", "unobservable", "observable_nuisance")):
        raise AssertionError("A mandatory null fixture falsely demonstrated material utility")
    if any(v["physical_claim"] or v["cost_reduction"] != "NOT_DEMONSTRATED" for v in summaries.values()):
        raise AssertionError("Synthetic origin or fixed-wait cost boundary was lost")
    (output / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    return summaries
