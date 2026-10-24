"""Sampled orchestral rendering with per-note expression and microtonal pitch.

FluidSynth and an independently licensed GM SoundFont supply recorded instrument
samples. This renderer never claims a recording of a live orchestra or a learned
performance model. A separate channel for each sounding note preserves cents,
vibrato and phrase envelopes even inside a chord.
"""
from __future__ import annotations

import ctypes as C
import ctypes.util
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import wave

import numpy as np


PROGRAMS = {
    "violin": 40, "viola": 41, "cello": 42, "bass": 43,
    "contrabass": 43, "strings": 48, "flute": 73, "oboe": 68,
    "clarinet": 71, "bassoon": 70, "horn": 60, "french-horn": 60,
    "trumpet": 56, "trombone": 57, "tuba": 58, "harp": 46,
    "timpani": 47, "piano": 0, "celesta": 8, "glockenspiel": 9,
}
ALIASES = {"violins": "violin", "violins_1": "violin", "violins_2": "violin",
           "violin2": "violin",
           "first_violins": "violin", "second_violins": "violin", "violas": "viola",
           "cellos": "cello", "basses": "bass", "double_bass": "bass",
           "french_horn": "horn", "french_horns": "horn"}
LAYER_OFFSETS = {"violin": (-2.0, 2.0), "viola": (-1.8, 1.8),
                 "cello": (-1.5, 1.5), "strings": (-3.0, 0.0, 3.0)}
MIDI_CHANNELS = 64
DEFAULT_PAN = {"violin": -.50, "viola": -.16, "cello": .24, "bass": .44,
               "strings": -.12, "flute": -.18, "oboe": .08, "clarinet": -.05,
               "bassoon": .23, "horn": -.36, "trumpet": .25,
               "trombone": .35, "harp": -.68, "timpani": .52}
ROOT = Path(__file__).resolve().parents[1]


def _finite(value, name):
    if isinstance(value, bool):
        raise ValueError(name + " must be a finite number")
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(name + " must be a finite number") from exc
    if not math.isfinite(value):
        raise ValueError(name + " must be a finite number")
    return value


def validate_score(score):
    if not isinstance(score, dict) or score.get("schema") != "symphony.score/1":
        raise ValueError("Expected symphony.score/1")
    events = score.get("events")
    if not isinstance(events, list) or not events or len(events) > 100_000:
        raise ValueError("A score needs between one and 100000 sounding events")
    normalized = []
    for i, event in enumerate(events):
        start = _finite(event["start_s"], "start_s")
        duration = _finite(event["duration_s"], "duration_s")
        pitch = _finite(event["midi_pitch"], "midi_pitch")
        velocity = _finite(event.get("velocity", 80), "velocity")
        cents = _finite(event.get("cents", 0), "cents")
        instrument = ALIASES.get(event.get("instrument"), event.get("instrument"))
        pan = _finite(event.get("pan", DEFAULT_PAN.get(instrument, 0)), "pan")
        if start < 0 or duration <= 0 or start + duration > 900:
            raise ValueError("Notes must occupy a positive window within 900 seconds")
        if not 0 <= pitch <= 127 or not 1 <= velocity <= 127 or abs(cents) > 200:
            raise ValueError("Pitch, cents or MIDI velocity is outside the rendering domain")
        if not -1 <= pan <= 1 or instrument not in PROGRAMS:
            raise ValueError("Unknown orchestral instrument or invalid pan")
        envelope = event.get("expression", [{"time": 0, "value": .85},
                                             {"time": .35, "value": 1},
                                             {"time": 1, "value": .82}])
        if not isinstance(envelope, list) or len(envelope) < 2:
            raise ValueError("Expression needs at least two normalized-time control points")
        times, values = [], []
        for point in envelope:
            t, value = _finite(point["time"], "expression time"), _finite(point["value"], "expression value")
            if not 0 <= t <= 1 or not 0 <= value <= 1.5:
                raise ValueError("Expression point lies outside its declared domain")
            times.append(t); values.append(value)
        if times[0] != 0 or times[-1] != 1 or any(a >= b for a, b in zip(times, times[1:])):
            raise ValueError("Expression times must increase from zero to one")
        vibrato = _finite(event.get("vibrato_hz", 5.2 if instrument in LAYER_OFFSETS else 4.8), "vibrato_hz")
        depth = _finite(event.get("vibrato_depth_cents", 3 if instrument in LAYER_OFFSETS else 1.4), "vibrato_depth_cents")
        delay = _finite(event.get("vibrato_delay_s", .18), "vibrato_delay_s")
        phase = _finite(event.get("vibrato_phase_rad", i * 2.399963229728653), "vibrato_phase_rad")
        if not 0 <= vibrato <= 12 or not 0 <= depth <= 50 or not 0 <= delay <= 10:
            raise ValueError("Vibrato parameters are outside the rendering domain")
        note = int(round(pitch))
        normalized.append({**event, "start_s": start, "duration_s": duration,
                           "midi_pitch": note, "cents": cents + 100 * (pitch - note),
                           "velocity": int(round(velocity)), "instrument": instrument,
                           "pan": pan, "expression_times": times, "expression_values": values,
                           "vibrato_hz": vibrato, "vibrato_depth_cents": depth,
                           "vibrato_delay_s": delay, "vibrato_phase_rad": phase})
    return normalized


