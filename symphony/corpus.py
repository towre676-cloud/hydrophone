"""Reproducible OpenScore ingestion and composer-balanced symbolic priors.

The corpus contains NOTATED scores, not recorded performers. These statistics
describe interval, rhythm and score-marking distributions. They do not measure
human rubato, vibrato, instrumental timbre or listener preference. Parsing uses
the master score only; excerpt/part copies and embedded pictures are excluded.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import hashlib
import json
from pathlib import Path, PurePosixPath
import urllib.request
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DURATIONS = {"long": Fraction(16), "breve": Fraction(8), "whole": Fraction(4),
             "half": Fraction(2), "quarter": Fraction(1), "eighth": Fraction(1, 2),
             "16th": Fraction(1, 4), "32nd": Fraction(1, 8), "64th": Fraction(1, 16),
             "128th": Fraction(1, 32), "256th": Fraction(1, 64), "512th": Fraction(1, 128),
             "1024th": Fraction(1, 256)}
GRACE_TAGS = {"acciaccatura", "appoggiatura", "grace4", "grace16", "grace32",
              "grace8after", "grace16after", "grace32after"}
HISTOGRAMS = ("interval_counts", "interval_transition_counts", "duration_counts",
              "pitch_class_counts", "dynamic_marking_counts", "articulation_counts")


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(2**20), b""):
            h.update(block)
    return h.hexdigest()


def git_blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def empty_profile():
    return {**{k: Counter() for k in HISTOGRAMS}, "score_count": 0,
            "notehead_count": 0, "pitched_attack_count": 0,
            "chord_event_count": 0, "grace_chord_count": 0,
            "unresolved_duration_count": 0, "tempo_mark_count": 0,
            "melodic_transition_count": 0}


def _duration(element, tuplets):
    explicit = element.findtext("duration")
    if explicit:
        value = 4 * Fraction(explicit)
    else:
        value = DURATIONS.get(element.findtext("durationType"))
        if value is None:
            return None
    dots = int(element.findtext("dots", "0"))
    if dots < 0 or dots > 4:
        raise ValueError("Unsupported dot count")
    value *= sum((Fraction(1, 2**j) for j in range(dots + 1)), Fraction())
    current, visited = element.findtext("Tuplet"), set()
    while current:
        if current in visited or current not in tuplets:
            return None
        visited.add(current)
        ratio, current = tuplets[current]
        value *= ratio
    return value if value > 0 else None


def _is_tied_continuation(note, tie_ids):
    if any(e.get("type") == "Tie" and e.find("prev") is not None
           for e in note.findall("Spanner")):
        return True
    return any(e.get("id") in tie_ids for e in note.findall("endSpanner"))


def parse_mscx(data):
    """Count score heads and top-note melodic transitions per staff/voice.

    Duration units are quarter-note beats. Grace chords are counted separately,
    tied continuations do not create a melodic attack, and rests of at least
    four quarter beats reset melodic/interval-transition continuity. Large
    melodic leaps remain in the audit totals but intervals beyond +/-24
    semitones are not used as compositional priors. Repeats are not unfolded.
    """
    root = ET.fromstring(data)
    score = root.find("Score") if root.tag != "Score" else root
    if score is None:
        raise ValueError("MuseScore master Score missing")
    profile = empty_profile()
    profile["score_count"] = 1
    parts = {}
    for part in score.findall("Part"):
        label = part.findtext("trackName", "unknown")
        for staff in part.findall("Staff"):
            parts[staff.get("id")] = label
    instruments = Counter(parts.values())
    master_staves = score.findall("Staff")
    tie_ids = {e.get("id") for staff in master_staves for e in staff.iter("Tie") if e.get("id")}
    tuplets = {}
    for item in (e for staff in master_staves for e in staff.iter("Tuplet")):
        if item.get("id"):
            normal, actual = item.findtext("normalNotes"), item.findtext("actualNotes")
            if normal and actual and int(normal) > 0 and int(actual) > 0:
                tuplets[item.get("id")] = (Fraction(int(normal), int(actual)), item.findtext("Tuplet"))
    for staff in score.findall("Staff"):
        previous_pitch, previous_interval = {}, {}
        for measure in staff.findall("Measure"):
            voices = measure.findall("voice") or [measure]
            for vi, voice in enumerate(voices):
                for element in voice:
                    if element.tag == "Rest":
                        duration = _duration(element, tuplets)
                        if duration is None or duration >= 4:
                            previous_pitch.pop(vi, None)
                            previous_interval.pop(vi, None)
                        continue
                    if element.tag == "Dynamic":
                        subtype = element.findtext("subtype", "unknown")
                        profile["dynamic_marking_counts"][subtype] += 1
                        continue
                    if element.tag == "Tempo":
                        profile["tempo_mark_count"] += 1
                        continue
                    if element.tag != "Chord":
                        continue
                    profile["chord_event_count"] += 1
                    notes = []
                    attacks = []
                    for note in element.findall("Note"):
                        raw = note.findtext("pitch")
                        if raw is None:
                            continue
                        pitch = int(raw)
                        if not 0 <= pitch <= 127:
                            raise ValueError("Pitch outside MIDI range")
                        notes.append(pitch)
                        profile["notehead_count"] += 1
                        profile["pitch_class_counts"][str(pitch % 12)] += 1
                        if not _is_tied_continuation(note, tie_ids):
                            attacks.append(pitch)
                    if any(element.find(tag) is not None for tag in GRACE_TAGS):
                        profile["grace_chord_count"] += 1
                        continue
                    profile["pitched_attack_count"] += len(attacks)
                    duration = _duration(element, tuplets)
                    if duration is None:
                        profile["unresolved_duration_count"] += 1
                    elif attacks:
                        profile["duration_counts"][str(duration)] += 1
                    for articulation in element.findall("Articulation"):
                        label = articulation.findtext("subtype", articulation.findtext("symbol", "unknown"))
                        profile["articulation_counts"][label] += 1
                    if not attacks:
                        continue
                    pitch = max(attacks)
                    if vi in previous_pitch:
                        interval = pitch - previous_pitch[vi]
                        profile["melodic_transition_count"] += 1
                        if abs(interval) <= 24:
                            profile["interval_counts"][str(interval)] += 1
                            if vi in previous_interval:
                                key = str(previous_interval[vi]) + "," + str(interval)
                                profile["interval_transition_counts"][key] += 1
                            previous_interval[vi] = interval
                        else:
                            previous_interval.pop(vi, None)
                    previous_pitch[vi] = pitch
    if not profile["notehead_count"]:
        raise ValueError("No pitched noteheads found")
    profile["instrument_staves"] = dict(instruments)
    return profile


def merge_profile(target, source):
    for key in HISTOGRAMS:
        target[key].update(source[key])
    for key, value in source.items():
        if key not in HISTOGRAMS and isinstance(value, int):
            target[key] += value


def balanced_probabilities(composers, key):
    """Equal mixture of per-composer normalized histograms with observations."""
    eligible = [p[key] for p in composers.values() if sum(p[key].values()) > 0]
    sums = defaultdict(float)
    for histogram in eligible:
        total = sum(histogram.values())
        for item, value in histogram.items():
            sums[item] += value / total / len(eligible)
    return dict(sorted(sums.items()))


def _safe_member_index(archive):
    index = {}
    for item in archive.infolist():
        p = PurePosixPath(item.filename)
        if p.is_absolute() or ".." in p.parts:
            raise ValueError("Unsafe archive member")
        if len(p.parts) < 2:
            if item.is_dir():
                continue
            raise ValueError("Unrooted archive member")
        relative = str(PurePosixPath(*p.parts[1:]))
        if relative in index and not item.is_dir():
            raise ValueError("Duplicate archive member")
        index[relative] = item
    return index


def acquire(source, cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (source["id"] + ".zip")
    if path.exists() and file_sha256(path) == source["archive_sha256"]:
        return path
    temp = path.with_suffix(".part")
    with urllib.request.urlopen(source["archive_url"], timeout=60) as response, temp.open("wb") as stream:
        while block := response.read(2**20):
            stream.write(block)
    if file_sha256(temp) != source["archive_sha256"]:
        temp.unlink(missing_ok=True)
        raise ValueError("Pinned corpus archive SHA256 mismatch")
    temp.replace(path)
    return path


def ingest(sources_path, files_path, cache, output):
    sources = json.loads(Path(sources_path).read_text(encoding="utf-8"))
    expected = [json.loads(line) for line in Path(files_path).read_text(encoding="utf-8").splitlines() if line]
    per_source = defaultdict(list)
    for row in expected:
        per_source[row["source_id"]].append(row)
    aggregate, composers, seen, index, failures = empty_profile(), {}, set(), [], []
    for source in sources["sources"]:
        path = acquire(source, cache)
        with zipfile.ZipFile(path) as archive:
            members = _safe_member_index(archive)
            actual = {n for n in members if n.startswith("scores/") and n.endswith(".mscx")}
            required = {row["path"] for row in per_source[source["id"]]}
            if actual != required:
                raise ValueError("Pinned archive score set differs from manifest")
            for number, row in enumerate(per_source[source["id"]]):
                data = archive.read(members[row["path"]])
                if len(data) != row["bytes"] or git_blob_sha(data) != row["git_blob_sha1"]:
                    raise ValueError("Source score bytes differ from pinned Git blob")
                sha = hashlib.sha256(data).hexdigest()
                composer = row["composer"]
                record = {**row, "sha256": sha, "duplicate_bytes": sha in seen}
                if sha in seen:
                    index.append(record)
                    continue
                seen.add(sha)
                try:
                    profile = parse_mscx(data)
                except (ET.ParseError, ValueError, TypeError) as exc:
                    record["parse_error"] = str(exc)
                    failures.append({"source_id": source["id"], "path": row["path"], "reason": str(exc)})
                    index.append(record)
                    continue
                record.update({k: v for k, v in profile.items() if k not in HISTOGRAMS})
                composers.setdefault(composer, empty_profile())
                merge_profile(composers[composer], profile)
                merge_profile(aggregate, profile)
                index.append(record)
                if number % 100 == 0:
                    print(source["id"], number + 1, "/", len(required), "scores", flush=True)
    balanced = {key.replace("_counts", "_probabilities"): balanced_probabilities(composers, key)
                for key in HISTOGRAMS}
    profile = {"schema": "fusion.music-corpus-profile/1", "evidence_type": "NOTATED_SCORE_STATISTICS",
               "sources": sources["sources"], "source_file_count": len(expected),
               "unique_raw_score_count": len(seen), "parsed_score_count": aggregate["score_count"],
               "composer_count": len(composers), "composers": sorted(composers),
               "aggregate": aggregate, "balanced": balanced,
               "composer_profiles": dict(sorted(composers.items())), "parse_failures": failures,
               "parser_semantics": parse_mscx.__doc__.strip(),
               "limits": ["Composer identities are score metadata; no recorded-performer count is implied.",
                          "Byte deduplication is not semantic work/edition deduplication.",
                          "These priors do not estimate performed timing, vibrato or listener preference.",
                          "A top-note chord reduction is used per staff/voice; inner-voice counterpoint is not reconstructed.",
                          "Repeat signs are not unfolded; numeric durations describe notated events."]}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "corpus_profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "corpus_index.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in index), encoding="utf-8")
    return profile


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=ROOT / "symphony/corpus_sources/sources.json")
    parser.add_argument("--files", type=Path, default=ROOT / "symphony/corpus_sources/files.jsonl")
    parser.add_argument("--cache", type=Path, default=ROOT / "results/symphony_corpus")
    parser.add_argument("--output", type=Path, default=ROOT / "data/symphony")
    args = parser.parse_args(argv)
    result = ingest(args.sources, args.files, args.cache, args.output)
    print(json.dumps({k: result[k] for k in ("source_file_count", "unique_raw_score_count", "parsed_score_count", "composer_count")}, indent=2))


if __name__ == "__main__":
    main()
