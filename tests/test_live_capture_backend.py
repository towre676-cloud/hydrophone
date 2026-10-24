"""Exercise the complete live-capture code path with no audio driver or device.

The module injected under ``sounddevice`` is a deterministic software backend.
Passing these checks does not validate PortAudio, OS routing, driver timing,
electrical configuration, or the mechanical apparatus.
"""
from array import array
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
import wave

from instrument.capture import capture_probe
from instrument.probe import compile_probe, load_probe, sha256


class MockSoundDevice(ModuleType):
    __version__ = 'TEST_BACKEND_NO_DEVICE'

    class CallbackStop(Exception):
        pass

    class CallbackAbort(Exception):
        pass

    def __init__(self, input_pcm, *, mode='complete', input_channels=4):
        super().__init__('sounddevice')
        self.input_pcm = input_pcm
        self.mode = mode
        self.input_channels = input_channels
        self.calls = []
        self.outputs = []
        self.stream_kwargs = None
        self.stream = None

    def query_devices(self, device):
        self.calls.append(('query_devices', device))
        return {'name':'MOCK_DUPLEX_NOT_HARDWARE', 'max_input_channels':self.input_channels,
                'max_output_channels':2, 'hostapi':0, 'default_samplerate':8000.}

    def check_input_settings(self, **kwargs):
        self.calls.append(('check_input_settings', kwargs))

    def check_output_settings(self, **kwargs):
        self.calls.append(('check_output_settings', kwargs))

    def RawStream(self, **kwargs):
        self.calls.append(('RawStream', kwargs['device']))
        self.stream_kwargs = kwargs
        if self.mode == 'construct_failure':
            raise OSError('mock driver rejected stream construction')
        self.stream = MockStream(self, kwargs)
        return self.stream


class MockStream:
    def __init__(self, backend, kwargs):
        self.backend = backend
        self.kwargs = kwargs
        self.position = 0
        self.exited = False
        self.closed = False

    def close(self):
        if self.backend.mode == 'cleanup_failure':
            self.backend.calls.append(('close_failed',self.position))
            raise OSError('mock driver failed to close the stream')
        self.closed = True
        self.backend.calls.append(('close', self.position))

    def __enter__(self):
        self.backend.calls.append(('enter', 0))
        if self.backend.mode == 'timeout':
            return self
        callback = self.kwargs['callback']
        # Variable callback sizes deliberately overrun the final requested
        # sample count, exercising the final zero-filled output suffix.
        pattern = (257, 512, 63, 1024)
        index = 0
        while True:
            frames = pattern[index % len(pattern)]
            begin = self.position * self.kwargs['channels'][0] * 2
            end = begin + frames * self.kwargs['channels'][0] * 2
            data = memoryview(self.backend.input_pcm)[begin:end]
            if self.backend.mode == 'callback_abort' and index == 1:
                data = data[:-1]
            clock = SimpleNamespace(inputBufferAdcTime=1+self.position/8000,
                outputBufferDacTime=1.03+self.position/8000,
                currentTime=1.01+self.position/8000)
            output = bytearray([255] * (frames * 4))
            status = 'MOCK input overflow; lost sample count unknown' if self.backend.mode == 'flagged' and index == 1 else ''
            try:
                callback(data, output, frames, clock, status)
            except (self.backend.CallbackStop, self.backend.CallbackAbort):
                self.backend.outputs.append(bytes(output))
                self.kwargs['finished_callback']()
                return self
            self.backend.outputs.append(bytes(output))
            self.position += frames
            if self.backend.mode == 'partial_failure' and index == 0:
                # __enter__ fails after one accepted callback, as a stream
                # start/device failure can happen before the with body.
                raise OSError('mock stream failed after one callback')
            index += 1

    def __exit__(self, kind, value, traceback):
        self.exited = True
        self.backend.calls.append(('exit', self.position))
        self.close()
        return False


class LiveCaptureBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory()
        cls.root = Path(cls.workspace.name)
        target = cls.root/'targets.json'
        target.write_text(json.dumps({'calibration_targets':[{'target_Hz':261.626}, {'target_Hz':391.1253463782126}]}))
        cls.probe_path = cls.root/'probe/probe.json'
        compile_probe(target, cls.probe_path.parent, sample_rate=8000, plateau_s=4)
        cls.plan, cls.command, _ = load_probe(cls.probe_path)
        values = array('h', (((frame + 97*channel) % 20000)-10000
            for frame in range(cls.plan['frames'] + 1024) for channel in range(4)))
        if sys.byteorder != 'little':
            values.byteswap()
        cls.input_pcm = values.tobytes()

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def run_capture(self, mode, **options):
        case = tempfile.TemporaryDirectory()
        self.addCleanup(case.cleanup)
        output = Path(case.name)/'capture'
        backend = MockSoundDevice(self.input_pcm, mode=mode)
        with patch.dict(sys.modules, {'sounddevice':backend}):
            receipt = capture_probe(self.probe_path, output, execute=True,
                device=9, commissioning_id='MOCK_COMMISSIONING_NOT_PHYSICAL', **options)
        saved = json.loads((output/'capture.json').read_text())
        self.assertEqual(saved, receipt)
        return output, receipt, backend

    def wav_payload(self, output):
        with wave.open(str(output/'multichannel_audio.wav'),'rb') as stream:
            metadata = (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes())
            return metadata, stream.readframes(stream.getnframes())

    def test_complete_backend_lifecycle_preserves_all_input_and_output_bytes(self):
        output, receipt, backend = self.run_capture('complete')
        self.assertEqual(receipt['status'],'COMPLETE_NO_HOST_FLAGS')
        self.assertEqual(receipt['frames_received'], self.plan['frames'])
        self.assertEqual(receipt['missing_samples'],0)
        self.assertTrue(backend.stream.exited)
        self.assertTrue(backend.stream.closed)
        self.assertEqual(backend.stream_kwargs['channels'],(4,2))
        self.assertEqual(backend.stream_kwargs['device'],9)
        self.assertTrue(backend.stream_kwargs['never_drop_input'])
        self.assertEqual(backend.stream_kwargs['dtype'],'int16')
        metadata, payload = self.wav_payload(output)
        self.assertEqual(metadata,(4,2,8000,self.plan['frames']))
        self.assertEqual(payload,self.input_pcm[:self.plan['frames']*8])
        played = b''.join(backend.outputs)
        self.assertEqual(played[:len(self.command)],self.command)
        self.assertTrue(len(played)>len(self.command))
        self.assertEqual(played[len(self.command):],bytes(len(played)-len(self.command)))
        for record in receipt['raw_files'].values():
            self.assertEqual(record['sha256'],sha256(output/record['path']))
        self.assertFalse(receipt['physical_readiness_verified'])
        self.assertEqual(receipt['sounddevice_version'],'TEST_BACKEND_NO_DEVICE')

    def test_host_flag_preserves_full_bytes_but_never_claims_known_lost_count(self):
        output, receipt, backend = self.run_capture('flagged')
        self.assertEqual(receipt['frames_received'],self.plan['frames'])
        self.assertEqual(receipt['status'],'REVIEW_REQUIRED')
        self.assertIsNone(receipt['missing_samples'])
        self.assertIn('unknown',receipt['host_flags'][0]['status'])
        self.assertEqual(self.wav_payload(output)[1],self.input_pcm[:self.plan['frames']*8])
        self.assertTrue(backend.stream.closed)

    def test_callback_abort_silences_the_failed_buffer_and_saves_received_prefix(self):
        output, receipt, backend = self.run_capture('callback_abort')
        self.assertEqual(receipt['status'],'REVIEW_REQUIRED')
        self.assertEqual(receipt['frames_received'],257)
        self.assertIn('dimensions changed',receipt['callback_error'])
        self.assertIsNone(receipt['missing_samples'])
        self.assertEqual(backend.outputs[-1],bytes(512*4))
        metadata, payload = self.wav_payload(output)
        self.assertEqual(metadata[-1],257)
        self.assertEqual(payload,self.input_pcm[:257*8])
        self.assertTrue(backend.stream.closed)

    def test_stream_construction_failure_does_not_claim_output_was_issued(self):
        output, receipt, backend = self.run_capture('construct_failure')
        self.assertEqual(receipt['status'],'REVIEW_REQUIRED')
        self.assertEqual(receipt['frames_received'],0)
        self.assertIn('stream construction',receipt['stream_error'])
        self.assertEqual(receipt['hardware_commands_issued'],0)
        self.assertIsNone(receipt['missing_samples'])
        self.assertEqual(self.wav_payload(output)[1],b'')
        self.assertIsNone(backend.stream)

    def test_partial_stream_start_failure_retains_prefix_and_closes_stream(self):
        output, receipt, backend = self.run_capture('partial_failure')
        self.assertEqual(receipt['status'],'REVIEW_REQUIRED')
        self.assertEqual(receipt['frames_received'],257)
        self.assertIn('after one callback',receipt['stream_error'])
        self.assertIsNone(receipt['missing_samples'])
        self.assertEqual(self.wav_payload(output)[1],self.input_pcm[:257*8])
        self.assertTrue(backend.stream.closed)

    def test_stream_that_never_callbacks_times_out_and_preserves_failure_receipt(self):
        # Only the collector's host deadline is advanced; no real sleep or
        # device clock is used by this software backend.
        times=iter([100.,200.])
        output, receipt, backend = self.run_capture('timeout',clock=lambda:next(times))
        self.assertEqual(receipt['status'],'REVIEW_REQUIRED')
        self.assertIn('TimeoutError',receipt['stream_error'])
        self.assertEqual(receipt['frames_received'],0)
        self.assertEqual(receipt['hardware_commands_issued'],0)
        self.assertTrue(backend.stream.closed)
        self.assertEqual(self.wav_payload(output)[1],b'')

    def test_cleanup_failure_prevents_a_clean_capture_even_after_all_frames(self):
        output, receipt, backend = self.run_capture('cleanup_failure')
        self.assertEqual(receipt['frames_received'],self.plan['frames'])
        self.assertEqual(receipt['status'],'REVIEW_REQUIRED')
        self.assertIn('failed to close',receipt['cleanup_error'])
        self.assertIsNone(receipt['missing_samples'])
        self.assertFalse(backend.stream.closed)
        self.assertEqual(self.wav_payload(output)[1],self.input_pcm[:self.plan['frames']*8])

    def test_wrong_device_capacity_fails_before_stream_open_or_output_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'capture'
            backend=MockSoundDevice(self.input_pcm,input_channels=2)
            with patch.dict(sys.modules, {'sounddevice':backend}):
                with self.assertRaisesRegex(ValueError,'lacks the declared channel count'):
                    capture_probe(self.probe_path,output,execute=True,device=9,
                        commissioning_id='MOCK_ONLY')
            self.assertEqual([c[0] for c in backend.calls],['query_devices'])
            self.assertFalse(output.exists())


if __name__=='__main__':
    unittest.main()
