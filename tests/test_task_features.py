import copy
import csv
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
import wave

from evaluation.demo import synthetic_binding
from evaluation.protocol import digest
from instrument.task_features import extractor_revision, extract_features, extract_outcome
from instrument.task_features import _cents_with_arithmetic_bound
from instrument.task_features import _validate_force_port
from instrument.episode import compile_episode_commands


ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.write_text(json.dumps(value,indent=2)+'\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(root):
    root.mkdir()
    core=json.loads((ROOT/'experiments/clay_tuning_v1/contract.json').read_text())
    rate=48000;count=21*rate
    write_json(root/'core.json',core)
    compile_episode_commands(root/'core.json',root/'commands')
    for name in ('probe.json','source_probe.wav','experiment_core.json','drive_command.wav'):
        shutil.copyfile(root/'commands/full'/name,root/name)
    shutil.copyfile(root/'commands/full/drive_command.wav',root/'full.wav')
    shutil.copyfile(root/'commands/reduced/drive_command.wav',root/'reduced.wav')
    with wave.open(str(root/'full.wav'),'rb') as stream:full=stream.readframes(count)
    audio=bytearray()
    for u,_ in struct.iter_unpack('<hh',full):
        audio.extend(struct.pack('<hhhh',round(.4*u),round(.8*u),u,0))
    with wave.open(str(root/'audio.wav'),'wb') as stream:
        stream.setparams((4,2,rate,count,'NONE','not compressed'));stream.writeframes(audio)
    with (root/'slow.csv').open('w',newline='') as stream:
        writer=csv.writer(stream,lineterminator='\n')
        writer.writerow(['logger_time_s','force_N','displacement_m','temperature_C'])
        for i in range(1051):
            t=F(i,50)
            writer.writerow([str(t),str(1-t/20),'0.0001',str(22+t/100)])
    run={'schema':'fusion.run/1','run_id':'SYNTHETIC_EPISODE',
        'specimen_id':'SYNTHETIC_CLAY','history_protocol':'H1','data_origin':'synthetic',
        'rod_state':'in',
        'calibration_id':'SYNTHETIC_CALIBRATION','validity_domain':'synthetic task adapter tests only',
        'raw_files':{role:{'path':name,'sha256':sha(root/name)} for role,name in
            [('multichannel_audio','audio.wav'),('drive_command','drive_command.wav'),('slow_force_displacement','slow.csv')]},
        'audio':{'sample_rate_Hz':rate,'channel_map':['hydrophone_raw','bridge_acceleration_raw','drive_loopback_raw','sync_marker_raw'],
            'gain_per_channel':[1,1,1,1],'missing_samples':0},
        'sync':{'offset_s':'0','drift_rate':'0','sync_residual_s':'0','method':'synthetic shared clock',
            'drive_to_audio':{'offset_s':'0','drift_rate':'0','sync_residual_s':'0','method':'synthetic shared clock'}}}
    write_json(root/'run.json',run);write_json(root/'core.json',core)
    binding=synthetic_binding()
    binding.update({'raw_feature_extractor_revision':extractor_revision(),
        'drive_waveform_sha256':sha(root/'full.wav'),'reduced_drive_waveform_sha256':sha(root/'reduced.wav')})
    qualification={'schema':'hydrophone.task-feature-qualification/1','status':'qualified_declaration',
        'data_origin':'synthetic','run_id':run['run_id'],'raw_run_sha256':sha(root/'run.json'),
        'experiment_core_sha256':digest(core),'binding':binding,'evidence_files':[],
        'episode_epoch':{'audio_time_at_write_end_s':'0','adc_nominal_seconds_per_episode_second':'1',
            'total_episode_time_error_bound_s':'0','qualified_episode_interval_s':['0','21'],
            'validation_id':binding['synchronization_validation_id']},
        'channels':{'hydrophone':0,'bridge':1,'drive':2,'pitch':1},
        'mode_transition':{'validation_id':'SYNTHETIC_MODE_TRANSITION',
            'before_first_pluck_complete':True,
            'scope':'qualified_writer_release_and_required_rod_state_including_settling',
            'completion_including_settling_upper_s':'-0.1','writer_state_after':'disconnected',
            'rod_state_after':'in','actual_event_records':[]},
        'slow':{'time_pairing_validation_id':'SYNTHETIC_PAIRING','slow_calibration_validation_id':'SYNTHETIC_SI',
            'temperature_validation_id':'SYNTHETIC_TEMPERATURE','alignment_scope':'qualified_reconstructed_channel_times',
            'force_port':{'measurement_role':'synthetic_reaction_trace','port_validation_id':'SYNTHETIC_FORCE_PORT',
                'physical_sensor_serial':'NO_PHYSICAL_SENSOR','mount_id':'NO_PHYSICAL_MOUNT',
                'connection_state_during_1_2_s':'synthetic_not_applicable','evidence_ids':[]},
            'max_sample_gap_s':'0.021','channel_time_correction_s':{k:'0' for k in ['force_N','displacement_m','temperature_C']},
            'channel_time_error_bound_s':{k:'0' for k in ['force_N','displacement_m','temperature_C']}},
        'probe_detection':{'validation_id':'SYNTHETIC_DRIVE_OMISSION','drive_phasor_error_full_scale':'0.00001',
            'full_min_full_scale':{f:'0.005' for f in core['excitation']['frequencies_Hz']},
            'reduced_max_full_scale':{f:'0.0001' for f in core['excitation']['frequencies_Hz']}}}
    write_json(root/'qualification.json',qualification)
    for role,start,end,pluck,cents in [('pre',F('0.1'),F(1),'0',.5),('post',F('18.1'),F(20),'18',-1.)]:
        pitch={'schema':'hydrophone.qualified-free-decay-pitch/1','status':'qualified_declaration',
            'data_origin':'synthetic','probe_kind':'free_decay_pluck','run_id':run['run_id'],
            'pitch_bound_validation_id':binding['pitch_bound_validation_id'],
            'pitch_probe_qualification_id':binding['pitch_probe_qualification_id'],
            'raw_audio_sha256':sha(root/'audio.wav'),'analysis_channel':1,'window_frames':[int(start*rate),int(end*rate)],
            'pluck_episode_time_s':pluck,'read_id':'SYNTHETIC_'+role,'read_role':role,
            'pitch_Hz_SI':format(float(core['task']['target_Hz'])*2**(cents/1200),'.17g'),
            'pitch_error_cents':'0.25','error_scope':'complete_pitch_error_including_ADC_clock_nonstationarity_and_estimator'}
        write_json(root/(role+'_pitch.json'),pitch)
    write_json(root/'request.json',{'schema':'hydrophone.task-episode-request/1','data_origin':'synthetic',
        'run_id':run['run_id'],'condition':'connected_clay','write_protocol':'H1','policy_arm':'fusion_full','decision_time_s':'4.5',
        'cost_s':{'preparation_s':'21','reset_s':'1','calibration_share_s':'1','acquisition_s':'4',
            'waiting_s':'1.5','compute_s':'0.5','retune_s':'12','verification_s':'2'}})
    write_json(root/'action.json',{'schema':'hydrophone.qualified-manual-action/1','status':'qualified_declaration',
        'run_id':run['run_id'],'data_origin':'synthetic','action_qualification_id':binding['action_qualification_id'],
        'action':'raise5','realized_action_cents':'5','realized_action_error_cents':'0.1',
        'measurement_window_episode_s':['5','17'],'raw_audio_sha256':sha(root/'audio.wav'),
        'window_frames':[5*rate,17*rate],
        'measurement_id':'SYNTHETIC_ACTION_MEASUREMENT'})


class TaskFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=tempfile.TemporaryDirectory();cls.fixture=Path(cls.base.name)/'fixture'
        fixture(cls.fixture)

    @classmethod
    def tearDownClass(cls):cls.base.cleanup()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'case'
        shutil.copytree(self.fixture,self.root)

    def tearDown(self):self.tmp.cleanup()

    def change(self,name,edit):
        path=self.root/name;value=json.loads(path.read_text());edit(value);write_json(path,value)

    def refresh_run(self):
        self.change('qualification.json',lambda q:q.update(raw_run_sha256=sha(self.root/'run.json')))

    def pre(self):
        r=self.root
        return extract_features(r/'run.json',r/'core.json',r/'qualification.json',r/'pre_pitch.json',r/'request.json',r/'features')

    def post(self):
        r=self.root
        return extract_outcome(r/'run.json',r/'core.json',r/'qualification.json',r/'post_pitch.json',r/'action.json',r/'outcome')

    def reduce_command(self):
        for name in ('probe.json','source_probe.wav','experiment_core.json','drive_command.wav'):
            shutil.copyfile(self.root/'commands/reduced'/name,self.root/name)
        self.change('run.json',lambda r:r['raw_files']['drive_command'].update(path='drive_command.wav',sha256=sha(self.root/'drive_command.wav')))

    def test_full_extraction_matches_exact_slow_windows_and_known_complex_ratios(self):
        result=self.pre()['record'];f=result['features']
        self.assertEqual(F(f['relaxation_N']),F('0.04'))
        self.assertEqual(F(f['slow_force_N']),F('0.9055'))
        self.assertEqual(F(f['temperature_C']),F('22.0149'))
        self.assertAlmostEqual(float(f['pre_pitch_cents']),.5,places=8)
        self.assertAlmostEqual(float(f['water_feature']),.4,delta=.001)
        self.assertAlmostEqual(float(f['bridge_feature']),.8,delta=.001)
        self.assertEqual(result['probe_fit']['first_frame'],100800)
        self.assertEqual(result['probe_fit']['stop_frame'],187200)
        self.assertFalse(result['physical_claim'])

    def test_reduced_omission_has_no_probe_features(self):
        self.change('request.json',lambda q:q.update(policy_arm='fusion_reduced'))
        self.reduce_command()
        # Keep measured bridge/water channels; electrical loopback is truly silent.
        path=self.root/'audio.wav'
        with wave.open(str(path),'rb') as stream:params=stream.getparams();pcm=bytearray(stream.readframes(stream.getnframes()))
        for at in range(4,len(pcm),8):pcm[at:at+2]=b'\0\0'
        with wave.open(str(path),'wb') as stream:stream.setparams(params);stream.writeframes(pcm)
        self.change('run.json',lambda r:r['raw_files']['multichannel_audio'].update(sha256=sha(path)))
        self.change('pre_pitch.json',lambda r:r.update(raw_audio_sha256=sha(path)))
        self.refresh_run();result=self.pre()['record']
        self.assertEqual(result['feature_end_s'],'2')
        self.assertNotIn('water_feature',result['features']);self.assertNotIn('bridge_feature',result['features'])

    def test_reduced_arm_rejects_observed_probe_even_with_silence_command(self):
        self.change('request.json',lambda q:q.update(policy_arm='fusion_reduced'))
        self.reduce_command()
        self.refresh_run()
        with self.assertRaisesRegex(ValueError,'presence/omission'):self.pre()

    def test_disabled_qualification_and_synthetic_relabel_reject(self):
        self.change('qualification.json',lambda q:q.update(status='not_qualified'))
        with self.assertRaisesRegex(ValueError,'incomplete or disabled'):self.pre()
        self.change('qualification.json',lambda q:q.update(status='qualified_declaration',data_origin='physical_measurement'))
        with self.assertRaisesRegex(ValueError,'origins'):self.pre()

    def test_raw_hash_and_extractor_revision_are_replayed(self):
        self.change('qualification.json',lambda q:q['binding'].update(raw_feature_extractor_revision='obsolete'))
        with self.assertRaisesRegex(ValueError,'source revision'):self.pre()
        self.change('qualification.json',lambda q:q['binding'].update(raw_feature_extractor_revision=extractor_revision()))
        with (self.root/'slow.csv').open('a') as stream:stream.write('modified\n')
        with self.assertRaisesRegex(ValueError,'SHA256'):self.pre()

    def test_drive_line_cannot_substitute_for_natural_pitch(self):
        self.change('pre_pitch.json',lambda p:p.update(probe_kind='driven_multitone'))
        with self.assertRaisesRegex(ValueError,'free-decay'):self.pre()

    def test_future_pitch_cannot_be_used_as_pre_action_feature(self):
        self.change('pre_pitch.json',lambda p:p.update(window_frames=[868800,960000]))
        with self.assertRaisesRegex(ValueError,'Pitch window'):self.pre()

    def test_unqualified_pitch_error_cannot_be_hidden(self):
        self.change('pre_pitch.json',lambda p:p.update(pitch_error_cents='1.001'))
        with self.assertRaisesRegex(ValueError,'task maximum'):self.pre()

    def test_unqualified_temperature_or_filter_pairing_rejects(self):
        self.change('qualification.json',lambda q:q['slow'].update(temperature_validation_id=None))
        with self.assertRaisesRegex(ValueError,'temperature_validation_id'):self.pre()
        self.change('qualification.json',lambda q:q['slow'].update(temperature_validation_id='SYNTHETIC_TEMPERATURE',alignment_scope='uncorrected_same_row'))
        with self.assertRaisesRegex(ValueError,'reconstructed times'):self.pre()

    def test_outcome_is_independent_and_matches_evaluator_fields(self):
        result=self.post()['record']
        self.assertAlmostEqual(float(result['outcome_cents']),-1,places=8)
        self.assertGreaterEqual(F(result['outcome_error_cents']),F(1,4))
        self.assertLess(F(result['outcome_error_cents'])-F(1,4),F(1,10**9))
        self.assertEqual(result['realized_action_cents'],'5')
        self.assertEqual(result['outcome_start_s'],'18');self.assertEqual(result['outcome_end_s'],'20')
        self.assertNotIn('features',result)

    def test_action_achievement_cannot_reuse_future_outcome(self):
        self.change('action.json',lambda p:p.update(measurement_window_episode_s=['18.1','20']))
        with self.assertRaisesRegex(ValueError,'precede independent outcome'):self.post()

    def test_outcome_window_requires_support_for_timing_allowance(self):
        self.change('qualification.json',lambda q:q['episode_epoch'].update(audio_time_at_write_end_s='1',total_episode_time_error_bound_s='0.001'))
        self.change('run.json',lambda r:r['sync']['drive_to_audio'].update(offset_s='1'))
        self.refresh_run()
        self.change('post_pitch.json',lambda p:p.update(window_frames=[916800,1008000]))
        with self.assertRaisesRegex(ValueError,'timing allowance'):self.post()

    def test_declared_clock_errors_cannot_be_omitted_from_channel_pairing(self):
        self.change('run.json',lambda r:r['sync'].update(sync_residual_s='0.0005'))
        self.refresh_run()
        with self.assertRaisesRegex(ValueError,'omits declared'):self.pre()

    def test_reduced_arm_is_not_available_before_omission_audit(self):
        self.change('request.json',lambda r:r.update(policy_arm='fusion_reduced',decision_time_s='2.5'))
        with self.assertRaisesRegex(ValueError,'pre-action data window boundary'):self.pre()

    def test_registered_clock_guard_controls_decision_availability(self):
        self.change('qualification.json',lambda q:q['binding'].update(clock_error_bound_s='0.1'))
        self.change('request.json',lambda r:r.update(decision_time_s='4.1'))
        with self.assertRaisesRegex(ValueError,'pre-action data window boundary'):self.pre()

    def test_pitch_unit_conversion_has_an_exact_arithmetic_enclosure(self):
        from decimal import Decimal,localcontext
        with localcontext() as context:
            context.prec=80
            for ratio in (F(1),F(2),F(1,2),F(3,2),F(101,100),F(100,101)):
                center,error=_cents_with_arithmetic_bound(ratio)
                expected=Decimal(1200)*(Decimal(ratio.numerator)/Decimal(ratio.denominator)).ln()/Decimal(2).ln()
                error_decimal=Decimal(error.numerator)/Decimal(error.denominator)
                self.assertLessEqual(abs(Decimal(center)-expected),error_decimal+Decimal('1e-70'))
        self.assertEqual(_cents_with_arithmetic_bound(F(1)),('0',F(0)))
        self.assertEqual(_cents_with_arithmetic_bound(F(2)),('1200',F(0)))

    def test_actual_recording_tail_and_channel_roles_cannot_disappear(self):
        self.change('request.json',lambda r:r['cost_s'].update(reset_s='0'))
        with self.assertRaisesRegex(ValueError,'recording tail'):self.pre()
        self.change('request.json',lambda r:r['cost_s'].update(reset_s='1'))
        self.change('qualification.json',lambda q:q['channels'].update(drive=0,hydrophone=2))
        with self.assertRaisesRegex(ValueError,'canonical installed channel'):self.pre()

    def test_mode_transition_cannot_be_assumed_instantaneous(self):
        self.change('qualification.json',lambda q:q['mode_transition'].update(before_first_pluck_complete=False))
        with self.assertRaisesRegex(ValueError,'transition is unqualified'):self.pre()
        self.change('qualification.json',lambda q:q['mode_transition'].update(before_first_pluck_complete=True,completion_including_settling_upper_s='0.01'))
        with self.assertRaisesRegex(ValueError,'extends beyond'):self.pre()

    def test_disconnected_writer_cannot_be_relabelled_as_postwrite_material_force(self):
        writer={'measurement_role':'writer_in_series','port_validation_id':'declared_writer_calibration',
            'physical_sensor_serial':'cell_123','mount_id':'removable_carriage',
            'connection_state_during_1_2_s':'disconnected','evidence_ids':['installed_force_calibration']}
        with self.assertRaisesRegex(ValueError,'permanent clay-reaction port'):
            _validate_force_port('physical_measurement',writer,writer)
        permanent={**writer,'measurement_role':'permanent_clay_reaction','connection_state_during_1_2_s':'connected'}
        with self.assertRaisesRegex(ValueError,'installed operator configuration'):
            _validate_force_port('physical_measurement',permanent,writer)
        _validate_force_port('physical_measurement',permanent,copy.deepcopy(permanent))


if __name__=='__main__':unittest.main()
