"""Phrase-coherent orchestral performance of a symbolic score.

This is an authored performance model, not a claim to have learned a conductor
from symbolic scores.  All parts share one continuous musical clock; variation
is correlated by phrase and section, rather than independent timing noise.
Velocity is MIDI velocity in [1, 127].  ``expression`` values are relative gains
at normalized positions within each performed note.
"""
from __future__ import annotations

from copy import deepcopy
import bisect
import math
import random


_FAMILIES = {
    "strings": "strings", "violin": "strings", "violin1": "strings",
    "violin2": "strings", "viola": "strings", "cello": "strings",
    "bass": "strings", "double_bass": "strings", "contrabass": "strings",
    "flute": "winds", "oboe": "winds", "clarinet": "winds", "bassoon": "winds",
    "horn": "brass", "trumpet": "brass", "trombone": "brass", "tuba": "brass",
    "harp": "plucked", "piano": "plucked", "celesta": "plucked",
    "timpani": "percussion", "cymbal": "percussion", "cymbals": "percussion",
    "triangle": "percussion", "percussion": "percussion",
}
_GATE = {"strings": 1.025, "winds": .91, "brass": .94,
         "plucked": .88, "percussion": .83}
_VIBRATO = {"strings": (5.2, 10.5, .24), "winds": (5.3, 5.0, .25),
            "brass": (4.8, 2.2, .30), "plucked": (0., 0., 0.),
            "percussion": (0., 0., 0.)}
_ROLES = {"melody": 1.08, "countermelody": .96, "counter_melody": .96,
          "harmony": .83, "pad": .79, "accompaniment": .81,
          "bass": .91, "ostinato": .84, "rhythm": .88,
          "percussion": .88}
_DEFAULT = {"rubato_strength": .035, "cadence_ritard": .065,
            "ensemble_spread_ms": 5., "phrase_dynamic_depth": .14,
            "intonation_drift_cents": .28}


def _number(value, label, lower=None, upper=None):
    if isinstance(value, bool):
        raise ValueError(label + " must be a finite number")
    try:
        value = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(label + " must be a finite number") from exc
    if not math.isfinite(value) or (lower is not None and value < lower) or (upper is not None and value > upper):
        raise ValueError(label + " is outside its finite allowed range")
    return value


def _smoothstep(x):
    x = max(0., min(1., x))
    return x * x * (3. - 2. * x)


def _family(instrument):
    name = str(instrument).lower().replace(" ", "_").replace("-", "_")
    if name in _FAMILIES:
        return _FAMILIES[name]
    # Section labels such as "violin_i" and "french_horn" remain usable.
    for needle, family in (("violin", "strings"), ("viola", "strings"),
                           ("cello", "strings"), ("string", "strings"),
                           ("bassoon", "winds"), ("clarinet", "winds"),
                           ("flute", "winds"), ("oboe", "winds"),
                           ("horn", "brass"), ("trumpet", "brass"),
                           ("trombone", "brass"), ("tuba", "brass"),
                           ("timpani", "percussion"), ("cymbal", "percussion"),
                           ("harp", "plucked"), ("piano", "plucked")):
        if needle in name:
            return family
    return "strings"


def _phrases(score, events):
    inferred = {}
    for event in events:
        pid = str(event.get("phrase_id", "phrase-0"))
        start, end = event["start_beat"], event["start_beat"] + event["duration_beats"]
        if pid not in inferred:
            inferred[pid] = {"id": pid, "start_beat": start, "end_beat": end, "intensity": 1.}
        else:
            inferred[pid]["start_beat"] = min(inferred[pid]["start_beat"], start)
            inferred[pid]["end_beat"] = max(inferred[pid]["end_beat"], end)
    declared = score.get("phrases", [])
    if isinstance(declared, dict):
        declared = [{"id": key, **value} for key, value in declared.items()]
    if not isinstance(declared, list):
        raise ValueError("phrases must be a list or keyed object")
    for phrase in declared:
        pid = str(phrase.get("id", phrase.get("phrase_id", "")))
        if not pid:
            raise ValueError("Every phrase needs an identity")
        start = _number(phrase["start_beat"], "phrase start", 0.)
        end_value = phrase.get("end_beat")
        if end_value is None:
            end_value = start + _number(phrase["duration_beats"], "phrase duration", 1e-6)
        end = _number(end_value, "phrase end", start + 1e-6)
        intensity = _number(phrase.get("intensity", 1.), "phrase intensity", .25, 1.5)
        inferred[pid] = {**phrase, "id": pid, "start_beat": start,
                         "end_beat": end, "intensity": intensity}
    # An event's phrase envelope must cover its onset, even when a sustained
    # note intentionally rings through the following phrase.
    for event in events:
        phrase = inferred[str(event.get("phrase_id", "phrase-0"))]
        if not phrase["start_beat"] <= event["start_beat"] <= phrase["end_beat"]:
            raise ValueError("An event onset lies outside its declared phrase")
    return inferred


