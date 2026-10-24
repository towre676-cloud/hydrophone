"""Known-signal checks for the stdlib PCM response analysis, not hardware trials."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import struct
import tempfile
import unittest
import wave


SOURCE = Path(__file__).resolve().parents[1] / "instrument" / "analyze.py"
SPEC = importlib.util.spec_from_file_location("analyze_under_test", SOURCE)
ANALYZE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZE)


def write_pcm(path, rows, *, rate=4096, width=2):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(len(rows[0]))
        f.setsampwidth(width)
        f.setframerate(rate)
        if width == 2:
            f.writeframes(b"".join(struct.pack("<" + "h" * len(row), *row) for row in rows))
        else:
            f.writeframes(bytes([128] * (len(rows) * len(rows[0]))))


class ToneAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make_multitone(self, *, zero_drive=False, zero_reference=False, clip_channel=None):
        rate, n = 4096, 5003
        frequencies = [123.4, 337.7, 810.2]
        drive = [complex(.12, .04), complex(-.08, .10), complex(.06, -.03)]
        response_gains = [1.25*complex(math.cos(.4), math.sin(.4)),
                          .62*complex(math.cos(-.75), math.sin(-.75)),
                          1.10*complex(math.cos(1.10), math.sin(1.10))]
        reference_gains = [.75*complex(math.cos(-.2), math.sin(-.2)),
                           .90*complex(math.cos(.30), math.sin(.30)),
                           1.2*complex(math.cos(-.4), math.sin(-.4))]
        dc = [.02, -.03, .01]
        slopes = [.008, -.006, .004]
        rows = []
        for i in range(n):
            t = i/rate
            values = [dc[c] + slopes[c]*t for c in range(3)]
            for j, frequency in enumerate(frequencies):
                carrier = complex(math.cos(2*math.pi*frequency*t), math.sin(2*math.pi*frequency*t))
                for c, gain in enumerate((1, response_gains[j], reference_gains[j])):
                    values[c] += (drive[j]*gain*carrier).real
            if zero_drive:
                values[0] = 0.02 + .008*t  # no requested drive tones
            if zero_reference:
                values[2] = 0.0
            rows.append([round(v*32768) for v in values])
        if clip_channel is not None:
            rows[450][clip_channel] = 32767
        path = self.base / "multitone.wav"
        write_pcm(path, rows, rate=rate)
        return path, frequencies, response_gains, reference_gains, rows

    def test_joint_multitone_recovers_complex_gains_dc_trend_and_window_hash(self):
        path, freqs, expected, ref, rows = self.make_multitone()
        result = ANALYZE.analyze_tones(path, frequencies_Hz=freqs, reference_channel=2,
                                       start_s=.0713, end_s=1.16)
        self.assertEqual(result["fit"]["method"], "scaled_column_pivoted_Householder_QR")
        self.assertLess(result["fit"]["scaled_R_infinity_condition_number"], 20)
        for tone, gain, reference_gain in zip(result["tones"], expected, ref):
            got = tone["response_over_drive"]
            self.assertAlmostEqual(got["real"], gain.real, delta=2e-5)
            self.assertAlmostEqual(got["imag"], gain.imag, delta=2e-5)
            self.assertAlmostEqual(got["amplitude"], abs(gain), delta=2e-5)
            self.assertAlmostEqual(got["phase_rad"], math.atan2(gain.imag, gain.real), delta=2e-5)
            rg = tone["reference_over_drive"]
            self.assertAlmostEqual(rg["real"], reference_gain.real, delta=2e-5)
            self.assertAlmostEqual(rg["imag"], reference_gain.imag, delta=2e-5)
            rr = tone["response_over_reference"]
            self.assertAlmostEqual(rr["real"], (gain/reference_gain).real, delta=3e-5)
            self.assertAlmostEqual(rr["imag"], (gain/reference_gain).imag, delta=3e-5)
        origin = result["window"]["phase_origin_time_s"]
        for c, (dc, slope) in enumerate(zip([.02,-.03,.01],[.008,-.006,.004])):
            channel = result["channels"][str(c)]
            self.assertAlmostEqual(channel["dc_at_window_midpoint_full_scale"], dc+slope*origin, delta=2e-6)
            self.assertAlmostEqual(channel["linear_trend_full_scale_per_s"], slope, delta=3e-6)
            self.assertLess(channel["residual_rms_full_scale"], 1.1e-5)
        self.assertEqual(result["source_file_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        first, stop = result["window"]["start_frame_inclusive"], result["window"]["end_frame_exclusive"]
        selected_pcm = b"".join(struct.pack("<hhh", *row) for row in rows[first:stop])
        self.assertEqual(result["selected_pcm_sha256"], hashlib.sha256(selected_pcm).hexdigest())
        json.dumps(result, allow_nan=False)
        self.assertIn("uncalibrated", result["units"]["ratios"])

    def test_reject_zero_drive_and_zero_reference(self):
        path, freqs, *_ = self.make_multitone(zero_drive=True)
        with self.assertRaisesRegex(ANALYZE.AnalysisError, "Drive tone.*zero or unresolved"):
            ANALYZE.analyze_tones(path, frequencies_Hz=freqs)
        path, freqs, *_ = self.make_multitone(zero_reference=True)
        with self.assertRaisesRegex(ANALYZE.AnalysisError, "Reference tone.*zero or unresolved"):
            ANALYZE.analyze_tones(path, frequencies_Hz=freqs, reference_channel=2)

    def test_additive_noise_is_reported_as_residual_not_a_calibration_bound(self):
        path,freqs,gains,_,rows=self.make_multitone()
        rng=random.Random(20261024)
        noise_std=0.002
        noisy=[[value+round(32768*noise_std*rng.gauss(0,1)) for value in row] for row in rows]
        write_pcm(path,noisy)
        result=ANALYZE.analyze_tones(path,frequencies_Hz=freqs,reference_channel=2)
        for channel in result['channels'].values():
            self.assertGreater(channel['residual_rms_full_scale'],.0018)
            self.assertLess(channel['residual_rms_full_scale'],.0022)
        for tone,expected in zip(result['tones'],gains):
            ratio=tone['response_over_drive']
            self.assertAlmostEqual(ratio['real'],expected.real,delta=.003)
            self.assertAlmostEqual(ratio['imag'],expected.imag,delta=.003)
        self.assertTrue(any('not certified' in x for x in result['assumptions']))

    def test_zero_response_is_finite_zero_gain(self):
        n=2048; rate=4096
        path=self.base/"zero_response.wav"
        write_pcm(path, [[round(7000*math.cos(2*math.pi*200*i/rate)),0] for i in range(n)])
        r=ANALYZE.analyze_tones(path,frequencies_Hz=[200])
        self.assertEqual(r["tones"][0]["response_over_drive"]["amplitude"],0.)
        self.assertIsNone(r["tones"][0]["response_over_drive"]["phase_rad"])
        json.dumps(r,allow_nan=False)

    def test_clipping_rejected_on_every_used_channel_but_unused_allowed(self):
        for channel in range(3):
            path,freqs,*_=self.make_multitone(clip_channel=channel)
            with self.assertRaisesRegex(ANALYZE.AnalysisError,"Clipping"):
                ANALYZE.analyze_tones(path,frequencies_Hz=freqs,reference_channel=2)
        path,freqs,*_=self.make_multitone(clip_channel=2)
        ANALYZE.analyze_tones(path,frequencies_Hz=freqs)
        # Negative rail is equally invalid.
        raw=bytearray(path.read_bytes());raw[44:46]=struct.pack('<h',-32768);path.write_bytes(raw)
        with self.assertRaisesRegex(ANALYZE.AnalysisError,"Clipping"):
            ANALYZE.analyze_tones(path,frequencies_Hz=freqs)

    def test_invalid_frequencies_channels_and_windows(self):
        path,freqs,*_=self.make_multitone()
        for invalid in [[],[0],[-1],[2048],[3000],[float('nan')],[float('inf')],[123,123],[True]]:
            with self.subTest(frequencies=invalid),self.assertRaises(ANALYZE.AnalysisError):
                ANALYZE.analyze_tones(path,frequencies_Hz=invalid)
        for kw in [{'drive_channel':3},{'response_channel':-1},{'reference_channel':4},
                   {'reference_channel':0},{'drive_channel':1},{'drive_channel':True},
                   {'start_s':-.1},{'end_s':2},{'start_s':.5,'end_s':.2},
                   {'start_s':float('nan')},{'end_s':float('inf')}]:
            with self.subTest(kw=kw),self.assertRaises(ANALYZE.AnalysisError):
                ANALYZE.analyze_tones(path,frequencies_Hz=freqs,**kw)

    def test_short_and_ill_conditioned_bases(self):
        path,freqs,*_=self.make_multitone()
        with self.assertRaisesRegex(ANALYZE.AnalysisError,"too short"):
            ANALYZE.analyze_tones(path,frequencies_Hz=freqs,end_s=.002)
        for invalid in [[123.4,123.4+1e-9],[1e-10]]:
            with self.subTest(frequencies=invalid),self.assertRaisesRegex(ANALYZE.AnalysisError,"rank deficient|ill-conditioned|zero or invalid"):
                ANALYZE.analyze_tones(path,frequencies_Hz=invalid)

    def test_invalid_pcm_empty_and_truncated_files(self):
        path=self.base/'8bit.wav'
        write_pcm(path,[[0,0] for _ in range(100)],width=1)
        with self.assertRaisesRegex(ANALYZE.AnalysisError,'PCM16'):
            ANALYZE.analyze_tones(path,frequencies_Hz=[100])
        path=self.base/'empty.wav'
        with wave.open(str(path),'wb') as f:
            f.setnchannels(2);f.setsampwidth(2);f.setframerate(4096);f.writeframes(b'')
        with self.assertRaises(ANALYZE.AnalysisError):
            ANALYZE.analyze_tones(path,frequencies_Hz=[100])
        path,freqs,*_=self.make_multitone()
        path.write_bytes(path.read_bytes()[:-20])
        with self.assertRaisesRegex(ANALYZE.AnalysisError,'truncated'):
            ANALYZE.analyze_tones(path,frequencies_Hz=freqs)


if __name__=='__main__':
    unittest.main()
