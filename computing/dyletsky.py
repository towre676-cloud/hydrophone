"""Dependency-free replay of the archived Dyletsky interval-tuning proxy.

This model assigns offsets to twelve chromatic pitch classes. It is not an
authenticated historical prescription, a spelling-aware score model, or a
calibrated controller for the proposed four-string object. The separate
four-string projection below only evaluates ideal fixed-length,
fixed-linear-density tension requirements. It never issues commands.

The interval targets and named weighting rules reproduce the saved
``dyletsky_engine.py`` (April 2026) discussed during archive recovery.
Weighted RMS uses sum(w*r**2)/sum(w), matching the least-squares objective.
"""
from __future__ import annotations

from fractions import Fraction
import math


PITCH_CLASSES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
INTERVAL_STEPS = (("M3", 4), ("m3", 3), ("P5", 7))
QUARTER_COMMA_TARGETS = {"M3": -13.68628614, "m3": 10.26471460, "P5": -3.42157153}
NATURAL_HEX = frozenset((0, 2, 4, 5, 7, 9))
HARD_HEX = frozenset((7, 9, 11, 0, 2, 4))
SOFT_HEX = frozenset((5, 7, 9, 10, 0, 2))
MODE_FINALS = frozenset((2, 4, 5, 7))
MODE_RECITING = frozenset((9, 0, 7, 2))
STRATEGIES = (
    "ET", "hex_natural", "hex_hard", "hex_soft", "modal_finals",
    "modal_reciting", "liturgy", "resurrection", "passion", "cadence",
    "cadence_soft", "diatonic_thirds", "concerto",
)
# Preserve the physical-design service's 17 labels at the score boundary.
# The archived numerical solver above still has only twelve pitch classes.
SPELLINGS17 = ("C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B")
SPELLING_TO_PROXY = {
    "C": "C", "C#": "C#", "Db": "C#", "D": "D", "D#": "Eb", "Eb": "Eb",
    "E": "E", "F": "F", "F#": "F#", "Gb": "F#", "G": "G", "G#": "Ab",
    "Ab": "Ab", "A": "A", "A#": "Bb", "Bb": "Bb", "B": "B",
}


def _finite(value, label):
    if isinstance(value, bool):
        raise ValueError(label + " must be a finite number")
    try:
        converted = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(label + " must be a finite number") from exc
    if not math.isfinite(converted):
        raise ValueError(label + " must be a finite number")
    return converted


def build_interval_jacobian():
    """Return integer 36x12 incidence rows and (family,start,end) labels."""
    rows, labels = [], []
    for family, step in INTERVAL_STEPS:
        for start in range(12):
            end = (start + step) % 12
            row = [0] * 12
            row[start], row[end] = -1, 1
            rows.append(row)
            labels.append((family, start, end))
    return rows, labels


def strategy_weights(strategy="ET"):
    """Return the archived positive interval priorities in Jacobian order."""
    if strategy not in STRATEGIES:
        raise ValueError("Unknown tuning strategy: " + str(strategy))
    _, labels = build_interval_jacobian()
    result = []
    for family, start, end in labels:
        natural = start in NATURAL_HEX and end in NATURAL_HEX
        hard = start in HARD_HEX and end in HARD_HEX
        soft = start in SOFT_HEX and end in SOFT_HEX
        if strategy == "ET":
            weight = 1.0
        elif strategy == "hex_natural":
            weight = 3.0 if natural else 1.0
        elif strategy == "hex_hard":
            weight = 3.0 if hard else 1.0
        elif strategy == "hex_soft":
            weight = 3.0 if soft else 1.0
        elif strategy == "modal_finals":
            weight = 5.0 if end in MODE_FINALS else 1.0
        elif strategy == "modal_reciting":
            weight = 3.0 if end in MODE_RECITING else 1.0
        elif strategy == "liturgy":
            weight = (2.5 if family in ("M3", "m3") else 1.0) * (1.5 if natural else 1.0)
        elif strategy == "resurrection":
            weight = (4.0 if hard else 1.0) * (2.0 if end in MODE_FINALS else 1.0)
        elif strategy == "passion":
            weight = (3.0 if family == "m3" else 1.0) * (2.0 if start in SOFT_HEX else 1.0)
        elif strategy == "cadence":
            weight = 5.0 if end in (4, 7, 11) else 1.0
        elif strategy == "cadence_soft":
            weight = 5.0 if end in (5, 9, 0) else 1.0
        elif strategy == "diatonic_thirds":
            weight = 3.0 if family in ("M3", "m3") and natural else 1.0
        else:  # concerto
            weight = (2.0 if natural else 1.0) * (2.0 if end in MODE_FINALS else 1.0)
        result.append(weight)
    return result


