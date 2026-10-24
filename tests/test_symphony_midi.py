"""Independent file-level checks for the actual portable performance exports."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
import wave

from symphony.midi import write_midi
from symphony.player import generate_player


def decode_tracks(path):
    raw = path.read_bytes()
    magic, size, format_id, count, ppq = struct.unpack(">4sIHHH", raw[:14])
    assert (magic, size, format_id) == (b"MThd", 6, 1)
    offset, tracks = 14, []

    def vlq(data, position):
        result = 0
        while True:
            byte = data[position]
            position += 1
            result = 128 * result + (byte & 127)
            if byte < 128:
                return result, position

    for _ in range(count):
        marker, length = struct.unpack(">4sI", raw[offset:offset + 8])
        assert marker == b"MTrk"
        data = raw[offset + 8:offset + 8 + length]
        offset += 8 + length
        position, absolute, events = 0, 0, []
        while position < len(data):
            delta, position = vlq(data, position)
            absolute += delta
            status = data[position]
            position += 1
            if status == 255:
                kind = data[position]
                position += 1
                length, position = vlq(data, position)
                events.append((absolute, status, kind, data[position:position + length]))
                position += length
            else:
                length = 1 if status & 240 in (192, 208) else 2
                events.append((absolute, status, data[position:position + length]))
                position += length
        assert events[-1][1:3] == (255, 47)
        tracks.append(events)
    assert offset == len(raw)
    return ppq, tracks


class SymphonyMidiTests(unittest.TestCase):
    def score(self):
        return {"schema": "symphony.score/1", "title": "A tide of light", "tempo_bpm": 120,
                "performed_tempo_map": [{"time_s": 0, "bpm": 120}, {"time_s": 1, "bpm": 60}],
                "events": [{"start_s": 0.25, "duration_s": 0.5, "midi_pitch": 60,
                            "cents": -3.4, "velocity": 0.7, "instrument": "cello", "pan": -0.2},
                           {"start_s": 1.5, "duration_s": 0.5, "midi_pitch": 72,
                            "cents": 1.9, "velocity": 85, "instrument": "flute", "pan": 0.4}]}

    def test_real_midi_tracks_timing_programs_and_note_release(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "music.mid"
            report = write_midi(self.score(), p)
            ppq, tracks = decode_tracks(p)
            self.assertEqual((ppq, len(tracks), report["notes"]), (960, 3, 2))
            tempos = [(e[0], int.from_bytes(e[3], "big")) for e in tracks[0] if e[1:3] == (255, 81)]
            self.assertEqual(tempos, [(0, 500000), (1920, 1000000)])
            notes = [e for track in tracks[1:] for e in track if e[1] & 240 in (128, 144)]
            self.assertEqual([(e[0], e[1] & 240, e[2][0]) for e in notes],
                             [(480, 144, 60), (1440, 128, 60), (2400, 144, 72), (2880, 128, 72)])
            self.assertFalse(any(e[1] & 240 == 224 for track in tracks for e in track if e[1] != 255))
            self.assertIn("AUDIO_CENTS_NOT_REPRESENTED", report["tuning"])

    def test_invalid_notes_and_empty_performances_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for key, value in (("midi_pitch", 200), ("duration_s", -1), ("start_s", -2)):
                score = self.score()
                score["events"][0][key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    write_midi(score, Path(d) / "invalid.mid")
            with self.assertRaises(ValueError):
                write_midi({"schema": "symphony.score/1", "events": []}, Path(d) / "empty.mid")

    def test_sustained_phrase_envelope_is_exported_as_section_expression(self):
        with tempfile.TemporaryDirectory() as d:
            score = self.score()
            score["events"][0]["expression"] = [{"time": 0, "value": 0.3},
                                                   {"time": 0.5, "value": 1},
                                                   {"time": 1, "value": 0.5}]
            path = Path(d) / "expressive.mid"
            report = write_midi(score, path)
            _, tracks = decode_tracks(path)
            controls = [(e[0], e[2][1]) for e in tracks[1] if e[1] & 240 == 176 and e[2][0] == 11]
            self.assertIn((480, 38), controls)
            self.assertIn((960, 127), controls)
            self.assertGreater(report["expression_changes"], 3)

    def test_excerpt_does_not_keep_later_tempo_events_as_silent_music(self):
        with tempfile.TemporaryDirectory() as d:
            score = self.score()
            score["performed_tempo_map"].append({"time_s": 180, "bpm": 90})
            path = Path(d) / "excerpt.mid"
            report = write_midi(score, path)
            _, tracks = decode_tracks(path)
            self.assertEqual(report["tempo_changes"], 2)
            self.assertTrue(all(track[-1][0] <= 3360 for track in tracks))

    def test_self_contained_player_has_actual_audio_and_safe_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            wav, midi = root / "performance.wav", root / "performance.mid"
            with wave.open(str(wav), "wb") as stream:
                stream.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
                stream.writeframes(b"\0\0" * 16000)
            score = self.score()
            score["title"] = "<script>oops</script>"
            score["sections"] = [{"start_s": 0, "end_s": 2, "name": "<opening>"},
                                 {"start_s": 60, "end_s": 120, "name": "UNRENDERED_MOVEMENT"}]
            score["events"][0]["instrument"] = "</script><script>oops</script>"
            write_midi(score, midi)
            out = root / "listen.html"
            report = generate_player(score, wav, out, midi_path=midi)
            source = out.read_text()
            self.assertEqual(report["duration_s"], 2)
            self.assertTrue(report["audio_embedded"])
            self.assertTrue(report["midi_embedded"])
            self.assertIn("data:audio/", source)
            self.assertIn("base64,", source)
            self.assertNotIn("<script>oops</script>", source)
            self.assertIn("&lt;script&gt;oops&lt;/script&gt;", source)
            self.assertNotIn("__DATA__", source)
            self.assertNotIn("https://", source)
            self.assertNotIn("UNRENDERED_MOVEMENT", source)

    def test_missing_rendered_audio_is_not_a_fake_player(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "Rendered audio"):
                generate_player(self.score(), Path(d) / "absent.wav", Path(d) / "player.html")
            empty = Path(d) / "empty.mp3"
            empty.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "Nonempty rendered audio"):
                generate_player(self.score(), empty, Path(d) / "player.html")


if __name__ == "__main__":
    unittest.main()
