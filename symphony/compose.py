"""Compose original recurring themes with corpus-conditioned melodic choices.

The form, thematic seed and orchestration grammar are authored. Empirical,
composer-balanced interval, transition and rhythm distributions score new
melodic paths. This is statistical composition, not a pretrained audio model
and not retrieval of a source musician's melody.
"""
from __future__ import annotations

from collections import Counter
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import unicodedata


RANGES = {
    "violin": (67, 88), "violin2": (62, 79), "viola": (53, 72),
    "cello": (43, 67), "bass": (31, 52), "flute": (72, 93),
    "oboe": (62, 83), "clarinet": (57, 83), "bassoon": (40, 67),
    "horn": (45, 76), "trumpet": (60, 83), "harp": (43, 91),
    "timpani": (36, 50),
}
PANS = {"violin": -.58, "violin2": -.28, "viola": .12, "cello": .42,
        "bass": .66, "flute": -.15, "oboe": .04, "clarinet": .2,
        "bassoon": .3, "horn": -.35, "trumpet": .35, "harp": -.65,
        "timpani": .12}
MINOR = (0, 2, 3, 5, 7, 8, 10)
MAJOR = (0, 2, 4, 5, 7, 9, 11)
# Harmonic functions in a D-centred narrative; transposition is explicit.
MINOR_PLAN = ((0, "minor"), (8, "major"), (3, "major"), (10, "major"),
              (5, "minor"), (8, "major"), (7, "dominant"), (0, "minor"))
MAJOR_PLAN = ((0, "major"), (9, "minor"), (7, "major"), (5, "major"),
              (4, "minor"), (2, "minor"), (7, "dominant"), (0, "major"))
SCHERZO_PLAN = ((0, "major"), (7, "major"), (9, "minor"), (4, "minor"),
                (5, "major"), (2, "minor"), (7, "dominant"), (0, "major"))
CHORDS = {"major": (0, 4, 7), "minor": (0, 3, 7), "dominant": (0, 4, 7, 10)}
MOTIF = (0, 2, 1, 4, 3, 2, 1, 0, -1, 0)
SECOND_THEME = (4, 3, 2, 1, 0, -1, 0, 2, 1, 0)
PATTERNS4 = ((1, .5, .5, 1, 1), (1.5, .5, 1, 1), (.5, .5, 1, 1, 1), (2, 1, 1))
PATTERNS3 = ((1, .5, .5, 1), (.5, .5, .5, .5, 1), (1.5, .5, 1), (1, 1, 1))


def _load(value):
    if value is None:
        return {}
    return json.loads(Path(value).read_text()) if isinstance(value, (str, Path)) else value


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _distributions(profile):
    balanced = profile.get("balanced", {})
    intervals = balanced.get("interval_probabilities", {})
    transitions = balanced.get("interval_transition_probabilities", {})
    rhythms = balanced.get("duration_probabilities", {})
    return intervals, transitions, rhythms


def select_palette(profile, name="all"):
    """Select composer-balanced priors without silently shrinking source counts."""
    if name == "all":
        return profile
    names = {
        "romantic": ("brahms", "schubert", "schumann", "dvorak", "tchaikovsky", "mendelssohn",
                     "beach", "farrenc", "elgar", "borodin", "grieg", "rachmaninoff", "rachmaninov"),
        "luminous": ("debussy", "ravel", "faure", "boulanger", "chaminade", "bonis", "delius", "hahn", "chausson"),
        "classical": ("haydn", "mozart", "beethoven", "arriaga", "cambini", "cherubini", "onslow"),
    }
    if name not in names:
        raise ValueError("Unknown composer palette")
    def ascii_name(value):
        return "".join(c for c in unicodedata.normalize("NFD", value.lower())
                       if unicodedata.category(c) != "Mn")
    chosen = [c for c in profile.get("composer_profiles", {})
              if any(token in ascii_name(c) for token in names[name])]
    if not chosen:
        raise ValueError("Composer palette has no parsed source profiles")
    result = dict(profile)
    balanced = {}
    for source, target in (("interval_counts", "interval_probabilities"),
                           ("interval_transition_counts", "interval_transition_probabilities"),
                           ("duration_counts", "duration_probabilities")):
        accumulated = Counter()
        eligible = 0
        for composer in chosen:
            counts = profile["composer_profiles"][composer][source]
            total = sum(counts.values())
            if total:
                eligible += 1
                for key, count in counts.items():
                    accumulated[key] += count / total
        balanced[target] = {key: value / eligible for key, value in accumulated.items()}
    result["balanced"] = balanced
    result["selected_palette"] = name
    result["selected_composers"] = chosen
    return result