def _tempo_points(score):
    tempo = _number(score.get("tempo_bpm", 84.), "tempo_bpm", 20., 300.)
    points = score.get("tempo_map", [{"beat": 0., "bpm": tempo}])
    if not isinstance(points, list) or not points:
        raise ValueError("tempo_map must be a nonempty list of beat/bpm anchors")
    result = []
    for point in points:
        beat = _number(point.get("beat", point.get("start_beat")), "tempo beat", 0.)
        bpm = _number(point.get("bpm", point.get("tempo_bpm")), "tempo bpm", 20., 300.)
        if result and beat <= result[-1][0]:
            raise ValueError("Tempo anchors must be strictly increasing")
        result.append((beat, bpm))
    if result[0][0] > 0:
        result.insert(0, (0., tempo))
    return result


def _interpolate(points, x):
    beats = [p[0] for p in points]
    i = bisect.bisect_right(beats, x) - 1
    if i < 0:
        return points[0][1]
    if i >= len(points) - 1:
        return points[-1][1]
    a, b = points[i], points[i + 1]
    return a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])


def _clock(score, phrases, end_beat, parameters, lead_in):
    base = _tempo_points(score)
    ordered = sorted(phrases.values(), key=lambda p: (p["start_beat"], p["id"]))
    # Include all symbolic onsets/endpoints through an eighth-beat mesh.  The
    # inverse tempo integral is exact for each linear-bpm mesh segment.
    anchors = {0., end_beat}
    anchors.update(p[0] for p in base if p[0] <= end_beat)
    anchors.update(i / 8. for i in range(math.ceil(end_beat * 8.) + 1) if i / 8. <= end_beat)
    for phrase in ordered:
        anchors.add(phrase["start_beat"])
        anchors.add(phrase["end_beat"])
    curve = []
    for beat in sorted(anchors):
        active = [p for p in ordered if p["start_beat"] <= beat <= p["end_beat"]]
        factor = 1.
        if active:
            phrase = max(active, key=lambda p: p["start_beat"])
            pos = (beat - phrase["start_beat"]) / (phrase["end_beat"] - phrase["start_beat"])
            # A slight forward motion through the middle, then a prepared
            # cadence.  The same curve controls every orchestral section.
            factor += parameters["rubato_strength"] * math.sin(math.pi * pos)
            factor -= .28 * parameters["rubato_strength"] * math.exp(-((pos - .08) / .16) ** 2)
            factor -= parameters["cadence_ritard"] * _smoothstep((pos - .74) / .26)
        curve.append((beat, max(16., min(330., _interpolate(base, beat) * factor))))
    times = [lead_in]
    for (a, bpm_a), (b, bpm_b) in zip(curve, curve[1:]):
        slope = (bpm_b - bpm_a) / (b - a)
        elapsed = 60. * (b - a) / bpm_a if abs(slope) < 1e-12 else 60. * math.log(bpm_b / bpm_a) / slope
        times.append(times[-1] + elapsed)
    beats = [x[0] for x in curve]

    def to_seconds(beat):
        i = min(len(curve) - 1, max(0, bisect.bisect_right(beats, beat) - 1))
        a, bpm_a = curve[i]
        if i == len(curve) - 1:
            return times[i] + 60. * (beat - a) / bpm_a
        b, bpm_b = curve[i + 1]
        slope = (bpm_b - bpm_a) / (b - a)
        delta = beat - a
        return times[i] + (60. * delta / bpm_a if abs(slope) < 1e-12 else 60. * math.log((bpm_a + slope * delta) / bpm_a) / slope)

    return to_seconds, [{"beat": beat, "bpm": bpm, "time_s": time}
                        for (beat, bpm), time in zip(curve, times)]


