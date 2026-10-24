from copy import deepcopy
import math
import unittest

from symphony.performance import perform


def fixture():
    events = []
    for beat in range(16):
        for instrument, role, pitch in (("violin", "melody", 72), ("cello", "bass", 48),
                                        ("flute", "countermelody", 79), ("horn", "harmony", 60)):
            events.append({"event_id": f"{instrument}-{beat}", "start_beat": beat,
                           "duration_beats": 1., "midi_pitch": pitch,
                           "instrument": instrument, "role": role, "velocity": 80,
                           "cents": -3., "phrase_id": "a" if beat < 8 else "b"})
    return {"schema": "symphony.score/1", "tempo_bpm": 80,
            "phrases": [{"id": "a", "start_beat": 0, "end_beat": 8},
                        {"id": "b", "start_beat": 8, "end_beat": 16, "intensity": 1.1}],
            "sections": [{"name": "opening", "start_beat": 0, "end_beat": 8}],
            "events": events}


class PerformanceTests(unittest.TestCase):
    def test_deterministic_copy_with_no_fabricated_training_claim(self):
        score = fixture()
        before = deepcopy(score)
        a, b = perform(score, seed=7), perform(score, seed=7)
        self.assertEqual(a, b)
        self.assertEqual(score, before)
        self.assertFalse(a["performance"]["recorded_performer_model_trained"])
        self.assertEqual(len(a["events"]), len(score["events"]))

    def test_shared_clock_preserves_chord_coherence(self):
        result = perform(fixture(), seed=9)
        for beat in range(16):
            arrivals = [e["start_s"] for e in result["events"] if e["start_beat"] == beat]
            self.assertLess(max(arrivals) - min(arrivals), .05)
        times = result["performed_tempo_map"]
        self.assertTrue(all(a["time_s"] < b["time_s"] for a, b in zip(times, times[1:])))
        self.assertTrue(all(e["start_s"] >= 0 and e["duration_s"] > 0 for e in result["events"]))

    def test_phrasing_is_a_shared_tempo_shape_not_note_jitter(self):
        result = perform(fixture())
        curve = result["performed_tempo_map"]
        early = min(curve, key=lambda p: abs(p["beat"] - 1.))
        middle = min(curve, key=lambda p: abs(p["beat"] - 4.))
        cadence = min(curve, key=lambda p: abs(p["beat"] - 7.875))
        self.assertGreater(middle["bpm"], early["bpm"])
        self.assertLess(cadence["bpm"], middle["bpm"])
        a = [e for e in result["events"] if e["instrument"] == "violin" and e["phrase_id"] == "a"]
        self.assertGreater(a[4]["velocity"], a[0]["velocity"])

    def test_written_pitch_and_part_order_are_preserved(self):
        result = perform(fixture())
        for e in result["events"]:
            self.assertEqual(e["written_cents"], -3.)
            self.assertLess(abs(e["cents"] - e["written_cents"]), .6)
            self.assertTrue(math.isfinite(e["vibrato_hz"]))
            self.assertTrue(0 < e["velocity"] <= 127)
        for instrument in ("violin", "cello", "flute", "horn"):
            notes = [e for e in result["events"] if e["instrument"] == instrument]
            self.assertTrue(all(a["start_s"] < b["start_s"] for a, b in zip(notes, notes[1:])))

    def test_explicit_tempo_map_and_zero_rubato_have_known_integral(self):
        score = fixture()
        score["tempo_map"] = [{"beat": 0, "bpm": 60}, {"beat": 16, "bpm": 120}]
        profile = {"performance_parameters": {"rubato_strength": 0, "cadence_ritard": 0}}
        result = perform(score, profile=profile)
        last = result["performed_tempo_map"][-1]
        self.assertAlmostEqual(last["time_s"] - .045, 16 * math.log(2), places=11)
        self.assertGreater(result["sections"][0]["end_s"], result["sections"][0]["start_s"])

    def test_dense_phrase_changes_never_reverse_written_part(self):
        score = fixture()
        score.pop("phrases")
        score["events"] = [{"event_id": str(i), "start_beat": i * .002,
                            "duration_beats": .002, "midi_pitch": 60 + i % 5,
                            "instrument": "violin", "phrase_id": str(i)} for i in range(20)]
        result = perform(score, {"performance_parameters": {"ensemble_spread_ms": 16}}, seed=1)
        notes = sorted(result["events"], key=lambda e: e["start_beat"])
        self.assertTrue(all(a["start_s"] < b["start_s"] for a, b in zip(notes, notes[1:])))

    def test_actual_performance_profile_changes_bounded_priors_with_lineage(self):
        profile = {"schema": "symphony.performance-profile/1", "performance_count": 400,
                   "performer_count": 20, "source_manifest_sha256": "a" * 64,
                   "performance_statistics": {"median_tempo_cv": .12, "median_velocity_iqr": 24}}
        result = perform(fixture(), profile)
        self.assertAlmostEqual(result["performance"]["parameters"]["rubato_strength"], .042)
        self.assertAlmostEqual(result["performance"]["parameters"]["phrase_dynamic_depth"], .16)
        self.assertEqual(result["performance"]["measured_performance_priors"]["performance_count"], 400)
        self.assertFalse(result["performance"]["recorded_performer_model_trained"])
        profile["source_manifest_sha256"] = None
        with self.assertRaisesRegex(ValueError, "source-manifest"):
            perform(fixture(), profile)

    def test_local_tempo_statistics_take_precedence_and_quiet_layers_survive(self):
        profile = {"schema": "symphony.performance-profile/1", "performance_count": 400,
                   "source_manifest_sha256": "a" * 64,
                   "performance_statistics": {"median_tempo_cv": .6, "median_local_tempo_cv": .06}}
        score = fixture()
        score["phrases"][0]["intensity"] = .3
        for event in score["events"]:
            event["velocity"] = 45
        result = perform(score, profile)
        self.assertAlmostEqual(result["performance"]["parameters"]["rubato_strength"], .021)
        self.assertEqual(result["performance"]["measured_performance_priors"]["tempo_statistic"], "median_local_tempo_cv")
        self.assertGreaterEqual(min(e["velocity"] for e in result["events"]), 37)

    def test_invalid_or_already_performed_data_rejected(self):
        for key, value in (("start_beat", -1), ("duration_beats", 0),
                           ("midi_pitch", float("nan")), ("velocity", 128)):
            score = fixture()
            score["events"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                perform(score)
        with self.assertRaisesRegex(ValueError, "already"):
            perform(perform(fixture()))
        with self.assertRaisesRegex(ValueError, "Unknown"):
            perform(fixture(), {"performance_parameters": {"pretend_learning": 1}})


if __name__ == "__main__":
    unittest.main()
