from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from computing.cli import load_json, main
from computing.object_adapter import synthetic_fixture, sample_transcript


class CLITests(unittest.TestCase):
    def test_plan_and_runtime_decision(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            contract = synthetic_fixture()
            (root / "contract.json").write_text(json.dumps(contract))
            transcript = sample_transcript(contract, "slow_plunger_acquisition", {"force": "0.42", "displacement": "0.001"})
            (root / "transcript.json").write_text(json.dumps(transcript))
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["plan", str(root / "contract.json")])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.getvalue())["protocols"], ["slow_plunger_acquisition"])
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["decide", str(root / "contract.json"), str(root / "transcript.json")])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.getvalue())["actions"], ["report_low_memory"])

    def test_duplicate_keys_and_nonfinite_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "input.json"
            for content in ('{"a":1,"a":2}', '{"a":NaN}'):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    load_json(path)

    def test_bad_contract_returns_validation_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "input.json"
            path.write_text('{"schema":"unified-object/fusion-adapter/v1"}')
            err = io.StringIO()
            with redirect_stderr(err):
                code = main(["plan", str(path)])
            self.assertEqual(code, 2)
            self.assertIn("error:", err.getvalue())
            self.assertNotIn("Traceback", err.getvalue())

    def test_array_contract_and_manifest_are_clean_errors(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "array.json"
            path.write_text("[]")
            for command in ("plan", "validate", "audit-run"):
                err = io.StringIO()
                with redirect_stderr(err):
                    code = main([command, str(path)])
                self.assertEqual(code, 2)
                self.assertIn("JSON object", err.getvalue())


if __name__ == "__main__":
    unittest.main()
