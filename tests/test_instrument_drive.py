"""Physical-command file checks, independent of the renderer's sample loop."""
from array import array
import copy
import hashlib
import math
from pathlib import Path
import sys
import tempfile
import unittest
import wave

from instrument.drive import render_score


def score_of(events):
    return {"schema":"fusion.score/1", "engine_id":"test-spelled-engine",
            "data_origin":"software_generated_score", "seed":41,
            "events":events}


def event(frequency=440, start=0.02, duration=0.1, amplitude=0.5):
    return {"event_id":"one", "target_Hz":frequency, "start_s":start,
            "duration_s":duration, "source_amplitude":amplitude,
            "spelling":"Gb", "pitch_class":6, "source_pan":-0.6,
            "local_memory":[0,-1], "offset_cents":2.5}


def read_pcm(path):
    with wave.open(str(path), "rb") as audio:
        info=(audio.getnchannels(), audio.getsampwidth(), audio.getframerate(),audio.getnframes())
        values=array('h',audio.readframes(audio.getnframes()))
    if sys.byteorder!='little':
        values.byteswap()
    return info, list(values)


class InstrumentDriveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_known_tone_timing_frequency_level_and_provenance(self):
        source=score_of([event()])
        original=copy.deepcopy(source)
        path=self.root/'tone.wav'
        receipt=render_score(source,path,sample_rate=8000,peak=0.25)
        info,pcm=read_pcm(path)
        self.assertEqual(info,(1,2,8000,960))
        self.assertTrue(all(x==0 for x in pcm[:160]))
        interior=pcm[240:800]
        crossings=[i for i in range(1,len(interior)) if interior[i-1]<=0<interior[i]]
        estimated=8000*(len(crossings)-1)/(crossings[-1]-crossings[0])
        self.assertAlmostEqual(estimated,440,delta=1.1)
        self.assertAlmostEqual(max(map(abs,pcm))/32767,0.25,delta=1/32767)
        rms=math.sqrt(sum(x*x for x in interior)/len(interior))/32767
        self.assertAlmostEqual(rms,0.25/math.sqrt(2),delta=0.004)
        self.assertEqual(receipt['events'],original['events'])
        self.assertEqual(receipt['source_score_metadata']['engine_id'],'test-spelled-engine')
        self.assertEqual(source,original)
        self.assertEqual(receipt['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(receipt['source_event_count'],1)
        self.assertEqual(receipt['clipping_count'],0)
        self.assertFalse(receipt['hardware_execution_enabled'])
        self.assertEqual(receipt['hardware_commands_issued'],0)

    def test_determinism_and_identical_overlap_superposition(self):
        tone=event(frequency=500,start=0,duration=0.1,amplitude=0.7)
        one=score_of([tone])
        a,b,c=(self.root/name for name in ['a.wav','b.wav','twice.wav'])
        r1=render_score(one,a,sample_rate=8000)
        r2=render_score(one,b,sample_rate=8000)
        r3=render_score(score_of([tone,dict(tone,event_id='two')]),c,sample_rate=8000)
        self.assertEqual(a.read_bytes(),b.read_bytes())
        self.assertEqual(a.read_bytes(),c.read_bytes())
        self.assertEqual(r1['sha256'],r2['sha256'])
        self.assertAlmostEqual(r3['normalization_gain'],r1['normalization_gain']/2)
        self.assertEqual(r3['source_event_count'],2)

    def test_two_frequencies_survive_shared_mono_mix_with_bounded_peak(self):
        source=score_of([event(500,0,.2,1),event(800,0,.2,.5)])
        path=self.root/'mix.wav'
        receipt=render_score(source,path,sample_rate=8000,peak=.2)
        _,pcm=read_pcm(path)
        region=pcm[200:1400]
        def amplitude(freq):
            real=sum(x*math.cos(math.tau*freq*i/8000) for i,x in enumerate(region))
            imag=sum(x*math.sin(math.tau*freq*i/8000) for i,x in enumerate(region))
            return 2*math.hypot(real,imag)/len(region)
        a,b,unwanted=map(amplitude,[500,800,1100])
        self.assertGreater(a,1000)
        self.assertAlmostEqual(a/b,2,delta=.002)
        self.assertLess(unwanted,1)
        self.assertLessEqual(max(map(abs,pcm))/32767,.2+.5/32767)
        self.assertEqual(receipt['channels'],1)
        self.assertFalse(receipt['source_pan_applied'])
        self.assertEqual(receipt['clipping_count'],0)

    def test_invalid_tones_and_limits_rejected_before_writing(self):
        cases=[{'target_Hz':0},{'target_Hz':-1},{'target_Hz':4000},
               {'target_Hz':math.nan},{'target_Hz':math.inf},
               {'start_s':-1},{'start_s':math.inf},{'start_s':True},
               {'duration_s':0},{'duration_s':-1},{'duration_s':math.nan},
               {'duration_s':121},{'source_amplitude':-1}]
        for i,change in enumerate(cases):
            with self.subTest(change=change):
                out=self.root/f'invalid-{i}.wav'
                with self.assertRaises(ValueError):
                    render_score(score_of([dict(event(),**change)]),out,sample_rate=8000)
                self.assertFalse(out.exists())
        for i,params in enumerate([{'peak':0},{'peak':1.1},{'peak':math.inf},
                                   {'sample_rate':0},{'sample_rate':True},{'sample_rate':8000.5},
                                   {'max_duration_s':0},{'max_duration_s':math.inf}]):
            with self.subTest(params=params):
                out=self.root/f'params-{i}.wav'
                with self.assertRaises(ValueError):
                    render_score(score_of([event()]),out,**params)
                self.assertFalse(out.exists())
        with self.assertRaises(ValueError):
            render_score(score_of([]),self.root/'empty.wav')

    def test_short_artifact_and_silent_relative_amplitude(self):
        short=self.root/'short.wav'
        receipt=render_score(score_of([event(500,0,.004,1)]),short,sample_rate=8000)
        info,pcm=read_pcm(short)
        self.assertEqual(info,(1,2,8000,32))
        self.assertEqual(short.stat().st_size,108)
        self.assertGreater(max(map(abs,pcm)),6000)
        self.assertEqual(pcm[0],0)
        self.assertEqual(receipt['events'][0]['spelling'],'Gb')
        silent=self.root/'silent.wav'
        quiet=render_score(score_of([event(500,0,.004,0)]),silent,sample_rate=8000)
        self.assertTrue(all(x==0 for x in read_pcm(silent)[1]))
        self.assertEqual(quiet['normalization_gain'],0)
        self.assertEqual(quiet['actual_peak_full_scale'],0)


if __name__=='__main__':
    unittest.main()
