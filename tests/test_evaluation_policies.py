from copy import deepcopy
import json
import unittest

from evaluation.policies import ABSTAIN, choose_action, fit_policies, training_loss


def contract():
    return {"action_ids": ["hold", "raise5"],
            "feature_sets": {"memoryless": ["pre_pitch_cents", "temperature_C", "displacement_m"],
                             "digital_log": ["pre_pitch_cents", "temperature_C", "displacement_m", "write_code"],
                             "digital_full": ["pre_pitch_cents", "temperature_C", "displacement_m", "write_code",
                                              "slow_force_N", "relaxation_N", "bridge_feature", "water_feature"]},
            "fusion_reduced_features": ["slow_force_N"]}


def rows():
    result = []
    for history in (-1, 1):
        for replicate in range(8):
            for action in ("hold", "raise5"):
                drift = -5 if history == -1 else 0
                outcome = drift + (5 if action == "raise5" else 0)
                features = {"pre_pitch_cents": "0", "temperature_C": "20", "displacement_m": "0.001",
                            "write_code": str(history), "slow_force_N": str(history), "relaxation_N": "0",
                            "bridge_feature": "1", "water_feature": "1"}
                result.append({"cohort": "development", "action": action,
                               "outcome_cents": str(outcome), "outcome_error_cents": "0",
                               "features": features, "run_id": f"{history}-{replicate}-{action}"})
    return result


class FrozenPolicyTests(unittest.TestCase):
    def test_log_and_full_learn_useful_action_memoryless_ties(self):
        model = fit_policies(rows(), contract())
        low, high = deepcopy(rows()[0]), deepcopy(rows()[-1])
        for arm in ("digital_log", "digital_full", "fusion_full", "fusion_reduced"):
            self.assertEqual(choose_action(model, arm, low), "raise5")
            self.assertEqual(choose_action(model, arm, high), "hold")
        self.assertEqual(choose_action(model, "memoryless", low), "hold")
        self.assertEqual(choose_action(model, "constant", low), "hold")

    def test_fusion_full_is_same_predictor_and_json_round_trip(self):
        model = fit_policies(rows(), contract())
        self.assertEqual(model["models"]["fusion_full"], model["models"]["digital_full"])
        reloaded = json.loads(json.dumps(model, allow_nan=False))
        self.assertEqual(choose_action(model, "digital_full", rows()[0]),
                         choose_action(reloaded, "fusion_full", rows()[0]))
        self.assertFalse(model["physical_bound_claim"])

    def test_outcome_never_read_at_decision_time(self):
        model = fit_policies(rows(), contract())
        probe = deepcopy(rows()[0])
        expected = choose_action(model, "digital_full", probe)
        del probe["outcome_cents"]
        del probe["outcome_error_cents"]
        del probe["action"]
        self.assertEqual(choose_action(model, "digital_full", probe), expected)

    def test_confirmation_is_not_admitted_to_fit(self):
        data = rows()
        data[0]["cohort"] = "confirmation"
        with self.assertRaisesRegex(ValueError, "development cohort"):
            fit_policies(data, contract())

    def test_missing_actions_features_and_nonfinite_rejected(self):
        with self.assertRaisesRegex(ValueError, "both tuning actions"):
            fit_policies([r for r in rows() if r["action"] == "hold"], contract())
        for field, value in (("temperature_C", "NaN"), ("slow_force_N", None)):
            data = rows()
            data[0]["features"][field] = value
            with self.assertRaisesRegex(ValueError, "finite"):
                fit_policies(data, contract())
        model = fit_policies(rows(), contract())
        missing = deepcopy(rows()[0])
        del missing["features"]["water_feature"]
        with self.assertRaisesRegex(ValueError, "Missing policy feature"):
            choose_action(model, "digital_full", missing)

    def test_optional_predeclared_domain_abstains(self):
        c = contract()
        c["policy_domain"] = {"max_abs_scaled_feature": "2"}
        model = fit_policies(rows(), c)
        probe = deepcopy(rows()[0])
        probe["features"]["slow_force_N"] = "100"
        self.assertEqual(choose_action(model, "digital_full", probe), ABSTAIN)

    def test_empirical_target_bound_and_invalid_readout_error(self):
        self.assertEqual(training_loss({"outcome_cents": "3", "outcome_error_cents": "1"}), 0.04)
        self.assertEqual(training_loss({"outcome_cents": "1e200", "outcome_error_cents": "0"}), 1)
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            training_loss({"outcome_cents": "0", "outcome_error_cents": "-1"})

    def test_training_packet_is_deterministic_and_does_not_mutate_input(self):
        data, c = rows(), contract()
        before = deepcopy((data, c))
        a, b = fit_policies(data, c), fit_policies(data, c)
        self.assertEqual(a, b)
        self.assertEqual((data, c), before)
        self.assertEqual(len(a["development_sha256"]), 64)

    def test_empty_reduced_features_are_an_intercept_policy(self):
        c = contract()
        c["fusion_reduced_features"] = []
        model = fit_policies(rows(), c)
        self.assertEqual(model["models"]["fusion_reduced"]["feature_names"], [])
        self.assertEqual(choose_action(model, "fusion_reduced", rows()[0]), "hold")


if __name__ == "__main__":
    unittest.main()