def _measured_priors(profile):
    """Bounded authored mapping from actually summarized performance data.

    Locally detrended beat-interval CV is preferred.  Global CV includes
    written tempo changes as well as rubato; either is used only as a shaping
    prior, never as a recovered conductor trajectory.  Piano key-duration
    statistics are deliberately excluded from bowed/wind articulation.
    """
    if not profile or profile.get("schema") != "symphony.performance-profile/1":
        return {}, None
    count = profile.get("performance_count")
    digest = profile.get("source_manifest_sha256")
    if (isinstance(count, bool) or not isinstance(count, int) or count <= 0
            or not isinstance(digest, str) or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)):
        raise ValueError("A measured performance profile needs positive count and source-manifest SHA256")
    statistics = profile.get("performance_statistics", {})
    if not isinstance(statistics, dict):
        raise ValueError("performance_statistics must be an object")
    values, used = {}, {}
    tempo_key = "median_local_tempo_cv" if statistics.get("median_local_tempo_cv") is not None else "median_tempo_cv"
    if statistics.get(tempo_key) is not None:
        cv = _number(statistics[tempo_key], tempo_key, 0., 10.)
        values["rubato_strength"] = max(.012, min(.075, .35 * cv))
        values["cadence_ritard"] = max(.035, min(.11, .55 * cv))
        used[tempo_key] = cv
    if statistics.get("median_velocity_iqr") is not None:
        iqr = _number(statistics["median_velocity_iqr"], "median_velocity_iqr", 0., 127.)
        values["phrase_dynamic_depth"] = max(.06, min(.20, iqr / 150.))
        used["median_velocity_iqr"] = iqr
    return values, {
        "schema": profile["schema"], "source_manifest_sha256": digest,
        "performance_count": count, "performer_count": profile.get("performer_count"),
        "tempo_statistic": tempo_key,
        "used_statistics": used,
        "mapping": {"rubato_strength": "clip(0.35 * " + tempo_key + ", 0.012, 0.075)",
                    "cadence_ritard": "clip(0.55 * " + tempo_key + ", 0.035, 0.11)",
                    "phrase_dynamic_depth": "clip(median_velocity_iqr / 150, 0.06, 0.20)"},
        "scope": "Measured piano-performance priors with authored mappings; detrended local tempo CV is preferred, while global CV includes written/form changes. Orchestral bow/breath technique and phrase trajectories remain authored.",
    }


