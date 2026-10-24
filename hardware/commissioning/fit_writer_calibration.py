"""Fit installed affine writer channels against frozen reference measurements.

Development rows determine the fit; distinct held-out reference levels check
it. Finite-point residuals are empirical evidence, not a uniform calibration
bound. The generated writer-calibration/1 proposal always remains unqualified.
Complete independent domain/error/timing review before enabling the readout.
"""
from __future__ import annotations

import argparse
import copy
import csv
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path

REQUIRED = ("channel", "split", "level_id", "direction", "approach", "raw_V",
            "reference_SI", "reference_error_SI", "raw_error_V", "temperature_C",
            "excitation_V", "settled", "reference_evidence_id", "data_origin")


def finite(value, label):
    if value is None or isinstance(value, bool):
        raise ValueError(label+" must be finite")
    try:
        x = F(str(value))
        y = float(x)
    except (TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
        raise ValueError(label+" must be finite") from exc
    if not math.isfinite(y):
        raise ValueError(label+" must be finite")
    return x


def read_references(path):
    rows = []
    with Path(path).open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source, strict=True)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or not set(REQUIRED) <= set(reader.fieldnames):
            raise ValueError("Reference CSV needs unique required headers: "+", ".join(REQUIRED))
        for line, row in enumerate(reader, 2):
            if None in row or any(row.get(k) is None for k in REQUIRED):
                raise ValueError(f"Incomplete reference CSV row {line}")
            if row["channel"] not in ("force", "position", "temperature_C") or row["split"] not in ("development", "validation"):
                raise ValueError("Unknown channel or frozen development/validation split")
            approaches = ("heating", "cooling") if row["channel"] == "temperature_C" else ("loading", "unloading")
            if row["direction"] not in ("positive", "negative") or row["approach"] not in approaches:
                raise ValueError("Signed direction and appropriate loading/unloading or heating/cooling approach must be explicit")
            if row["settled"].casefold() != "true":
                raise ValueError("Only independently checked settled reference rows can be fitted")
            if not row["level_id"] or not row["reference_evidence_id"]:
                raise ValueError("Reference level and evidence identities are required")
            if row["data_origin"] not in ("physical_reference_measurement_declared", "synthetic_demo"):
                raise ValueError("Reference measurement origin must be explicit")
            parsed = {**row, "source_line": line}
            for key in ("raw_V", "reference_SI", "reference_error_SI", "raw_error_V", "temperature_C", "excitation_V"):
                parsed[key] = finite(row[key], key)
            if parsed["reference_error_SI"] < 0 or parsed["raw_error_V"] < 0 or parsed["excitation_V"] <= 0:
                raise ValueError("Reference/raw errors must be nonnegative and excitation positive")
            if ((parsed["reference_SI"] > 0 and row["direction"] != "positive") or
                (parsed["reference_SI"] < 0 and row["direction"] != "negative")):
                raise ValueError("Declared direction conflicts with signed SI reference")
            rows.append(parsed)
    if not rows or len({r["data_origin"] for r in rows}) != 1:
        raise ValueError("Need one explicit, unmixed reference evidence origin")
    return rows


