import hashlib,json,tempfile,unittest
from pathlib import Path
from instrument.demo import demo
from instrument.run import analyze_run

class RunTests(unittest.TestCase):
    def test_hash_bound_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); result=demo(p)
            self.assertEqual(result['dyletsky_target_count'],4)
            self.assertLess(result['max_complex_gain_error'],.001)
            analysis=analyze_run(p/'run.json')
            self.assertFalse(analysis['hardware_execution_enabled'])
            self.assertFalse(analysis['evidence_levels']['physical_model_certified'])
            run=json.loads((p/'run.json').read_text());run['audio']['sha256']='0'*64
            (p/'run.json').write_text(json.dumps(run))
            with self.assertRaisesRegex(ValueError,'SHA256'):analyze_run(p/'run.json')

    def test_path_and_origin_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);demo(p)
            run=json.loads((p/'run.json').read_text());run['audio']['path']='../outside.wav'
            (p/'run.json').write_text(json.dumps(run))
            with self.assertRaisesRegex(ValueError,'escapes'):analyze_run(p/'run.json')
            run['data_origin']='unknown';(p/'run.json').write_text(json.dumps(run))
            with self.assertRaisesRegex(ValueError,'origin|declare'):analyze_run(p/'run.json')

if __name__=='__main__':unittest.main()
