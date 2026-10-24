#!/usr/bin/env python3
"""Use the recovered Fusion engine with genuine Dyletsky score targets.

This is an OFFLINE SYNTHETIC DECISION TEST, not a hardware driver. The musical
targets come from instrument_score.json. Every reading interval, tuning error,
action effect, tolerance, and probe cost below is declared, synthetic data.

Python 3.10+, standard library only. Example:
  python fusion_bridge.py --score output/instrument_score.json
"""
from __future__ import annotations

import argparse
from fractions import Fraction as F
import hashlib
import importlib.util
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDORED = HERE / "recovered_fusion"


def json_safe(value):
    if isinstance(value, F):
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [json_safe(v) for v in value]
    return value


def recovered_engine():
    provenance = json.loads((VENDORED / "provenance.json").read_text())
    path = VENDORED / "fusion_engine.py"
    observed_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if observed_hash != provenance["engine_sha256"]:
        raise ValueError("Vendored Fusion engine differs from recovered source")
    spec = importlib.util.spec_from_file_location("recovered_fusion_engine", path)
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    replay = json_safe(engine.run())
    expected = json.loads((VENDORED / "results.json").read_text())
    if replay != expected:
        raise AssertionError("Recovered Fusion replay differs from archived results")
    return engine, provenance, replay


def tuning_model(target):
    """Six finite hypotheses; tuning error and sensor nuisance are distinct.

    Coarse pitch error is measured in units of four cents, with +/- 1/2
    normalized reading error (= +/- 2 cents). Closed endpoints are included.
    Fine pitch has +/- 1/2 cent error. The nuisance coordinate is a declared
    synthetic sensor configuration code, NOT a measured hydrophone gain.
    """
    target_hz = float(target["target_Hz"])
    if not math.isfinite(target_hz) or target_hz <= 0:
        raise ValueError("Every Dyletsky calibration target requires positive finite Hz")
    states = [(error, nuisance) for error in (-4, 0, 4) for nuisance in (0, 1)]
    corrections = {"LOWER_4_CENTS": F(-4), "RAISE_4_CENTS": F(4)}
    tolerance = F(4)
    good = [{name for name, correction in corrections.items()
             if abs(F(error) + correction) <= tolerance}
            for error, _ in states]
    probes = [
        {"name": "coarse_pitch", "cost": 1,
         "values": [F(error, 4) for error, _ in states]},
        {"name": "fine_pitch", "cost": 4,
         "values": [F(error) for error, _ in states]},
        {"name": "sensor_nuisance_code", "cost": 2,
         "values": [F(2*nuisance) for _, nuisance in states]},
    ]
    return states, corrections, good, probes, tolerance


def demonstrate_target(engine, target):
    states, corrections, good, probes, tolerance = tuning_model(target)
    actions = tuple(corrections)
    epsilon = F(1, 2)
    task_labels = [error for error, _ in states]
    plans = {purpose: engine.optimal_panel(good, actions, probes, epsilon,
                                           purpose=purpose, task_labels=task_labels)
             for purpose in ("action", "task", "state")}
    assert [plans[p]["cost"] for p in ("action", "task", "state")] == [1, 4, 6]
    panel = [i for i, probe in enumerate(probes)
             if probe["name"] in plans["action"]["panel"]]
    # Use the recovered independent interval-arrangement checker too; no
    # duplicate implementation of its hyperedge solver is introduced here.
    assert engine.sufficient_by_arrangement(panel, good, actions, probes, epsilon)
    decisions = []
    for reading in (F(-1, 2), F(0), F(1, 2)):
        compatible = [i for i, value in enumerate(probes[0]["values"])
                      if abs(reading - value) <= epsilon]
        common = sorted(engine.common_actions(compatible, good, actions))
        assert compatible and common
        chosen = common[0]
        after = [F(states[i][0]) + corrections[chosen] for i in compatible]
        assert max(map(abs, after)) <= tolerance
        decisions.append({
            "synthetic_coarse_normalized_reading": reading,
            "compatible_state_indices": compatible,
            "compatible_error_cents": sorted({states[i][0] for i in compatible}),
            "compatible_sensor_nuisance_codes": sorted({states[i][1] for i in compatible}),
            "common_successful_actions": common,
            "selected_offline_action": chosen,
            "assumed_correction_cents": corrections[chosen],
            "post_action_error_cents": sorted(set(after)),
            "full_state_identified": len(compatible) == 1,
            "tuning_task_identified": len({states[i][0] for i in compatible}) == 1,
            "physical_execution_enabled": False,
        })
    assert not decisions[0]["tuning_task_identified"]
    assert len(decisions[0]["compatible_state_indices"]) == 4
    # Endpoint enlargement destroys the guarantee: at epsilon=1, coarse
    # readings can join both opposing errors, whose successful sets are disjoint.
    assert not engine.sufficient_by_arrangement([0], good, actions, probes, F(1))
    return {
        "dyletsky_target": target,
        "hypotheses": [{"state_index": i, "tuning_error_cents": error,
                        "sensor_nuisance_code": nuisance,
                        "nominal_frequency_Hz_approximate": float(target["target_Hz"])*2**(error/1200)}
                       for i, (error, nuisance) in enumerate(states)],
        "successful_actions_by_state": [sorted(g) for g in good],
        "probes": probes,
        "normalized_closed_noise_radius": epsilon,
        "target_tolerance_cents": tolerance,
        "optimal_panels_for_declared_costs": plans,
        "synthetic_decisions": decisions,
        "coarse_panel_fails_when_closed_noise_radius_equals_1": True,
        "certificate_scope": "Exact rational finite normalized-cents table only; frequency conversion is display arithmetic",
    }