def _prob(mapping, key, floor=.0005):
    value = mapping.get(str(key), floor)
    try:
        return max(floor, float(value))
    except (ValueError, TypeError):
        return floor


def _degree(tonic, scale, degree):
    octave, index = divmod(degree, 7)
    return tonic + 12 * octave + scale[index]


def _nearest(pc, target, low, high):
    candidates = [p for p in range(low, high + 1) if p % 12 == pc % 12]
    return min(candidates, key=lambda p: abs(p - target))


def _rhythm(meter, rng, probabilities, active):
    patterns = PATTERNS3 if meter == 3 else PATTERNS4
    weights = []
    for pattern in patterns:
        logs = [math.log(_prob(probabilities, str(Fraction(x).limit_denominator(16)), .04)) for x in pattern]
        # Avoid always choosing the shortest, most frequent pattern.
        rate = len(pattern) / meter
        score = sum(logs) / len(logs) - (.35 * abs(rate - (1.65 if active else 1.1)))
        weights.append(math.exp(score))
    return rng.choices(patterns, weights=weights, k=1)[0]


def _melody(slots, tonic, scale, low, high, previous, profile, rng, transform=0):
    """Beam search keeps tonal structure, motif and measured interval priors."""
    intervals, transitions, _ = _distributions(profile)
    paths = [(0., previous, 0, 0, [])]
    for index, slot in enumerate(slots):
        chord = slot["chord_pcs"]
        thematic_material = SECOND_THEME if transform == 3 else MOTIF
        degree = thematic_material[index % len(thematic_material)]
        if transform == 1:
            degree = 2 - degree
        elif transform == 2:
            degree += (index // len(MOTIF)) % 2
        target = _degree(tonic + 12, scale, degree)
        candidates = [p for p in range(low, high + 1)
                      if (p - tonic) % 12 in scale or p % 12 in chord]
        if slot["cadence"]:
            candidates = [p for p in candidates if p % 12 in chord[:3]]
        if slot.get("final"):
            candidates = [p for p in candidates if p % 12 == chord[0]]
        options = []
        for cost, last, prev_interval, repeated, notes in paths:
            for pitch in candidates:
                delta = pitch - last
                if abs(delta) > 9:
                    continue
                repeat = repeated + 1 if pitch == last else 0
                if repeat > 1:
                    continue
                score = cost + .30 * math.log(_prob(intervals, delta, .025))
                score += .08 * math.log(_prob(transitions, f"{prev_interval},{delta}", .015))
                score -= .38 * abs(pitch - target)
                if delta == 0:
                    score -= .75
                score -= .095 * max(0, abs(delta) - 4) ** 2
                if slot["strong"] and pitch % 12 not in chord:
                    score -= 2.8
                if pitch % 12 in chord[:3]:
                    score += .18
                # A leap tends to resolve back by step rather than continue.
                if abs(prev_interval) >= 5:
                    score += .5 if delta * prev_interval < 0 and abs(delta) <= 3 else -.7
                score += .025 * rng.random()
                options.append((score, pitch, delta, repeat, notes + [pitch]))
        if not options:
            raise ValueError("Melodic beam has no reachable notes")
        paths = sorted(options, reverse=True, key=lambda item: item[0])[:18]
    return paths[0][-1]


def compose(profile=None, *, seed=20261024, title="The Water Remembers", bars_scale=1,
            tuning_profile=None, tonic_pc=2):
    """Return a new three-movement original score in quarter-note beats.

    bars_scale is a positive integer: scale=1 is a roughly 3.5 minute suite;
    scale=2 expands form/development. No source melody is copied.
    """
    if isinstance(bars_scale, bool) or not isinstance(bars_scale, int) or bars_scale < 1:
        raise ValueError("bars_scale must be a positive integer")
    profile, tuning = _load(profile), _load(tuning_profile)
    rng = random.Random(seed)
    intervals, _, durations = _distributions(profile)
    events, movements, phrases, harmonies = [], [], [], []
    cursor = 0.
    event_id = 0
    # A shared thematic contour returns in a transformed major-key finale.
    specifications = [
        ("I · Earth and breath", 24 * bars_scale, 4, 72, MINOR, MINOR_PLAN, .52, tonic_pc),
        ("II · Water in motion", 32 * bars_scale, 3, 132, MAJOR, SCHERZO_PLAN, .66, (tonic_pc + 3) % 12),
        ("III · The returning light", 32 * bars_scale, 4, 104, MAJOR, MAJOR_PLAN, .82, tonic_pc),
    ]
    tempo_map = []
    profile_id = _digest(profile) if profile else None
    tuning_by_pc = tuning.get("offsets_by_pitch_class", {})
    tuning_by_spelling = tuning.get("offsets_by_spelling", {})

    def add(start, duration, pitch, instrument, velocity, phrase_id, role="harmony", articulation=None):
        nonlocal event_id
        if duration <= 0:
            return
        lo, hi = RANGES[instrument]
        if not lo <= pitch <= hi:
            raise ValueError(f"{instrument} note {pitch} exceeds its declared working register")
        event_id += 1
        chromatic = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
        if mi > 0 and root_pc in (0, 2, 4, 6, 7, 9, 11):
            chromatic = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
        spelling = chromatic[pitch % 12]
        cent = float(tuning_by_spelling.get(spelling, tuning_by_pc.get(str(pitch % 12), 0)))
        event = {"event_id": f"n{event_id:06d}", "start_beat": round(start, 6),
                 "duration_beats": round(duration, 6), "midi_pitch": int(pitch),
                 "instrument": instrument, "velocity": max(12, min(112, round(velocity))),
                 "pan": PANS[instrument], "phrase_id": phrase_id, "role": role, "spelling": spelling,
                 "cents": cent, "tuning_source": tuning.get("engine_id", "equal_temperament")}
        if articulation:
            event["articulation"] = articulation
        events.append(event)

    for mi, (name, n_bars, meter, bpm, scale, progression, intensity, root_pc) in enumerate(specifications):
        start = cursor
        tonic = 60 + root_pc
        tempo_map.append({"beat": start, "bpm": bpm})
        movements.append({"id": f"movement-{mi+1}", "title": name, "start_beat": start,
                          "end_beat": start + n_bars * meter, "meter": meter,
                          "tempo_bpm": bpm, "tonic_pc": root_pc,
                          "mode": "minor" if mi == 0 else "major"})
        previous_melody = tonic + 12
        previous_inner = {"violin2": tonic + 7, "viola": tonic, "cello": tonic - 12}
        for phrase_index in range(n_bars // 8):
            phrase_id = f"m{mi+1}-p{phrase_index+1}"
            phrase_start = start + phrase_index * 8 * meter
            final_phrase = phrase_index == n_bars // 8 - 1
            phrase_intensity = intensity * (.65 + .35 * math.sin(math.pi * (phrase_index + .6) / (n_bars / 8 + .5)))
            if final_phrase:
                phrase_intensity = intensity * (.83 if mi < 2 else 1.12)
            phrases.append({"id": phrase_id, "start_beat": phrase_start,
                            "end_beat": phrase_start + 8 * meter,
                            "intensity": min(1, phrase_intensity), "movement_id": f"movement-{mi+1}"})
            slots = []
            chord_schedule = []
            for bar in range(8):
                root_offset, quality = progression[bar]
                # Middle phrases explore a related subdominant region.
                if phrase_index % 3 == 1 and bar in (1, 3):
                    root_offset, quality = ((5, "minor" if mi == 0 else "major")
                                             if bar == 1 else (2, "minor"))
                root = (root_pc + root_offset) % 12
                pcs = [(root + n) % 12 for n in CHORDS[quality]]
                chord_schedule.append((root, quality, pcs))
                bar_start = phrase_start + bar * meter
                harmonies.append({"start_beat": bar_start, "duration_beats": meter,
                                  "root_pc": root, "quality": quality, "phrase_id": phrase_id})
                pattern = _rhythm(meter, rng, durations, mi == 1)
                if bar == 7:
                    pattern = (meter - 1, 1) if not final_phrase else (meter,)
                local = 0
                for j, duration in enumerate(pattern):
                    # A measured breath closes each phrase; the finale holds.
                    if bar == 7 and j == len(pattern) - 1 and not final_phrase:
                        break
                    slots.append({"start": bar_start + local, "duration": duration,
                                  "chord_pcs": pcs, "strong": local == 0 or local == 2,
                                  "cadence": bar == 7, "final": final_phrase and bar == 7})
                    local += duration
            transform = 1 if mi == 1 and phrase_index % 2 else (3 if phrase_index % 3 == 1 else 0)
            if phrase_index % 3 == 2 and not final_phrase:
                transform = 2
            pitches = _melody(slots, tonic, scale, 69 + (root_pc > 7), 87,
                              previous_melody, profile, rng, transform)
            previous_melody = pitches[-1]
            lead = "oboe" if mi == 0 and phrase_index == 0 else ("flute" if mi == 1 else "violin")
            for j, (slot, pitch) in enumerate(zip(slots, pitches)):
                if lead == "oboe":
                    pitch = min(83, pitch)
                if lead == "flute":
                    pitch = max(72, pitch)
                add(slot["start"], slot["duration"], pitch, lead,
                    63 + 26 * phrase_intensity, phrase_id, "melody",
                    "staccato" if mi == 1 else "legato")
                if mi == 2 and phrase_index >= 2 and j % 2 == 0:
                    add(slot["start"], slot["duration"] * .93,
                        _nearest(pitch % 12, pitch - 12, 45, 76), "horn",
                        48 + 22 * phrase_intensity, phrase_id, "support")

            for bar, (root, quality, pcs) in enumerate(chord_schedule):
                bs = phrase_start + bar * meter
                energy = 44 + 26 * phrase_intensity
                sparse = mi == 0 and phrase_index == 0 and bar < 4
                bass = _nearest(root, 38 + (mi == 1) * 5, 31, 52)
                add(bs, meter * (.7 if mi == 1 else .96), bass, "bass", energy - 9, phrase_id,
                    "bass", "pizzicato" if mi == 1 else "legato")
                # Independent inner lines choose close chord tones, preserving register.
                for instrument, lower, upper, chord_index in (("cello", 45, 62, 0),
                                                               ("viola", 55, 68, 1),
                                                               ("violin2", 64, 78, 2)):
                    if sparse and instrument == "violin2":
                        continue
                    choices = [p for p in range(lower, upper + 1) if p % 12 in pcs[:3]]
                    target = previous_inner[instrument]
                    p = min(choices, key=lambda n: abs(n-target) + (.2 if n % 12 == pcs[chord_index % 3] else .8))
                    previous_inner[instrument] = p
                    if mi == 1:
                        # Scherzo texture: bass on the beat, inner voices answer.
                        for beat in range(1, meter):
                            add(bs + beat, .68, p, instrument, energy - 2, phrase_id,
                                "harmony", "staccato")
                    else:
                        add(bs, meter + .04, p, instrument, energy - (4 if instrument == "violin2" else 0),
                            phrase_id, "harmony", "legato")
                if mi == 0 and bar in (1, 3, 5):
                    # Harp colors mark harmonic changes rather than fill every gap.
                    for j, offset in enumerate((0, 1, 2, 1)):
                        p = _nearest(pcs[offset], 64 + 3*j, 43, 91)
                        add(bs + .5*j, 1.5, p, "harp", 40 + 10 * phrase_intensity, phrase_id, "color")
                if (mi == 0 and not sparse and bar in (2, 4)) or (mi == 2 and bar in (1, 3, 5)):
                    # Wind response occupies space after an opening melodic gesture.
                    instrument = "clarinet" if bar % 2 else "flute"
                    lower, upper = RANGES[instrument]
                    p = _nearest(pcs[1], 73 if instrument == "clarinet" else 81, lower, upper)
                    add(bs + meter / 2, meter / 2 - .12, p, instrument,
                        49 + 15 * phrase_intensity, phrase_id, "countermelody", "legato")
                if mi == 1 and bar < 7:
                    p = _nearest(pcs[2], 52, 40, 67)
                    add(bs, .8, p, "bassoon", 48 + 12 * phrase_intensity, phrase_id, "countermelody", "staccato")
                if mi == 2 and phrase_index >= 1 and bar in (0, 4, 6, 7):
                    for pc in pcs[:3]:
                        p = _nearest(pc, 62, 45, 76)
                        add(bs, meter * .85, p, "horn", 50 + 18 * phrase_intensity, phrase_id, "support")
                    if final_phrase and bar in (4, 6, 7):
                        p = _nearest(root, 74, 60, 83)
                        add(bs, meter - .15, p, "trumpet", 65 + 17 * phrase_intensity, phrase_id, "support")
                if mi == 2 and (bar == 6 or (final_phrase and bar in (0, 4, 7))):
                    p = _nearest(root, 43, 36, 50)
                    add(bs, 1.5, p, "timpani", 55 + 18 * phrase_intensity, phrase_id, "color")
        cursor += n_bars * meter
        # Silence between movements remains part of the shared score clock.
        if mi < len(specifications) - 1:
            cursor += bpm / 60 * 2.4

    score = {"schema": "symphony.score/1", "title": title, "seed": seed,
             "subtitle": "An original three-movement work · corpus-conditioned themes · expressive sampled orchestra",
             "composition_method": "authored_thematic_form_with_composer_balanced_corpus_scored_melodic_beam_search",
             "composer": "Hydrophone Symphony Engine", "tempo_bpm": 72, "tempo_map": tempo_map,
             "movements": movements, "sections": [dict(m) for m in movements], "phrases": phrases, "harmonies": harmonies,
             "events": sorted(events, key=lambda e: (e["start_beat"], e["event_id"])),
             "duration_beats": cursor, "source_analysis": {"corpus_profile_sha256": profile_id,
                "corpus_totals": {"score_count": profile.get("parsed_score_count", 0),
                                  "composer_count": profile.get("composer_count", 0),
                                  "notehead_count": profile.get("aggregate", {}).get("notehead_count", 0),
                                  "melodic_transition_count": profile.get("aggregate", {}).get("melodic_transition_count", 0)}, "balanced_by_composer": bool(intervals),
                "source_melodies_retrieved": False, "audio_model_trained": False,
                "tuning_profile_sha256": _digest(tuning) if tuning else None},
             "physical_hardware_commands_issued": 0}
    score["source_analysis"]["selected_palette"] = profile.get("selected_palette", "all")
    score["source_analysis"]["selected_composers"] = profile.get("selected_composers", [])
    score["composition_sha256"] = _digest(score)
    return score


def score_statistics(score):
    """Report composition mechanics without claiming an aesthetic metric."""
    counts = Counter(e["instrument"] for e in score["events"])
    melody = [e for e in score["events"] if e["role"] == "melody"]
    leaps = [b["midi_pitch"]-a["midi_pitch"] for a, b in zip(melody, melody[1:])
             if a["phrase_id"] == b["phrase_id"]]
    return {"events": len(score["events"]), "instruments": dict(counts),
            "movements": len(score["movements"]), "phrases": len(score["phrases"]),
            "melodic_intervals": dict(sorted(Counter(leaps).items())),
            "maximum_within_phrase_melodic_leap_semitones": max(map(abs, leaps), default=0),
            "aesthetic_quality_automatically_proved": False}