def familywise_column_sums():
    """Exact structural cancellation certificate, one row per interval family.

    Every family's incidence rows sum to zero. Consequently *any* target
    and priority constant within each family produces zero forcing.
    """
    rows, _ = build_interval_jacobian()
    return [[sum(rows[i][j] for i in range(12 * family, 12 * (family + 1)))
             for j in range(12)] for family in range(3)]


def _linear_solve(matrix, rhs):
    """Gaussian elimination with partial pivoting and explicit singularity."""
    n = len(rhs)
    a = [list(row) + [rhs[i]] for i, row in enumerate(matrix)]
    scale = max((abs(v) for row in matrix for v in row), default=0.0)
    if not scale:
        raise ValueError("Tuning normal matrix is singular")
    for column in range(n):
        pivot = max(range(column, n), key=lambda i: abs(a[i][column]))
        if abs(a[pivot][column]) <= scale * 1e-14:
            raise ValueError("Tuning normal matrix is singular or numerically unresolved")
        a[column], a[pivot] = a[pivot], a[column]
        divisor = a[column][column]
        for j in range(column, n + 1):
            a[column][j] /= divisor
        for i in range(column + 1, n):
            factor = a[i][column]
            for j in range(column, n + 1):
                a[i][j] -= factor * a[column][j]
    answer = [0.0] * n
    for i in range(n - 1, -1, -1):
        answer[i] = a[i][n] - sum(a[i][j] * answer[j] for j in range(i + 1, n))
    if not all(math.isfinite(x) for x in answer):
        raise ValueError("Tuning solve overflowed")
    return answer


