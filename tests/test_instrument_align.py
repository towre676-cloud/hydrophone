import csv
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest
import wave

from instrument.align import align_drive
from instrument.probe import compile_probe
from instrument.synchronize import read_clock

try:
    import numpy as np
    import scipy
except ImportError:
    np = None


@unittest.skipIf(np is None, 'optional numpy/scipy unavailable')
class DriveAlignment(unittest.TestCase):
    def fixture(self, root, *, frequencies=None, lag=73, gain=.8, noise=0.):
        frequencies = frequencies or [261.626,292.39573306577114,326.759563456652,391.1253463782126]
        source = root/'targets.json'
        source.write_text(json.dumps({'calibration_targets':[{'target_Hz':f} for f in frequencies]}))
        compile_probe(source, root/'probe', sample_rate=8000, plateau_s=4, peak=.03)
        with wave.open(str(root/'probe/drive_command.wav'),'rb') as stream:
            source_pcm = np.frombuffer(stream.readframes(stream.getnframes()),dtype='<i2').reshape(-1,2)[:,0]
        loopback = np.zeros(len(source_pcm),dtype=float)
        if lag >= 0:
            loopback[lag:] = gain*source_pcm[:len(source_pcm)-lag]
        else:
            loopback[:lag] = gain*source_pcm[-lag:]
        if noise:
            loopback += np.random.default_rng(773).normal(0,noise,len(loopback))
        channels = np.zeros((len(loopback),4),dtype='<i2')
        channels[:,2] = np.rint(loopback).astype('<i2')
        recording = root/'recording.wav'
        self.write_wav(recording,channels)
        return root/'probe/probe.json',recording

    @staticmethod
    def write_wav(path, channels):
        with wave.open(str(path),'wb') as stream:
            stream.setparams((channels.shape[1],2,8000,len(channels),'NONE','not compressed'))
            stream.writeframes(channels.astype('<i2').tobytes())

    def test_integer_delay_and_gain_recover_three_evidence_bound_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); probe,recording=self.fixture(root,noise=.5)
            result=align_drive(probe,recording,root/'alignment',max_delay_s=.1)
            self.assertEqual([a['lag_frames'] for a in result['anchors']],[73]*3)
            self.assertTrue(all(a['peak_correlation']>.999 for a in result['anchors']))
            clock=read_clock(root/'alignment/drive_clock.json','drive_time_s')
            self.assertEqual(Fraction(clock['offset_s']),Fraction(73,8000))
            self.assertEqual(Fraction(clock['drift_rate']),0)
            self.assertFalse(clock['between_marker_bound_verified'])
            self.assertFalse(result['physical_clock_bound_verified'])
            self.assertEqual(result['hardware_commands_issued'],0)
            with (root/'alignment/markers.csv').open() as stream:
                markers=list(csv.DictReader(stream))
            self.assertEqual(Fraction(markers[0]['drive_time_s']),1)
            self.assertEqual(Fraction(markers[-1]['drive_time_s']),5)

    def test_negative_delay_requires_explicit_bracket(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); probe,recording=self.fixture(root,lag=-31)
            result=align_drive(probe,recording,root/'alignment',min_delay_s=-.05,max_delay_s=.05)
            self.assertEqual([a['lag_frames'] for a in result['anchors']],[-31]*3)

    def test_affine_clock_drift_changes_anchor_lags_without_fractional_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);probe,recording=self.fixture(root)
            with wave.open(str(root/'probe/drive_command.wav')) as stream:
                command=np.frombuffer(stream.readframes(stream.getnframes()),dtype='<i2').reshape(-1,2)[:,0].astype(float)
            frames=np.arange(len(command));slope=1.0003
            warped=.8*np.interp((frames-73)/slope,frames,command,left=0,right=0)
            channels=np.zeros((len(command),4),dtype='<i2');channels[:,2]=np.rint(warped).astype('<i2')
            self.write_wav(recording,channels)
            result=align_drive(probe,recording,root/'alignment')
            lags=[a['lag_frames'] for a in result['anchors']]
            self.assertTrue(lags[0]<lags[1]<lags[2])
            clock=read_clock(root/'alignment/drive_clock.json','drive_time_s')
            self.assertAlmostEqual(float(Fraction(clock['drift_rate'])),.0003,delta=1/(8000*4))
            self.assertFalse(result['physical_clock_bound_verified'])

    def test_periodic_single_tone_is_rejected_as_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); probe,recording=self.fixture(root,frequencies=[250.])
            with self.assertRaisesRegex(ValueError,'Ambiguous'):
                align_drive(probe,recording,root/'alignment',max_delay_s=.1)

    def test_silence_clipping_and_wrong_channel_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); probe,recording=self.fixture(root,gain=0.)
            with self.assertRaisesRegex(ValueError,'zero or unresolved'):
                align_drive(probe,recording,root/'zero',max_delay_s=.1)
            channels=np.zeros((48000,4),dtype='<i2');channels[16000,2]=32767
            self.write_wav(recording,channels)
            with self.assertRaisesRegex(ValueError,'clipped'):
                align_drive(probe,recording,root/'clipped')
            with self.assertRaisesRegex(ValueError,'outside the recording'):
                align_drive(probe,recording,root/'badchannel',loopback_channel=4)

    def test_inversion_and_boundary_peaks_are_not_silently_aligned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);probe,recording=self.fixture(root,gain=-.8)
            with self.assertRaisesRegex(ValueError,'threshold|Ambiguous'):
                align_drive(probe,recording,root/'inverted',max_delay_s=.1)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);probe,recording=self.fixture(root,lag=0)
            with self.assertRaisesRegex(ValueError,'boundary'):
                align_drive(probe,recording,root/'boundary',max_delay_s=.1)

    def test_no_false_precision_or_search_extrapolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);probe,recording=self.fixture(root)
            with self.assertRaisesRegex(ValueError,'sub-half-sample'):
                align_drive(probe,recording,root/'precision',audio_pick_error_s=0)
            with self.assertRaisesRegex(ValueError,'three sample positions'):
                align_drive(probe,recording,root/'narrow',max_delay_s=.0001)
            with self.assertRaisesRegex(ValueError,'declared delay search leaves'):
                align_drive(probe,recording,root/'outside',min_delay_s=-1,max_delay_s=1)
            with self.assertRaisesRegex(ValueError,'Declared map error'):
                align_drive(probe,recording,root/'bound',declared_error_s=.00001,max_delay_s=.1)

    def test_wav_metadata_and_payload_must_match_the_requested_timing_basis(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);probe,recording=self.fixture(root)
            original=recording.read_bytes()
            bad_rate=bytearray(original);bad_rate[24:28]=(16000).to_bytes(4,'little')
            recording.write_bytes(bad_rate)
            with self.assertRaisesRegex(ValueError,'command sample rate'):
                align_drive(probe,recording,root/'rate')
            recording.write_bytes(original[:-16])
            with self.assertRaisesRegex(ValueError,'truncated'):
                align_drive(probe,recording,root/'truncated')


if __name__=='__main__':
    unittest.main()
