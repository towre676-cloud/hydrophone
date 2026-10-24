from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest
import wave


@unittest.skipUnless(importlib.util.find_spec("numpy"), "Optional sampled renderer requires NumPy")
class ScoreValidationTests(unittest.TestCase):
    @staticmethod
    def fixture():
        return {"schema": "symphony.score/1", "events": [
            {"start_s": 0, "duration_s": .5, "midi_pitch": 69, "cents": 5,
             "velocity": 80, "instrument": "violin", "pan": -.3}]}

    def test_invalid_data_and_instruments_rejected_before_rendering(self):
        from symphony.render import validate_score
        for key, value in (("start_s", -1), ("duration_s", 0), ("midi_pitch", 128),
                           ("velocity", 0), ("cents", float("nan")), ("instrument", "spaceship")):
            score = self.fixture(); score["events"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_score(score)

    def test_expression_and_fractional_pitch_are_preserved(self):
        from symphony.render import validate_score
        score = self.fixture()
        score["events"][0].update(midi_pitch=69.25, expression=[
            {"time": 0, "value": .2}, {"time": .4, "value": 1.1}, {"time": 1, "value": .5}])
        event = validate_score(score)[0]
        self.assertEqual(event["midi_pitch"], 69)
        self.assertEqual(event["cents"], 30)
        self.assertEqual(event["expression_values"], [.2, 1.1, .5])
        score["events"][0]["expression"][1]["time"] = 0
        with self.assertRaisesRegex(ValueError, "increase"):
            validate_score(score)

    def test_sampled_render_has_audio_stereo_headroom_and_source_identity(self):
        from symphony.render import render_score, find_soundfont
        try:
            find_soundfont()
        except FileNotFoundError:
            self.skipTest("Documented optional orchestral SoundFont not installed")
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.wav"
            result = render_score(self.fixture(), path, sample_rate=16000)
            with wave.open(str(path)) as stream:
                self.assertEqual(stream.getnchannels(), 2)
                self.assertEqual(stream.getframerate(), 16000)
                data = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").reshape(-1, 2)
            self.assertGreater(np.sqrt(np.mean(data.astype(float) ** 2)), 20)
            self.assertGreater(np.max(np.abs(data[:, 0].astype(int) - data[:, 1].astype(int))), 50)
            self.assertEqual(result["clipped_sample_count"], 0)
            self.assertLessEqual(result["peak_full_scale"], .891)
            self.assertEqual(len(result["soundfont_sha256"]), 64)
            self.assertFalse(result["live_orchestra_recording"])
            self.assertEqual(result["hardware_commands_issued"], 0)


if __name__ == "__main__":
    unittest.main()
