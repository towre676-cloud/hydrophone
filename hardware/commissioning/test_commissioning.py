"""Synthetic motion-enclosure and held-out calibration tests, not live trials."""
import copy
import csv
import hashlib
from fractions import Fraction as F
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import sys
import unittest

HERE=Path(__file__).resolve().parent


def load_module(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module


MOTION=load_module('motion')
FIT=load_module('fit_writer_calibration')
TRACE=load_module('trace_bound')


class MotionTests(unittest.TestCase):
    def setUp(self):
        self.r=json.loads((HERE/'examples/motion.synthetic.json').read_text())

    def qualify(self,r=None,**kw):
        return MOTION.qualify_motion(r or self.r,configuration_id='SYNTHETIC-M03-WET-ONLY',**kw)

    def test_all_probe_tones_bound_and_supported_peak(self):
        result=self.qualify()
        self.assertEqual(result['status'],'SYNTHETIC_WITHIN_LIMIT')
        self.assertFalse(result['hardware_execution_enabled'])
        self.assertFalse(result['whole_diaphragm_qualified'])
        self.assertEqual(len(result['tone_bounds_at_reference']),4)
        bound=F(result['boss_motion_peak_upper_m'])
        nominal=0.
        for t in self.r['tones']:
            a=complex(float(t['bridge_acceleration_m_per_s2']['real']),float(t['bridge_acceleration_m_per_s2']['imag']))
            R=complex(float(t['boss_over_bridge_displacement']['real']),float(t['boss_over_bridge_displacement']['imag']))
            nominal+=abs(a)*abs(R)/(2*math.pi*t['frequency_SI_Hz'])**2
        self.assertGreater(float(bound),nominal)
        peak=F(result['largest_supported_digital_peak_under_bound'])
        exact=self.qualify(digital_peak=str(peak))
        self.assertTrue(exact['within_declared_limit'])
        self.assertLessEqual(F(exact['boss_motion_peak_upper_m']),F('.00001'))
        too_big=self.qualify(digital_peak='.02')
        self.assertEqual(too_big['status'],'EXCEEDS_DECLARED_MOTION_LIMIT')

    def test_unknown_band_missing_frequency_configuration_or_scaling_blocks(self):
        for mutation in [lambda r:r['remainder_bounds']['outside_measured_band_peak_m'].update(bound_m=None),
                         lambda r:r['tones'].pop(),
                         lambda r:r.update(configuration_id='wrong'),
                         lambda r:r['conditions'].update(bounds_include_projection_and_rotation=False),
                         lambda r:r['amplitude_scaling'].update(covers_waveform_quantization_and_nonlinearity=False),
                         lambda r:r['tones'][0].update(transfer_domain_covers_frequency_amplitude_preload=False),
                         lambda r:r.update(boss_motion_limit_m='.00002'),
                         lambda r:r.update(observed_motion_band_SI_Hz=None),
                         lambda r:r.update(measurement_time_interval_SI_s=[1,9]),
                         lambda r:r.update(target_port='whole_diaphragm_max')]:
            r=copy.deepcopy(self.r);mutation(r)
            self.assertEqual(self.qualify(r)['status'],'BLOCKED')
        self.assertEqual(self.qualify(digital_peak='.03')['status'],'BLOCKED')

    def test_physical_evidence_requires_matching_raw_file_hashes(self):
        r=copy.deepcopy(self.r);r['evidence_type']='physical_measurements_declared'
        self.assertEqual(self.qualify(r)['status'],'BLOCKED')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for i,e in enumerate(r['evidence_files']):
                data=('known test bytes '+str(i)).encode();name=f'evidence_{i}.txt'
                (root/name).write_bytes(data);e.update(path=name,sha256=hashlib.sha256(data).hexdigest())
            good=MOTION.qualify_motion(r,configuration_id=r['configuration_id'],evidence_root=root)
            self.assertTrue(good['within_declared_limit'])
            self.assertTrue(good['evidence_hashes_checked'])
            self.assertFalse(good['evidence_authenticity_verified'])
            (root/'evidence_0.txt').write_text('tampered')
            bad=MOTION.qualify_motion(r,configuration_id=r['configuration_id'],evidence_root=root)
            self.assertEqual(bad['status'],'BLOCKED')

    def test_direct_displacement_and_velocity_modes(self):
        r=copy.deepcopy(self.r)
        for t in r['tones']:
            t.update(mode='direct_boss_displacement',boss_displacement_m={'real':'.000001','imag':'0','error_radius_abs':'.0000001'})
        r['amplitude_scaling']={'mode':'measured_reference_only'}
        result=self.qualify(r)
        self.assertEqual(F(result['sum_tone_peak_bounds_at_reference_m']),F('.0000044'))
        self.assertEqual(self.qualify(r,digital_peak='.005')['status'],'BLOCKED')
        for t in r['tones']:
            t.update(mode='direct_boss_velocity',boss_velocity_m_per_s={'real':'.002','imag':'0','error_radius_abs':'.0001'})
        self.assertTrue(self.qualify(r)['within_declared_limit'])

    def test_template_nonfinite_negative_and_frequency_uncertainty_block(self):
        template=json.loads((HERE/'motion_record.template.json').read_text())
        self.assertEqual(self.qualify(template)['status'],'BLOCKED')
        for value in [None,'NaN',-.1,400]:
            r=copy.deepcopy(self.r);r['tones'][0]['frequency_error_Hz']=value
            self.assertEqual(self.qualify(r)['status'],'BLOCKED')
        r=copy.deepcopy(self.r);r['tones'][0]['bridge_acceleration_m_per_s2']['error_radius_abs']=-1
        self.assertEqual(self.qualify(r)['status'],'BLOCKED')

    def test_square_root_upper_enclosure_exact(self):
        for x in [F(0),F(2),F(1,10**60),F(987654321,101)]:
            upper=MOTION.sqrt_upper(x)
            self.assertGreaterEqual(upper*upper,x)

    def test_transfer_from_calibrated_boss_and_acceleration_phasors(self):
        f=300.;a=complex(3.,.2);expected=complex(1.2,.1)
        boss=-a*expected/(2*math.pi*f)**2
        result=MOTION.derive_boss_over_bridge({'real':boss.real,'imag':boss.imag,'error_radius_abs':1e-9},
                    {'real':a.real,'imag':a.imag,'error_radius_abs':.01},f,.01)
        nominal=complex(float(F(result['real'])),float(F(result['imag'])))
        self.assertLessEqual(abs(nominal-expected),float(F(result['error_radius_abs'])))
        self.assertFalse(result['hardware_execution_enabled'])
        with self.assertRaises(MOTION.Blocked):
            MOTION.derive_boss_over_bridge({'real':0,'imag':0,'error_radius_abs':0},
                    {'real':0,'imag':0,'error_radius_abs':0},300,0)


class WriterCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.path=self.base/'references.csv'
        self.path.write_bytes((HERE/'examples/writer_references.synthetic.csv').read_bytes())
        self.template=json.loads((HERE.parent/'readout/writer_calibration.template.json').read_text())

    def tearDown(self):self.tmp.cleanup()

    def modify(self,callback):
        with self.path.open(newline='') as f:r=csv.DictReader(f);fields=r.fieldnames;rows=list(r)
        callback(rows)
        with self.path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

    def test_affine_fit_holdout_and_readout_proposal(self):
        result,proposal=FIT.fit_writer_calibration(self.path,self.template)
        self.assertAlmostEqual(result['fit_channels']['force']['scale_SI_per_V'],22.08,delta=3e-6)
        self.assertAlmostEqual(result['fit_channels']['position']['scale_SI_per_V'],.0025,delta=1e-8)
        self.assertEqual(proposal['schema'],'hydrophone.writer-calibration/1')
        self.assertEqual(proposal['status'],'fit_proposal_not_qualified')
        self.assertEqual(proposal['evidence_type'],'synthetic_demo')
        self.assertIsNone(proposal['channels']['force']['total_error_SI'])
        self.assertEqual(proposal['timing'],self.template['timing'])
        self.assertFalse(result['calibration_authenticity_verified'])

    def test_holdout_not_used_to_fit_and_bad_budget_detected(self):
        before,_=FIT.fit_writer_calibration(self.path,self.template)
        def change(rows):
            for r in rows:
                if r['channel']=='force' and r['split']=='validation':r['raw_V']=str(float(r['raw_V'])+.01)
        self.modify(change)
        template=copy.deepcopy(self.template);template['channels']['force']['total_error_SI']=.01
        after,proposal=FIT.fit_writer_calibration(self.path,template)
        self.assertEqual(before['fit_channels']['force']['exact_decimal_fit'],after['fit_channels']['force']['exact_decimal_fit'])
        self.assertGreater(float(F(after['fit_channels']['force']['held_out_point_error_upper_SI'])),.2)
        self.assertTrue(any('contradicted' in x for x in after['review_obligations']))
        self.assertNotEqual(proposal['status'],'measured_with_declared_scope')

    def test_nonheldout_level_unsettled_negative_error_and_mixed_origin_reject(self):
        original=self.path.read_bytes()
        for mutation in [lambda rows:rows[-1].update(level_id='development-5'),
                         lambda rows:rows[-1].update(settled='false'),
                         lambda rows:rows[-1].update(raw_error_V='-1'),
                         lambda rows:rows[-1].update(data_origin='physical_reference_measurement_declared')]:
            self.path.write_bytes(original);self.modify(mutation)
            with self.assertRaises(ValueError):FIT.fit_writer_calibration(self.path,self.template)

    def test_optional_temperature_channel_uses_reference_fit_not_nominal_TMP36(self):
        self.path.write_bytes((HERE/'examples/writer_references_with_temperature.synthetic.csv').read_bytes())
        result,proposal=FIT.fit_writer_calibration(self.path,self.template)
        t=result['fit_channels']['temperature_C']
        self.assertAlmostEqual(t['scale_SI_per_V'],97.5,delta=.01)
        self.assertNotEqual(t['scale_SI_per_V'],100)
        self.assertAlmostEqual(t['zero_raw_V'],.51,delta=.001)
        self.assertEqual(proposal['channels']['temperature_C']['SI_unit'],'degC')
        self.assertIsNone(proposal['channels']['temperature_C']['total_error_SI'])
        self.assertEqual(proposal['scope'],self.template['scope'])


class TraceBoundTests(unittest.TestCase):
    def test_between_sample_sawtooth_peak_is_not_discarded(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'trace.csv'
            path.write_text('time_s,displacement_m,displacement_error_m\n0,0,.1\n1,0,.1\n')
            r=TRACE.bound_trace(path,speed_bound_m_per_s=2,speed_bound_evidence_id='DECLARED-TEST',
                                max_sample_gap_s=1,data_origin='synthetic_demo',configuration_id='TEST')
            # A 2m/s triangle can reach 1m between these zero samples.
            self.assertEqual(F(r['conditional_continuous_peak_upper_m']),F('1.1'))
            self.assertFalse(r['hardware_execution_enabled'])

    def test_unknown_speed_or_excessive_gap_reject(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'trace.csv';path.write_text('time_s,displacement_m,displacement_error_m\n0,0,0\n1,0,0\n')
            for speed,gap in [(None,1),(1,'.5')]:
                with self.assertRaises(ValueError):
                    TRACE.bound_trace(path,speed_bound_m_per_s=speed,speed_bound_evidence_id='TEST',
                                      max_sample_gap_s=gap,data_origin='synthetic_demo',configuration_id='TEST')


if __name__=='__main__':unittest.main()