def solve_tuning(strategy="ET", targets=None, ridge=0.01, weights=None):
    """Solve min sum_i w_i(J_i x-b_i)^2 + ridge*||x||^2 with C=0.

    ``weights`` may override the named priorities with 36 nonnegative
    numbers. Targets have keys M3,m3,P5 and are interval corrections in
    cents relative to the archived equal-tempered pitch-class baseline.
    The exact forcing diagnostic treats the validated float64 decimal
    representations as rational values; the least-squares solve is float64.
    """
    rows, labels = build_interval_jacobian()
    target_input = QUARTER_COMMA_TARGETS if targets is None else targets
    if not isinstance(target_input, dict) or set(target_input) != {family for family, _ in INTERVAL_STEPS}:
        raise ValueError("Targets must have exactly the keys M3, m3, P5")
    target_values = {key: _finite(value, "target " + key) for key, value in target_input.items()}
    regularization = _finite(ridge, "ridge")
    if regularization < 0:
        raise ValueError("ridge must be nonnegative")
    if weights is None:
        priorities = strategy_weights(strategy)
    else:
        if not isinstance(weights, (list, tuple)) or len(weights) != 36:
            raise ValueError("Custom weights must contain 36 entries")
        priorities = [_finite(value, "weight") for value in weights]
    if any(w < 0 for w in priorities) or sum(priorities) <= 0:
        raise ValueError("Weights must be nonnegative with positive total")
    b = [target_values[family] for family, _, _ in labels]
    reduced = [row[1:] for row in rows]
    normal = [[sum(w * row[i] * row[j] for w, row in zip(priorities, reduced))
               + (regularization if i == j else 0.0)
               for j in range(11)] for i in range(11)]
    rhs = [sum(w * row[j] * value for w, row, value in zip(priorities, reduced, b))
           for j in range(11)]
    if not all(math.isfinite(v) for row in normal for v in row) or not all(math.isfinite(v) for v in rhs):
        raise ValueError("Tuning normal equations overflowed")
    exact_rhs = [sum((Fraction(str(w)) * row[j] * Fraction(str(value))
                     for w, row, value in zip(priorities, reduced, b)), Fraction(0))
                 for j in range(11)]
    exact_zero = all(value == 0 for value in exact_rhs)
    # An exact zero forcing has x=0 as a minimizer even if custom zero
    # weights leave the unregularized normal matrix rank deficient.
    x = [0.0] * 11 if exact_zero else _linear_solve(normal, rhs)
    full = [0.0] + x
    residuals = [sum(a * v for a, v in zip(row, full)) - value for row, value in zip(rows, b)]
    weighted_squared = sum(w * r * r for w, r in zip(priorities, residuals))
    normal_residual = [sum(normal[i][j] * x[j] for j in range(11)) - rhs[i] for i in range(11)]
    objective = weighted_squared + regularization * sum(v * v for v in x)
    forcing_squared = sum(v * v for v in rhs)
    if not all(math.isfinite(v) for v in (weighted_squared, objective, forcing_squared, *normal_residual)):
        raise ValueError("Tuning diagnostics overflowed")
    return {
        "status": "NUMERICAL_PITCH_CLASS_PROXY_ONLY",
        "strategy": strategy if weights is None else "custom",
        "targets_cents": target_values,
        "ridge": regularization,
        "offsets_cents": dict(zip(PITCH_CLASSES, full)),
        "weighted_rms_cents": math.sqrt(weighted_squared / sum(priorities)),
        "weighted_squared_residual": weighted_squared,
        "objective": objective,
        "forcing_norm": math.sqrt(forcing_squared),
        "forcing_exact_decimal_rationals": [str(value) for value in exact_rhs],
        "forcing_exactly_zero": exact_zero,
        "familywise_column_sums": familywise_column_sums(),
        "normal_equation_residual_max": max(abs(v) for v in normal_residual),
        "interval_rows": 36,
        "free_pitch_offsets": 11,
        "reference_pitch": "C",
        "chromatic_spelling_model": "TWELVE_PITCH_CLASS_PROXY",
        "physical_mapping_status": "UNBOUND",
        "physical_readiness": False,
        "hardware_commands_issued": 0,
    }


def ideal_string_plan(tuning, strings):
    """Project selected pitch classes onto four ideal string declarations.

    Each record requires id,pitch_class,base_frequency_hz,base_tension_N.
    Optional tension_bounds_N=[lo,hi] prefilters the ideal requested
    tension. No supplied number is treated as measured or authenticated.
    The four strings select four offsets; they do not realize eleven
    independent pitch controls or the full 36-row residual objective.
    """
    if not isinstance(strings, (list, tuple)) or len(strings) != 4:
        raise ValueError("The proposed object requires exactly four declared strings")
    if (not isinstance(tuning, dict) or not isinstance(tuning.get("offsets_cents"), dict)
            or set(tuning["offsets_cents"]) != set(PITCH_CLASSES)):
        raise ValueError("A complete twelve-pitch-class tuning result is required")
    offsets = {pc: _finite(value, "pitch offset") for pc, value in tuning["offsets_cents"].items()}
    if any(not isinstance(record, dict) for record in strings):
        raise ValueError("Each string declaration must be an object")
    ids = [record.get("id") for record in strings]
    if any(not isinstance(name, str) or not name for name in ids) or len(set(ids)) != 4:
        raise ValueError("Each physical string needs a unique nonempty identifier")
    result = []
    for record in strings:
        pc = record.get("pitch_class")
        if not isinstance(pc, str) or pc not in offsets:
            raise ValueError("Unknown pitch class on string " + record["id"])
        frequency = _finite(record.get("base_frequency_hz"), "base frequency")
        tension = _finite(record.get("base_tension_N"), "base tension")
        if frequency <= 0 or tension <= 0:
            raise ValueError("Declared base frequency and tension must be positive")
        cents = offsets[pc]
        try:
            frequency_ratio = 2.0 ** (cents / 1200.0)
            tension_ratio = 2.0 ** (cents / 600.0)
        except OverflowError as exc:
            raise ValueError("Requested offset overflows the ideal string model") from exc
        target_frequency, target_tension = frequency * frequency_ratio, tension * tension_ratio
        if not all(math.isfinite(v) and v > 0 for v in (target_frequency, target_tension, frequency_ratio, tension_ratio)):
            raise ValueError("Requested offset is outside finite ideal string range")
        bounds = record.get("tension_bounds_N")
        status = "UNRESOLVED_NO_TENSION_BOUNDS"
        if bounds is not None:
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
                raise ValueError("Tension bounds require lower and upper endpoints")
            low, high = (_finite(value, "tension bound") for value in bounds)
            if low < 0 or low > high:
                raise ValueError("Invalid tension bounds")
            status = ("WITHIN_DECLARED_IDEAL_STRING_BOUNDS" if low <= target_tension <= high
                      else "OUTSIDE_DECLARED_TENSION_BOUNDS")
        result.append({
            "string_id": record["id"], "pitch_class": pc, "offset_cents": cents,
            "frequency_ratio": frequency_ratio, "target_frequency_hz": target_frequency,
            "required_tension_ratio": tension_ratio, "target_tension_N": target_tension,
            "bound_status": status,
        })
    bound_statuses = {row["bound_status"] for row in result}
    status = ("REJECTED_BY_DECLARED_TENSION_BOUNDS" if "OUTSIDE_DECLARED_TENSION_BOUNDS" in bound_statuses
              else "UNRESOLVED_TENSION_BOUNDS" if "UNRESOLVED_NO_TENSION_BOUNDS" in bound_statuses
              else "WITHIN_DECLARED_IDEAL_BOUNDS_MAPPING_UNBOUND")
    return {
        "status": status, "strings": result,
        "physical_string_count": 4, "selected_pitch_classes": [s["pitch_class"] for s in strings],
        "full_twelve_pitch_objective_realized": False,
        "assumptions": ["fixed vibrating length", "fixed linear mass density", "ideal flexible string",
                        "declared independent tension bounds", "no calibrated bridge/clay/water coupling"],
        "physical_mapping_status": "UNBOUND",
        "physical_readiness": False, "hardware_commands_issued": 0,
    }