def _fit_channel(rows, channel):
    dev = [r for r in rows if r["channel"] == channel and r["split"] == "development"]
    val = [r for r in rows if r["channel"] == channel and r["split"] == "validation"]
    for name, subset in (("development", dev), ("validation", val)):
        if len(subset) < 4:
            raise ValueError(channel+" needs at least four "+name+" rows")
        approaches = {"heating", "cooling"} if channel == "temperature_C" else {"loading", "unloading"}
        if ((channel != "temperature_C" and {r["direction"] for r in subset} != {"positive", "negative"}) or
            {r["approach"] for r in subset} != approaches):
            raise ValueError(channel+" "+name+" rows must cover the required directions and approaches")
    if {r["level_id"] for r in dev} & {r["level_id"] for r in val}:
        raise ValueError("Held-out reference level IDs overlap development")
    if ({r["reference_SI"] for r in dev} & {r["reference_SI"] for r in val}) - {F(0)}:
        raise ValueError("Nonzero held-out reference levels must be distinct from development")
    if len({r["raw_V"] for r in dev}) < 3 or len({r["reference_SI"] for r in dev}) < 3:
        raise ValueError("Development fit needs at least three distinct raw and reference levels")
    mean_raw = sum(r["raw_V"] for r in dev)/len(dev)
    mean_ref = sum(r["reference_SI"] for r in dev)/len(dev)
    denominator = sum((r["raw_V"]-mean_raw)**2 for r in dev)
    slope = sum((r["raw_V"]-mean_raw)*(r["reference_SI"]-mean_ref) for r in dev)/denominator
    if slope == 0:
        raise ValueError("Fitted sensor scale is zero")
    intercept = mean_ref-slope*mean_raw
    zero = -intercept/slope
    # The readout consumes these serialized decimal floats. Check the model
    # actually exported to it, rather than silently dropping serialization error.
    exported_slope = finite(float(slope), "exported slope")
    exported_zero = finite(float(zero), "exported zero")
    details = []
    for r in dev+val:
        prediction = exported_slope*(r["raw_V"]-exported_zero)
        residual = prediction-r["reference_SI"]
        # Conditional finite-reference-point bound, not a continuum bound.
        bound = abs(residual)+r["reference_error_SI"]+abs(exported_slope)*r["raw_error_V"]
        details.append({"source_line": r["source_line"], "split": r["split"],
                        "level_id": r["level_id"], "reference_SI": str(r["reference_SI"]),
                        "raw_V": str(r["raw_V"]), "prediction_SI": str(prediction),
                        "signed_residual_SI": str(residual),
                        "conditional_point_error_upper_SI": str(bound)})
    envelopes = {split: max(F(d["conditional_point_error_upper_SI"]) for d in details if d["split"] == split)
                 for split in ("development", "validation")}
    own = dev+val
    return {"channel": channel, "SI_unit": {"force":"N","position":"m","temperature_C":"degC"}[channel],
            "model": "SI=(raw_V-zero_raw_V)*scale_SI_per_V",
            "reference_error_semantics": "exact-decimal serialized coefficient model; computational runtime rounding is a separate error-budget term",
            "scale_SI_per_V": float(slope), "zero_raw_V": float(zero),
            "exact_decimal_fit": {"scale_SI_per_V": str(slope), "intercept_SI": str(intercept), "zero_raw_V": str(zero)},
            "development_rows": len(dev), "held_out_rows": len(val),
            "development_point_error_upper_SI": str(envelopes["development"]),
            "held_out_point_error_upper_SI": str(envelopes["validation"]),
            "finite_point_error_upper_SI": str(max(envelopes.values())),
            "observed_raw_span_V": [str(min(r["raw_V"] for r in own)), str(max(r["raw_V"] for r in own))],
            "observed_reference_span_SI": [str(min(r["reference_SI"] for r in own)), str(max(r["reference_SI"] for r in own))],
            "observed_temperature_C": [str(min(r["temperature_C"] for r in own)), str(max(r["temperature_C"] for r in own))],
            "observed_excitation_V": [str(min(r["excitation_V"] for r in own)), str(max(r["excitation_V"] for r in own))],
            "reference_evidence_ids": sorted({r["reference_evidence_id"] for r in own}),
            "rows": details}


