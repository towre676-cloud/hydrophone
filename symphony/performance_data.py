"""Reproducible statistical priors from actual performed piano MIDI.

ATEPP supplies named-pianist dynamics; ASAP supplies aligned beat timing.
These descriptive priors are not an orchestral performance model or a
listening-quality result. Raw corpus downloads remain outside source control.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import defaultdict, deque
from concurrent.futures import ProcessPoolExecutor
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import statistics as st
import struct
import zipfile


ATEPP_COMMIT = "088fb434ec1687d934282be1737bfe2518ea55cd"
ASAP_COMMIT = "afc815c75c42e83a79c03feb6da8a35e77d4c6b8"
ATEPP_URL = "https://drive.usercontent.google.com/download?id=1Df2KUdqvXtgvhvzx2D10YaQRbpP23rOS&export=download&confirm=t"
_ARCHIVES = {}
COMPOSER_ALIASES = {
    "Bach": "Johann Sebastian Bach", "Balakirev": "Mily Balakirev",
    "Beethoven": "Ludwig van Beethoven", "Brahms": "Johannes Brahms",
    "Chopin": "Frédéric Chopin", "Debussy": "Claude Debussy", "Glinka": "Mikhail Glinka",
    "Haydn": "Franz Joseph Haydn", "Liszt": "Franz Liszt", "Mozart": "Wolfgang Amadeus Mozart",
    "Prokofiev": "Sergei Prokofiev", "Rachmaninoff": "Sergei Rachmaninoff",
    "Ravel": "Maurice Ravel", "Schubert": "Franz Schubert", "Schumann": "Robert Schumann",
    "Scriabin": "Alexander Scriabin",
}


def _vlq(data, offset):
    value = 0
    for _ in range(4):
        if offset >= len(data):
            raise ValueError("Truncated MIDI variable integer")
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 127)
        if byte < 128:
            return value, offset
    raise ValueError("Overlong MIDI variable integer")


def parse_midi(data):
    """Read note timing/velocity in format 0/1 SMF, including running status.

    Note ends are key-release events; acoustic sustain is not inferred.
    Tempo changes from all tracks are used on the common tick timeline.
    """
    if data[:4] != b"MThd" or len(data) < 14:
        raise ValueError("Expected standard MIDI header")
    hlen = struct.unpack(">I", data[4:8])[0]
    if hlen < 6 or 8 + hlen > len(data):
        raise ValueError("Invalid MIDI header length")
    form, tracks, division = struct.unpack(">HHH", data[8:14])
    if form not in (0, 1) or not tracks or not division or division & 0x8000:
        raise ValueError("Only metrical format-0/1 MIDI is supported")
    offset, tempos, events = 8 + hlen, [(0, 500000)], []
    for track in range(tracks):
        if offset + 8 > len(data) or data[offset:offset + 4] != b"MTrk":
            raise ValueError("Missing MIDI track")
        length = struct.unpack(">I", data[offset + 4:offset + 8])[0]
        chunk = data[offset + 8:offset + 8 + length]
        if len(chunk) != length:
            raise ValueError("Truncated MIDI track")
        offset += 8 + length
        pos, tick, running, order = 0, 0, None, 0
        while pos < length:
            delta, pos = _vlq(chunk, pos)
            tick += delta
            if pos >= length:
                raise ValueError("Missing MIDI status")
            status = chunk[pos]
            if status < 128:
                if running is None:
                    raise ValueError("Running status without prior channel status")
                status = running
            else:
                pos += 1
            if status == 0xFF:
                if pos >= length:
                    raise ValueError("Missing MIDI meta type")
                typ = chunk[pos]
                pos += 1
                size, pos = _vlq(chunk, pos)
                value = chunk[pos:pos + size]
                if len(value) != size:
                    raise ValueError("Truncated MIDI meta event")
                pos += size
                if typ == 0x51 and size == 3:
                    tempo = int.from_bytes(value, "big")
                    if not tempo:
                        raise ValueError("Zero MIDI tempo")
                    tempos.append((tick, tempo))
                running = None
            elif status in (0xF0, 0xF7):
                size, pos = _vlq(chunk, pos)
                if pos + size > length:
                    raise ValueError("Truncated MIDI system event")
                pos += size
                running = None
            elif 0x80 <= status < 0xF0:
                running = status
                command, channel = status >> 4, status & 15
                size = 1 if command in (0xC, 0xD) else 2
                value = chunk[pos:pos + size]
                if len(value) != size or any(x >= 128 for x in value):
                    raise ValueError("Invalid MIDI channel data")
                pos += size
                if command in (8, 9):
                    events.append((tick, track, order, channel, value[0],
                                   value[1] if command == 9 else 0))
                order += 1
            else:
                raise ValueError("Unsupported MIDI system status")
    # Last tempo at a shared tick wins, matching sequential track merge.
    at_tick = dict(tempos)
    ticks = sorted(at_tick)
    seconds, elapsed, previous = [], 0.0, 0
    tempo = 500000
    for tick in ticks:
        elapsed += (tick - previous) * tempo / (division * 1e6)
        seconds.append(elapsed)
        previous, tempo = tick, at_tick[tick]
    def time_at(tick):
        i = bisect_right(ticks, tick) - 1
        return seconds[i] + (tick - ticks[i]) * at_tick[ticks[i]] / (division * 1e6)
    active, notes, unresolved = defaultdict(deque), [], 0
    for tick, track, order, channel, pitch, velocity in sorted(events):
        key = (track, channel, pitch)
        if velocity:
            active[key].append((tick, velocity))
        elif active[key]:
            start, strength = active[key].popleft()
            if tick > start:
                notes.append((time_at(start), time_at(tick), pitch, strength))
    unresolved = sum(len(x) for x in active.values())
    notes.sort()
    return {"notes": notes, "unclosed_notes": unresolved,
            "tempo_event_count": len(at_tick), "division": division}


def quantile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    p = (len(ordered) - 1) * fraction
    lo, hi = math.floor(p), math.ceil(p)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (p - lo)


def beat_statistics(text):
    beats = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[2] in {"b", "db", "bR"}:
            try:
                value = float(fields[0])
                if math.isfinite(value):
                    beats.append(value)
            except ValueError:
                pass
    beats = sorted(set(beats))
    intervals = [b - a for a, b in zip(beats, beats[1:]) if .08 <= b - a <= 5]
    if len(intervals) < 8:
        return {}
    median = st.median(intervals)
    local_ratios = [value / st.median(intervals[max(0, i - 4):i + 5])
                    for i, value in enumerate(intervals)]
    local_center = st.median(local_ratios)
    local_mad = st.median(abs(value - local_center) for value in local_ratios) / local_center
    return {"tempo_cv": st.pstdev(intervals) / st.mean(intervals),
            "local_tempo_mad": local_mad,
            "local_tempo_cv": st.pstdev(local_ratios) / st.mean(local_ratios),
            "beat_tempo_change": st.median(abs(b - a) / median for a, b in zip(intervals, intervals[1:])),
            "beat_interval_median_s": median, "annotated_beats": len(beats)}


def note_statistics(parsed):
    notes = parsed["notes"]
    if not notes:
        raise ValueError("No completed positive-duration notes")
    velocities = [x[3] for x in notes]
    # Upper note in each 30 ms onset cluster gives a descriptive melodic
    # key-gate proxy. It is not a score-aligned bow/breath articulation.
    melody, bucket = [], []
    start = notes[0][0]
    for note in notes:
        if note[0] - start <= .03:
            bucket.append(note)
        else:
            melody.append(max(bucket, key=lambda x: (x[2], x[3])))
            bucket, start = [note], note[0]
    if bucket:
        melody.append(max(bucket, key=lambda x: (x[2], x[3])))
    gates = [(a[1] - a[0]) / (b[0] - a[0]) for a, b in zip(melody, melody[1:])
             if .05 <= b[0] - a[0] <= 3]
    return {"note_count": len(notes), "duration_s": max(n[1] for n in notes),
            "velocity_median": st.median(velocities),
            "velocity_iqr": quantile(velocities, .75) - quantile(velocities, .25),
            "velocity_range": quantile(velocities, .95) - quantile(velocities, .05),
            "gate_ratio": st.median(gates) if gates else None,
            "unclosed_notes": parsed["unclosed_notes"]}


def _init_archives(archives):
    global _ARCHIVES
    _ARCHIVES = {name: zipfile.ZipFile(path) for name, path in archives.items()}


def _analyze(job):
    source, archive_path, composer, work, artist, quality, annotation_path = job
    result = {"dataset": source, "path": archive_path, "composer": composer,
              "work": work, "performer": artist or "", "quality": quality,
              "split": "holdout" if int(hashlib.sha256((composer + "|" + work).encode()).hexdigest()[:8], 16) % 5 == 0 else "fit"}
    try:
        data = _ARCHIVES[source].read(archive_path)
        result.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        result.update(note_statistics(parse_midi(data)))
        if annotation_path:
            result.update(beat_statistics(_ARCHIVES[source].read(annotation_path).decode("utf-8")))
        result["status"] = "parsed"
        result["eligible_for_prior"] = not any(tag in quality.lower() for tag in ("low quality", "background noise", "corrupted", "applause"))
    except (ValueError, KeyError, IndexError, struct.error, UnicodeError) as exc:
        result.update(status="rejected", error=str(exc), eligible_for_prior=False)
    return result


def balanced_statistic(rows, field, grouping):
    grouped = defaultdict(lambda: defaultdict(list))
    for row in rows:
        value = row.get(field)
        if value is not None and math.isfinite(value):
            grouped[row[grouping]][row["work"]].append(value)
    # Equal work weight within person/composer, then equal group weight.
    group_values = [st.median(st.median(v) for v in works.values()) for works in grouped.values()]
    return st.median(group_values) if group_values else None


def build_profile(atepp_zip, atepp_metadata, asap_zip, output, workers=4):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    jobs = []
    with zipfile.ZipFile(atepp_zip) as z:
        names = {n.split("/", 1)[1]: n for n in z.namelist() if n.startswith("ATEPP-1.2/") and n.endswith(".mid")}
        basename_index = defaultdict(list)
        for archive_path in names.values():
            basename_index[Path(archive_path).name].append(archive_path)
        metadata = list(csv.DictReader(Path(atepp_metadata).open(encoding="utf-8")))
        for row in metadata:
            path = row["midi_path"]
            resolved = names.get(path)
            if resolved is None:
                candidates = basename_index[Path(path).name]
                # The released ZIP contains mangled Unicode directory names;
                # unique unchanged numeric performance filenames retain identity.
                if len(candidates) != 1:
                    raise ValueError("ATEPP metadata path has no unique archive identity: " + path)
                resolved = candidates[0]
            jobs.append(("ATEPP", resolved, row["composer"], row["composition_id"], row["artist"], row["quality"], None))
    with zipfile.ZipFile(asap_zip) as z:
        prefix = z.namelist()[0].split("/")[0] + "/"
        metadata = list(csv.DictReader(io.StringIO(z.read(prefix + "metadata.csv").decode())))
        for row in metadata:
            jobs.append(("ASAP", prefix + row["midi_performance"], row["composer"], row["title"], "", "", prefix + row["performance_annotations"]))
    archives = {"ATEPP": str(atepp_zip), "ASAP": str(asap_zip)}
    results = []
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_archives, initargs=(archives,)) as pool:
        for i, row in enumerate(pool.map(_analyze, jobs, chunksize=16)):
            results.append(row)
            if (i + 1) % 1000 == 0:
                print(json.dumps({"processed": i + 1, "planned": len(jobs)}), flush=True)
    seen = set()
    for row in results:
        if row["status"] == "parsed":
            row["duplicate_bytes"] = row["sha256"] in seen
            seen.add(row["sha256"])
            if row["duplicate_bytes"]:
                row["eligible_for_prior"] = False
    parsed = [r for r in results if r["status"] == "parsed"]
    fit = [r for r in parsed if r["eligible_for_prior"] and r["split"] == "fit"]
    atepp = [r for r in fit if r["dataset"] == "ATEPP"]
    asap = [r for r in fit if r["dataset"] == "ASAP"]
    summaries = {}
    fit_ids = {id(r) for r in fit}
    for source in archives:
        items = [r for r in parsed if r["dataset"] == source]
        summaries[source] = {"parsed_performances": len(items), "notes": sum(r["note_count"] for r in items),
                             "hours": sum(r["duration_s"] for r in items) / 3600,
                             "named_performers": sorted({r["performer"] for r in items if r["performer"]}),
                             "composers": sorted({r["composer"] for r in items}),
                             "fit_eligible_performances": sum(id(r) in fit_ids for r in items)}
    manifest = {"schema": "symphony.performance-source-manifest/1", "ATEPP": {
        "source": "https://github.com/tangjjbetsy/ATEPP", "version": "1.2", "metadata_commit": ATEPP_COMMIT, "license": "CC-BY-4.0",
        "archive_url": ATEPP_URL, "archive_sha256": hashlib.sha256(Path(atepp_zip).read_bytes()).hexdigest(),
        "metadata_sha256": hashlib.sha256(Path(atepp_metadata).read_bytes()).hexdigest(),
        "kind": "automatic MIDI transcriptions of recorded piano performances; not original audio"},
        "ASAP": {"source": "https://github.com/fosfrancesco/asap-dataset", "commit": ASAP_COMMIT,
        "license": "CC-BY-NC-SA-4.0", "archive_sha256": hashlib.sha256(Path(asap_zip).read_bytes()).hexdigest(),
        "kind": "performed MIDI and aligned beat annotations; distinct human identities not inferred from filenames"}}
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    statistics = {"median_local_tempo_mad": balanced_statistic(asap, "local_tempo_mad", "composer"),
                  "median_local_tempo_cv": balanced_statistic(asap, "local_tempo_cv", "composer"),
                  "median_tempo_cv": balanced_statistic(asap, "tempo_cv", "composer"),
                  "median_beat_tempo_change": balanced_statistic(asap, "beat_tempo_change", "composer"),
                  "median_velocity_iqr": balanced_statistic(atepp, "velocity_iqr", "performer"),
                  "median_velocity_range": balanced_statistic(atepp, "velocity_range", "performer"),
                  "median_gate_ratio": balanced_statistic(atepp, "gate_ratio", "performer")}
    profile = {"schema": "symphony.performance-profile/1", "performance_count": len(parsed),
               "composer_count": len({COMPOSER_ALIASES.get(r["composer"], r["composer"]) for r in parsed}), "performer_count": len({r["performer"] for r in parsed if r["performer"]}),
               "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
               "analysis_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "performance_statistics": statistics, "per_dataset": summaries,
               "fit_performances": len(fit),
               "named_performers_in_fit": len({r["performer"] for r in fit if r["performer"]}),
               "fit_note_records": sum(r["note_count"] for r in fit), "holdout_performances": sum(r["split"] == "holdout" for r in parsed),
               "parse_failures": len(results) - len(parsed), "exact_byte_duplicates": sum(r.get("duplicate_bytes", False) for r in parsed),
               "provenance": {"timing_fields": "ASAP fit split; equal composer/work weight. Local CV divides each beat interval by its centered 9-beat running median. Local MAD is the median absolute deviation of those ratios divided by their median, with no Gaussian rescaling. Global CV also contains written/form tempo changes.", "dynamic_fields": "ATEPP fit split; equal named pianist/work weight", "gate_fields": "ATEPP upper-note onset-cluster key-release proxy; not orchestral articulation", "split": "SHA256(composer|work) mod5; holdout=0; fit statistics exclude holdout and flagged low-quality/noisy/corrupted/applause ATEPP records"},
               "limitations": ["Statistical priors, not a trained orchestral model or a listening-quality guarantee.", "Piano-specific key releases and velocity distributions require authored orchestral mapping.", "Combined composer identities use the explicit ASAP-to-ATEPP alias map; original labels remain in the index.", "ASAP performer identities are not authenticated; named performer count comes only from ATEPP metadata.", "ATEPP transcriptions can contain note/timing/velocity errors; quality filters and robust aggregation reduce but do not remove them."]}
    (output / "performance_profile.json").write_text(json.dumps(profile, indent=2) + "\n")
    (output / "performance_sources.json").write_text(json.dumps(manifest, indent=2) + "\n")
    fields = sorted({k for row in results for k in row})
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fields)
    writer.writeheader()
    writer.writerows(results)
    index_bytes = stream.getvalue().encode("utf-8")
    compressed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=compressed, mtime=0) as packed:
        packed.write(index_bytes)
    (output / "performance_index.csv.gz").write_bytes(compressed.getvalue())
    print(json.dumps({"parsed": len(parsed), "notes": sum(r["note_count"] for r in parsed), "named_performers": profile["performer_count"], "fit": len(fit), "statistics": statistics}, indent=2), flush=True)
    return profile


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_sources(root=Path("results/corpora")):
    """Fetch three public, byte-pinned inputs; no account/login is used."""
    from urllib.request import Request, urlopen
    root = Path(root)
    inputs = [
        (root / "ATEPP-1.2.zip", ATEPP_URL,
         "c319ba3eeed06aaa23e808c00db7c3a6f29a06d848af26272189e42f0101c0b8"),
        (root / "ATEPP-metadata-1.2.csv",
         f"https://raw.githubusercontent.com/tangjjbetsy/ATEPP/{ATEPP_COMMIT}/ATEPP-metadata-1.2.csv",
         "b6bed1190cb85e607282fe4b761bc42d017f8144851940a4103aaa1a1d84536d"),
        (root / "asap/asap.zip",
         f"https://codeload.github.com/fosfrancesco/asap-dataset/zip/{ASAP_COMMIT}",
         "11d2fb8b68acb3fa8468f7ddf8b546a7f8df6f6dc72e672d28a20d94128890e0"),
    ]
    for path, url, expected in inputs:
        if path.exists() and _file_sha256(path) == expected:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".part")
        try:
            with urlopen(Request(url, headers={"User-Agent": "HydrophoneSymphonyResearch/1.0"}), timeout=60) as response, temporary.open("wb") as stream:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    stream.write(chunk)
            if _file_sha256(temporary) != expected:
                raise ValueError("Performance source changed: " + url)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return {"files": len(inputs), "download_bytes": sum(path.stat().st_size for path, _, _ in inputs)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--atepp-zip", type=Path, default=Path("results/corpora/ATEPP-1.2.zip"))
    p.add_argument("--atepp-metadata", type=Path, default=Path("results/corpora/ATEPP-metadata-1.2.csv"))
    p.add_argument("--asap-zip", type=Path, default=Path("results/corpora/asap/asap.zip"))
    p.add_argument("--output", type=Path, default=Path("data/symphony"))
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--download", action="store_true", help="Download/verify byte-pinned public corpus inputs first")
    args = p.parse_args()
    if args.download:
        print(json.dumps(fetch_sources()), flush=True)
    build_profile(args.atepp_zip, args.atepp_metadata, args.asap_zip, args.output, args.workers)


if __name__ == "__main__":
    main()