def find_soundfont(soundfont=None):
    candidates = []
    if soundfont is not None:
        candidates.append(Path(soundfont))
    if os.environ.get("HYDROPHONE_SOUNDFONT"):
        candidates.append(Path(os.environ["HYDROPHONE_SOUNDFONT"]))
    candidates += [ROOT / "assets/symphony/GeneralUser-GS.sf2",
                   Path("/usr/share/sounds/sf2/FluidR3_GM.sf2"),
                   Path("/usr/share/sounds/sf2/TimGM6mb.sf2")]
    for candidate in candidates:
        if candidate.is_file():
            with candidate.open("rb") as stream:
                magic = stream.read(12)
            if magic[:4] != b"RIFF" or magic[8:12] != b"sfbk":
                raise ValueError("SoundFont file is not a RIFF sfbk bank")
            return candidate.resolve()
    raise FileNotFoundError("Install the documented GM SoundFont in assets/symphony, or pass soundfont=")


class FluidSynth:
    """Small checked ctypes binding; no audio device is opened."""

    def __init__(self, soundfont, sample_rate):
        library = os.environ.get("HYDROPHONE_FLUIDSYNTH_LIB") or ctypes.util.find_library("fluidsynth")
        if not library:
            native = ROOT / "assets/symphony/native/runtime/usr/lib/x86_64-linux-gnu"
            candidate = native / "libfluidsynth.so.3"
            if candidate.is_file():
                for dependency in ("libinstpatch-1.0.so.2", "libpipewire-0.3.so.0"):
                    path = native / dependency
                    if path.is_file():
                        C.CDLL(str(path), mode=C.RTLD_GLOBAL)
                library = str(candidate)
        if not library:
            raise RuntimeError("FluidSynth native library is required for sampled orchestral rendering")
        self.lib = C.CDLL(library)
        self.settings = self.synth = None
        self._bind("new_fluid_settings", C.c_void_p, [])
        self._bind("delete_fluid_settings", None, [C.c_void_p])
        self._bind("fluid_settings_setnum", C.c_int, [C.c_void_p, C.c_char_p, C.c_double])
        self._bind("fluid_settings_setint", C.c_int, [C.c_void_p, C.c_char_p, C.c_int])
        self._bind("new_fluid_synth", C.c_void_p, [C.c_void_p])
        self._bind("delete_fluid_synth", None, [C.c_void_p])
        self._bind("fluid_synth_sfload", C.c_int, [C.c_void_p, C.c_char_p, C.c_int])
        self._bind("fluid_synth_program_select", C.c_int, [C.c_void_p, C.c_int, C.c_uint, C.c_uint, C.c_uint])
        self._bind("fluid_synth_cc", C.c_int, [C.c_void_p, C.c_int, C.c_int, C.c_int])
        self._bind("fluid_synth_pitch_bend", C.c_int, [C.c_void_p, C.c_int, C.c_int])
        self._bind("fluid_synth_pitch_wheel_sens", C.c_int, [C.c_void_p, C.c_int, C.c_int])
        self._bind("fluid_synth_noteon", C.c_int, [C.c_void_p, C.c_int, C.c_int, C.c_int])
        self._bind("fluid_synth_noteoff", C.c_int, [C.c_void_p, C.c_int, C.c_int])
        self._bind("fluid_synth_all_sounds_off", C.c_int, [C.c_void_p, C.c_int])
        self._bind("fluid_synth_count_midi_channels", C.c_int, [C.c_void_p])
        self._bind("fluid_synth_write_float", C.c_int,
                   [C.c_void_p, C.c_int, C.c_void_p, C.c_int, C.c_int, C.c_void_p, C.c_int, C.c_int])
        self.settings = self.lib.new_fluid_settings()
        if not self.settings:
            raise RuntimeError("FluidSynth settings allocation failed")
        for name, value in ((b"synth.sample-rate", sample_rate), (b"synth.gain", .42),
                            (b"synth.reverb.room-size", .72), (b"synth.reverb.damp", .38),
                            (b"synth.reverb.width", 75), (b"synth.reverb.level", .28),
                            (b"synth.chorus.level", .15), (b"synth.chorus.depth", 6),
                            (b"synth.chorus.speed", .24)):
            self.lib.fluid_settings_setnum(self.settings, name, float(value))
        # Keep the qualified channel envelope explicit. The pinned native
        # build was unstable at 256 channels during a full composition build;
        # this 64-channel configuration passes that end-to-end replay.
        for name, value in ((b"synth.midi-channels", MIDI_CHANNELS), (b"synth.polyphony", 512),
                            (b"synth.cpu-cores", 1), (b"synth.threadsafe-api", 0),
                            (b"synth.chorus.active", 1), (b"synth.reverb.active", 1)):
            self.lib.fluid_settings_setint(self.settings, name, value)
        self.synth = self.lib.new_fluid_synth(self.settings)
        if not self.synth:
            self.close(); raise RuntimeError("FluidSynth renderer allocation failed")
        if self.lib.fluid_synth_count_midi_channels(self.synth) != MIDI_CHANNELS:
            self.close(); raise RuntimeError("FluidSynth did not honor the qualified channel count")
        self.sfid = self.lib.fluid_synth_sfload(self.synth, os.fsencode(soundfont), 0)
        if self.sfid < 0:
            self.close(); raise ValueError("SoundFont could not be loaded")

    def _bind(self, name, result, arguments):
        fn = getattr(self.lib, name); fn.restype = result; fn.argtypes = arguments

    def cc(self, channel, number, value):
        self.lib.fluid_synth_cc(self.synth, channel, number, int(np.clip(value, 0, 127)))

    def bend(self, channel, cents):
        # Explicit four-semitone range leaves room for the complete supported
        # cents offset plus fractional MIDI pitch, vibrato and section spread.
        value = int(round(8192 + 8192 * cents / 400))
        self.lib.fluid_synth_pitch_bend(self.synth, channel, max(0, min(16383, value)))

    def start(self, channel, event, detune):
        self.lib.fluid_synth_all_sounds_off(self.synth, channel)
        program = PROGRAMS[event["instrument"]]
        if event.get("articulation") == "pizzicato" and event["instrument"] in {"violin", "viola", "cello", "bass", "contrabass", "strings"}:
            program = 45  # GM pizzicato strings: use recorded plucked attacks.
        if self.lib.fluid_synth_program_select(self.synth, channel, self.sfid, 0, program) < 0:
            raise ValueError("SoundFont has no requested orchestral preset")
        # Set bend range explicitly so arbitrary user-selected banks do not
        # inherit stateful RPN settings from an earlier note.
        self.lib.fluid_synth_pitch_wheel_sens(self.synth, channel, 4)
        self.cc(channel, 7, 100)
        self.cc(channel, 10, round(63.5 * (event["pan"] + 1)))
        self.cc(channel, 91, 48)
        self.cc(channel, 93, 10 if event["instrument"] in LAYER_OFFSETS else 0)
        self.cc(channel, 11, event["expression_values"][0] * 100)
        self.bend(channel, event["cents"] + detune)
        self.lib.fluid_synth_noteon(self.synth, channel, event["midi_pitch"], event["velocity"])

    def block(self, frames):
        left, right = np.empty(frames, dtype=np.float32), np.empty(frames, dtype=np.float32)
        result = self.lib.fluid_synth_write_float(self.synth, frames, left.ctypes.data, 0, 1,
                                                 right.ctypes.data, 0, 1)
        if result < 0:
            raise RuntimeError("FluidSynth audio block failed")
        return np.column_stack((left, right))

    def close(self):
        if self.synth:
            self.lib.delete_fluid_synth(self.synth); self.synth = None
        if self.settings:
            self.lib.delete_fluid_settings(self.settings); self.settings = None


