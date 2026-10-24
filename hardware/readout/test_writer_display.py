"""Offline mathematical, validity and native-capture integration checks."""
import copy
import csv
from fractions import Fraction
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("writer_display", HERE/"writer_display.py")
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


class Clock:
    def __init__(self): self.now = 100.12
    def __call__(self): return self.now


def inputs():
    record = json.loads((HERE/"writer_calibration.synthetic.json").read_text())
    context = json.loads((HERE/"writer_session.synthetic.json").read_text())
    return record, context


def start(serial="SYNTHETIC_T7", rate=50, origin=100):
    return {"schema":"hydrophone.t7-observation/1", "kind":"start", "identifier":serial,
            "device_info":[7,1,serial,0,0,64], "actual_scan_rate_Hz":rate,
            "configuration":{"scan_list":w.SCAN_LIST,"stream_resolution_index":7,"range_V":10,"scans_per_read":5},
            "stream_start_host_before_s":origin,"stream_start_host_after_s":origin+.01}


def row(index=0, force=1., position=.0001, rate=50):
    return {"sample_index":index,"time_s":index/rate,"raw_force_V":1.25+force/20,
            "raw_displacement_V":3+position/.001,"raw_marker_V":.05,"raw_excitation_V":2.5,
            "row_has_gap":False,"gap_channels":[],"invalid_channels":[]}


def block(rows):
    return {"schema":"hydrophone.t7-observation/1","kind":"block","host_monotonic_s":100.12,
            "device_scan_backlog":0,"ljm_scan_backlog":0,"rows":rows}


