from array import array
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from instrument.episode import compile_episode_commands
from instrument.probe import load_probe,sha256
from instrument.capture import capture_probe
from instrument.align import align_drive

ROOT=Path(__file__).resolve().parents[1]


class EpisodeCommands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.base=Path(cls.tmp.name)/'commands'
        cls.result=compile_episode_commands(ROOT/'experiments/clay_tuning_v1/contract.json',cls.base)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_actual_played_files_have_distinct_registered_hashes_and_exact_slot(self):
        full,pcm,_=load_probe(self.base/'full/probe.json')
        reduced,silence,_=load_probe(self.base/'reduced/probe.json')
        self.assertEqual(full['frames'],21*48000)
        self.assertNotEqual(full['drive_command']['sha256'],reduced['drive_command']['sha256'])
        self.assertFalse(any(silence))
        self.assertFalse(any(pcm[:2*48000*4]));self.assertFalse(any(pcm[4*48000*4:]))
        self.assertTrue(any(pcm[2*48000*4:4*48000*4]))
        self.assertEqual(full['tail_cost']['component'],'reset_s')
        report=capture_probe(self.base/'full/probe.json',self.base/'unused_dry')
        self.assertEqual(report['duration_s'],21)
        self.assertEqual(report['hardware_commands_issued'],0)

    def test_even_rehashed_injected_excitation_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'reduced';shutil.copytree(self.base/'reduced',case)
            wav=case/'drive_command.wav'
            with wave.open(str(wav),'rb') as stream:values=array('h');values.frombytes(stream.readframes(stream.getnframes()))
            values[0]=100
            with wave.open(str(wav),'wb') as stream:
                stream.setparams((2,2,48000,21*48000,'NONE','not compressed'));stream.writeframes(values.tobytes())
            plan=json.loads((case/'probe.json').read_text());plan['drive_command']['sha256']=sha256(wav)
            (case/'probe.json').write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError,'presence/omission'):load_probe(case/'probe.json')

    def test_source_waveform_cannot_be_swapped_under_same_core(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'reduced';shutil.copytree(self.base/'reduced',case)
            source=case/'source_probe.wav'
            with wave.open(str(source),'wb') as stream:
                stream.setparams((1,2,48000,96000,'NONE','not compressed'));stream.writeframes(bytes(96000*2))
            plan=json.loads((case/'probe.json').read_text());plan['source_probe']['sha256']=sha256(source)
            (case/'probe.json').write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError,'independently replayed'):load_probe(case/'probe.json')

    def test_reduced_silence_does_not_invent_waveform_clock_anchors(self):
        with self.assertRaisesRegex(ValueError,'independently qualified clock'):
            align_drive(self.base/'reduced/probe.json',self.base/'reduced/drive_command.wav',self.base/'unmade_alignment')

    def test_rehashed_core_cannot_move_the_registered_timeline(self):
        from evaluation.protocol import digest
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'full';shutil.copytree(self.base/'full',case)
            core_file=case/'experiment_core.json';core=json.loads(core_file.read_text())
            core['timing_s_relative_to_write_end']['dyletsky_probe_start']='12'
            core_file.write_text(json.dumps(core))
            plan=json.loads((case/'probe.json').read_text())
            plan['experiment_core']['sha256']=sha256(core_file)
            plan['experiment_core_canonical_sha256']=digest(core)
            (case/'probe.json').write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError,'exact clay-history'):load_probe(case/'probe.json')

    def test_engineering_probe_cli_keeps_its_own_parameters(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=subprocess.run([sys.executable,'-m','instrument','probe',
                str(ROOT/'design/fusion_design/dyletsky/output/instrument_plan.json'),
                '--sample-rate','8000','--plateau','4','--output-dir',str(Path(tmp)/'probe')],
                cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['sample_rate_Hz'],8000)

if __name__=='__main__':unittest.main()
