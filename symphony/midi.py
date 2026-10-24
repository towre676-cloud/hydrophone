"""Portable Standard MIDI performance export, preserving performed note times.

The audio renderer can apply per-note microtuning. This MIDI deliberately uses
standard equal-tempered notes: section-wide bends cannot independently tune
simultaneous notes, and silently bending a whole section would be misleading.
"""
from __future__ import annotations

from collections import defaultdict
import math
from pathlib import Path
import struct


PPQ = 960
PROGRAMS = {"strings": 48, "violin": 40, "violin2": 40, "viola": 41, "cello": 42,
            "bass": 43, "contrabass": 43, "flute": 73, "oboe": 68,
            "clarinet": 71, "bassoon": 70, "horn": 60, "trumpet": 56,
            "trombone": 57, "tuba": 58, "timpani": 47, "harp": 46,
            "piano": 0, "celesta": 8, "glockenspiel": 9}


def _number(value, label):
    if isinstance(value, bool):
        raise ValueError(label + " must be finite")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(label + " must be finite")
    return result


def _vlq(number):
    number = int(number)
    if not 0 <= number <= 0x0fffffff:
        raise ValueError("MIDI delta exceeds the four-byte variable-length range")
    data = [number & 127]
    while number >> 7:
        number >>= 7
        data.insert(0, (number & 127) | 128)
    return bytes(data)


def _meta(kind, content):
    if isinstance(content, str):
        content = content.encode("utf-8")
    return bytes((255, kind)) + _vlq(len(content)) + content


def _track(events, end_tick):
    payload = bytearray()
    previous = 0
    for tick, order, content in sorted(events, key=lambda x: (x[0], x[1])):
        payload.extend(_vlq(tick - previous))
        payload.extend(content)
        previous = tick
    payload.extend(_vlq(max(0, end_tick - previous)))
    payload.extend(_meta(47, b""))
    return b"MTrk" + struct.pack(">I", len(payload)) + payload


def _tempos(score):
    source = score.get("performed_tempo_map") or score.get("tempo_map") or []
    changes = {}
    for entry in source:
        # Beat-only composition maps have already shaped start_s/duration_s;
        # only an explicitly timed map can govern an absolute-time export.
        if "time_s" not in entry:
            continue
        time = _number(entry["time_s"], "tempo time")
        bpm = _number(entry.get("bpm", entry.get("tempo_bpm", 120)), "tempo")
        if time < 0 or not 4 <= bpm <= 1000:
            raise ValueError("Invalid MIDI tempo map")
        changes[time] = bpm
    if 0.0 not in changes:
        bpm = _number(score.get("tempo_bpm", 120), "tempo")
        if not 4 <= bpm <= 1000:
            raise ValueError("Invalid MIDI tempo")
        changes[0.0] = bpm
    return sorted(changes.items())


def _expression_events(rows, channel, tick_at):
    """Render a section-level envelope when the score contains note envelopes.

    A MIDI channel shares expression across its notes, so use the maximum
    currently requested envelope. Independent per-note dynamics remain an
    audio-renderer capability, rather than an implied MIDI capability.
    """
    envelopes = []
    for event, start, duration, pitch, velocity in rows:
        source = event.get("expression_envelope", event.get("expression", []))
        if not source:
            envelopes.append((start, duration, [(0.0, 1.0), (1.0, 1.0)]))
            continue
        knots = sorted((_number(knot["time"], "envelope time"),
                        _number(knot["value"], "envelope value")) for knot in source)
        if any(not 0 <= time <= 1 or not 0 <= value <= 1 for time, value in knots):
            raise ValueError("Expression envelope requires normalized time/value in 0..1")
        envelopes.append((start, duration, knots))
    if not any(event.get("expression_envelope", event.get("expression")) for event, *_ in rows):
        return []
    end = max(start + duration for start, duration, _ in envelopes)
    times = {i / 8 for i in range(math.ceil(end * 8) + 1)}
    for start, duration, knots in envelopes:
        times.add(start)
        times.update(start + duration * time for time, value in knots)

    def value_at(knots, position):
        if position <= knots[0][0]:
            return knots[0][1]
        for (a, va), (b, vb) in zip(knots, knots[1:]):
            if position <= b:
                return vb if b == a else va + (vb - va) * (position - a) / (b - a)
        return knots[-1][1]

    events, previous = [], None
    for time in sorted(times):
        active = [value_at(knots, (time - start) / duration)
                  for start, duration, knots in envelopes if start <= time < start + duration]
        value = round(127 * max(active, default=1.0))
        if value != previous:
            events.append((tick_at(time), 0, bytes((0xb0 | channel, 11, value))))
            previous = value
    return events


