from pathlib import Path
import tempfile
import unittest
import wave

from evaluation.protocol import read_json, bind_contract
from evaluation.demo import synthetic_binding
from evaluation.render import render_probe
from evaluation.observability import witnesses


class ProbeAndObservabilityTests(unittest.TestCase):
    def test_same_physical_renderer_produces_fixed_probe(self):
        core = read_json(Path(__file__).resolve().parents[1] / "experiments/clay_tuning_v1/contract.json")
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.wav", Path(d) / "b.wav"
            result = render_probe(core, a)
            again = render_probe(core, b)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(result["sha256"], again["sha256"])
            with wave.open(str(a)) as stream:
                self.assertEqual(stream.getnframes(), 96000)
                self.assertEqual(stream.getframerate(), 48000)
            self.assertFalse(result["hardware_execution_enabled"])

    def test_binding_rejects_over_ceiling_writer_and_identical_protocols(self):
        core = read_json(Path(__file__).resolve().parents[1] / "experiments/clay_tuning_v1/contract.json")
        for key, value in (("write_stroke_m", "0.000251"), ("force_limit_N", "5.01"),
                           ("reduced_drive_waveform_sha256", "0" * 64)):
            binding = synthetic_binding()
            binding[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                bind_contract(core, binding, "synthetic")

    def test_observable_memory_need_not_affect_the_action(self):
        report = witnesses()
        self.assertEqual(report["observable_task_delta_but_same_unconstrained_optimum"]["forcing"], ["0"])
        self.assertEqual(report["action_relevant_task_delta"]["forcing"], ["3"])


if __name__ == "__main__":
    unittest.main()
