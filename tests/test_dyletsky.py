import math
import unittest

from computing.dyletsky import (
    PITCH_CLASSES, SPELLINGS17, STRATEGIES, build_interval_jacobian, familywise_column_sums,
    ideal_string_plan, make_score, solve_tuning, strategy_weights,
)


class DyletskyTests(unittest.TestCase):
    def test_structural_familywise_cancellation(self):
        rows, labels = build_interval_jacobian()
        self.assertEqual((len(rows), len(rows[0]), len(labels)), (36, 12, 36))
        self.assertEqual(familywise_column_sums(), [[0] * 12] * 3)
        result = solve_tuning(weights=[3] * 12 + [5] * 12 + [11] * 12)
        self.assertTrue(result["forcing_exactly_zero"])
        self.assertEqual(set(result["offsets_cents"].values()), {0.0})

    def test_note_dependent_priorities_break_cancellation(self):
        result = solve_tuning("diatonic_thirds")
        self.assertFalse(result["forcing_exactly_zero"])
        self.assertGreater(result["forcing_norm"], 1)
        self.assertGreater(max(abs(v) for v in result["offsets_cents"].values()), 1)
        self.assertLess(result["normal_equation_residual_max"], 1e-10)
        self.assertEqual(result["offsets_cents"]["C"], 0)

    def test_correct_weighted_rms_not_squared_priorities(self):
        result = solve_tuning("liturgy")
        rows, labels = build_interval_jacobian()
        offsets = [result["offsets_cents"][pc] for pc in PITCH_CLASSES]
        w = strategy_weights("liturgy")
        residual = [sum(a * x for a, x in zip(row, offsets)) - result["targets_cents"][label[0]]
                    for row, label in zip(rows, labels)]
        expected = math.sqrt(sum(weight * r * r for weight, r in zip(w, residual)) / sum(w))
        wrong = math.sqrt(sum((weight * r) ** 2 for weight, r in zip(w, residual)) / sum(w))
        self.assertAlmostEqual(result["weighted_rms_cents"], expected, places=12)
        self.assertGreater(abs(expected - wrong), 1)

    def test_arbitrary_reachable_interval_data_zero_targets(self):
        result = solve_tuning(targets={"M3": 0, "m3": 0, "P5": 0}, ridge=0)
        self.assertEqual(result["weighted_rms_cents"], 0)
        self.assertTrue(result["forcing_exactly_zero"])

    def test_every_archived_strategy_finite_and_model_only(self):
        for strategy in STRATEGIES:
            with self.subTest(strategy=strategy):
                result = solve_tuning(strategy)
                self.assertTrue(math.isfinite(result["weighted_rms_cents"]))
                self.assertLess(result["normal_equation_residual_max"], 1e-9)
                self.assertFalse(result["physical_readiness"])
                self.assertEqual(result["hardware_commands_issued"], 0)

    def test_solver_rejects_invalid_and_unresolved_inputs(self):
        for kwargs in ({"ridge": -1}, {"ridge": float("nan")}, {"targets": {"M3": 0}},
                       {"weights": [0] * 36}, {"weights": [-1] + [1] * 35},
                       {"weights": [float("inf")] * 36}, {"strategy": "unknown"},
                       {"targets": {"M3": 1e200, "m3": 1e200, "P5": 1e200}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                solve_tuning(**kwargs)
        # A disconnected single-edge objective with nonzero forcing and
        # no ridge has no unique gauge-fixed solution.
        with self.assertRaises(ValueError):
            solve_tuning(weights=[1] + [0] * 35, ridge=0)

    def declared_strings(self):
        return [{"id": "s" + str(i), "pitch_class": pc, "base_frequency_hz": f,
                 "base_tension_N": 10, "tension_bounds_N": [1, 100]}
                for i, (pc, f) in enumerate(zip(("C", "E", "G", "B"), (130, 165, 196, 247)))]

    def test_ideal_frequency_and_tension_relationship(self):
        tuning = solve_tuning()
        tuning["offsets_cents"]["E"] = 1200
        plan = ideal_string_plan(tuning, self.declared_strings())
        e = plan["strings"][1]
        self.assertAlmostEqual(e["frequency_ratio"], 2)
        self.assertAlmostEqual(e["required_tension_ratio"], 4)
        self.assertAlmostEqual(e["target_tension_N"], 40)
        self.assertFalse(plan["full_twelve_pitch_objective_realized"])
        self.assertEqual(plan["physical_mapping_status"], "UNBOUND")
        self.assertFalse(plan["physical_readiness"])

    def test_bound_filter_and_missing_bounds_are_distinct(self):
        tuning = solve_tuning()
        tuning["offsets_cents"]["E"] = 1200
        strings = self.declared_strings()
        strings[1]["tension_bounds_N"] = [1, 20]
        self.assertEqual(ideal_string_plan(tuning, strings)["status"], "REJECTED_BY_DECLARED_TENSION_BOUNDS")
        del strings[1]["tension_bounds_N"]
        self.assertEqual(ideal_string_plan(tuning, strings)["status"], "UNRESOLVED_TENSION_BOUNDS")

    def test_exactly_four_declared_strings_and_finite_values(self):
        with self.assertRaises(ValueError):
            ideal_string_plan(solve_tuning(), self.declared_strings()[:3])
        strings = self.declared_strings()
        strings[0]["base_frequency_hz"] = float("nan")
        with self.assertRaises(ValueError):
            ideal_string_plan(solve_tuning(), strings)

    def score_event(self, spelling="C", voice=1, onset=0, duration=1):
        return {"spelling": spelling, "octave": 4, "voice": voice,
                "onset_s": onset, "duration_s": duration, "amplitude": 0.5,
                "tolerance_cents": 2}

    def test_score_preserves_enharmonic_labels_and_exposes_alias(self):
        score = make_score([self.score_event("C#", 1), self.score_event("Db", 2)], solve_tuning("liturgy"))
        self.assertEqual(score["schema"], "fusion.score/1")
        self.assertEqual([event["spelling"] for event in score["events"]], ["C#", "Db"])
        self.assertEqual([event["proxy_pitch_class"] for event in score["events"]], ["C#", "C#"])
        self.assertEqual(score["events"][0]["target_Hz"], score["events"][1]["target_Hz"])
        self.assertEqual(len(SPELLINGS17), 17)
        self.assertFalse(score["enharmonic_offsets_independent"])
        self.assertTrue(score["manual_tuning_requested"])
        self.assertFalse(score["physical_readiness"])
        self.assertEqual(score["hardware_commands_issued"], 0)

    def test_score_octave_reference_and_tuning_offsets(self):
        tuning = solve_tuning()
        tuning["offsets_cents"]["A"] = 1200
        event = self.score_event("A")
        score = make_score([event], tuning, reference_a4_hz=442)
        self.assertAlmostEqual(score["events"][0]["equal_temperament_Hz"], 442)
        self.assertAlmostEqual(score["events"][0]["target_Hz"], 884)
        event["octave"] = 5
        self.assertAlmostEqual(make_score([event], tuning, 442)["events"][0]["target_Hz"], 1768)

    def test_four_voice_polyphony_and_contiguous_voice_events(self):
        events = [self.score_event(pc, voice) for pc, voice in zip(("C", "E", "G", "B"), (1, 2, 3, 4))]
        events.append(self.score_event("C", 1, onset=1))
        score = make_score(events, solve_tuning())
        self.assertEqual(score["max_simultaneous_voices"], 4)
        self.assertFalse(score["events"][-1]["manual_tuning_requested"])
        five_voices = events[:4] + [self.score_event("D", 5)]
        with self.assertRaises(ValueError):
            make_score(five_voices, solve_tuning())

    def test_same_voice_overlap_is_rejected_and_decimal_boundary_is_exact(self):
        events = [self.score_event("C", 1, onset="0.2", duration="0.1"),
                  self.score_event("D", 1, onset="0.3", duration="0.1")]
        self.assertEqual(len(make_score(events, solve_tuning())["events"]), 2)
        events[1]["onset_s"] = "0.299"
        with self.assertRaises(ValueError):
            make_score(events, solve_tuning())

    def test_invalid_score_fields_are_rejected(self):
        variations = [
            {"spelling": "Cb"}, {"voice": 0}, {"voice": True}, {"octave": 4.5},
            {"duration_s": 0}, {"onset_s": -1}, {"amplitude": 1.1},
            {"tolerance_cents": -1}, {"target_Hz": 440}, {"onset_s": float("nan")},
            {"event_id": ""}, {"octave": 100000}, {"spelling": ["C"]},
        ]
        for update in variations:
            event = self.score_event()
            event.update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                make_score([event], solve_tuning())
        event = self.score_event()
        del event["duration_s"]
        with self.assertRaises(ValueError):
            make_score([event], solve_tuning())
        with self.assertRaises(ValueError):
            make_score([], solve_tuning())
        with self.assertRaises(ValueError):
            make_score([self.score_event()], solve_tuning(), reference_a4_hz=0)
        with self.assertRaises(ValueError):
            make_score([self.score_event()], {"offsets_cents": list(PITCH_CLASSES)})


if __name__ == "__main__":
    unittest.main()
