import csv
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import wave

from instrument.bench_demo import demo
from instrument.capture import DuplexCollector, capture_probe
from instrument.probe import load_probe, sha256
from instrument.seal import seal_capture
from instrument.run import analyze_run
from instrument.synchronize import fit_clock, read_clock


class CaptureLifecycle(unittest.TestCase):
    def test_variable_callbacks_preserve_frames_and_silence_tail(self):
        command=bytes(range(20))  # five stereo PCM16 frames
        c=DuplexCollector(command,5,1)
        clock=SimpleNamespace(inputBufferAdcTime=1.,outputBufferDacTime=1.1,currentTime=1.2)
        out=bytearray(12)
        self.assertFalse(c.process(bytes(range(6)),out,3,clock,''))
        self.assertEqual(bytes(out),command[:12])
        out=bytearray([255]*16)
        self.assertTrue(c.process(bytes(range(6,14)),out,4,clock,'input overflow'))
        self.assertEqual(bytes(out),command[12:]+bytes(8))
        self.assertEqual(bytes(c.recorded),bytes(range(10)))
        self.assertTrue(c.flags)

    def test_dimensions_reject_before_any_nonzero_output(self):
        c=DuplexCollector(bytes(16),4,1)
        out=bytearray([255]*8)
        with self.assertRaisesRegex(ValueError,'dimensions'):
            c.process(bytes(3),out,2,None,'')
        self.assertEqual(out,bytes(8))


class BenchEvidenceJoin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=tempfile.TemporaryDirectory()
        cls.fixture=Path(cls.base.name)/'fixture'
        cls.result=demo(cls.fixture)

    @classmethod
    def tearDownClass(cls):cls.base.cleanup()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)/'case'
        shutil.copytree(self.fixture,self.root)

    def tearDown(self):self.tmp.cleanup()

    def seal(self):
        return seal_capture(self.root/'capture/capture.json',self.root/'slow.csv',
            self.root/'operator_metadata.json',self.root/'logger_clock.json',
            self.root/'drive_clock.json',self.root/'joined')

    def rewrite(self,path,value):path.write_text(json.dumps(value))

    def test_known_complex_response_survives_nonzero_clock_drift(self):
        self.assertEqual(self.result['status'],'PASS')
        self.assertLess(self.result['max_complex_gain_error'],.0001)
        sealed=self.seal()
        run=json.loads(Path(sealed['run_manifest']).read_text())
        self.assertNotEqual(run['analysis']['tones']['frequencies_Hz'][0],
                            run['provenance']['nominal_dac_frequencies_Hz'][0])
        self.assertFalse(sealed['physical_readiness_verified'])
        read_clock(self.root/'joined/drive_clock.json','drive_time_s')
        read_clock(self.root/'joined/logger_clock.json','logger_time_s')

    def test_dry_run_has_no_device_import_or_output_directory(self):
        output=self.root/'dry_output'
        with patch.dict('sys.modules',{'sounddevice':None}):
            report=capture_probe(self.root/'capture/probe.json',output)
            self.assertEqual(report['mode'],'DRY_RUN')
            self.assertEqual(report['hardware_commands_issued'],0)
            self.assertFalse(output.exists())
            with self.assertRaisesRegex(ValueError,'explicit duplex'):
                capture_probe(self.root/'capture/probe.json',output,execute=True)

    def test_raw_marker_or_fitted_map_tampering_rejects(self):
        path=self.root/'drive_clock.json'; clock=json.loads(path.read_text())
        clock['offset_s']='0.02';self.rewrite(path,clock)
        with self.assertRaisesRegex(ValueError,'raw-marker replay'):self.seal()
        shutil.copyfile(self.fixture/'drive_clock.json',path)
        with (self.root/'drive_markers.csv').open('a') as stream:stream.write('5.9,5.99\n')
        with self.assertRaisesRegex(ValueError,'SHA256'):self.seal()

    def test_clock_bound_must_cover_marker_picking(self):
        with self.assertRaisesRegex(ValueError,'marker-picking'):
            fit_clock(self.root/'logger_markers.csv',declared_error_s='0',
                source_pick_error_s='.01',audio_pick_error_s='.001',method='test')

    def test_missing_actual_slow_coverage_rejects_even_with_wide_markers(self):
        path=self.root/'slow.csv'
        rows=path.read_text().splitlines();path.write_text('\n'.join(rows[:3])+'\n')
        with self.assertRaisesRegex(ValueError,'Actual slow sample support'):self.seal()

    def test_unreported_slow_gap_rejects(self):
        path=self.root/'slow.csv'
        rows=path.read_text().splitlines();path.write_text('\n'.join([rows[0]]+rows[1::4])+'\n')
        with self.assertRaisesRegex(ValueError,'maximum sampling gap'):self.seal()

    def test_flagged_capture_cannot_be_declared_clean(self):
        path=self.root/'capture/capture.json';capture=json.loads(path.read_text())
        capture['host_flags']=[{'frame':128,'status':'input overflow'}]
        self.rewrite(path,capture)
        with self.assertRaisesRegex(ValueError,'unflagged'):self.seal()

    def test_actual_wav_length_binds_capture_counters(self):
        audio=self.root/'capture/multichannel_audio.wav'
        with wave.open(str(audio),'wb') as stream:
            stream.setparams((4,2,8000,8,'NONE','not compressed'));stream.writeframes(bytes(64))
        path=self.root/'capture/capture.json';capture=json.loads(path.read_text())
        capture['raw_files']['multichannel_audio']['sha256']=sha256(audio)
        self.rewrite(path,capture)
        with self.assertRaisesRegex(ValueError,'frame count'):self.seal()

    def test_command_digest_rejects_before_device_access(self):
        command=self.root/'capture/drive_command.wav'
        with command.open('ab') as stream:stream.write(b'changed')
        with self.assertRaisesRegex(ValueError,'SHA256'):load_probe(self.root/'capture/probe.json')

    def test_native_slow_evidence_is_preserved_and_rechecked(self):
        path=self.root/'operator_metadata.json';metadata=json.loads(path.read_text())
        metadata['native_slow_raw_files']=[{'path':'slow.csv','sha256':sha256(self.root/'slow.csv')}]
        self.rewrite(path,metadata)
        joined=self.seal();manifest=Path(joined['run_manifest'])
        run=json.loads(manifest.read_text());record=run['raw_files']['native_slow_0']
        self.assertEqual((manifest.parent/record['path']).read_bytes(),(self.root/'slow.csv').read_bytes())
        with (manifest.parent/record['path']).open('a') as stream:stream.write('changed\n')
        with self.assertRaisesRegex(ValueError,'SHA256'):analyze_run(manifest)

    def test_synthetic_fixture_cannot_be_relabelled_with_incomplete_physical_metadata(self):
        path=self.root/'operator_metadata.json';metadata=json.loads(path.read_text())
        metadata['data_origin']='physical_measurement';self.rewrite(path,metadata)
        with self.assertRaisesRegex(ValueError,'completed setup identity'):self.seal()

    def test_correlation_receipt_must_bind_the_selected_recording(self):
        path=self.root/'alignment.json'
        self.rewrite(path,{'schema':'hydrophone.drive-alignment/1','recorded_wav_sha256':'wrong'})
        with self.assertRaisesRegex(ValueError,'alignment provenance'):self.seal()


if __name__=='__main__':unittest.main()
