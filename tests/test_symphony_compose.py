import copy
from pathlib import Path
import unittest

from symphony.compose import compose, score_statistics, RANGES
from symphony.performance import perform


class SymphonyCompositionTests(unittest.TestCase):
    def test_complete_form_registers_and_recurring_theme(self):
        score = compose(seed=71)
        self.assertEqual(len(score["movements"]), 3)
        self.assertEqual(len(score["phrases"]), 11)
        self.assertGreater(len(score["events"]), 700)
        self.assertEqual(score["physical_hardware_commands_issued"], 0)
        for event in score["events"]:
            low, high = RANGES[event["instrument"]]
            self.assertLessEqual(low, event["midi_pitch"])
            self.assertLessEqual(event["midi_pitch"], high)
            self.assertGreater(event["duration_beats"], 0)
        self.assertLessEqual(score_statistics(score)["maximum_within_phrase_melodic_leap_semitones"], 9)
        melody = [e for e in score["events"] if e["role"] == "melody"]
        self.assertGreater(len({e["midi_pitch"] for e in melody}), 8)

    def test_replay_and_corpus_prior_actually_changes_composition(self):
        profile_a = {"balanced": {"interval_probabilities": {"0": .8, "1": .05, "-1": .05}}}
        profile_b = {"balanced": {"interval_probabilities": {"5": .8, "-5": .1, "0": .01}}}
        a = compose(profile_a, seed=19)
        self.assertEqual(a, compose(profile_a, seed=19))
        b = compose(profile_b, seed=19)
        self.assertNotEqual([e["midi_pitch"] for e in a["events"]],
                            [e["midi_pitch"] for e in b["events"]])
        self.assertTrue(a["source_analysis"]["balanced_by_composer"])

    def test_actual_performance_has_movements_and_stays_in_musical_domain(self):
        score = perform(compose(seed=3), seed=3)
        self.assertGreater(score["duration_s"], 150)
        self.assertLess(score["duration_s"], 240)
        self.assertEqual(len(score["sections"]), 3)
        self.assertTrue(all(s["end_s"] > s["start_s"] for s in score["sections"]))
        self.assertTrue(all(0 <= e["start_s"] and 8 <= e["velocity"] <= 124 for e in score["events"]))
        self.assertTrue(any(e["vibrato_depth_cents"] > 0 for e in score["events"]))

    def test_enharmonic_spelling_and_palette_affect_the_actual_model(self):
        profile = {"composer_profiles": {
            "Brahms,_Johannes": {"interval_counts": {"2": 3}, "interval_transition_counts": {"2,2": 2}, "duration_counts": {"1": 2}},
            "Debussy,_Claude": {"interval_counts": {"-1": 3}, "interval_transition_counts": {"-1,-1": 2}, "duration_counts": {"1/2": 2}}}}
        from symphony.compose import select_palette
        selected = select_palette(profile, "romantic")
        self.assertEqual(selected["selected_composers"], ["Brahms,_Johannes"])
        score = compose(seed=9, tuning_profile={"engine_id": "spelled-fixture", "offsets_by_spelling": {"C#": -25, "Db": 20}})
        sharps = [e for e in score["events"] if e["spelling"] == "C#"]
        self.assertTrue(sharps)
        self.assertTrue(all(e["cents"] == -25 for e in sharps))

    def test_microtuning_is_preserved_for_audio_and_bad_expansion_rejects(self):
        score = compose(seed=1, tuning_profile={"engine_id": "verified-fixture", "offsets_by_pitch_class": {"2": -7.5}})
        self.assertTrue(any(e["cents"] == -7.5 for e in score["events"] if e["midi_pitch"] % 12 == 2))
        for value in (0, -1, True):
            with self.assertRaises(ValueError):
                compose(bars_scale=value)


if __name__ == "__main__":
    unittest.main()
