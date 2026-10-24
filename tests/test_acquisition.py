import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import wave

from computing.acquisition import audit_run


class AcquisitionTests(unittest.TestCase):
    def fixture(self, root, clipped=False):
        for name, channels in (("audio.wav", 4), ("drive.wav", 1)):
            with wave.open(str(root / name), "wb") as stream:
                stream.setnchannels(channels)
                stream.setsampwidth(2)
                stream.setframerate(8000)
                values = [0] * (800 * channels)
                if clipped and name == "audio.wav":
                    values[1] = 32767
                stream.writeframes(struct.pack("<" + "h" * len(values), *values))
        (root / "slow.csv").write_text("logger_time_s,force_N,displacement_m\n0,0.42,0.001\n0.1,0.41,0.001\n")
        def record(name):
            return {"path": name, "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest()}
        run = {"schema": "fusion.run/1", "run_id": "synthetic-test", "specimen_id": "simulated",
               "data_origin": "synthetic", "history_protocol": "declared-test", "calibration_id": "synthetic",
               "validity_domain": "synthetic-only", "raw_files": {"multichannel_audio": record("audio.wav"),
               "slow_force_displacement": record("slow.csv"), "drive_command": record("drive.wav")},
               "audio": {"sample_rate_Hz": 8000, "channel_map": ["string", "bridge", "hydrophone", "drive_reference"],
                         "gain_per_channel": [1, 1, 1, 1], "missing_samples": 0},
               "sync": {"offset_s": "0", "drift_rate": "0", "sync_residual_s": "0.001", "method": "synthetic-test",
                        "drive_to_audio": {"offset_s": "0", "drift_rate": "0", "sync_residual_s": "0", "method": "synthetic-test"}}}
        path = root / "run.json"
        path.write_text(json.dumps(run))
        return path, run

    def test_real_bytes_and_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            path, _ = self.fixture(Path(d))
            result = audit_run(path)
            self.assertEqual(result["status"], "RECORDED_DATA_CHECKS_PASSED")
            self.assertEqual(result["slow_force_range_N"], ["41/100", "21/50"])
            self.assertEqual(result["declared_clock_common_interval_length_s"], "49/500")
            self.assertFalse(result["physical_readiness"])

    def test_full_scale_sample_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as d:
            path, _ = self.fixture(Path(d), clipped=True)
            result = audit_run(path)
            self.assertEqual(result["audio"]["full_scale_sample_counts"], [0, 1, 0, 0])
            self.assertEqual(result["status"], "RECORDING_QUALITY_REQUIRES_REVIEW")

    def test_digest_and_declared_clock_failures(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path, run = self.fixture(root)
            run["sync"]["offset_s"] = "2"
            path.write_text(json.dumps(run))
            with self.assertRaisesRegex(ValueError, "common time"):
                audit_run(path)
            path, _ = self.fixture(root)
            (root / "slow.csv").write_text("tampered")
            with self.assertRaisesRegex(ValueError, "digest"):
                audit_run(path)

    def test_nonfinite_slow_record_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path, run = self.fixture(root)
            (root / "slow.csv").write_text("logger_time_s,force_N,displacement_m\n0,NaN,0.001\n1,0.4,0.001\n")
            run["raw_files"]["slow_force_displacement"]["sha256"] = hashlib.sha256((root / "slow.csv").read_bytes()).hexdigest()
            path.write_text(json.dumps(run))
            with self.assertRaisesRegex(ValueError, "finite"):
                audit_run(path)

    def test_channel_arrays_and_drive_clock_are_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path, run = self.fixture(root)
            run["audio"]["channel_map"] = "abcd"
            path.write_text(json.dumps(run))
            with self.assertRaisesRegex(ValueError, "Channel map"):
                audit_run(path)
            path, run = self.fixture(root)
            run["audio"]["gain_per_channel"] = "1111"
            path.write_text(json.dumps(run))
            with self.assertRaisesRegex(ValueError, "positive declared gain"):
                audit_run(path)
            path, run = self.fixture(root)
            del run["sync"]["drive_to_audio"]
            path.write_text(json.dumps(run))
            result = audit_run(path)
            self.assertEqual(result["drive_temporal_alignment"]["status"], "UNVERIFIED_NO_DRIVE_CLOCK_MAP")
            self.assertEqual(result["status"], "RECORDING_QUALITY_REQUIRES_REVIEW")


if __name__ == "__main__":
    unittest.main()