def write_midi(score, output_path):
    """Write a type-1 .mid with GM tracks and actual performed timing.

    A timed tempo map, when supplied, is encoded and integrated both ways so
    existing start_s/duration_s remain the authoritative performance times.
    """
    if score.get("schema") != "symphony.score/1":
        raise ValueError("Expected symphony.score/1")
    groups = defaultdict(list)
    for event in score.get("events", []):
        start = _number(event["start_s"], "note onset")
        duration = _number(event["duration_s"], "note duration")
        pitch = _number(event["midi_pitch"], "MIDI pitch")
        if start < 0 or duration <= 0 or pitch != round(pitch) or not 0 <= pitch <= 127:
            raise ValueError("Notes require a nonnegative onset, positive duration and integer MIDI pitch")
        instrument = str(event.get("instrument", "strings"))
        velocity = _number(event.get("velocity", 0.7), "velocity")
        velocity = velocity * 127 if velocity <= 1 else velocity
        if not 0 <= velocity <= 127:
            raise ValueError("MIDI velocity outside 0..127")
        if velocity > 0:
            groups[instrument].append((event, start, duration, int(pitch), max(1, round(velocity))))
    if not groups:
        raise ValueError("Cannot export an empty performance")
    if len(groups) > 15:
        raise ValueError("This single-port MIDI export supports at most 15 pitched sections")
    duration = max(start + length for rows in groups.values() for _, start, length, _, _ in rows)
    # An excerpt can retain its parent score's complete performance map.
    # Later tempo events would otherwise extend the MIDI with a silent tail.
    tempos = [(time, bpm) for time, bpm in _tempos(score) if time <= duration]

    def tick_at(time):
        ticks = 0.0
        for index, (begin, bpm) in enumerate(tempos):
            if begin >= time:
                break
            end = min(time, tempos[index + 1][0] if index + 1 < len(tempos) else time)
            ticks += (end - begin) * PPQ * bpm / 60
        return round(ticks)

    end_tick = tick_at(duration + 0.5)
    conductor = [(0, -4, _meta(3, score.get("title", "Hydrophone symphony"))),
                 (0, -3, _meta(1, "Expressive performed timing. MIDI uses standard note tuning; rendered audio retains note cents.")),
                 (0, -2, _meta(88, bytes((4, 2, 24, 8))))]
    for time, bpm in tempos:
        micros = round(60_000_000 / bpm)
        conductor.append((tick_at(time), -1, _meta(81, micros.to_bytes(3, "big"))))
    tracks = [_track(conductor, end_tick)]
    channels = [channel for channel in range(16) if channel != 9]
    notes, expression_changes = 0, 0
    for channel, (instrument, rows) in zip(channels, sorted(groups.items())):
        pans = [_number(row[0].get("pan", 0), "pan") for row in rows]
        pan = max(0, min(127, round(63.5 * (1 + sum(pans) / len(pans)))))
        data = [(0, -5, _meta(3, instrument.replace("_", " ").title())),
                (0, -4, bytes((0xc0 | channel, PROGRAMS.get(instrument, 48)))),
                (0, -3, bytes((0xb0 | channel, 7, 100))),
                (0, -2, bytes((0xb0 | channel, 10, pan))),
                (0, -1, bytes((0xb0 | channel, 91, 36)))]
        for event, start, length, pitch, velocity in rows:
            onset = tick_at(start)
            offset = max(onset + 1, tick_at(start + length))
            data.append((onset, 1, bytes((0x90 | channel, pitch, velocity))))
            data.append((offset, 0, bytes((0x80 | channel, pitch, 0))))
            notes += 1
        expression = _expression_events(rows, channel, tick_at)
        data.extend(expression)
        expression_changes += len(expression)
        data.append((end_tick, 2, bytes((0xb0 | channel, 123, 0))))
        tracks.append(_track(data, end_tick))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), PPQ) + b"".join(tracks))
    return {"schema": "symphony.midi-export/1", "path": str(output), "format": 1,
            "tracks": len(tracks), "notes": notes, "tempo_changes": len(tempos),
            "duration_s": duration, "ticks_per_quarter": PPQ,
            "tuning": "STANDARD_MIDI_NOTES_AUDIO_CENTS_NOT_REPRESENTED",
            "expression_changes": expression_changes,
            "expression_scope": "SHARED_SECTION_CC11_MAXIMUM_OF_ACTIVE_NOTE_ENVELOPES",
            "performed_timing_preserved": True}


export_midi = write_midi