def perform(score, profile=None, seed=20261024):
    """Return a performed copy of a ``symphony.score/1`` beat-based score.

    A ``symphony.performance-profile/1`` can supply hash-bound measured tempo
    and velocity priors.  Optional ``profile.performance_parameters`` override
    their bounded mappings.  Symbolic-corpus statistics never become purported
    observations of performer timing or vibrato.
    """
    if not isinstance(score, dict) or score.get("schema") != "symphony.score/1":
        raise ValueError("Expected a symphony.score/1 object")
    if score.get("performance", {}).get("schema") == "symphony.performance/1":
        raise ValueError("This score already contains a performed timing map")
    source = score.get("events")
    if not isinstance(source, list) or not source:
        raise ValueError("A nonempty symbolic event list is required")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("Performance seed must be an integer")
    result = deepcopy(score)
    events = result["events"]
    for i, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError("Each event must be an object")
        event["start_beat"] = _number(event["start_beat"], "event start", 0.)
        event["duration_beats"] = _number(event["duration_beats"], "event duration", .001, 256.)
        event["midi_pitch"] = _number(event["midi_pitch"], "midi_pitch", 0., 127.)
        event["velocity"] = _number(event.get("velocity", 76.), "velocity", 1., 127.)
        event["cents"] = _number(event.get("cents", 0.), "cents", -200., 200.)
        event.setdefault("instrument", "strings")
        event.setdefault("event_id", "note-" + str(i))
        event.setdefault("phrase_id", "phrase-0")
        event.setdefault("role", "harmony")
    parameters = dict(_DEFAULT)
    measured, measured_provenance = _measured_priors(profile)
    parameters.update(measured)
    supplied = (profile or {}).get("performance_parameters", {})
    if not isinstance(supplied, dict):
        raise ValueError("performance_parameters must be an object")
    ranges = {"rubato_strength": (0., .12), "cadence_ritard": (0., .20),
              "ensemble_spread_ms": (0., 16.), "phrase_dynamic_depth": (0., .30),
              "intonation_drift_cents": (0., 1.)}
    for key, value in supplied.items():
        if key not in parameters:
            raise ValueError("Unknown performance parameter: " + key)
        parameters[key] = _number(value, key, *ranges[key])
    phrases = _phrases(result, events)
    end_beat = max(e["start_beat"] + e["duration_beats"] for e in events)
    lead_in = .045
    clock, tempo = _clock(result, phrases, end_beat, parameters, lead_in)
    phrase_offsets, part_offsets, vibrato_phases = {}, {}, {}

    def correlated(key, scale):
        # Stable key-local random streams avoid changing the whole orchestra
        # when one extra note is added to a different part.
        return max(-2., min(2., random.Random(str(seed) + "|" + key).gauss(0., 1.))) * scale

    for event in events:
        pid, instrument = str(event["phrase_id"]), str(event["instrument"])
        family = _family(instrument)
        phrase = phrases[pid]
        pos = max(0., min(1., (event["start_beat"] - phrase["start_beat"]) /
                          (phrase["end_beat"] - phrase["start_beat"])))
        family_key, part_key = pid + "|" + family, pid + "|" + instrument
        if family_key not in phrase_offsets:
            phrase_offsets[family_key] = correlated("family|" + family_key, parameters["ensemble_spread_ms"] / 1500.)
        if part_key not in part_offsets:
            part_offsets[part_key] = correlated("part|" + part_key, parameters["ensemble_spread_ms"] / 3000.)
            vibrato_phases[part_key] = random.Random(str(seed) + "|vib|" + part_key).random() * 2 * math.pi
        attack_lead = {"strings": -.008, "winds": -.003, "brass": -.006,
                       "plucked": .001, "percussion": .003}[family]
        onset_offset = phrase_offsets[family_key] + part_offsets[part_key] + attack_lead
        raw_start = clock(event["start_beat"])
        raw_duration = clock(event["start_beat"] + event["duration_beats"]) - raw_start
        articulation = str(event.get("articulation", "legato" if family == "strings" else "natural"))
        gate = _GATE[family]
        if articulation in {"staccato", "spiccato"}:
            gate = .58 if family == "strings" else .62
        elif articulation in {"marcato", "accent"}:
            gate = .83
        elif articulation in {"tenuto", "slur", "legato"}:
            gate = 1.035 if family == "strings" else .97
        gate *= 1. + correlated("gate|" + part_key, .009)
        role = str(event["role"]).lower()
        arch = math.sin(math.pi * pos) ** 1.15
        phrase_gain = 1. - parameters["phrase_dynamic_depth"] + 1.4 * parameters["phrase_dynamic_depth"] * arch
        phrase_gain *= 1. - .055 * _smoothstep((pos - .82) / .18)
        gain = phrase_gain * (.65 + .35 * phrase["intensity"]) * _ROLES.get(role, .9)
        if event.get("accent") or articulation in {"accent", "marcato"}:
            gain *= 1.09
        # The performer respects written intonation.  Slow, small section
        # drift adds warmth without replacing the Dyletsky target field.
        drift = correlated("intonation|" + part_key, parameters["intonation_drift_cents"])
        event["written_cents"] = event["cents"]
        event["cents"] += drift * (.6 + .4 * math.sin(math.pi * pos))
        event["start_s"] = max(0., raw_start + onset_offset)
        event["duration_s"] = max(.04, raw_duration * gate)
        event["written_velocity"] = event["velocity"]
        # Written dynamics already control the sampled attack layer.  Keep
        # performance changes modest so a quiet composition is not repeatedly
        # attenuated into an inaudible low-velocity GM layer.
        velocity_shift = max(-8., min(8., 24. * (gain - 1.)))
        event["velocity"] = max(8, min(124, round(event["velocity"] + velocity_shift)))
        event["performance_family"] = family
        event["articulation"] = articulation
        event["onset_offset_s"] = onset_offset
        event["expression"] = [
            {"time": 0., "value": .86 if family in {"strings", "winds", "brass"} else 1.},
            {"time": .37, "value": 1.},
            {"time": .78, "value": .97},
            {"time": 1., "value": .78 if family in {"strings", "winds", "brass"} else .9},
        ]
        hz, depth, delay = _VIBRATO[family]
        event["vibrato_hz"] = hz + (correlated("vib-rate|" + part_key, .09) if hz else 0.)
        event["vibrato_depth_cents"] = depth * min(1., raw_duration / .8)
        event["vibrato_delay_s"] = min(delay, raw_duration * .4)
        event["vibrato_phase_rad"] = vibrato_phases[part_key]
    # Cap accidental overlap within a written part, while allowing a small
    # bow/slur connection.  Simultaneous chord notes remain simultaneous.
    parts = {}
    for event in events:
        key = (str(event["instrument"]), str(event.get("voice", event.get("part_id", event["role"]))))
        parts.setdefault(key, []).append(event)
    for notes in parts.values():
        starts = sorted(set(e["start_beat"] for e in notes))
        # At very dense phrase boundaries, a change in section arrival must
        # never reverse two written attacks.  Shift an entire simultaneous
        # chord together, preserving its internal alignment.
        previous_beat, previous_time = None, None
        for beat in starts:
            group = [e for e in notes if e["start_beat"] == beat]
            arrival = min(e["start_s"] for e in group)
            if previous_time is not None:
                separation = min(.003, max(.000001, .5 * (clock(beat) - clock(previous_beat))))
                if arrival < previous_time + separation:
                    shift = previous_time + separation - arrival
                    for event in group:
                        event["start_s"] += shift
                        event["onset_offset_s"] += shift
                    arrival += shift
            previous_beat, previous_time = beat, arrival
        for event in notes:
            next_i = bisect.bisect_right(starts, event["start_beat"] + 1e-9)
            if next_i < len(starts):
                next_start = min(e["start_s"] for e in notes if e["start_beat"] == starts[next_i])
                overlap = .026 if event["articulation"] in {"slur", "legato", "tenuto"} else -.012
                event["duration_s"] = max(.025, min(event["duration_s"], next_start - event["start_s"] + overlap))
    for section in result.get("sections", []):
        if "start_beat" in section:
            section["start_s"] = clock(_number(section["start_beat"], "section start", 0.))
        if "end_beat" in section:
            section["end_s"] = clock(_number(section["end_beat"], "section end", 0.))
        elif "start_beat" in section and "duration_beats" in section:
            section["end_s"] = clock(float(section["start_beat"]) + float(section["duration_beats"]))
    result["events"] = sorted(events, key=lambda e: (e["start_s"], str(e["instrument"]), e["midi_pitch"]))
    result["performed_tempo_map"] = tempo
    result["duration_s"] = max(e["start_s"] + e["duration_s"] for e in events)
    result["performance"] = {
        "schema": "symphony.performance/1", "seed": seed,
        "method": "shared phrase rubato, part-correlated arrival, shaped dynamics and articulation",
        "parameters": parameters, "lead_in_s": lead_in,
        "phrase_count": len(phrases), "event_count": len(events),
        "recorded_performer_model_trained": False,
        "measured_performance_priors": measured_provenance,
        "parameter_origin": ("measured statistical priors with authored mappings" if measured else "authored defaults")
                            + ("; explicit supplied overrides" if supplied else ""),
        "symbolic_profile_origin": (profile or {}).get("schema"),
        "scope": "Expressive rendering model; listening quality requires listening, not a unit-test claim.",
    }
    return result