def _render_pcm(events, sample_rate, soundfont, tail_s=3.0):
    duration = max(e["start_s"] + e["duration_s"] for e in events)
    total_frames = int(math.ceil((duration + tail_s) * sample_rate))
    output = np.zeros((total_frames, 2), dtype=np.float32)
    scheduled = sorted(enumerate(events), key=lambda x: (x[1]["start_s"], x[0]))
    channels = list(range(MIDI_CHANNELS)); channels.remove(9)
    active = []
    releasing = []
    cursor = 0
    peak_notes = 0
    synth = FluidSynth(soundfont, sample_rate)
    block_frames = max(32, int(sample_rate * .010))
    try:
        for position in range(0, total_frames, block_frames):
            now = position / sample_rate
            remaining = []
            for voice in active:
                event, channel, detune = voice
                age = now - event["start_s"]
                if age >= event["duration_s"]:
                    synth.lib.fluid_synth_noteoff(synth.synth, channel, event["midi_pitch"])
                    releasing.append((now + .65, channel))
                else:
                    progress = age / event["duration_s"]
                    expression = np.interp(progress, event["expression_times"], event["expression_values"])
                    # Smaller gain per section player prevents doubling from
                    # doubling section loudness. Voice independence supplies
                    # width; expression remains coherent across the section.
                    layers = len(LAYER_OFFSETS.get(event["instrument"], (0,)))
                    synth.cc(channel, 11, 100 * expression / math.sqrt(layers))
                    ramp = max(0., min(1., (age - event["vibrato_delay_s"]) / .3))
                    vibrato = ramp * event["vibrato_depth_cents"] * math.sin(
                        2 * math.pi * event["vibrato_hz"] * age + event["vibrato_phase_rad"] + detune * .35)
                    synth.bend(channel, event["cents"] + detune + vibrato)
                    remaining.append(voice)
            active = remaining
            retained = []
            for end, channel in releasing:
                if end <= now:
                    channels.append(channel)
                else:
                    retained.append((end, channel))
            releasing = retained
            while cursor < len(scheduled) and scheduled[cursor][1]["start_s"] <= now:
                _, event = scheduled[cursor]; cursor += 1
                for detune in LAYER_OFFSETS.get(event["instrument"], (0.,)):
                    if not channels:
                        raise ValueError("Score exceeds 63 independent render channels, including release tails")
                    channel = channels.pop()
                    synth.start(channel, event, detune)
                    active.append((event, channel, detune))
                peak_notes = max(peak_notes, len(active))
            count = min(block_frames, total_frames - position)
            output[position:position + count] = synth.block(count)
    finally:
        synth.close()
    return output, {"score_duration_s": duration, "release_tail_s": tail_s,
                    "peak_layered_voices": peak_notes, "control_period_s": block_frames / sample_rate}


