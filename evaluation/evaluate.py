"""Evaluate single-action confirmation episodes under one frozen contract.

No same-episode counterfactuals are constructed. Whole matched blocks,
not waveform samples, are the statistical units. Results remain conditional
on the declared measurement bounds, origin, preparation and independence.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import hashlib
from pathlib import Path
from .protocol import exact, digest, validate_registration, pitch_loss_interval, total_cost
from .policies import choose_action
from .statistics import lower_mean_test, binomial_worsening_test, exacthistory_discordance_test


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _average(values):
    return sum(values) / len(values)


def _registered_command_sha(row, registration):
    """Use the command qualified for the assigned acquisition protocol.

    A reduced policy omits the multitone probe. Its registered command is
    therefore a separately qualified no-probe/silence command, rather than
    the full-arm excitation template. Hash equality authenticates file
    identity only; actual drive transfer still requires qualified records.
    """
    field = "reduced_drive_waveform_sha256" if row["policy_arm"] == "fusion_reduced" else "drive_waveform_sha256"
    expected = registration["bound_contract"]["binding"].get(field)
    if not _sha(expected):
        raise ValueError("Assigned protocol has no qualified registered command digest")
    return expected


def _verify_physical_sources(row, registration, root, cache):
    from computing.acquisition import audit_run
    from .protocol import read_json
    if row.get("outcome_status") != "completed":
        relative = Path(row["failure_record_path"])
        path = (root / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(root):
            raise ValueError("Failure record must remain within record root")
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["failure_record_sha256"]:
            raise ValueError("Failure record digest mismatch")
        failure = read_json(path)
        if (failure.get("schema") != "fusion.failed-episode/1" or failure.get("ticket_id") != row["ticket_id"]
                or failure.get("status") != row["outcome_status"] or not failure.get("reason")):
            raise ValueError("Operational failure log disagrees with its assigned episode")
        return
    sources = {}
    for path_key, digest_key in (("raw_run_path", "raw_run_sha256"),
                                 ("pre_feature_path", "pre_feature_sha256"),
                                 ("outcome_record_path", "outcome_record_sha256")):
        relative = Path(row[path_key])
        path = (root / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(root):
            raise ValueError("Physical source must remain within the declared record root")
        key = (str(path), row[digest_key])
        if key not in cache:
            h = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(chunk)
            if h.hexdigest() != row[digest_key]:
                raise ValueError("Physical source digest mismatch: " + path_key)
            cache[key] = read_json(path)
        sources[path_key] = cache[key]
    raw = sources["raw_run_path"]
    raw_path = (root / row["raw_run_path"]).resolve()
    audit_key = (str(raw_path), "acquisition_audit")
    if audit_key not in cache:
        cache[audit_key] = audit_run(raw_path)
    audit = cache[audit_key]
    if audit["status"] != "RECORDED_DATA_CHECKS_PASSED" or raw["data_origin"] != "physical_measurement":
        raise ValueError("Physical acquisition record has unqualified byte/clock/quality status")
    if raw["calibration_id"] != registration["bound_contract"]["binding"]["calibration_id"]:
        raise ValueError("Raw acquisition calibration differs from the bound experiment")
    if audit["sha256"]["drive_command"] != _registered_command_sha(row, registration):
        raise ValueError("Acquired command differs from the registered assigned-protocol waveform")
    if raw.get("run_id") != row["run_id"]:
        raise ValueError("Raw run identity differs from its assigned episode")
    audio_key = ("completed_physical_audio", audit["sha256"]["multichannel_audio"])
    if audio_key in cache:
        raise ValueError("Physical audio evidence reused across randomized episodes")
    cache[audio_key] = True
    if raw["specimen_id"] != row["cartridge_id"] or raw["history_protocol"] != row["write_protocol"]:
        raise ValueError("Raw specimen/history identity differs from its episode")
    pre, post = sources["pre_feature_path"], sources["outcome_record_path"]
    if pre.get("features") != row["features"] or pre.get("feature_end_s") != row["feature_end_s"]:
        raise ValueError("Pre-action feature record disagrees with episode ledger")
    if pre.get("extractor_revision") != row["raw_feature_extractor_revision"]:
        raise ValueError("Pre-action extractor revision changed")
    for key in ("outcome_status", "outcome_cents", "outcome_error_cents", "outcome_start_s", "outcome_end_s",
                "realized_action_cents", "realized_action_error_cents", "pitch_bound_validation_id", "target_Hz"):
        if post.get(key) != row.get(key):
            raise ValueError("Independent outcome record disagrees with episode ledger: " + key)


def _independent_components(blocks):
    """Conservatively merge all blocks sharing a day OR a cartridge."""
    parent = {b: b for b in blocks}
    def find(b):
        while parent[b] != b:
            b = parent[b]
        return b
    keys = {}
    for b, identity in blocks.items():
        for key in [("day", identity[0])] + [("cartridge", c) for c in identity[1]]:
            if key in keys:
                parent[find(b)] = find(keys[key])
            else:
                keys[key] = b
    groups = defaultdict(list)
    for b in blocks:
        groups[find(b)].append(b)
    return list(groups.values())


def evaluate(registration, rows, record_root=None):
    core = validate_registration(registration)
    if not isinstance(rows, list) or not rows:
        raise ValueError("A nonempty confirmation episode list is required")
    bound = registration["bound_contract"]
    root = Path(record_root).resolve() if record_root is not None else None
    if bound["data_origin"] == "physical_measurement" and root is None:
        raise ValueError("Physical scoring requires a record root and hash-bound raw/pre-action/outcome files")
    source_cache = {}
    schedule = {r["ticket_id"]: r for r in registration["schedule"]}
    seen, preparations, cells, identities, order_times, common_overheads = set(), set(), {}, {}, defaultdict(list), {}
    condition_cartridges = {}
    completed_run_ids, completed_raw_digests = set(), set()
    max_pitch_error = exact(core["task"]["maximum_qualified_pitch_error_bound_cents"])
    outcome_timing = core["timing_s_relative_to_write_end"]
    for row in rows:
        if not isinstance(row, dict) or row.get("cohort") != "confirmation":
            raise ValueError("Confirmation rows only")
        ticket = row["ticket_id"]
        if ticket not in schedule or ticket in seen:
            raise ValueError("Unknown or duplicate randomized episode")
        seen.add(ticket)
        expected = schedule[ticket]
        for key in ("block_id", "condition", "write_protocol", "policy_arm"):
            if row[key] != expected[key]:
                raise ValueError("Randomized schedule mismatch: " + key)
        if row["registration_sha256"] != registration["registration_sha256"]:
            raise ValueError("Episode uses a different frozen contract or policy")
        if row["data_origin"] != bound["data_origin"]:
            raise ValueError("Synthetic and physical origins cannot be interchanged")
        if datetime.fromisoformat(row["acquired_utc"]) <= datetime.fromisoformat(registration["registered_utc"]):
            raise ValueError("Confirmation acquisition is not declared after registration")
        acquired = datetime.fromisoformat(row["acquired_utc"])
        if acquired.tzinfo is None or acquired.utcoffset().total_seconds() != 0:
            raise ValueError("Acquisition timestamp must explicitly use UTC")
        if row["day_id"] != acquired.date().isoformat():
            raise ValueError("Acquisition day identity disagrees with its timestamp")
        order_times[row["block_id"]].append((row["performed_order"], acquired))
        if row["preparation_id"] in preparations:
            raise ValueError("Each policy episode requires a freshly prepared replicate")
        preparations.add(row["preparation_id"])
        if row["performed_order"] != expected["order"]:
            raise ValueError("Performed order differs from randomized schedule")
        if exact(row["target_Hz"]) != exact(core["task"]["target_Hz"]):
            raise ValueError("The fixed independent scoring target changed")
        if row["cartridge_id"] in registration["development_cartridges"] or row["day_id"] in registration["development_days"]:
            raise ValueError("Development/confirmation cartridge or day leakage")
        block = row["block_id"]
        if block in identities and identities[block][0] != row["day_id"]:
            raise ValueError("A matched block must retain its acquisition day")
        if block not in identities:
            identities[block] = (row["day_id"], set())
        identities[block][1].add(row["cartridge_id"])
        cartridge_key = (block, "reference" if row["condition"] == "reference_cartridge" else "clay")
        if cartridge_key in condition_cartridges and condition_cartridges[cartridge_key] != row["cartridge_id"]:
            raise ValueError("Matched history/policy/pathway episodes changed the physical cartridge")
        condition_cartridges[cartridge_key] = row["cartridge_id"]
        source_hashes = ("raw_run_sha256", "pre_feature_sha256", "outcome_record_sha256") if row.get("outcome_status") == "completed" else ("failure_record_sha256",)
        for key in source_hashes:
            if not _sha(row.get(key)):
                raise ValueError("Missing raw/feature/outcome digest")
        if row.get("outcome_status") == "completed":
            if row["run_id"] in completed_run_ids or row["raw_run_sha256"] in completed_raw_digests:
                raise ValueError("Completed raw evidence reused across randomized episodes")
            completed_run_ids.add(row["run_id"])
            completed_raw_digests.add(row["raw_run_sha256"])
        if bound["data_origin"] == "physical_measurement":
            _verify_physical_sources(row, registration, root, source_cache)
        if row["calibration_id"] != bound["binding"]["calibration_id"] or row["pitch_bound_validation_id"] != bound["binding"]["pitch_bound_validation_id"]:
            raise ValueError("Calibration or qualified pitch bound changed")
        for field in ("raw_feature_extractor_revision", "synchronization_validation_id", "action_qualification_id"):
            if row[field] != bound["binding"][field]:
                raise ValueError("Qualified acquisition/action binding changed: " + field)
        for key in ("feature_end_s", "decision_time_s", "action_start_s", "action_end_s", "outcome_start_s", "outcome_end_s"):
            exact(row[key])
        clock_error = exact(bound["binding"]["clock_error_bound_s"])
        expected_feature_end = outcome_timing["slow_feature_end"] if row["policy_arm"] == "fusion_reduced" else outcome_timing["dyletsky_probe_end"]
        if abs(exact(row["feature_end_s"]) - exact(expected_feature_end)) > clock_error:
            raise ValueError("Feature window differs from the assigned protocol")
        if exact(row["feature_end_s"]) + 2 * clock_error >= exact(row["decision_time_s"]):
            raise ValueError("Features are not strictly pre-decision under clock bounds")
        if exact(row["decision_time_s"]) > exact(outcome_timing["decision_deadline"]) or exact(row["action_start_s"]) < exact(row["decision_time_s"]):
            raise ValueError("Decision/action timing violates the frozen protocol")
        for key, frozen_key in (("action_start_s", "action_start"), ("action_end_s", "action_end"),
                                ("outcome_start_s", "outcome_start"), ("outcome_end_s", "outcome_end")):
            if abs(exact(row[key]) - exact(outcome_timing[frozen_key])) > clock_error:
                raise ValueError("Changed action or scoring window: " + key)
        protocols = core["reduced_protocols"] if row["policy_arm"] == "fusion_reduced" else core["full_protocols"]
        if sorted(row["acquired_protocols"]) != sorted(protocols) or len(row["acquired_protocols"]) != len(set(row["acquired_protocols"])):
            raise ValueError("Actual acquisition menu differs from the assigned policy arm")
        if row.get("outcome_status") == "completed":
            code = {"connected_clay": 0, "rod_disconnected_clay": 1, "reference_cartridge": 2}[row["condition"]]
            if (exact(row["features"]["write_code"]) != int(row["write_protocol"] == "H1")
                    or exact(row["features"]["condition_code"]) != code):
                raise ValueError("Known preparation/condition features disagree with the assigned log")
        if row["policy_arm"] == "fusion_reduced" and any(k in row["features"] for k in ("bridge_feature", "water_feature")):
            raise ValueError("Reduced policy contains features from the omitted protocol")
        if row.get("outcome_status") == "completed":
            expected_action = choose_action(registration["policies"], row["policy_arm"], row)
            fallback = expected_action == "ABSTAIN"
            if fallback:
                expected_action = "hold"
            if row["action"] != expected_action:
                raise ValueError("Applied action differs from the frozen policy")
        else:
            fallback = True
            if row["action"] not in core["action_ids"]:
                raise ValueError("Failure ledger still requires its actual allowed action or HOLD fallback")
        if row.get("outcome_status") == "completed":
            if exact(row["outcome_error_cents"]) > max_pitch_error:
                raise ValueError("Unqualified outcome pitch error bound")
            desired = exact(core["task"]["actions"][row["action"]])
            achieved = exact(row["realized_action_cents"])
            action_error = exact(row["realized_action_error_cents"])
            if action_error < 0:
                raise ValueError("Negative action achievement uncertainty")
            action_failed = abs(achieved - desired) + action_error > exact(core["task"]["action_achievement_tolerance_cents"])
        else:
            action_failed = True
        if row["outcome_status"] not in {"completed", "action_failed", "pitch_unresolved", "acquisition_failed"}:
            raise ValueError("Unknown operational outcome status")
        loss = (exact(1), exact(1)) if action_failed else pitch_loss_interval(row, core)
        elapsed = sum(exact(row["cost_s"][k]) for k in ("acquisition_s", "waiting_s", "compute_s", "retune_s", "verification_s"))
        if abs(elapsed - exact(outcome_timing["outcome_end"])) > clock_error:
            raise ValueError("Postwrite cost ledger does not account for the fixed scoring epoch")
        if exact(row["cost_s"]["preparation_s"]) != exact(21):
            raise ValueError("Preparation time differs from the registered history schedule")
        overhead_key = (row["block_id"], row["condition"], row["write_protocol"])
        overhead = (exact(row["cost_s"]["reset_s"]), exact(row["cost_s"]["calibration_share_s"]))
        if overhead_key in common_overheads and common_overheads[overhead_key] != overhead:
            raise ValueError("Matched reset/calibration overhead changed across policy arms")
        common_overheads[overhead_key] = overhead
        key = (row["block_id"], row["condition"], row["write_protocol"], row["policy_arm"])
        if key in cells:
            raise ValueError("Duplicate matched preparation cell")
        cells[key] = {"loss": loss, "cost": total_cost(row, core), "fallback": fallback,
                      "decision_failure": action_failed, "pitch_error": row.get("outcome_cents"), "action": row["action"],
                      "qualified_outcome": row["outcome_status"] == "completed" and not action_failed}
    expected_keys = {(r["block_id"], r["condition"], r["write_protocol"], r["policy_arm"]) for r in schedule.values()}
    if set(cells) != expected_keys:
        return {"status": "INCOMPLETE_FIXED_HORIZON", "received_episodes": len(cells),
                "expected_episodes": len(expected_keys), "material_information": "NOT_DEMONSTRATED",
                "cost_reduction": "NOT_DEMONSTRATED", "data_origin": bound["data_origin"],
                "physical_claim": False}
    for times in order_times.values():
        ordered = [time for _, time in sorted(times)]
        if any(a >= b for a, b in zip(ordered, ordered[1:])):
            raise ValueError("Acquisition timestamps contradict the randomized performed order")
    groups = _independent_components(identities)
    # Equal unit weights; repeated observations cannot inflate the sample count.
    def unit(condition, arm, endpoint):
        values = []
        for group in groups:
            items = [cells[(b, condition, h, arm)] for b in group for h in core["histories"]]
            if endpoint == "lower":
                values.append(_average([x["loss"][0] for x in items]))
            elif endpoint == "upper":
                values.append(_average([x["loss"][1] for x in items]))
            else:
                values.append(_average([x["cost"] for x in items]))
        return values
    def conservative_gain(condition, baseline):
        return [a - b for a, b in zip(unit(condition, baseline, "lower"), unit(condition, "fusion_full", "upper"))]
    options = {"alpha": exact(core["statistics"]["family_alpha"]), "comparisons": core["statistics"]["comparisons"]}
    margin = exact(core["statistics"]["minimum_connected_improvement"])
    gain_current = conservative_gain("connected_clay", "memoryless")
    gain_log = conservative_gain("connected_clay", "digital_log")
    tests = {"gain_over_memoryless": lower_mean_test(gain_current, margin, **options),
             "gain_over_known_write_log": lower_mean_test(gain_log, margin, **options)}
    linked_events = 0
    for group in groups:
        b = min(group)  # fixed lexical representative, never chosen by outcomes
        a0, a1 = [cells[(b, "connected_clay", h, "constant")] for h in ("H0", "H1")]
        f0, f1 = [cells[(b, "connected_clay", h, "fusion_full")] for h in ("H0", "H1")]
        discordant = (a0["loss"] == (0, 0) and a1["loss"] == (1, 1)) or (a1["loss"] == (0, 0) and a0["loss"] == (1, 1))
        linked_events += bool(discordant and all(x["qualified_outcome"] for x in (a0, a1, f0, f1))
                              and f0["action"] != f1["action"]
                              and f0["loss"][1] == 0 and f1["loss"][1] == 0)
    tests["history_linked_action_success"] = exacthistory_discordance_test(linked_events, len(groups), **options)
    # An upper bound on reference gain is controlled separately. Combined
    # with connected gain>.1 this establishes a positive difference, not
    # a ten-percentage-point lower bound on that interaction.
    reference_gain_upper = [a - b for a, b in zip(unit("reference_cartridge", "memoryless", "upper"), unit("reference_cartridge", "fusion_full", "lower"))]
    tests["reference_gain_guard"] = binomial_worsening_test(reference_gain_upper,
        exact(core["statistics"]["maximum_reference_gain_probability"]), **options)
    excess = [a - b for a, b in zip(unit("connected_clay", "fusion_reduced", "upper"), unit("connected_clay", "fusion_full", "lower"))]
    tests["reduced_noninferiority"] = binomial_worsening_test(excess,
        exact(core["statistics"]["reduced_noninferiority_margin"]), **options)
    full_cost, reduced_cost = unit("connected_clay", "fusion_full", "cost"), unit("connected_clay", "fusion_reduced", "cost")
    savings = [(a - b) / max(a, b) if max(a, b) else exact(0) for a, b in zip(full_cost, reduced_cost)]
    tests["total_cost_saving"] = lower_mean_test(savings,
        exact(core["statistics"]["minimum_normalized_total_cost_saving"]), **options)
    horizon = len(groups) >= core["confirmation"]["planned_blocks"]
    material = horizon and all(tests[k]["passed"] for k in ("gain_over_memoryless", "gain_over_known_write_log", "reference_gain_guard", "history_linked_action_success"))
    cost = horizon and tests["reduced_noninferiority"]["passed"] and tests["total_cost_saving"]["passed"]
    metrics = {condition: {arm: {"failure_rate_lower": str(_average(unit(condition, arm, "lower"))),
                                 "failure_rate_upper": str(_average(unit(condition, arm, "upper"))),
                                 "mean_total_cost_s": str(_average(unit(condition, arm, "cost")))}
                            for arm in core["policy_arms"]} for condition in core["conditions"]}
    origin = bound["data_origin"]
    return {"schema": "fusion.experiment-result/1", "status": "FIXED_HORIZON_EVALUATED" if horizon else "INSUFFICIENT_INDEPENDENT_UNITS",
            "registration_sha256": registration["registration_sha256"], "confirmation_sha256": digest(rows),
            "data_origin": origin, "episodes": len(rows), "raw_blocks": len(identities),
            "independent_units_after_shared_day_or_cartridge_merge": len(groups),
            "history_linked_action_success_units": linked_events,
            "material_information": ("USEFUL_WITHIN_DECLARED_CONFIRMATION_DESIGN" if material else "NOT_DEMONSTRATED"),
            "cost_reduction": "DEMONSTRATED_WITHIN_DECLARED_COST_MODEL" if cost else "NOT_DEMONSTRATED",
            "physical_claim": False,
            "conditional_physical_inference": origin == "physical_measurement" and material,
            "raw_sources_byte_verified": origin == "physical_measurement" and root is not None,
            "origin_authentication": "DECLARED_ORIGIN_AND_DIGESTS_ONLY",
            "digital_comparison": "SAME_FULL_INFORMATION_AND_IDENTICAL_PREDICTOR; NO_DIGITAL_COMPUTATIONAL_ADVANTAGE_CLAIM",
            "metrics": metrics, "tests": tests,
            "decision_fallbacks": sum(x["fallback"] for x in cells.values()),
            "operational_failures": sum(x["decision_failure"] for x in cells.values()),
            "interpretation": "Conditional on valid error bounds, randomized matched preparations, qualified measurements and independent confirmation units. No autonomous clay-computing or universal speedup claim."}