def run(score_path):
    score_bytes = score_path.read_bytes()
    score = json.loads(score_bytes)
    if score.get("schema") != "fusion.score/1":
        raise ValueError("Expected score schema fusion.score/1")
    if score.get("data_origin") != "software_generated_score":
        raise ValueError("This bridge accepts software-generated targets, not physical measurements")
    targets = score.get("calibration_targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("Score must export nonempty calibration_targets")
    engine, provenance, replay = recovered_engine()
    target_results = [demonstrate_target(engine, target) for target in targets]
    return json_safe({
        "schema": "fusion.dyletsky-decision-bridge/1",
        "evidence_status": "REAL_SOFTWARE_TARGETS_WITH_SYNTHETIC_BOUNDED_READINGS",
        "physical_execution_enabled": False,
        "score_source_name": score_path.name,
        "score_sha256": hashlib.sha256(score_bytes).hexdigest(),
        "recovered_engine_provenance": provenance,
        "recovered_engine_independent_replay": {
            "archive_results_equal": True,
            "panel_cross_checks": replay["independent_panel_cross_checks"],
            "minimal_obstructions": replay["minimal_obstruction_count"],
            "archived_music_gram_determinant": replay["music"]["gram_determinant"],
        },
        "target_count": len(targets),
        "target_results": target_results,
        "semantic_assumptions": [
            "Finite hypothetical tuning errors are -4, 0, +4 cents relative to each actual Dyletsky target; they are not measured frequencies.",
            "An action adds its declared correction exactly and preserves all other state; real string tuning, drift and coupling require a calibrated actuation model.",
            "The acceptable performance goal is final absolute tuning error at most 4 cents; this declared tolerance is not an established perceptual or instrument specification.",
            "Probe costs 1, 4, 2 are illustrative units, not measured duration, money, or computation cost.",
            "Closed bounded errors and independent rectangular reading possibilities are exactly the recovered engine's finite model semantics.",
            "Probes are fixed-panel non-state-changing observations or require a reset; an invasive probe needs a new protocol contract.",
            "Sensor nuisance code is synthetic. No hydrophone calibration or inferred clay material parameter is supplied.",
            "Targets and nominal displayed frequencies use software floating-point arithmetic; the exact decision certificate concerns the declared rational normalized-cents table.",
            "A common successful correction is retained even with four compatible hypotheses and unresolved tuning task. Full state identification is unnecessary for this declared action.",
            "No theorem extension, physical performance advantage, real-world noise guarantee, or hardware controller is asserted.",
        ],
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score", type=Path, default=HERE/"output"/"instrument_score.json")
    parser.add_argument("--out", type=Path, default=HERE/"output"/"fusion_bridge_results.json")
    args = parser.parse_args()
    result = run(args.score.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({"status": result["evidence_status"], "targets": result["target_count"],
                      "archive_replay_checks": result["recovered_engine_independent_replay"]["panel_cross_checks"],
                      "declared_action_task_state_costs": [1,4,6],
                      "compatible_states_for_first_boundary_decision": 4,
                      "physical_execution_enabled": False}))


if __name__ == "__main__":
    main()