def fit_writer_calibration(reference_csv, template):
    """Return empirical fit receipt plus a compatible, still-blocked proposal."""
    if template.get("schema") != "hydrophone.writer-calibration/1":
        raise ValueError("Expected readout writer-calibration/1 template")
    rows = read_references(reference_csv)
    names = ["force", "position"]+(["temperature_C"] if any(r["channel"] == "temperature_C" for r in rows) else [])
    fitted = {channel: _fit_channel(rows, channel) for channel in names}
    proposal = copy.deepcopy(template)
    proposal["status"] = "fit_proposal_not_qualified"
    proposal["evidence_type"] = ("synthetic_demo" if rows[0]["data_origin"] == "synthetic_demo"
                                  else "physical_calibration_declared")
    review = []
    for name, fit in fitted.items():
        if name not in proposal["channels"]:
            proposal["channels"][name] = {"raw_column":"raw_temperature_V", "SI_unit":"degC",
                "sensor_serial":None,"chain_id":None,"sign_convention":"Celsius relative to zero degrees Celsius",
                "zero_raw_V":None,"scale_SI_per_V":None,"raw_valid_V":[None,None],
                "raw_error_bound_V":None,"valid_SI":[None,None],"total_error_SI":None,
                "uncertainty_kind":"deterministic_bound_declared","uniform_bound_justification_id":None,
                "reference_evidence_ids":[]}
        target = proposal["channels"][name]
        target["zero_raw_V"] = fit["zero_raw_V"]
        target["scale_SI_per_V"] = fit["scale_SI_per_V"]
        target["reference_evidence_ids"] = fit["reference_evidence_ids"]
        empirical = F(fit["finite_point_error_upper_SI"])
        total = target.get("total_error_SI")
        if total is None:
            review.append(name+": independent uniform total_error_SI/domain justification missing")
        elif finite(total, "total_error_SI") < empirical:
            review.append(name+": declared uniform error is contradicted by finite reference checks")
        elif not target.get("uniform_bound_justification_id"):
            review.append(name+": uniform_bound_justification_id missing")
        else:
            review.append(name+": assigned budget covers these finite references only; continuum/domain review still required")
    ids = sorted({r["reference_evidence_id"] for r in rows})
    proposal["reference_evidence_ids"] = ids
    digest = hashlib.sha256(Path(reference_csv).read_bytes()).hexdigest()
    proposal["fit_source"] = {"reference_csv_sha256": digest,
                              "fit_method": "development_only_exact_decimal_affine_OLS",
                              "held_out_nonzero_levels_disjoint": True,
                              "finite_point_envelopes_are_not_uniform_bounds": True}
    proposal["warning"] = "UNQUALIFIED fit proposal: do not enable until independent uniform error/domain, identity, timing, filter, freshness and slew review is completed."
    receipt = {"schema": "hydrophone.writer-calibration-fit-result/1",
               "status": "FINITE_REFERENCE_FIT_AND_HOLDOUT_CHECKED_NOT_UNIFORM_QUALIFICATION",
               "source_csv_sha256": digest, "evidence_type": proposal["evidence_type"],
               "fit_channels": fitted, "review_obligations": review,
               "hardware_execution_enabled": False, "calibration_authenticity_verified": False,
               "limitations": ["Reference/raw error terms are supplied bounds, not inferred certificates.",
                   "Held-out levels were not used to fit coefficients; the file split still needs independent freezing/provenance.",
                   "Finite checks do not bound unseen loads, temperature, excitation, drift, hysteresis or dynamics.",
                   "Readout's total_error_SI must include raw ADC uncertainty once; it must not be double counted.",
                   "No timing, slew, paired epoch, or full uniform calibration bound is manufactured by this fitter."]}
    return receipt, proposal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("references", type=Path)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--record-output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.record_output.exists() or args.output.resolve() == args.record_output.resolve():
        raise ValueError("Choose two distinct new output paths; preserve previous calibration receipts")
    receipt, proposal = fit_writer_calibration(args.references, json.loads(args.template.read_text()))
    for path, result in ((args.output, receipt), (args.record_output, proposal)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"status": receipt["status"], "record_status": proposal["status"],
                      "physical_calibration_enabled": False}))


if __name__ == "__main__":
    main()
