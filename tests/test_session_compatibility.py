import copy,json,tempfile,unittest
from pathlib import Path
from computing import dyletsky
from examples.create_synthetic_run import generate
from instrument.drive import render_score
from instrument.run import analyze_run

class SessionCompatibility(unittest.TestCase):
    def test_proxy_score_renders_without_losing_spelling(self):
        events=[{'spelling':'C#','octave':4,'voice':1,'onset_s':0,'duration_s':.02,'amplitude':.4,'tolerance_cents':2},
                {'spelling':'Db','octave':4,'voice':2,'onset_s':0,'duration_s':.02,'amplitude':.2,'tolerance_cents':2}]
        score=dyletsky.make_score(events,dyletsky.solve_tuning('ET'))
        with tempfile.TemporaryDirectory() as tmp:
            manifest=render_score(score,Path(tmp)/'proxy.wav',sample_rate=8000)
            self.assertFalse(manifest['hardware_execution_enabled'])
            normalized=copy.deepcopy(score)
            for e in normalized['events']:
                e['start_s']=e.pop('onset_s');e['source_amplitude']=e.pop('amplitude')
            render_score(normalized,Path(tmp)/'normalized.wav',sample_rate=8000)
            self.assertEqual((Path(tmp)/'proxy.wav').read_bytes(),(Path(tmp)/'normalized.wav').read_bytes())
            clash=copy.deepcopy(score);clash['events'][0]['start_s']=1
            with self.assertRaisesRegex(ValueError,'Conflicting'):render_score(clash,Path(tmp)/'bad.wav')
            clash=copy.deepcopy(score);clash['events'][0]['source_amplitude']=.9
            with self.assertRaisesRegex(ValueError,'Conflicting'):render_score(clash,Path(tmp)/'bad.wav')

    def test_canonical_raw_run_joins_auditor_and_signal_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=generate(Path(tmp));run=json.loads(path.read_text())
            run['analysis']={'tones':{'frequencies_Hz':[196.], 'drive_channel':'drive_reference_raw',
                    'response_channel':'hydrophone_raw','reference_channel':'bridge_raw','start_s':.025,'end_s':.225}}
            path.write_text(json.dumps(run));result=analyze_run(path)
            self.assertEqual(result['source_manifest_schema'],'fusion.run/1')
            self.assertFalse(result['acquisition_audit']['physical_readiness'])
            self.assertEqual(result['slow']['source_time_column'],'logger_time_s')
            self.assertIn('logger_time_s',result['slow']['raw_start'])
            self.assertAlmostEqual(result['audio']['tones'][0]['response_over_drive']['amplitude'],.3,delta=.001)
            self.assertFalse(result['evidence_levels']['clock_alignment_verified'])
            self.assertEqual(result['audio']['source_file_sha256'],run['raw_files']['multichannel_audio']['sha256'])
            run['analysis']['tones']['drive_channel']='not-a-channel';path.write_text(json.dumps(run))
            with self.assertRaisesRegex(ValueError,'Unknown audio channel'):analyze_run(path)

    def test_no_implicit_tone_model_from_raw_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=generate(Path(tmp))
            with self.assertRaisesRegex(ValueError,'explicit analysis'):analyze_run(path)

    def test_proxy_equal_temperament_and_recovered_v6_remain_distinct(self):
        proxy=dyletsky.solve_tuning('ET')
        self.assertTrue(all(x==0 for x in proxy['offsets_cents'].values()))
        root=Path(__file__).resolve().parents[1]
        actual=json.loads((root/'design/fusion_design/dyletsky/output/engine_audit.json').read_text())
        self.assertAlmostEqual(actual['v6']['ET']['xnorm'],13.888884643011824,places=11)
        spelling=actual['gen2']['hex_nat']['offsets_by_spelling']
        self.assertNotEqual(spelling['C#'],spelling['Db'])

if __name__=='__main__':unittest.main()
