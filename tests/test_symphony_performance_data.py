import struct
import unittest

from symphony.performance_data import parse_midi, beat_statistics, note_statistics, balanced_statistic


def vlq(value):
    out = [value & 127]
    value >>= 7
    while value:
        out.insert(0, (value & 127) | 128)
        value >>= 7
    return bytes(out)


def midi(events, division=480):
    data = b"".join(vlq(delta) + event for delta, event in events)
    data += b"\x00\xff\x2f\x00"
    return b"MThd" + struct.pack(">IHHH", 6, 0, 1, division) + b"MTrk" + struct.pack(">I", len(data)) + data


class PerformedMusicDataTests(unittest.TestCase):
    def test_real_tempo_change_converts_note_duration(self):
        data = midi([(0, b"\x90\x3c\x40"), (240, b"\xff\x51\x03\x0f\x42\x40"),
                     (240, b"\x80\x3c\x00")])
        result = parse_midi(data)
        self.assertEqual(len(result["notes"]), 1)
        self.assertAlmostEqual(result["notes"][0][1], .75)
        self.assertEqual(result["notes"][0][3], 64)

    def test_running_status_and_velocity_zero_end(self):
        result = parse_midi(midi([(0, b"\x90\x3c\x40"), (0, b"\x40\x50"),
                                  (480, b"\x3c\x00"), (0, b"\x40\x00")]))
        self.assertEqual([n[2] for n in result["notes"]], [60, 64])
        self.assertEqual(result["unclosed_notes"], 0)

    def test_truncation_and_invalid_division_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_midi(midi([(0, b"\x90\x3c\x40")])[:-2])
        with self.assertRaises(ValueError):
            parse_midi(midi([], division=0x8001))

    def test_overlapping_same_pitch_uses_fifo_key_releases(self):
        data = midi([(0, b"\x90\x3c\x40"), (120, b"\x90\x3c\x50"),
                     (120, b"\x80\x3c\x00"), (120, b"\x80\x3c\x00")])
        notes = parse_midi(data)["notes"]
        self.assertAlmostEqual(notes[0][1], .25)
        self.assertAlmostEqual(notes[1][1], .375)

    def test_annotation_rubato_uses_actual_beat_times(self):
        text = "\n".join(f"{i*.5}\t{i*.5}\t{'db' if i%4==0 else 'b'}" for i in range(12))
        self.assertEqual(beat_statistics(text)["tempo_cv"], 0)
        changed = text.replace("5.0\t5.0", "5.1\t5.1")
        self.assertGreater(beat_statistics(changed)["tempo_cv"], 0)
        self.assertEqual(beat_statistics("0\t0\t4/4"), {})

    def test_person_and_work_balance_prevents_large_artist_domination(self):
        rows = [{"performer": "A", "work": "one", "v": 0}] * 100
        rows += [{"performer": "B", "work": "two", "v": 100}]
        self.assertEqual(balanced_statistic(rows, "v", "performer"), 50)

    def test_summary_does_not_infer_acoustic_pedal_sustain(self):
        parsed = parse_midi(midi([(0, b"\x90\x3c\x40"), (480, b"\x80\x3c\x00")]))
        result = note_statistics(parsed)
        self.assertEqual(result["note_count"], 1)
        self.assertEqual(result["duration_s"], .5)
        self.assertIsNone(result["gate_ratio"])


if __name__ == "__main__":
    unittest.main()
