from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation.protocol import bind_contract, freeze, read_json, validate_registration, pitch_loss_interval, digest
from evaluation.demo import synthetic_binding, make_development, make_confirmation
from evaluation.evaluate import evaluate, _verify_physical_sources


ROOT = Path(__file__).resolve().parents[1]


class ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = read_json(ROOT / "experiments/clay_tuning_v1/contract.json")
        cls.dev = make_development(cls.core, "coupled")
        cls.bound = bind_contract(cls.core, synthetic_binding(), "synthetic")
        cls.registration = freeze(cls.bound, cls.dev, [f"block-{i}" for i in range(64)],
                                  timestamp="2026-10-24T12:00:00+00:00")
        cls.rows = make_confirmation(cls.registration, "coupled")

    def test_stipulated_coupling_passes_but_not_physical_or_cost_claim(self):
        r = evaluate(self.registration, self.rows)
        self.assertEqual(r["material_information"], "USEFUL_WITHIN_DECLARED_CONFIRMATION_DESIGN")
        self.assertFalse(r["physical_claim"])
        self.assertEqual(r["cost_reduction"], "NOT_DEMONSTRATED")
        self.assertEqual(r["episodes"], 2304)

    def test_detectable_state_without_task_coupling_fails_utility(self):
        dev = make_development(self.core, "no_task_coupling")
        reg = freeze(self.bound, dev, [f"block-{i}" for i in range(64)], timestamp="2026-10-24T12:00:00+00:00")
        r = evaluate(reg, make_confirmation(reg, "no_task_coupling"))
        self.assertEqual(r["material_information"], "NOT_DEMONSTRATED")

    def test_unobservable_different_optimal_actions_fail(self):
        dev = make_development(self.core, "unobservable")
        reg = freeze(self.bound, dev, [f"block-{i}" for i in range(64)], timestamp="2026-10-24T12:00:00+00:00")
        r = evaluate(reg, make_confirmation(reg, "unobservable"))
        self.assertEqual(r["material_information"], "NOT_DEMONSTRATED")

    def test_observable_nuisance_with_no_write_history_effect_fails(self):
        # All readouts still predict future pitch, but H0 and H1 now have
        # identical state in every block: this is not a history effect.
        rows = make_confirmation(self.registration, "observable_nuisance")
        result = evaluate(self.registration, rows)
        self.assertTrue(result["tests"]["gain_over_memoryless"]["passed"])
        self.assertFalse(result["tests"]["history_linked_action_success"]["passed"])
        self.assertEqual(result["material_information"], "NOT_DEMONSTRATED")

    def test_registration_round_trip_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "registration.json"
            p.write_text(json.dumps(self.registration))
            reg = read_json(p)
            validate_registration(reg)
            reg["bound_contract"]["core"]["task"]["success_abs_cents"] = "20"
            with self.assertRaisesRegex(ValueError, "digest"):
                validate_registration(reg)
        reg = deepcopy(self.registration)
        reg["implementation_sha256"]["evaluation/statistics.py"] = "0" * 64
        reg["registration_sha256"] = digest({k: v for k, v in reg.items() if k != "registration_sha256"})
        with self.assertRaisesRegex(ValueError, "implementation changed"):
            validate_registration(reg)

    def test_confirmation_leakage_and_future_features_rejected(self):
        for key, value, message in (("cartridge_id", "dev-cartridge-0", "leakage"),
                                    ("feature_end_s", "19", "Feature window"),
                                    ("data_origin", "physical_measurement", "origins")):
            rows = deepcopy(self.rows)
            rows[0][key] = value
            with self.assertRaisesRegex(ValueError, message):
                evaluate(self.registration, rows)

    def test_changed_action_target_or_schedule_rejected(self):
        for key, value in (("target_Hz", "440"), ("performed_order", 999), ("action", "INVALID")):
            rows = deepcopy(self.rows)
            rows[0][key] = value
            with self.assertRaises(ValueError):
                evaluate(self.registration, rows)

    def test_missing_and_ambiguous_pitch_are_not_success(self):
        self.assertEqual(pitch_loss_interval({"outcome_status": "pitch_unresolved"}, self.core), (1, 1))
        self.assertEqual(pitch_loss_interval({"outcome_status": "completed", "outcome_cents": "2", "outcome_error_cents": "0.5"}, self.core), (0, 1))

    def test_action_achievement_requires_its_own_error_bound(self):
        rows = deepcopy(self.rows)
        rows[0]["realized_action_error_cents"] = "1"
        result = evaluate(self.registration, rows)
        self.assertEqual(result["operational_failures"], 1)

    def test_failed_acquisition_is_an_operational_failure_not_a_dropped_trial(self):
        rows = deepcopy(self.rows)
        row = rows[0]
        row["outcome_status"] = "acquisition_failed"
        row["features"] = {}
        row["action"] = "hold"
        row["failure_record_sha256"] = digest({"synthetic_failure": row["ticket_id"]})
        result = evaluate(self.registration, rows)
        self.assertEqual(result["operational_failures"], 1)
        self.assertEqual(result["episodes"], 2304)

    def test_shared_cartridge_does_not_create64_independent_units(self):
        rows = deepcopy(self.rows)
        for row in rows:
            row["cartridge_id"] = "shared-confirmation-cartridge"
        result = evaluate(self.registration, rows)
        self.assertEqual(result["independent_units_after_shared_day_or_cartridge_merge"], 1)
        self.assertEqual(result["status"], "INSUFFICIENT_INDEPENDENT_UNITS")
        self.assertEqual(result["material_information"], "NOT_DEMONSTRATED")

    def test_distinct_reference_cartridges_are_valid_actual_identities(self):
        rows = deepcopy(self.rows)
        for row in rows:
            if row["condition"] == "reference_cartridge":
                row["cartridge_id"] = "actual-reference-" + row["block_id"]
        result = evaluate(self.registration, rows)
        self.assertEqual(result["independent_units_after_shared_day_or_cartridge_merge"], 64)
        self.assertEqual(result["status"], "FIXED_HORIZON_EVALUATED")

    def test_reusing_only_the_reference_cartridge_still_merges_units(self):
        rows = deepcopy(self.rows)
        for row in rows:
            if row["condition"] == "reference_cartridge":
                row["cartridge_id"] = "shared-reference"
        result = evaluate(self.registration, rows)
        self.assertEqual(result["independent_units_after_shared_day_or_cartridge_merge"], 1)
        self.assertEqual(result["material_information"], "NOT_DEMONSTRATED")

    def test_material_identity_cannot_change_within_matched_contrasts(self):
        rows = deepcopy(self.rows)
        row = next(r for r in rows if r["condition"] == "connected_clay")
        row["cartridge_id"] = "different-material-for-one-arm"
        with self.assertRaisesRegex(ValueError, "changed the physical cartridge"):
            evaluate(self.registration, rows)

    def test_completed_run_identity_or_digest_cannot_be_reused(self):
        for key in ("run_id", "raw_run_sha256"):
            rows = deepcopy(self.rows)
            rows[1][key] = rows[0][key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "raw evidence reused"):
                evaluate(self.registration, rows)

    def test_known_log_baseline_must_receive_the_correct_log(self):
        rows = deepcopy(self.rows)
        row = next(r for r in rows if r["write_protocol"] == "H1")
        row["features"]["write_code"] = "0"
        with self.assertRaisesRegex(ValueError, "assigned log"):
            evaluate(self.registration, rows)

    def test_early_stop_is_incomplete_and_no_claim(self):
        result = evaluate(self.registration, self.rows[:36])
        self.assertEqual(result["status"], "INCOMPLETE_FIXED_HORIZON")
        self.assertFalse(result["physical_claim"])

    def test_omitted_protocol_cannot_secretly_be_recorded(self):
        rows = deepcopy(self.rows)
        row = next(r for r in rows if r["policy_arm"] == "fusion_reduced")
        row["acquired_protocols"].append("dyletsky_probe")
        with self.assertRaisesRegex(ValueError, "acquisition menu"):
            evaluate(self.registration, rows)

    def test_fresh_preparations_and_before_registration(self):
        rows = deepcopy(self.rows)
        rows[1]["preparation_id"] = rows[0]["preparation_id"]
        with self.assertRaisesRegex(ValueError, "freshly prepared"):
            evaluate(self.registration, rows)
        rows = deepcopy(self.rows)
        rows[0]["acquired_utc"] = "2026-10-23T00:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "after registration"):
            evaluate(self.registration, rows)

    def test_unbound_hardware_and_origin_promotion_rejected(self):
        binding = synthetic_binding()
        binding["action_qualification_id"] = None
        with self.assertRaisesRegex(ValueError, "not bound"):
            bind_contract(self.core, binding, "physical_measurement")
        bound = bind_contract(self.core, synthetic_binding(), "physical_measurement")
        with self.assertRaisesRegex(ValueError, "origin"):
            freeze(bound, self.dev, [f"block-{i}" for i in range(64)])
        dev = deepcopy(self.dev)
        for row in dev:
            row["data_origin"] = "physical_measurement"
        reg = freeze(bound, dev, [f"block-{i}" for i in range(64)], timestamp="2026-10-24T12:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "record root"):
            evaluate(reg, self.rows)

    def test_feature_window_clock_order_and_invented_time_saving_rejected(self):
        rows = deepcopy(self.rows)
        rows[0]["feature_end_s"] = "-1"
        with self.assertRaisesRegex(ValueError, "Feature window"):
            evaluate(self.registration, rows)
        rows = deepcopy(self.rows)
        rows[1]["acquired_utc"] = rows[0]["acquired_utc"]
        with self.assertRaisesRegex(ValueError, "timestamps contradict"):
            evaluate(self.registration, rows)
        rows = deepcopy(self.rows)
        row = next(r for r in rows if r["policy_arm"] == "fusion_reduced")
        row["cost_s"]["waiting_s"] = "0"
        with self.assertRaisesRegex(ValueError, "cost ledger"):
            evaluate(self.registration, rows)


class PhysicalCommandBindingTests(unittest.TestCase):
    """Exercise source-identity branches, not laboratory authentication."""

    def fixture(self, root, arm):
        row = {"run_id": "test-run", "policy_arm": arm, "outcome_status": "completed", "cartridge_id": "declared-cartridge",
               "write_protocol": "H0", "features": {"pre_pitch_cents": "0"},
               "feature_end_s": "2" if arm == "fusion_reduced" else "4",
               "raw_feature_extractor_revision": "test-extractor", "outcome_cents": "0",
               "outcome_error_cents": "0.1", "outcome_start_s": "18", "outcome_end_s": "20",
               "realized_action_cents": "0", "realized_action_error_cents": "0.1",
               "pitch_bound_validation_id": "test-pitch", "target_Hz": "326"}
        raw = {"run_id": "test-run", "data_origin": "physical_measurement", "calibration_id": "test-calibration",
               "specimen_id": row["cartridge_id"], "history_protocol": row["write_protocol"]}
        pre = {"features": row["features"], "feature_end_s": row["feature_end_s"],
               "extractor_revision": row["raw_feature_extractor_revision"]}
        post_fields = ("outcome_status", "outcome_cents", "outcome_error_cents", "outcome_start_s", "outcome_end_s",
                       "realized_action_cents", "realized_action_error_cents", "pitch_bound_validation_id", "target_Hz")
        post = {key: row[key] for key in post_fields}
        for name, record, path_key, sha_key in (("raw.json", raw, "raw_run_path", "raw_run_sha256"),
                                               ("pre.json", pre, "pre_feature_path", "pre_feature_sha256"),
                                               ("post.json", post, "outcome_record_path", "outcome_record_sha256")):
            path = root / name
            path.write_text(json.dumps(record))
            row[path_key], row[sha_key] = name, hashlib.sha256(path.read_bytes()).hexdigest()
        registration = {"bound_contract": {"binding": {"calibration_id": "test-calibration",
                            "drive_waveform_sha256": "a" * 64, "reduced_drive_waveform_sha256": "b" * 64}}}
        return row, registration

    def test_full_and_reduced_protocol_commands_are_distinct(self):
        for arm, expected, wrong in (("fusion_full", "a" * 64, "b" * 64),
                                      ("fusion_reduced", "b" * 64, "a" * 64)):
            with self.subTest(arm=arm), tempfile.TemporaryDirectory() as d:
                root = Path(d).resolve()
                row, registration = self.fixture(root, arm)
                with patch("computing.acquisition.audit_run", return_value={
                        "status": "RECORDED_DATA_CHECKS_PASSED", "sha256": {"drive_command": expected, "multichannel_audio": "c" * 64}}):
                    _verify_physical_sources(row, registration, root, {})
                with patch("computing.acquisition.audit_run", return_value={
                        "status": "RECORDED_DATA_CHECKS_PASSED", "sha256": {"drive_command": wrong, "multichannel_audio": "c" * 64}}):
                    with self.assertRaisesRegex(ValueError, "assigned-protocol waveform"):
                        _verify_physical_sources(row, registration, root, {})

    def test_physical_audio_bytes_cannot_be_copied_into_another_episode(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            row, registration = self.fixture(root, "fusion_full")
            with patch("computing.acquisition.audit_run", return_value={
                    "status": "RECORDED_DATA_CHECKS_PASSED",
                    "sha256": {"drive_command": "a" * 64, "multichannel_audio": "c" * 64}}):
                cache = {}
                _verify_physical_sources(row, registration, root, cache)
                with self.assertRaisesRegex(ValueError, "audio evidence reused"):
                    _verify_physical_sources(row, registration, root, cache)

    def test_reduced_protocol_cannot_fall_back_to_full_command_digest(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            row, registration = self.fixture(root, "fusion_reduced")
            del registration["bound_contract"]["binding"]["reduced_drive_waveform_sha256"]
            with patch("computing.acquisition.audit_run", return_value={
                    "status": "RECORDED_DATA_CHECKS_PASSED", "sha256": {"drive_command": "a" * 64, "multichannel_audio": "c" * 64}}):
                with self.assertRaisesRegex(ValueError, "no qualified registered command"):
                    _verify_physical_sources(row, registration, root, {})


if __name__ == "__main__":
    unittest.main()
