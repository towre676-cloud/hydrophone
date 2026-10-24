"""Build a playable, corpus-conditioned orchestral suite."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from .compose import compose, score_statistics, select_palette
from .performance import perform


ROOT = Path(__file__).resolve().parents[1]


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def build(args):
    from .render import render_score, encode_mp3
    from .midi import write_midi
    from .player import generate_player
    profile = _read(args.profile)
    performance_profile = _read(args.performance_profile)
    if not profile.get("parsed_score_count") or not profile.get("balanced"):
        raise ValueError("Build needs a parsed corpus profile; run the corpus ingestion first")
    composition_profile = select_palette(profile, args.palette)
    written = compose(composition_profile, seed=args.seed, title=args.title, bars_scale=args.bars_scale,
                      tuning_profile=_read(args.tuning_profile), tonic_pc=args.tonic_pc)
    score = perform(written, profile=performance_profile, seed=args.seed)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    _write(output / "written_score.json", written)
    _write(output / "performed_score.json", score)
    if args.preview_seconds:
        score["events"] = [e for e in score["events"] if e["start_s"] < args.preview_seconds]
        for event in score["events"]:
            event["duration_s"] = min(event["duration_s"], args.preview_seconds - event["start_s"])
        score["duration_s"] = args.preview_seconds
    with tempfile.TemporaryDirectory(prefix="hydrophone-music-") as temporary:
        wav = Path(temporary) / "performance.wav"
        render = render_score(score, wav, sample_rate=args.sample_rate)
        encoding = encode_mp3(wav, output / "performance.mp3", bitrate=args.bitrate)
        midi = write_midi(score, output / "performance.mid")
        player = generate_player(score, output / "performance.mp3", output / "player.html",
                                 midi_path=output / "performance.mid")
    render["output_wav"] = "transient PCM master; reproduce with the recorded build parameters"
    render["pcm_master_preserved"] = False
    receipt = {"schema": "symphony.build/1", "title": args.title, "seed": args.seed,
               "build_parameters": {"bars_scale": args.bars_scale, "tonic_pc": args.tonic_pc,
                                    "palette": args.palette, "sample_rate": args.sample_rate,
                                    "bitrate": args.bitrate},
               "composition": score_statistics(written), "render": render,
               "mp3": encoding, "midi": midi, "player": player,
               "corpus_profile_sha256": hashlib.sha256(args.profile.read_bytes()).hexdigest(),
               "performance_profile_sha256": hashlib.sha256(args.performance_profile.read_bytes()).hexdigest(),
               "corpus": {k: profile[k] for k in ("source_file_count", "parsed_score_count", "composer_count")},
               "performed_data": {k: performance_profile.get(k) for k in
                                  ("performance_count", "performer_count", "fit_performances", "holdout_performances")},
               "performance": score["performance"], "physical_hardware_commands_issued": 0,
               "quality_scope": "Sampled virtual orchestra with corpus-conditioned composition and performance priors; aesthetic quality requires listening."}
    _write(output / "build_receipt.json", receipt)
    print(json.dumps({"player": str(output / "player.html"), "audio": str(output / "performance.mp3"),
                      "duration_s": player["duration_s"], "note_events": len(score["events"]),
                      "score_composers": profile["composer_count"],
                      "named_pianists": performance_profile.get("performer_count")}, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("compose", "build"):
        p = sub.add_parser(name)
        p.add_argument("--profile", type=Path, default=ROOT / "data/symphony/corpus_profile.json")
        p.add_argument("--tuning-profile", type=Path, default=ROOT / "data/symphony/dyletsky_profile.json")
        p.add_argument("--seed", type=int, default=20261024)
        p.add_argument("--title", default="The Water Remembers")
        p.add_argument("--bars-scale", type=int, default=1)
        p.add_argument("--tonic-pc", type=int, default=2, choices=range(12))
        p.add_argument("--palette", choices=("all", "romantic", "luminous", "classical"), default="all")
        if name == "compose":
            p.add_argument("--output", type=Path, required=True)
        else:
            p.add_argument("--performance-profile", type=Path,
                           default=ROOT / "data/symphony/performance_profile.json")
            p.add_argument("--output-dir", type=Path, default=ROOT / "results/symphony")
            p.add_argument("--sample-rate", type=int, default=32000)
            p.add_argument("--bitrate", default="192k", choices=("128k", "160k", "192k", "256k", "320k"))
            p.add_argument("--preview-seconds", type=float)
    args = parser.parse_args(argv)
    try:
        if args.command == "compose":
            score = compose(select_palette(_read(args.profile), args.palette), seed=args.seed, title=args.title,
                            bars_scale=args.bars_scale, tuning_profile=_read(args.tuning_profile),
                            tonic_pc=args.tonic_pc)
            _write(args.output, score)
            print(json.dumps(score_statistics(score), indent=2))
        else:
            build(args)
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, ImportError) as exc:
        sys.stderr.write("error: " + str(exc) + "\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
