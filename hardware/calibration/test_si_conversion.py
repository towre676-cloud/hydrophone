"""Synthetic algebra/contract checks; no actual sensor was calibrated."""
import copy
from fractions import Fraction as F
import importlib.util
import json
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("calibration_conversion",HERE/"si_conversion.py")
MODULE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MODULE)


def records():
    calibration=json.loads((HERE/'calibration_record.synthetic_example.json').read_text())
    analysis={"schema":"hydrophone.stationary-tone-analysis/1","pcm":{"sample_rate_Hz":48000},
              "source_file_sha256":"a"*64,"tones":[{"frequency_Hz":300.0,
              "channel_phasors_full_scale_peak":{"0":{"real":.2,"imag":0},
                "1":{"real":.03,"imag":.04},"2":{"real":.05,"imag":.01}}}]}
    return analysis,calibration


class ConversionTests(unittest.TestCase):
    def test_known_complex_si_and_distinct_transfer_units(self):
        a,c=records()
        result=MODULE.convert_analysis(a,c,configuration_id='SYNTHETIC-CHAIN-A',temperature_C=20,adc_nominal_seconds_per_SI_second=1,adc_timebase_factor_error_abs=0)
        t=result['tones'][0]
        # Hydrophone S=.01+.02i FS/Pa; (.03+.04i)/S=2.2-.4i Pa.
        self.assertAlmostEqual(t['channels_SI']['1']['real'],2.2)
        self.assertAlmostEqual(t['channels_SI']['1']['imag'],-.4)
        self.assertEqual(t['transfers']['pressure_per_drive_voltage']['SI_unit'],'Pa/(V)')
        self.assertEqual(t['transfers']['pressure_per_bridge_acceleration']['SI_unit'],'Pa/(m/s^2)')
        self.assertFalse(result['pressure_per_force_available'])
        self.assertEqual(result['evidence_type'],'synthetic_demo')
        self.assertFalse(result['calibration_authenticity_verified'])
        self.assertIsNone(t['channels_SI']['1']['error_radius_abs_exact_decimal_model'])

    def test_deterministic_disk_bound_contains_explicit_perturbations(self):
        a,c=records()
        errors={str(i):{'300.0':'0.001'} for i in range(3)}
        r=MODULE.convert_analysis(a,c,configuration_id='SYNTHETIC-CHAIN-A',temperature_C=20,adc_nominal_seconds_per_SI_second=1,adc_timebase_factor_error_abs=0,
                                  phasor_error_bounds_full_scale=errors)
        p=r['tones'][0]['channels_SI']['1']
        center=complex(p['real'],p['imag'])
        bound=float(F(p['error_radius_abs_exact_decimal_model']))
        # Each deterministic corner used here lies in its declared disk.
        for dy in [complex(.001,0),complex(0,.001),complex(-.001,0)]:
            for ds in [complex(.0001,0),complex(0,.0001),complex(-.0001,0)]:
                actual=(complex(.03,.04)+dy)/(complex(.01,.02)+ds)
                self.assertLessEqual(abs(actual-center),bound)
        self.assertEqual(p['bound_status'],'conditional_on_declared_deterministic_disks')

    def test_nominal_statistical_uncertainty_is_not_a_deterministic_bound(self):
        a,c=records();c['channels'][1]['points'][0]['uncertainty_kind']='expanded_uncertainty_declared'
        r=MODULE.convert_analysis(a,c,configuration_id='SYNTHETIC-CHAIN-A',temperature_C=20,adc_nominal_seconds_per_SI_second=1,adc_timebase_factor_error_abs=0,
                                  phasor_error_bounds_full_scale={'1':{'300.0':.001}})
        self.assertIsNone(r['tones'][0]['channels_SI']['1']['error_radius_abs_exact_decimal_model'])

    def test_template_wrong_setup_phase_frequency_and_zero_rejected(self):
        a,c=records()
        template=json.loads((HERE/'calibration_record.template.json').read_text())
        with self.assertRaisesRegex(ValueError,'not enabled'):
            MODULE.convert_analysis(a,template,configuration_id='SYNTHETIC-CHAIN-A',temperature_C=20,adc_nominal_seconds_per_SI_second=1,adc_timebase_factor_error_abs=0)
        for mutation in [lambda c:c.update(configuration_id='wrong'),
                         lambda c:c.update(sample_rate_Hz=44100),
                         lambda c:c['channels'][1].update(phase_response_measured=False),
                         lambda c:c['channels'][1].update(SI_unit='N'),
                         lambda c:c['channels'][1].update(role='dynamic_force'),
                         lambda c:c['channels'][1]['points'][0].update(frequency_Hz=301),
                         lambda c:c['channels'][1]['points'][0].update(sensitivity_FS_per_SI={'real':0,'imag':0})]:
            bad=copy.deepcopy(c);mutation(bad)
            with self.assertRaises(ValueError):
                MODULE.convert_analysis(a,bad,configuration_id='SYNTHETIC-CHAIN-A',temperature_C=20,adc_nominal_seconds_per_SI_second=1,adc_timebase_factor_error_abs=0)
        with self.assertRaisesRegex(ValueError,'Temperature'):
            MODULE.convert_analysis(a,c,configuration_id='SYNTHETIC-CHAIN-A',temperature_C=35,adc_nominal_seconds_per_SI_second=1,adc_timebase_factor_error_abs=0)

    def test_force_transfer_requires_distinct_force_sensor_role(self):
        a,c=records();force=copy.deepcopy(c['channels'][2])
        force.update(analysis_channel=3,role='dynamic_force',quantity='force',SI_unit='N')
        c['channels'].append(force)
        a['tones'][0]['channel_phasors_full_scale_peak']['3']={'real':.1,'imag':0}
        r=MODULE.convert_analysis(a,c,configuration_id='SYNTHETIC-CHAIN-A',temperature_C=20,adc_nominal_seconds_per_SI_second=1,adc_timebase_factor_error_abs=0)
        self.assertTrue(r['pressure_per_force_available'])
        self.assertEqual(r['tones'][0]['transfers']['pressure_per_measured_force']['SI_unit'],'Pa/(N)')

    def test_conservative_zero_uncertainty_guard_and_nonfinite(self):
        with self.assertRaisesRegex(ValueError,'zero bound'):
            MODULE._ratio_with_disk((F(1),F(0)),(F(1),F(0)),F(0),F(1))
        for x in ['NaN','Infinity',True,None]:
            with self.assertRaises(ValueError):MODULE._f(x)

    def test_ADC_nominal_frequency_is_not_silently_SI_Hz(self):
        a,c=records()
        with self.assertRaisesRegex(ValueError,'Independent ADC'):
            MODULE.convert_analysis(a,c,configuration_id='SYNTHETIC-CHAIN-A',temperature_C=20)
        for channel in c['channels']:
            channel['points'][0]['frequency_Hz']=303
            channel['points'][0]['frequency_domain_halfwidth_Hz']='0.03'
        r=MODULE.convert_analysis(a,c,configuration_id='SYNTHETIC-CHAIN-A',temperature_C=20,
                                  adc_nominal_seconds_per_SI_second='1.01',adc_timebase_factor_error_abs='.0001')
        self.assertEqual(r['tones'][0]['frequency_SI_Hz_exact_decimal_model'],'303')
        self.assertEqual(r['tones'][0]['frequency_SI_error_Hz_exact_decimal_model'],'3/100')
        with self.assertRaisesRegex(ValueError,'frequency domain'):
            MODULE.convert_analysis(a,c,configuration_id='SYNTHETIC-CHAIN-A',temperature_C=20,
                                      adc_nominal_seconds_per_SI_second='1.01',adc_timebase_factor_error_abs='.0002')

    def test_slow_scale_zero_interval_and_fixture_scope(self):
        r=MODULE.convert_slow_sample(110,zero_raw=100,scale_SI_per_raw='.01',SI_unit='N',
                                     raw_error_abs=1,zero_error_abs=2,scale_error_abs='.001')
        self.assertEqual(r['exact_decimal_model'],'1/10')
        self.assertEqual(r['conditional_interval_exact_decimal_model'],['63/1000','143/1000'])
        self.assertEqual(r['zero_raw_preserved'],'100')
        with self.assertRaises(ValueError):MODULE.convert_slow_sample(1,zero_raw=0,scale_SI_per_raw=0,SI_unit='N')
        with self.assertRaises(ValueError):MODULE.convert_slow_sample(1,zero_raw=0,scale_SI_per_raw=1,SI_unit='m',raw_error_abs=1)


if __name__=='__main__':unittest.main()
