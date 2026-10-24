"""Opt-in duplex PCM capture. Dry-run never imports or opens sounddevice.

Hardware operation is unverified until an operator commissions the device and
fixture. Dropout flags cannot reveal the number of lost samples; a flagged
capture is preserved for diagnosis and cannot be sealed as a clean run.
"""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import threading
import time
import wave
from .probe import load_probe, sha256


class DuplexCollector:
    """Bounded memory callback core; independently exercisable without hardware."""
    def __init__(self, command, frames, input_channels):
        self.command = memoryview(command)
        self.target = frames
        self.inputs = input_channels
        self.recorded = bytearray(frames * input_channels * 2)
        self.position = 0
        self.flags = []
        self.callback_count = 0
        self.clock_first = None
        self.clock_last = None
        self.error = None

    def process(self, indata, outdata, frames, clock, status):
        """Fill every output byte, then copy the in-range input sample prefix."""
        outdata[:] = b'\0' * len(outdata)
        if (not isinstance(frames, int) or frames <= 0 or
            len(indata) != frames * self.inputs * 2 or len(outdata) != frames * 4):
            raise ValueError('Duplex callback buffer dimensions changed')
        keep = min(frames, self.target - self.position)
        if status:
            self.flags.append({'frame': self.position, 'status': str(status)})
        if self.callback_count >= 100000:
            raise ValueError('Callback budget exceeded')
        times = {name: float(getattr(clock, name)) for name in
                 ('inputBufferAdcTime', 'outputBufferDacTime', 'currentTime')}
        if not all(math.isfinite(t) for t in times.values()):
            raise ValueError('Nonfinite host callback timestamps')
        times['frame'] = self.position
        self.clock_first = self.clock_first or times
        self.clock_last = times
        offset = self.position * self.inputs * 2
        self.recorded[offset:offset + keep * self.inputs * 2] = memoryview(indata)[:keep * self.inputs * 2]
        outdata[:keep * 4] = self.command[self.position * 4:(self.position + keep) * 4]
        self.position += keep
        self.callback_count += 1
        return self.position >= self.target


def capture_probe(probe_path, output_dir, *, execute=False, device=None,
                  commissioning_id=None):
    plan, command, command_path = load_probe(probe_path)
    root = Path(output_dir)
    if root.exists():
        raise ValueError('Capture directory must be new')
    preflight = {'schema': 'hydrophone.capture-preflight/1', 'mode': 'DRY_RUN',
        'input_channels': plan['input_channel_map'], 'output_channels': 2,
        'sample_rate_Hz': plan['sample_rate_Hz'], 'duration_s': plan['frames']/plan['sample_rate_Hz'],
        'command_sha256': sha256(command_path), 'device': device,
        'hardware_commands_issued': 0, 'physical_readiness_verified': False}
    if not execute:
        return preflight
    if isinstance(device, bool) or not isinstance(device, int) or device < 0:
        raise ValueError('Execution requires one explicit duplex PortAudio device index')
    if not isinstance(commissioning_id, str) or not commissioning_id.strip():
        raise ValueError('Execution requires an operator commissioning record ID')
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise ValueError('Install optional hardware/requirements-capture.txt for device operation') from exc
    info = sd.query_devices(device)
    n = len(plan['input_channel_map'])
    if info['max_input_channels'] < n or info['max_output_channels'] < 2:
        raise ValueError('Selected duplex device lacks the declared channel count')
    sd.check_input_settings(device=device, channels=n, dtype='int16', samplerate=plan['sample_rate_Hz'])
    sd.check_output_settings(device=device, channels=2, dtype='int16', samplerate=plan['sample_rate_Hz'])
    collector = DuplexCollector(command, plan['frames'], n)
    finished = threading.Event()
    started = datetime.now(timezone.utc).isoformat()
    root.mkdir(parents=True)
    (root/'drive_command.wav').write_bytes(command_path.read_bytes())
    (root/'probe.json').write_bytes(Path(probe_path).read_bytes())

    def callback(indata, outdata, frames, clock, status):
        try:
            done = collector.process(indata, outdata, frames, clock, status)
        except Exception as exc:
            outdata[:] = b'\0' * len(outdata)
            collector.error = str(exc)
            raise sd.CallbackAbort
        if done:
            raise sd.CallbackStop

    failure = None
    try:
        with sd.RawStream(device=device, channels=(n, 2), samplerate=plan['sample_rate_Hz'],
                dtype='int16', blocksize=0, latency='high', never_drop_input=True,
                callback=callback, finished_callback=finished.set) as stream:
            deadline = time.monotonic() + plan['frames']/plan['sample_rate_Hz'] + 15
            while not finished.wait(.25):
                if time.monotonic() > deadline:
                    raise TimeoutError('Audio stream did not finish before its time budget')
    except (Exception, KeyboardInterrupt) as exc:
        failure = type(exc).__name__ + ': ' + str(exc)
    wav = root/'multichannel_audio.wav'
    with wave.open(str(wav), 'wb') as stream:
        stream.setparams((n, 2, plan['sample_rate_Hz'], collector.position, 'NONE', 'not compressed'))
        stream.writeframes(memoryview(collector.recorded)[:collector.position*n*2])
    complete = (collector.position == plan['frames'] and not collector.flags
                and not collector.error and failure is None)
    receipt = {'schema': 'hydrophone.capture/1',
        'status': 'COMPLETE_NO_HOST_FLAGS' if complete else 'REVIEW_REQUIRED',
        'capture_method': 'sounddevice.RawStream', 'sounddevice_version': sd.__version__,
        'operator_commissioning_id': commissioning_id, 'started_utc': started,
        'device_index': device, 'device_info': dict(info),
        'sample_rate_Hz': plan['sample_rate_Hz'], 'channel_map': plan['input_channel_map'],
        'frames_received': collector.position, 'frames_requested': plan['frames'],
        'callback_count': collector.callback_count, 'host_flags': collector.flags,
        'callback_error': collector.error, 'stream_error': failure,
        'missing_samples': 0 if complete else None,
        'host_clock_first': collector.clock_first, 'host_clock_last': collector.clock_last,
        'probe_sha256': sha256(root/'probe.json'),
        'raw_files': {name: {'path': file, 'sha256': sha256(root/file)} for name, file in
            [('multichannel_audio', wav.name), ('drive_command', 'drive_command.wav')]},
        'hardware_commands_issued': 1, 'physical_readiness_verified': False,
        'qualifications': ['Host flags absent does not independently prove sample continuity.',
            'Host ADC/DAC timestamps are diagnostics, not measured loopback calibration.',
            'Record external logger/audio sync markers and import the slow record before sealing.',
            'No force, displacement, temperature or emergency-stop interlock runs in Python.',
            'No mechanical write or automatic string tuning command is issued.']}
    (root/'capture.json').write_text(json.dumps(receipt, indent=2, allow_nan=False)+'\n')
    return receipt
