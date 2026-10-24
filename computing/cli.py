"""Dependency-free command line for the unified instrument's offline core."""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Nonfinite JSON number: " + value)


def load_json(path):
    # Preserve decimal tokens exactly, without binary-float reinterpretation.
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique,
                      parse_float=Fraction, parse_constant=_reject_constant)


def encoded(value):
    return json.dumps(value, indent=2, allow_nan=False,
                      default=lambda v: str(v) if isinstance(v, Fraction) else list(v)) + "\n"


def demo(output):
    from . import fusion_engine, object_adapter, memory, dyletsky
    from .panel_search import optimize
    output.mkdir(parents=True, exist_ok=True)
    fixture, adapter = object_adapter.replay()
    artifacts = {"fusion_results.json": fusion_engine.run(),
                 "object_contract.json": fixture,
                 "adapter_results.json": adapter,
                 "panel_result.json": optimize(fixture)}
    histories = []
    for t in ("0", "1", "10", "30", "60"):
        model = {"k0_N_per_m": ["99", "101"], "k1_N_per_m": ["396", "404"],
                 "deformation_m": ["0.00099", "0.00101"],
                 "initial_memory_m": "0.0002", "hold_time_s": t,
                 "tau_s": "10", "readout_error_N": "0.01"}
        low = memory.hold_bounds(model)
        model["initial_memory_m"] = "0.0008"
        high = memory.hold_bounds(model)
        # Actual field structure is checked explicitly, not a physical fit.
        from copy import deepcopy
        timed = deepcopy(fixture)
        timed["model"]["force_evaluation"] = "instantaneous snapshot at declared hold epoch"
        timed["model"]["hold_time_s"] = t
        timed["model"]["finite_acquisition_window_and_memory_drift"] = "CONSTANT_DEFORMATION_HOLD_PROPAGATED"
        timed["model"]["bound_origin"] = "computing.memory.hold_bounds rational enclosure"
        feature = timed["protocols"][1]["features"][0]
        feature["intervals"] = {"low_memory": low["force_N"], "high_memory": high["force_N"]}
        histories.append({"hold_time_s": t, "model": timed["model"], "low_memory": low, "high_memory": high,
                          "decision_panel": optimize(timed)})
    artifacts["memory_hold_results.json"] = histories
    artifacts["dyletsky_tuning.json"] = dyletsky.solve_tuning("diatonic_thirds")
    for name, data in artifacts.items():
        (output / name).write_text(encoded(data), encoding="utf-8")
    return {"status": "OFFLINE_SYNTHETIC_REPLAY_PASSED", "output_directory": str(output),
            "files": list(artifacts), "original_panel_checks": 600,
            "object_grouped_panel_checks": 16, "physical_readiness": False,
            "hardware_commands_issued": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("demo", help="Replay synthetic mathematics and create reviewable outputs")
    p.add_argument("--output-dir", type=Path, default=Path("results/demo"))
    for name in ("validate", "plan"):
        p = sub.add_parser(name)
        p.add_argument("contract", type=Path)
    p = sub.add_parser("decide")
    p.add_argument("contract", type=Path)
    p.add_argument("transcript", type=Path)
    p = sub.add_parser("memory", help="Exact constant-deformation hold bounds")
    p.add_argument("model", type=Path)
    p = sub.add_parser("music", help="Archived twelve-pitch proxy and optional four-string projection")
    p.add_argument("--strategy", default="diatonic_thirds")
    p.add_argument("--ridge", type=float, default=0.01)
    p.add_argument("--strings", type=Path)
    p.add_argument("--score", type=Path, help="Spelling-preserving event records")
    p = sub.add_parser("audit-run", help="Validate raw acquisition records without authenticating the laboratory")
    p.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = demo(args.output_dir)
        elif args.command in ("validate", "plan", "decide"):
            from . import object_adapter
            contract = load_json(args.contract)
            if args.command == "validate":
                ids, actions = object_adapter.validate(contract)
                result = {"status": "DECLARED_MODEL_CONTRACT_VALID", "hypotheses": len(ids),
                          "actions": len(actions), "protocols": len(contract["protocols"]),
                          "physical_readiness": False, "hardware_commands_issued": 0}
            elif args.command == "plan":
                from .panel_search import optimize
                result = optimize(contract)
            else:
                result = object_adapter.decide(contract, load_json(args.transcript))
        elif args.command == "memory":
            from .memory import hold_bounds
            result = hold_bounds(load_json(args.model))
        elif args.command == "music":
            from . import dyletsky
            result = {"tuning": dyletsky.solve_tuning(args.strategy, ridge=args.ridge)}
            if args.strings:
                result["string_plan"] = dyletsky.ideal_string_plan(result["tuning"], load_json(args.strings))
            if args.score:
                result["score"] = dyletsky.make_score(load_json(args.score), result["tuning"])
        else:
            from .acquisition import audit_run
            result = audit_run(args.manifest)
        sys.stdout.write(encoded(result))
        return 0
    except (ValueError, TypeError, KeyError, IndexError, ZeroDivisionError, OverflowError,
            OSError, ArithmeticError) as exc:
        sys.stderr.write("error: " + str(exc) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
