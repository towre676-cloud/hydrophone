#!/usr/bin/env python3
"""Grouped, heterogeneous interval adapter for the proposed unified object.

Python 3.10+, standard library only. No hardware commands are issued.
Run `python object_adapter.py` to replay its exact synthetic example.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import json
from pathlib import Path

from .fusion_engine import obstruction_edges, subsets, common_actions


def exact(value):
    if isinstance(value, bool) or not isinstance(value, (int, str, F)):
        raise ValueError("Exact numbers must be integers or rational/decimal strings")
    return F(value)


def validate(contract):
    if not isinstance(contract, dict):
        raise ValueError("The model contract must be a JSON object")
    if contract.get("schema") != "unified-object/fusion-adapter/v1":
        raise ValueError("Unknown adapter schema")
    if contract.get("evidence_scope") not in {
            "EXACT_SYNTHETIC_MODEL_NOT_MEASURED", "DECLARED_MODEL_BOUNDS_NOT_PHYSICALLY_QUALIFIED"}:
        raise ValueError("This adapter version cannot authenticate measured/calibrated evidence")
    states, actions, protocols = (contract.get(k) for k in ("hypotheses", "actions", "protocols"))
    if not states or not actions or not protocols:
        raise ValueError("Hypotheses, actions, and acquisition protocols must be nonempty")
    ids = [s["id"] for s in states]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate hypothesis identifier")
    action_ids = [a["id"] for a in actions]
    if len(action_ids) != len(set(action_ids)):
        raise ValueError("Duplicate action identifier")
    for a in actions:
        if set(a["evaluation"]) != set(ids):
            raise ValueError("Incomplete action evaluation coverage")
        if any(v not in {"PASS_WITH_BOUND", "FAIL_WITH_BOUND", "UNRESOLVED"}
               for v in a["evaluation"].values()):
            raise ValueError("Invalid action evaluation")
    protocol_ids = [p["id"] for p in protocols]
    if len(protocol_ids) != len(set(protocol_ids)):
        raise ValueError("Duplicate protocol identifier")
    for p in protocols:
        if exact(p["cost"]) < 0 or p["cost_unit"] != contract["cost_unit"]:
            raise ValueError("Invalid or incompatible protocol cost")
        if not p["features"]:
            raise ValueError("An acquisition must provide declared features")
        if p.get("reset_semantics") not in {"COMMON_RESET", "COMPLETE_PROTOCOL_MODEL"}:
            raise ValueError("Probe disturbance/reset semantics are required")
        feature_ids = [f["id"] for f in p["features"]]
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("Duplicate feature in a protocol")
        for feature in p["features"]:
            for key in ("unit", "location_id", "transfer_path_id", "calibration_id", "clock_id"):
                if not feature.get(key):
                    raise ValueError("Missing feature provenance: " + key)
            if set(feature["intervals"]) != set(ids):
                raise ValueError("Missing hypothesis interval; unknown is not zero error")
            for interval in feature["intervals"].values():
                if len(interval) != 2 or exact(interval[0]) > exact(interval[1]):
                    raise ValueError("Invalid closed interval")
    if contract["uncertainty_geometry"] != "CONSERVATIVE_OUTER_PRODUCT":
        raise ValueError("This adapter implements rectangular outer bounds only")
    return ids, action_ids


def prepared(contract):
    ids, action_ids = validate(contract)
    good = [{a["id"] for a in contract["actions"]
             if a["evaluation"][state] == "PASS_WITH_BOUND"} for state in ids]
    edges = obstruction_edges(good, action_ids)
    return ids, action_ids, good, edges


def excludes(protocol, edge, ids):
    """One grouped acquisition separates an obstruction via ANY feature."""
    return any(max(exact(f["intervals"][ids[i]][0]) for i in edge)
               > min(exact(f["intervals"][ids[i]][1]) for i in edge)
               for f in protocol["features"])


def select_panel(contract):
    ids, actions, good, edges = prepared(contract)
    protocols = contract["protocols"]
    candidates = []
    for panel in subsets(range(len(protocols))):
        if all(any(excludes(protocols[p], e, ids) for p in panel) for e in edges):
            candidates.append((sum(exact(protocols[p]["cost"]) for p in panel), len(panel), panel))
    if not candidates:
        return {"status": "NO_CERTIFIED_PANEL_WITH_CURRENT_EVIDENCE", "physical_readiness": False,
                "metadata_validation": "IDENTIFIER_CONSISTENCY_ONLY",
                "minimal_obstructions": [[ids[i] for i in sorted(e)] for e in edges]}
    cost, _, panel = min(candidates)
    return {"status": "PANEL_FOR_DECLARED_MODEL", "cost": str(cost),
            "cost_unit": contract["cost_unit"],
            "protocols": [protocols[p]["id"] for p in panel],
            "physical_readiness": False, "metadata_validation": "IDENTIFIER_CONSISTENCY_ONLY",
            "evidence_scope": contract["evidence_scope"]}


def decide(contract, transcript):
    if not isinstance(transcript, dict):
        raise ValueError("The observation transcript must be a JSON object")
    ids, actions, good, _ = prepared(contract)
    by_id = {p["id"]: p for p in contract["protocols"]}
    compatible = set(range(len(ids)))
    for protocol_id, observed_features in transcript.items():
        if protocol_id not in by_id:
            raise ValueError("Unknown acquired protocol")
        features = by_id[protocol_id]["features"]
        if set(observed_features) != {f["id"] for f in features}:
            raise ValueError("Incomplete acquisition: declared grouped features are missing")
        for feature in features:
            observed = observed_features[feature["id"]]
            for key in ("unit", "calibration_id", "clock_id"):
                if observed.get(key) != feature[key]:
                    raise ValueError("Observation metadata mismatch: " + key)
            value = exact(observed["value"])
            compatible &= {i for i, state in enumerate(ids)
                           if exact(feature["intervals"][state][0]) <= value
                           <= exact(feature["intervals"][state][1])}
    if not compatible:
        return {"status": "OUT_OF_DECLARED_MODEL", "actions": [], "hypotheses": [],
                "physical_readiness": False, "hardware_command_issued": False}
    acceptable = sorted(common_actions(compatible, good, actions))
    return {"status": "COMMON_ACTION_FOR_DECLARED_MODEL" if acceptable else
            "NO_CERTIFIED_ACTION_WITH_CURRENT_EVIDENCE",
            "actions": acceptable, "hypotheses": [ids[i] for i in sorted(compatible)],
            "physical_readiness": False, "metadata_validation": "IDENTIFIER_CONSISTENCY_ONLY",
            "evidence_scope": contract["evidence_scope"], "hardware_command_issued": False}


def arrangement_sufficient(contract, panel):
    """Separate exact checker: enumerate closed-interval observation cells."""
    ids, actions, good, _ = prepared(contract)
    dimensions = []
    for p in panel:
        for feature in contract["protocols"][p]["features"]:
            intervals = [tuple(map(exact, feature["intervals"][state])) for state in ids]
            endpoints = sorted({v for interval in intervals for v in interval})
            samples = endpoints + [(a + b) / 2 for a, b in zip(endpoints, endpoints[1:])]
            dimensions.append({frozenset(i for i, (lo, hi) in enumerate(intervals) if lo <= x <= hi)
                               for x in samples})
    for possible in product(*dimensions):
        cell = set(range(len(ids)))
        for membership in possible:
            cell.intersection_update(membership)
        if cell and not common_actions(cell, good, actions):
            return False
    return True


def synthetic_fixture():
    def feature(name, unit, intervals, location="clay-plunger", path="plunger-to-pad"):
        return {"id": name, "unit": unit, "location_id": location, "transfer_path_id": path,
                "calibration_id": "SYNTHETIC_CALIBRATION", "clock_id": "SYNTHETIC_CLOCK",
                "intervals": intervals}
    # Exact force bounds follow from a passive standard-linear-solid model.
    parameters = {"k0": [F(99), F(101)], "k1": [F(396), F(404)],
                  "deformation_m": [F(99, 100000), F(101, 100000)],
                  "force_error_N": F(1, 100)}
    intervals = {}
    for state, memory in (("low_memory", F(1, 5000)), ("high_memory", F(1, 1250))):
        k0, k1, e, error = (parameters[k] for k in ("k0", "k1", "deformation_m", "force_error_N"))
        # e > memory throughout, so force is increasing in e,k0,k1.
        assert e[0] > memory
        intervals[state] = [str(k0[0] * e[0] + k1[0] * (e[0] - memory) - error),
                            str(k0[1] * e[1] + k1[1] * (e[1] - memory) + error)]
    # At omega=1000 rad/s and tau=10 s, dynamic storage/loss stiffness
    # does not depend on the initial memory. These bounds are illustrative,
    # not identified string or hydrophone transfers.
    same_storage = {s: ["494", "506"] for s in intervals}
    same_loss = {s: ["39/1000", "41/1000"] for s in intervals}
    ratio = F(10000)
    for k0 in parameters["k0"]:
        for k1 in parameters["k1"]:
            storage = k0 + k1 * ratio ** 2 / (1 + ratio ** 2)
            loss = k1 * ratio / (1 + ratio ** 2)
            assert F(494) <= storage <= F(506)
            assert F(39, 1000) <= loss <= F(41, 1000)
    return {"schema": "unified-object/fusion-adapter/v1",
            "evidence_scope": "EXACT_SYNTHETIC_MODEL_NOT_MEASURED",
            "model": {"name": "passive standard linear solid",
                      "coordinate": "direct clay deformation; ideal single-port replay only",
                      "mapping_to_actual_bridge_and_plunger": "UNIDENTIFIED",
                      "tau_s": "10", "dynamic_angular_frequency_rad_per_s": "1000",
                      "force_evaluation": "instantaneous snapshot at t=0 with stated internal memory",
                      "finite_acquisition_window_and_memory_drift": "NOT_MODELED",
                      "k0_interval_N_per_m": ["99", "101"],
                      "k1_interval_N_per_m": ["396", "404"],
                      "hardware_validity": "NOT_ESTABLISHED"},
            "cost_unit": "DECLARED_PROTOCOL_COST",
            "uncertainty_geometry": "CONSERVATIVE_OUTER_PRODUCT",
            "hypotheses": [{"id": s} for s in intervals],
            "actions": [
                {"id": "report_low_memory", "evaluation": {"low_memory": "PASS_WITH_BOUND", "high_memory": "FAIL_WITH_BOUND"}},
                {"id": "report_high_memory", "evaluation": {"low_memory": "FAIL_WITH_BOUND", "high_memory": "PASS_WITH_BOUND"}}],
            "protocols": [
                {"id": "dynamic_transfer_acquisition", "cost": "1", "cost_unit": "DECLARED_PROTOCOL_COST",
                 "reset_semantics": "COMMON_RESET", "features": [
                     feature("storage_stiffness", "N/m", same_storage),
                     feature("loss_stiffness", "N/m", same_loss)]},
                {"id": "slow_plunger_acquisition", "cost": "2", "cost_unit": "DECLARED_PROTOCOL_COST",
                 "reset_semantics": "COMMON_RESET", "features": [
                     feature("force", "N", intervals),
                     feature("displacement", "m", {s: ["99/100000", "101/100000"] for s in intervals})]}]}


def sample_transcript(contract, protocol_id, values):
    protocol = next(p for p in contract["protocols"] if p["id"] == protocol_id)
    return {protocol_id: {f["id"]: {"value": values[f["id"]], "unit": f["unit"],
                                   "calibration_id": f["calibration_id"], "clock_id": f["clock_id"]}
                          for f in protocol["features"]}}


def replay():
    fixture = synthetic_fixture()
    assert select_panel(fixture)["protocols"] == ["slow_plunger_acquisition"]
    dynamic = sample_transcript(fixture, "dynamic_transfer_acquisition",
                                {"storage_stiffness": "500", "loss_stiffness": "1/25"})
    slow_a = sample_transcript(fixture, "slow_plunger_acquisition", {"force": "21/50", "displacement": "1/1000"})
    slow_b = sample_transcript(fixture, "slow_plunger_acquisition", {"force": "9/50", "displacement": "1/1000"})
    assert decide(fixture, dynamic)["status"] == "NO_CERTIFIED_ACTION_WITH_CURRENT_EVIDENCE"
    assert decide(fixture, slow_a)["actions"] == ["report_low_memory"]
    assert decide(fixture, slow_b)["actions"] == ["report_high_memory"]
    assert decide(fixture, {})["status"] == "NO_CERTIFIED_ACTION_WITH_CURRENT_EVIDENCE"
    # One acquisition with two features is charged once.
    common = deepcopy(fixture)
    dynamic_features = common["protocols"][0]["features"]
    dynamic_features[0]["intervals"] = {"low_memory": ["0", "1"], "high_memory": ["2", "3"]}
    assert select_panel(common)["cost"] == "1"
    # Shared closed endpoint must still permit both histories.
    touching = deepcopy(fixture)
    touching["protocols"][1]["features"][0]["intervals"] = {
        "low_memory": ["0", "1"], "high_memory": ["1", "2"]}
    assert select_panel(touching)["status"] == "NO_CERTIFIED_PANEL_WITH_CURRENT_EVIDENCE"
    # A failed bound and an unresolved action remain different statuses.
    unresolved = deepcopy(fixture)
    unresolved["actions"][0]["evaluation"]["low_memory"] = "UNRESOLVED"
    assert decide(unresolved, slow_a)["status"] == "NO_CERTIFIED_ACTION_WITH_CURRENT_EVIDENCE"
    outlier = sample_transcript(fixture, "slow_plunger_acquisition", {"force": "10", "displacement": "1/1000"})
    assert decide(fixture, outlier)["status"] == "OUT_OF_DECLARED_MODEL"
    rejected = []
    malformed = []
    wrong_unit = deepcopy(slow_a)
    wrong_unit["slow_plunger_acquisition"]["displacement"]["unit"] = "mm"
    malformed.append(("unit_mismatch", lambda: decide(fixture, wrong_unit)))
    wrong_clock = deepcopy(slow_a)
    wrong_clock["slow_plunger_acquisition"]["force"]["clock_id"] = "UNSYNCHRONIZED"
    malformed.append(("clock_mismatch", lambda: decide(fixture, wrong_clock)))
    missing = deepcopy(fixture)
    del missing["protocols"][0]["features"][0]["intervals"]["low_memory"]
    malformed.append(("missing_bound", lambda: select_panel(missing)))
    partial = deepcopy(slow_a)
    del partial["slow_plunger_acquisition"]["displacement"]
    malformed.append(("missing_grouped_feature", lambda: decide(fixture, partial)))
    malformed.append(("nonfinite_or_float", lambda: exact(float("nan"))))
    spoofed = deepcopy(fixture)
    spoofed["evidence_scope"] = "MEASURED_AND_VALIDATED"
    malformed.append(("unsupported_physical_evidence_claim", lambda: select_panel(spoofed)))
    for name, function in malformed:
        try:
            function()
        except ValueError:
            rejected.append(name)
        else:
            raise AssertionError("Malformed data accepted: " + name)
    comparisons = 0
    for model in (fixture, common, touching, unresolved):
        ids, actions, good, edges = prepared(model)
        for panel in subsets(range(len(model["protocols"]))):
            cover = all(any(excludes(model["protocols"][p], e, ids) for p in panel) for e in edges)
            assert cover == arrangement_sufficient(model, panel)
            comparisons += 1
    force = fixture["protocols"][1]["features"][0]["intervals"]
    margin = exact(force["low_memory"][0]) - exact(force["high_memory"][1])
    assert margin == F(51, 250)
    return fixture, {"evidence": fixture["evidence_scope"], "selected": select_panel(fixture),
                     "dynamic_only": decide(fixture, dynamic), "slow_low": decide(fixture, slow_a),
                     "slow_high": decide(fixture, slow_b), "force_intervals_N": force,
                     "force_interval_separation_N": str(margin),
                     "independent_grouped_panel_checks": comparisons,
                     "rejected_invalid_contracts": rejected, "hardware_commands_issued": 0}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("object_adapter_results.json"))
    parser.add_argument("--fixture", type=Path, default=Path("plunger_fixture.json"))
    args = parser.parse_args()
    fixture, result = replay()
    args.fixture.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