class WriterDisplayTests(unittest.TestCase):
    def monitor(self, *, record=None, context=None, output_dir=None):
        r, c = inputs()
        clock = Clock()
        monitor = w.WriterReadout(record or r, context or c, clock=clock, wall_clock=lambda:NOW,
                                 allow_synthetic=True, output_dir=output_dir)
        monitor.observe(start())
        return monitor, clock

    def test_known_affine_value_and_current_interval_include_age_and_filter(self):
        monitor, clock = self.monitor()
        monitor.observe(block([row()]))
        result = monitor.snapshot()
        self.assertEqual(result["status"], "WITHIN_DECLARED_LIMITS")
        self.assertFalse(result["physical_observation_qualified"])
        force, pos = [result["channels"][role] for role in w.ROLES]
        self.assertAlmostEqual(force["nominal_SI"], 1.)
        self.assertAlmostEqual(pos["nominal_SI"], .0001)
        # Independent arithmetic: clock 100.12; earliest force 99.99999.
        self.assertAlmostEqual(force["sample_age_upper_s"], .12001)
        self.assertAlmostEqual(force["current_error_SI"], .05+.2*(.12001+.1))
        # Position is acquired 670 us after the force channel, with 10 us error.
        self.assertAlmostEqual(pos["sample_age_upper_s"], .11934)
        self.assertAlmostEqual(pos["current_error_SI"], .000002+.000005*(.11934+.1))

    def test_long_decimal_bounds_are_not_truncated_through_float(self):
        perturbation = "0.10000000000000000000000001"
        self.assertEqual(w.rational(perturbation), Fraction(perturbation))
        self.assertNotEqual(w.rational(perturbation), Fraction(str(float(perturbation))))
        # A declared bound just below 0.1 leaves 4.9 strictly below 5.
        # Rounding it to float first would change the STOP classification.
        record, context = inputs()
        record["channels"]["force"]["total_error_SI"] = "0.09999999999999999999999999"
        record["timing"]["per_channel"]["force"]["max_abs_slew_SI_per_s"] = 0
        monitor, _ = self.monitor(record=record,context=context)
        monitor.observe(block([row(force=4.9)]))
        result = monitor.snapshot()
        self.assertNotIn("FORCE UNCERTAINTY REACHES INITIAL LIMIT",result["reasons"])
        self.assertGreaterEqual(Fraction.from_float(result["channels"]["force"]["current_error_SI"]),
                                Fraction(record["channels"]["force"]["total_error_SI"]))

    def test_watchdog_stale_without_new_callback_and_stop_latches(self):
        monitor, clock = self.monitor()
        monitor.observe(block([row()]))
        clock.now += 1
        stale = monitor.snapshot()
        self.assertEqual(stale["status"], "STOP")
        self.assertTrue(any("STALE" in x for x in stale["reasons"]))
        # New delivery cannot silently clear a STOP; a fresh run is required.
        clock.now = 100.14
        monitor.observe(block([row(1)]))
        self.assertEqual(monitor.snapshot()["status"], "STOP")

    def test_fresh_delivery_of_old_scan_is_not_fresh_measurement(self):
        monitor, clock = self.monitor()
        clock.now = 110
        message = block([row()])
        message["host_monotonic_s"] = 110
        monitor.observe(message)
        result = monitor.snapshot()
        self.assertGreater(result["channels"]["force"]["sample_age_upper_s"], 9)
        self.assertEqual(result["status"], "STOP")

    def test_uncertainty_stops_before_nominal_five_newtons(self):
        monitor, _ = self.monitor()
        monitor.observe(block([row(force=4.94, position=.000249)]))
        result = monitor.snapshot()
        self.assertLess(result["channels"]["force"]["nominal_SI"], 5)
        self.assertLess(result["channels"]["position"]["nominal_SI"], .00025)
        self.assertIn("FORCE UNCERTAINTY REACHES INITIAL LIMIT", result["reasons"])
        self.assertIn("POSITION UNCERTAINTY REACHES INITIAL LIMIT", result["reasons"])

    def test_signed_negative_calibration_and_negative_limit(self):
        record, context = inputs()
        record["channels"]["force"]["scale_SI_per_V"] = -20
        monitor, _ = self.monitor(record=record,context=context)
        monitor.observe(block([row(force=1,position=-.0001)]))
        result = monitor.snapshot()
        self.assertAlmostEqual(result["channels"]["force"]["nominal_SI"],-1)
        self.assertAlmostEqual(result["channels"]["position"]["nominal_SI"],-.0001)
        self.assertEqual(result["status"],"WITHIN_DECLARED_LIMITS")
        monitor, _ = self.monitor(record=record,context=context)
        monitor.observe(block([row(force=4.94)]))
        self.assertIn("FORCE UNCERTAINTY REACHES INITIAL LIMIT",monitor.snapshot()["reasons"])

    def test_tare_preserves_native_zero_and_absolute_limit(self):
        monitor, clock = self.monitor()
        monitor.observe(block([row(force=1)]))
        original = copy.deepcopy(monitor.calibration)
        monitor.set_display_tare("Independent reference set; display only")
        self.assertEqual(monitor.calibration, original)
        self.assertAlmostEqual(monitor.tare["native_row"]["raw_force_V"], 1.3)
        clock.now += .02
        monitor.observe(block([row(1, force=4.94)]))
        result = monitor.snapshot()
        self.assertIn("FORCE UNCERTAINTY REACHES INITIAL LIMIT", result["reasons"])
        self.assertAlmostEqual(result["channels"]["force"]["nominal_SI"], 4.94)
        self.assertIn("limits remain absolute", w.render_terminal(result))

    def test_gap_in_middle_of_block_does_not_disappear_behind_latest_row(self):
        monitor, _ = self.monitor()
        rows = [row(i) for i in range(3)]
        rows[1]["row_has_gap"] = True
        rows[1]["raw_force_V"] = -9999
        rows[1]["gap_channels"] = ["AIN0"]
        monitor.observe(block(rows))
        result = monitor.snapshot()
        self.assertEqual(result["sample_index"], 2)
        self.assertEqual(result["status"], "STOP")
        self.assertTrue(any("GAP" in x for x in result["reasons"]))

    def test_backlog_clipping_and_calibration_domain_failures_stop(self):
        examples = [({"device_scan_backlog":1}, {}), ({}, {"raw_force_V":10}),
                    ({}, {"raw_force_V":1.60001}), ({}, {"raw_displacement_V":float("nan")}),
                    ({}, {"raw_excitation_V":2.7})]
        for metadata, changes in examples:
            with self.subTest(metadata=metadata, changes=changes):
                monitor, _ = self.monitor()
                sample = row(); sample.update(changes)
                message = block([sample]); message.update(metadata)
                monitor.observe(message)
                self.assertEqual(monitor.snapshot()["status"], "STOP")

    def test_incomplete_clock_slew_bound_or_template_cannot_qualify(self):
        for missing in ("clock", "slew", "template"):
            with self.subTest(missing=missing):
                record, context = inputs()
                if missing == "clock": record["timing"]["clock_origin_evidence_id"] = None
                if missing == "slew": record["timing"]["per_channel"]["force"]["max_abs_slew_SI_per_s"] = None
                if missing == "template": record = json.loads((HERE/"writer_calibration.template.json").read_text())
                monitor, _ = self.monitor(record=record, context=context)
                monitor.observe(block([row()]))
                self.assertEqual(monitor.snapshot()["status"], "STOP")
                self.assertFalse(monitor.snapshot()["channels"])

    def test_serial_settings_rate_temperature_and_direction_scope_are_checked(self):
        record, context = inputs()
        cases = []
        bad = copy.deepcopy(context); bad["force_sensor_serial"] = "DIFFERENT"; cases.append((record,bad))
        bad = copy.deepcopy(context); bad["temperature_C"] = 23.9; bad["temperature_error_C"] = .2; cases.append((record,bad))
        bad = copy.deepcopy(record); bad["scope"]["qualified_direction_scope"] = ["positive"]; cases.append((bad,context))
        bad = copy.deepcopy(context); bad["temperature_observed_utc"] = "2026-10-23T00:00:00Z"; cases.append((record,bad))
        for rec, ctx in cases:
            with self.assertRaises(ValueError):
                w.validate_calibration(rec,ctx,now=NOW,allow_synthetic=True)
        for event in (start(serial="WRONG"), start(rate=55)):
            monitor, _ = self.monitor()
            monitor.observe(event)
            monitor.observe(block([row()]))
            self.assertEqual(monitor.snapshot()["status"], "STOP")

    def test_derived_csv_keeps_native_time_raw_values_and_pairing(self):
        with tempfile.TemporaryDirectory() as folder:
            monitor, _ = self.monitor(output_dir=folder)
            sample = row()
            monitor.observe(block([sample]))
            monitor.observe({"schema":"hydrophone.t7-observation/1","kind":"end","receipt":{"raw_files":{"original.csv":{"sha256":"known-native-hash"}}}})
            report = monitor.close()
            with (Path(folder)/"writer_observations.csv").open() as stream:
                saved = list(csv.DictReader(stream))
            self.assertEqual(float(saved[0]["raw_force_V"]), sample["raw_force_V"])
            self.assertEqual(float(saved[0]["logger_time_s"]), sample["time_s"])
            self.assertEqual(saved[0]["pairing_id"], "SYNTHETIC_NATIVE_PAIRING")
            self.assertEqual(report["native_end"]["receipt"]["raw_files"]["original.csv"]["sha256"], "known-native-hash")
            self.assertEqual(report["motor_commands"], 0)

    def test_e02_profile_requires_exact_five_channels_and_retains_temperature_voltage(self):
        record, context = inputs()
        record["scope"]["wiring_profile"] = "E02"
        record["scope"]["scan_list"] = w.SCAN_LIST+["AIN8"]
        with tempfile.TemporaryDirectory() as folder:
            clock = Clock()
            monitor = w.WriterReadout(record,context,clock=clock,wall_clock=lambda:NOW,
                allow_synthetic=True,output_dir=folder)
            event = start()
            event["configuration"].update(wiring_profile="E02",scan_list=w.SCAN_LIST+["AIN8"])
            monitor.observe(event)
            sample = row();sample["raw_temperature_V"] = .71
            monitor.observe(block([sample]))
            self.assertEqual(monitor.snapshot()["status"], "WITHIN_DECLARED_LIMITS")
            report = monitor.close()
            with (Path(folder)/"writer_observations.csv").open() as stream:
                saved = list(csv.DictReader(stream))
            self.assertEqual(float(saved[0]["raw_temperature_V"]),.71)
            self.assertNotIn("temperature_C",saved[0])
            self.assertEqual(report["calibration"]["scope"]["wiring_profile"],"E02")

    def test_synthetic_record_is_rejected_before_sdk_loading_for_hardware(self):
        record, context = inputs()
        context["temperature_observed_utc"] = w.utc_now().isoformat()
        with tempfile.TemporaryDirectory() as folder:
            cal, ctx = Path(folder)/"cal.json", Path(folder)/"ctx.json"
            cal.write_text(json.dumps(record)); ctx.write_text(json.dumps(context))
            with patch.object(w,"_load_t7",side_effect=AssertionError("SDK path touched")):
                self.assertEqual(w.main(["--execute","--identifier","470123456","--calibration",str(cal),
                    "--context",str(ctx),"--output-dir",str(Path(folder)/"live")]),2)
            self.assertFalse((Path(folder)/"live").exists())

    def test_offline_demo_reaches_limit_stop_without_hardware_import(self):
        with patch.object(w,"_load_t7",side_effect=AssertionError("SDK path touched")):
            scenes = w.run_demo()
        self.assertTrue(all(scene["synthetic"] for scene in scenes))
        self.assertEqual(scenes[0]["status"], "WITHIN_DECLARED_LIMITS")
        self.assertEqual(scenes[-1]["status"], "STOP")

    def test_actual_t7_capture_observer_with_mock_sdk_preserves_native_file(self):
        native_spec = importlib.util.spec_from_file_location("native_t7_test_helpers", HERE.parent/"electronics"/"test_t7_capture.py")
        helpers = importlib.util.module_from_spec(native_spec); native_spec.loader.exec_module(helpers)
        t7 = w._load_t7()
        record, context = inputs()
        record["scope"]["adc_serial"] = context["adc_serial"] = "470123456"
        with tempfile.TemporaryDirectory() as folder:
            clock = helpers.MockClock(); sdk = helpers.MockLJM(clock)
            monitor = w.WriterReadout(record,context,clock=clock,wall_clock=lambda:NOW,
                allow_synthetic=True,output_dir=Path(folder)/"readout")
            receipt = t7.capture(Path(folder)/"native",identifier="470123456",execute=True,
                duration_s=12,ljm_module=sdk,clock=clock,sleep=clock.sleep,observer=monitor.observe)
            report = monitor.close()
            self.assertEqual(receipt["status"], "CAPTURE_COMPLETED")
            self.assertEqual(report["rows_seen"], 600)
            self.assertEqual(report["native_end"]["receipt"]["raw_files"],receipt["raw_files"])
            self.assertEqual(report["final_observation"]["status"],"STOP")
            native = Path(folder)/"native"/"raw_slow_volts.csv"
            self.assertEqual(w.hashlib.sha256(native.read_bytes()).hexdigest(),receipt["raw_files"][native.name]["sha256"])


if __name__ == "__main__":
    unittest.main()
