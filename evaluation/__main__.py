"""Freeze and evaluate the prospective clay-history tuning experiment."""
import argparse
import json
from pathlib import Path
import sys

from .protocol import bind_contract, freeze, read_json, validate_registration


def write(path, value):
    content = json.dumps(value, indent=2, allow_nan=False) + "\n"
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")
    else:
        sys.stdout.write(content)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("demo")
    p.add_argument("--contract", type=Path, default=Path("experiments/clay_tuning_v1/contract.json"))
    p.add_argument("--output-dir", type=Path, default=Path("results/evaluation"))
    p = sub.add_parser("probe")
    p.add_argument("--contract", type=Path, default=Path("experiments/clay_tuning_v1/contract.json"))
    p.add_argument("--wav", required=True, type=Path)
    p.add_argument("--output", type=Path)
    p = sub.add_parser("observability")
    p.add_argument("--output", type=Path)
    p = sub.add_parser("bind")
    p.add_argument("core", type=Path)
    p.add_argument("binding", type=Path)
    p.add_argument("--origin", required=True, choices=["synthetic", "physical_measurement"])
    p.add_argument("--output", required=True, type=Path)
    p = sub.add_parser("freeze")
    p.add_argument("bound", type=Path)
    p.add_argument("development", type=Path)
    p.add_argument("blocks", type=Path)
    p.add_argument("--output", required=True, type=Path)
    p = sub.add_parser("decide")
    p.add_argument("registration", type=Path)
    p.add_argument("pre_action_features", type=Path)
    p.add_argument("--arm", default="fusion_full")
    p.add_argument("--output", type=Path)
    p = sub.add_parser("score")
    p.add_argument("registration", type=Path)
    p.add_argument("confirmation", type=Path)
    p.add_argument("--record-root", type=Path, help="Required raw/source-record directory for physical data")
    p.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            from .demo import run_demo
            write(None, run_demo(args.contract, args.output_dir))
        elif args.command == "probe":
            from .render import render_probe
            args.wav.parent.mkdir(parents=True, exist_ok=True)
            write(args.output, render_probe(read_json(args.contract), args.wav))
        elif args.command == "observability":
            from .observability import witnesses
            write(args.output, witnesses())
        elif args.command == "bind":
            write(args.output, bind_contract(read_json(args.core), read_json(args.binding), args.origin))
        elif args.command == "freeze":
            write(args.output, freeze(read_json(args.bound), read_json(args.development), read_json(args.blocks)))
        elif args.command == "decide":
            from .policies import choose_action
            registration = read_json(args.registration)
            validate_registration(registration)
            choice = choose_action(registration["policies"], args.arm, read_json(args.pre_action_features))
            write(args.output, {"requested_action": choice, "operational_action": "hold" if choice == "ABSTAIN" else choice,
                                "registration_sha256": registration["registration_sha256"],
                                "hardware_commands_issued": 0, "physical_readiness": False})
        else:
            from .evaluate import evaluate
            write(args.output, evaluate(read_json(args.registration), read_json(args.confirmation), args.record_root))
        return 0
    except (ValueError, KeyError, TypeError, OSError, ArithmeticError) as exc:
        sys.stderr.write("error: " + str(exc) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