def make_score(events, tuning, reference_a4_hz=440):
    """Export a spelling-preserving ``fusion.score/1`` scheduling proxy.

    Required event keys: spelling,octave,voice,onset_s,duration_s,amplitude,
    tolerance_cents. An optional unique event_id is preserved. Voices are
    integer slots 1..4. Intervals are half-open, so contiguous same-voice
    events are allowed; overlapping same-voice notes are rejected.

    C# and Db remain different score labels but use the same offset and
    semitone baseline from the twelve-class tuning proxy. This is NOT a
    seventeen-independent-pitch engine. Manual tuning transitions have no
    calibrated timing or actuator mapping, and no command is issued.
    """
    if not isinstance(events, (list, tuple)) or not events:
        raise ValueError("Score events must be a nonempty list")
    if (not isinstance(tuning, dict) or not isinstance(tuning.get("offsets_cents"), dict)
            or set(tuning["offsets_cents"]) != set(PITCH_CLASSES)):
        raise ValueError("A complete twelve-pitch-class tuning result is required")
    offsets = {pc: _finite(value, "pitch offset") for pc, value in tuning["offsets_cents"].items()}
    reference = _finite(reference_a4_hz, "reference A4 frequency")
    if reference <= 0:
        raise ValueError("Reference A4 frequency must be positive")
    required = {"spelling", "octave", "voice", "onset_s", "duration_s", "amplitude", "tolerance_cents"}
    scheduled, ids = [], set()
    for index, event in enumerate(events):
        if not isinstance(event, dict) or not required <= set(event) or set(event) - required - {"event_id"}:
            raise ValueError("Score event has missing, unknown, or derived fields")
        spelling = event["spelling"]
        if not isinstance(spelling, str) or spelling not in SPELLING_TO_PROXY:
            raise ValueError("Score spelling must belong to the design's17-label vocabulary")
        octave, voice = event["octave"], event["voice"]
        if isinstance(octave, bool) or not isinstance(octave, int):
            raise ValueError("Octave must be an integer")
        if isinstance(voice, bool) or not isinstance(voice, int) or not 1 <= voice <= 4:
            raise ValueError("Voice must be an integer from1 through4")
        onset = _finite(event["onset_s"], "note onset")
        duration = _finite(event["duration_s"], "note duration")
        amplitude = _finite(event["amplitude"], "note amplitude")
        tolerance = _finite(event["tolerance_cents"], "pitch tolerance")
        if onset < 0 or duration <= 0 or not 0 <= amplitude <= 1 or tolerance < 0:
            raise ValueError("Invalid note timing, amplitude, or pitch tolerance")
        onset_q, duration_q = Fraction(str(event["onset_s"])), Fraction(str(event["duration_s"]))
        end_q = onset_q + duration_q
        try:
            end = float(end_q)
        except OverflowError as exc:
            raise ValueError("Note endpoint is outside finite timing range") from exc
        if not math.isfinite(end):
            raise ValueError("Note endpoint is outside finite timing range")
        event_id = event.get("event_id", "event-" + str(index + 1).zfill(4))
        if not isinstance(event_id, str) or not event_id or event_id in ids:
            raise ValueError("Score event identifiers must be unique nonempty strings")
        ids.add(event_id)
        proxy = SPELLING_TO_PROXY[spelling]
        semitone = PITCH_CLASSES.index(proxy)
        cents = offsets[proxy]
        try:
            equal_temperament = reference * 2.0 ** ((12 * (octave - 4) + semitone - 9) / 12.0)
            target = equal_temperament * 2.0 ** (cents / 1200.0)
        except (OverflowError, ZeroDivisionError) as exc:
            raise ValueError("Score pitch is outside finite frequency range") from exc
        if not all(math.isfinite(value) and value > 0 for value in (equal_temperament, target)):
            raise ValueError("Score pitch is outside finite frequency range")
        scheduled.append({
            "event_id": event_id, "spelling": spelling, "octave": octave,
            "target_Hz": target, "equal_temperament_Hz": equal_temperament,
            "offset_cents": cents, "proxy_pitch_class": proxy,
            "onset_s": onset, "duration_s": duration, "end_s": end,
            "voice": voice, "amplitude": amplitude, "tolerance_cents": tolerance,
            "_onset_q": onset_q, "_end_q": end_q,
        })
    scheduled.sort(key=lambda event: (event["_onset_q"], event["voice"], event["event_id"]))
    voice_end, previous_frequency = {}, {}
    transitions, boundaries = [], []
    for event in scheduled:
        voice, start, end = event["voice"], event["_onset_q"], event["_end_q"]
        if voice in voice_end and start < voice_end[voice]:
            raise ValueError("Overlapping score events request the same physical voice")
        voice_end[voice] = end
        requested = previous_frequency.get(voice) != event["target_Hz"]
        event["manual_tuning_requested"] = requested
        if requested:
            transitions.append({"event_id": event["event_id"], "voice": voice,
                                "requested_by_s": event["onset_s"], "target_Hz": event["target_Hz"],
                                "execution_status": "MANUAL_TUNING_TIMING_UNQUALIFIED"})
        previous_frequency[voice] = event["target_Hz"]
        boundaries.extend(((start, 1), (end, -1)))
    active, peak = 0, 0
    for _, delta in sorted(boundaries, key=lambda boundary: (boundary[0], boundary[1])):
        active += delta
        peak = max(peak, active)
        if active > 4:
            raise ValueError("Score polyphony exceeds four simultaneous physical strings")
    for event in scheduled:
        del event["_onset_q"], event["_end_q"]
    return {
        "schema": "fusion.score/1", "status": "SPELLING_PRESERVED_TWELVE_CLASS_PROXY",
        "reference_a4_hz": reference, "events": scheduled,
        "spelled_pitch_labels": list(SPELLINGS17),
        "pitch_model": "17_PRESERVED_LABELS_ALIASED_TO12_PITCH_CLASSES",
        "enharmonic_offsets_independent": False,
        "simultaneous_voice_limit": 4, "max_simultaneous_voices": peak,
        "manual_tuning_requested": bool(transitions), "manual_tuning_requests": transitions,
        "manual_tuning_transition_timing": "UNQUALIFIED",
        "physical_mapping_status": "UNBOUND", "physical_readiness": False,
        "hardware_commands_issued": 0,
    }
