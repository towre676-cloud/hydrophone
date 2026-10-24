import csv
from fractions import Fraction
import itertools
from pathlib import Path
import tempfile
import unittest

from instrument.slow import analyze_slow


class SlowFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "slow.csv"

    def write_rows(self, rows, fields=None):
        fields = fields or ["time_s", "force_N", "displacement_m"]
        with self.path.open("w", newline="", encoding="utf-8") as target:
            writer = csv.DictWriter(target, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return self.path

    def loop_rows(self):
        return [dict(time_s=i, force_N=force, displacement_m=x)
                for i, (force, x) in enumerate(zip([2, 2, 0, 0, 2], [0, 1, 1, 0, 0]))]

    def test_two_joule_closed_loop_and_unknown_default_closure(self):
        path = self.write_rows(self.loop_rows())
        default = analyze_slow(path)
        self.assertEqual(default["work"]["sampled_path_work_J"], 2)
        self.assertIsNone(default["closure"]["geometric_loop_closed"])
        self.assertIsNone(default["closure"]["force_returned"])
        measured = analyze_slow(path, displacement_closure_tolerance_m=0,
                                force_return_tolerance_N=0)
        self.assertTrue(measured["closure"]["geometric_loop_closed"])
        self.assertTrue(measured["closure"]["force_returned"])
        self.assertFalse(measured["work"]["dissipation_identified"])

    def test_reversing_path_orientation_preserves_negative_work(self):
        original = self.loop_rows()
        reverse = [dict(row, time_s=i) for i, row in enumerate(reversed(original))]
        result = analyze_slow(self.write_rows(reverse), displacement_closure_tolerance_m=0)
        self.assertEqual(result["work"]["sampled_path_work_J"], -2)
        self.assertTrue(result["closure"]["geometric_loop_closed"])
        self.assertFalse(result["physical_readiness"])

    def test_nonclosed_path_is_work_not_loop_dissipation(self):
        result = analyze_slow(self.write_rows(self.loop_rows()[:2]),
                              displacement_closure_tolerance_m=.01,
                              force_return_tolerance_N=0)
        self.assertEqual(result["work"]["sampled_path_work_J"], 2)
        self.assertFalse(result["closure"]["geometric_loop_closed"])
        self.assertTrue(result["closure"]["force_returned"])
        self.assertFalse(result["work"]["dissipation_identified"])

    def hold_rows(self):
        rows = [dict(time_s=100+i, force_N=5, displacement_m=.1,
                     stage="baseline_before", temperature_C=21) for i in range(5)]
        rows += [dict(time_s=105+i, force_N=force, displacement_m=.2,
                      stage="hold", temperature_C=21.1)
                 for i, force in enumerate([15, 13, 11, 9, 7])]
        return rows

    def test_hold_retains_dc_baseline_and_actual_clock(self):
        rows = self.hold_rows()
        result = analyze_slow(self.write_rows(rows, list(rows[0])), max_hold_drift_m=0,
                              force_error_N=0, rod_state="disconnected")
        self.assertEqual(result["raw_start"]["time_s"], 100)
        self.assertEqual(result["raw_start"]["force_N"], 5)
        self.assertEqual(result["baseline"]["sample_count"], 5)
        self.assertEqual(result["baseline"]["force_mean_N"], 5)
        hold = result["hold_analysis"]["windows"][0]
        self.assertTrue(hold["eligible"])
        self.assertEqual(hold["time_start_s"], 105)
        self.assertEqual(hold["elapsed_from_record_start_s"], 5)
        self.assertEqual(hold["duration_s"], 4)
        self.assertEqual(hold["features"]["force_drop_N"], 8)
        self.assertAlmostEqual(hold["features"]["relaxation_fraction"], .8)
        self.assertFalse(hold["features"]["relaxation_time_identified"])
        self.assertEqual(result["rod_state"], "disconnected")

    def test_hold_drift_or_unknown_tolerance_disqualifies_relaxation(self):
        rows = self.hold_rows()
        rows[-1]["displacement_m"] += .001
        path = self.write_rows(rows, list(rows[0]))
        unknown = analyze_slow(path)["hold_analysis"]["windows"][0]
        self.assertFalse(unknown["eligible"])
        self.assertIn("hold_displacement_tolerance_not_declared", unknown["reasons"])
        drifting = analyze_slow(path, max_hold_drift_m=.0001)["hold_analysis"]["windows"][0]
        self.assertFalse(drifting["eligible"])
        self.assertIsNone(drifting["features"])
        self.assertIn("hold_displacement_drift_exceeds_tolerance", drifting["reasons"])

    def test_explicit_window_needs_consistent_stage_when_present(self):
        rows = self.hold_rows()
        path = self.write_rows(rows, list(rows[0]))
        wrong_stage = analyze_slow(path, hold_window_s=(104, 109), max_hold_drift_m=1)
        self.assertFalse(wrong_stage["hold_analysis"]["windows"][0]["eligible"])
        self.assertIn("selected_samples_not_all_labelled_hold",
                      wrong_stage["hold_analysis"]["windows"][0]["reasons"])
        outside = analyze_slow(path, hold_window_s=(105, 110), max_hold_drift_m=1)
        self.assertIn("requested_window_outside_record",
                      outside["hold_analysis"]["windows"][0]["reasons"])

    def test_no_unlabelled_hold_inference_but_explicit_window_is_supported(self):
        rows = [{name: row[name] for name in ("time_s", "force_N", "displacement_m")}
                for row in self.hold_rows()[5:]]
        path = self.write_rows(rows)
        self.assertEqual(analyze_slow(path)["hold_analysis"]["windows"], [])
        result = analyze_slow(path, hold_window_s=(105, 109), max_hold_drift_m=0)
        self.assertTrue(result["hold_analysis"]["windows"][0]["eligible"])
        self.assertIsNone(result["hold_analysis"]["windows"][0]["features"]["relaxation_fraction"])

    def test_small_record_error_box_contains_all_corner_works(self):
        forces = [1.2, -.4, .7]
        positions = [.1, .6, -.2]
        rows = [dict(time_s=i, force_N=f, displacement_m=x)
                for i, (f, x) in enumerate(zip(forces, positions))]
        e_force, e_position = .05, .02
        result = analyze_slow(self.write_rows(rows), force_error_N=e_force,
                              displacement_error_m=e_position)
        low, high = result["work"]["sampled_path_interval_J"]
        for signs in itertools.product((-1, 1), repeat=6):
            true_force = [Fraction.from_float(f) + signs[i]*Fraction.from_float(e_force)
                          for i, f in enumerate(forces)]
            true_position = [Fraction.from_float(x) + signs[3+i]*Fraction.from_float(e_position)
                             for i, x in enumerate(positions)]
            corner_work = sum((true_force[i] + true_force[i+1])
                              *(true_position[i+1] - true_position[i])/2 for i in range(2))
            self.assertGreaterEqual(corner_work, Fraction.from_float(low))
            self.assertLessEqual(corner_work, Fraction.from_float(high))
        self.assertFalse(result["work"]["between_sample_path_error_bounded"])
        self.assertIn("interpolation_and_undersampling_excluded", result["work"]["error_bound_scope"])

    def test_bad_clock_nonfinite_data_and_missing_columns_fail(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            rows = self.loop_rows()
            rows[1]["force_N"] = value
            with self.assertRaises(ValueError):
                analyze_slow(self.write_rows(rows))
        rows = self.loop_rows()
        rows[1]["time_s"] = rows[0]["time_s"]
        with self.assertRaises(ValueError):
            analyze_slow(self.write_rows(rows))
        self.path.write_text("time_s,force_N\n0,1\n1,2\n")
        with self.assertRaises(ValueError):
            analyze_slow(self.path)

    def test_negative_or_nonfinite_declared_tolerances_fail(self):
        path = self.write_rows(self.loop_rows())
        for key in ("force_error_N", "displacement_error_m", "max_hold_drift_m",
                    "displacement_closure_tolerance_m", "force_return_tolerance_N"):
            for value in (-1, float("nan"), float("inf")):
                with self.assertRaises(ValueError):
                    analyze_slow(path, **{key: value})


if __name__ == "__main__":
    unittest.main()