def render_score(score, outpath, sample_rate=32000, soundfont=None):
    """Render event score into a stereo PCM16 WAV, opening no audio device."""
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or not 8000 <= sample_rate <= 96000:
        raise ValueError("Sample rate must be an integer from 8000 through 96000")
    events = validate_score(score)
    bank = find_soundfont(soundfont)
    pcm, performance = _render_pcm(events, sample_rate, bank)
    if not np.isfinite(pcm).all():
        raise ArithmeticError("Nonfinite synthesized audio")
    # Remove constant offsets and preserve the score's dynamic contour. One
    # global scale avoids pumping/flattening the phrase-to-phrase dynamics.
    pcm -= np.mean(pcm, axis=0, keepdims=True)
    peak = float(np.max(np.abs(pcm)))
    if peak <= 1e-8:
        raise ValueError("Rendered score is silent")
    gain = .89 / peak
    pcm *= gain
    fade = min(int(.08 * sample_rate), len(pcm) // 4)
    pcm[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)[:, None]
    quantized = np.rint(np.clip(pcm, -1, 1) * 32767).astype("<i2")
    target = Path(outpath)
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as stream:
        stream.setnchannels(2); stream.setsampwidth(2); stream.setframerate(sample_rate)
        stream.writeframes(quantized.tobytes())
    rms = float(np.sqrt(np.mean(np.square(pcm, dtype=np.float64))))
    return {"schema": "symphony.render/1", "backend": "sampled_instruments_fluidsynth",
            "source_score_sha256": hashlib.sha256(json.dumps(score, sort_keys=True, separators=(",", ":"),
                                                             allow_nan=False).encode()).hexdigest(),
            "output_wav": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "soundfont_path": str(bank), "soundfont_sha256": hashlib.sha256(bank.read_bytes()).hexdigest(),
            "sample_rate_Hz": sample_rate, "channels": 2, "sample_frames": len(pcm),
            "duration_s": len(pcm) / sample_rate, "event_count": len(events),
            "instruments": sorted({e["instrument"] for e in events}),
            "peak_full_scale": float(np.max(np.abs(pcm))), "rms_full_scale": rms,
            "global_normalization_gain": gain, "clipped_sample_count": int(np.sum(np.abs(pcm) >= 1)),
            "expression_control": "per-note envelope, delayed vibrato, independent cents and layered section players",
            "logical_midi_channels": MIDI_CHANNELS,
            "rendered_from_recorded_instrument_samples": True,
            "live_orchestra_recording": False, "physical_instrument_recorded": False,
            "hardware_commands_issued": 0, **performance}


def encode_mp3(wav_path, mp3_path, bitrate="192k"):
    """Optional portable listening copy; requires ffmpeg on PATH."""
    target = Path(mp3_path); target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(wav_path),
                    "-codec:a", "libmp3lame", "-b:a", bitrate, str(target)], check=True)
    return {"path": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "bytes": target.stat().st_size}
