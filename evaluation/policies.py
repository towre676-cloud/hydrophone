"""Frozen empirical policies for the preregistered two-action tuning task.

These are development-only, action-specific ridge regressions. They do
not provide physical error bounds or prove that material memory is useful.
Fusion-full intentionally shares the digital-full predictor; any reduction
claim must concern explicitly selected acquisition protocols and held-out
outcomes, rather than inventing predictive superiority for an exact solver.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math


SCHEMA = "fusion.frozen-policies/1"
RIDGE = 0.01
ACTION_IDS = ("hold", "raise5")
ABSTAIN = "ABSTAIN"
TIE_TOLERANCE = 1e-12


def _finite(value, label):
    if isinstance(value, bool):
        raise ValueError(label + " must be a finite number")
    try:
        result = float(Fraction(value) if isinstance(value, str) else value)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(label + " must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(label + " must be a finite number")
    return result


def _canonical(value):
    """Canonical JSON representation of declared inputs, including Fractions."""
    def exact_json(x):
        if isinstance(x, Fraction):
            return str(x)
        raise TypeError("Unsupported frozen input")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False,
                      default=exact_json)


def _feature_list(value, label, allow_empty=False):
    if (not isinstance(value, list) or (not value and not allow_empty)
            or any(not isinstance(x, str) or not x for x in value)
            or len(value) != len(set(value))):
        raise ValueError(label + " must be a list of unique nonempty feature names")
    if any(x.startswith("outcome") for x in value):
        raise ValueError("Post-action outcome fields cannot be policy features")
    return list(value)


def _contract_spec(contract):
    if not isinstance(contract, dict):
        raise ValueError("Policy contract must be a JSON object")
    if contract.get("action_ids") != list(ACTION_IDS):
        raise ValueError("The frozen tuning task requires ordered action_ids hold,raise5")
    feature_sets = contract.get("feature_sets")
    if not isinstance(feature_sets, dict):
        raise ValueError("Policy contract needs feature_sets")
    selected = {name: _feature_list(feature_sets.get(name), "feature_sets." + name)
                for name in ("memoryless", "digital_log", "digital_full")}
    reduced = _feature_list(contract.get("fusion_reduced_features"),
                            "fusion_reduced_features", allow_empty=True)
    if not set(reduced) <= set(selected["digital_full"]):
        raise ValueError("Reduced Fusion features must be a subset of digital_full features")
    domain = contract.get("policy_domain", {})
    if not isinstance(domain, dict):
        raise ValueError("policy_domain must be an object when supplied")
    maximum = domain.get("max_abs_scaled_feature")
    if maximum is not None:
        maximum = _finite(maximum, "max_abs_scaled_feature")
        if maximum <= 0:
            raise ValueError("max_abs_scaled_feature must be positive")
    selected["fusion_reduced"] = reduced
    return selected, maximum


def training_loss(row):
    """Empirical bounded target: min((|observed cents|+readout error)^2/400,1).

    This conservative per-row target is not a prediction interval for a
    fitted regression. Scientific confirmation uses independent outcomes.
    """
    if not isinstance(row, dict):
        raise ValueError("A development row must be an object")
    try:
        observed = _finite(row["outcome_cents"], "outcome_cents")
        error = _finite(row["outcome_error_cents"], "outcome_error_cents")
    except KeyError as exc:
        raise ValueError("Missing measured development outcome field: " + str(exc)) from exc
    if error < 0:
        raise ValueError("outcome_error_cents must be nonnegative")
    magnitude = abs(observed) + error
    if not math.isfinite(magnitude):
        raise ValueError("Development outcome magnitude overflowed")
    # Compare before squaring to keep even very large finite errors safe.
    return 1.0 if magnitude >= 20 else magnitude * magnitude / 400.0


def _values(row, features):
    if not isinstance(row, dict) or not isinstance(row.get("features"), dict):
        raise ValueError("A policy row needs a feature object")
    result = []
    for name in features:
        if name not in row["features"]:
            raise ValueError("Missing policy feature: " + name)
        result.append(_finite(row["features"][name], "feature " + name))
    return result


def _solve(matrix, rhs):
    n = len(rhs)
    a = [list(row) + [rhs[i]] for i, row in enumerate(matrix)]
    scale = max(abs(v) for row in matrix for v in row)
    for col in range(n):
        pivot = max(range(col, n), key=lambda i: abs(a[i][col]))
        if abs(a[pivot][col]) <= max(1.0, scale) * 1e-14:
            raise ValueError("Empirical policy fit is numerically unresolved")
        a[col], a[pivot] = a[pivot], a[col]
        divisor = a[col][col]
        for j in range(col, n + 1):
            a[col][j] /= divisor
        for i in range(col + 1, n):
            factor = a[i][col]
            for j in range(col, n + 1):
                a[i][j] -= factor * a[col][j]
    answer = [0.0] * n
    for i in range(n - 1, -1, -1):
        answer[i] = a[i][n] - math.fsum(a[i][j] * answer[j] for j in range(i + 1, n))
    if not all(math.isfinite(v) for v in answer):
        raise ValueError("Empirical policy coefficients are nonfinite")
    return answer


def _design(values, means, scales):
    z = [(x - m) / s for x, m, s in zip(values, means, scales)]
    features = [1.0] + z + [v * v for v in z]
    if not all(math.isfinite(v) for v in features):
        raise ValueError("Policy feature transform overflowed")
    return features, z


def _fit_arm(rows, features):
    values = [_values(row, features) for row in rows]
    means = [math.fsum(row[j] / len(rows) for row in values) for j in range(len(features))]
    if not all(math.isfinite(v) for v in means):
        raise ValueError("Development feature mean overflowed")
    centered = [[_finite(x - m, "centered development feature")
                 for x, m in zip(row, means)] for row in values]
    scales = [max(abs(row[j]) for row in centered) or 1.0 for j in range(len(features))]
    design = [_design(row, means, scales)[0] for row in values]
    coefficients = {}
    counts = {}
    for action in ACTION_IDS:
        indices = [i for i, row in enumerate(rows) if row["action"] == action]
        p = 1 + 2 * len(features)
        matrix = [[math.fsum(design[i][j] * design[i][k] for i in indices)
                   + (RIDGE if j == k and j > 0 else 0.0)
                   for k in range(p)] for j in range(p)]
        rhs = [math.fsum(design[i][j] * training_loss(rows[i]) for i in indices)
               for j in range(p)]
        coefficients[action] = _solve(matrix, rhs)
        counts[action] = len(indices)
    return {"feature_names": list(features), "means": means, "scales": scales,
            "scaling": "DEVELOPMENT_MEAN_AND_MAX_ABSOLUTE_CENTERED_DEVIATION",
            "terms": "INTERCEPT_THEN_SCALED_FEATURES_THEN_THEIR_SQUARES",
            "ridge": RIDGE, "penalized_intercept": False,
            "coefficients_by_action": coefficients, "development_action_counts": counts}


def fit_policies(development_rows, contract):
    """Fit complete policies using explicitly development-only rows.

    Contract feature lists determine the compared information sets. An
    optional policy_domain.max_abs_scaled_feature is a predeclared guard,
    not a coverage certificate. No confirmation row is admitted here.
    """
    sets, maximum = _contract_spec(contract)
    if not isinstance(development_rows, list) or not development_rows:
        raise ValueError("A nonempty development row list is required")
    rows = development_rows
    counts = {a: 0 for a in ACTION_IDS}
    for row in rows:
        if not isinstance(row, dict) or row.get("cohort") != "development":
            raise ValueError("Policy fitting accepts development cohort rows only")
        if row.get("action") not in counts:
            raise ValueError("Development row action must be hold or raise5")
        counts[row["action"]] += 1
        training_loss(row)
        for feature_set in sets.values():
            _values(row, feature_set)
    if any(count == 0 for count in counts.values()):
        raise ValueError("Development data must cover both tuning actions")
    means = {a: math.fsum(training_loss(row) / counts[a] for row in rows if row["action"] == a)
             for a in ACTION_IDS}
    best = "hold" if means["hold"] <= means["raise5"] + TIE_TOLERANCE else "raise5"
    policies = {name: _fit_arm(rows, features) for name, features in sets.items()}
    # Both names refer to identical parameters, not independently fitted contenders.
    policies["fusion_full"] = json.loads(_canonical(policies["digital_full"]))
    snapshot = json.loads(_canonical(contract))
    training = json.loads(_canonical(rows))
    frozen = {"schema": SCHEMA, "policy_type": "EMPIRICAL_ACTION_SPECIFIC_QUADRATIC_RIDGE",
              "action_ids": list(ACTION_IDS), "training_cohort": "development",
              "development_rows": len(rows), "development_action_counts": counts,
              "training_loss": "min((abs(outcome_cents)+outcome_error_cents)^2/400,1)",
              "ridge": RIDGE, "tie_preference": "hold", "tie_tolerance": TIE_TOLERANCE,
              "constant_action": best, "constant_action_mean_training_loss": means,
              "models": policies, "contract_snapshot": snapshot,
              "contract_sha256": hashlib.sha256(_canonical(snapshot).encode()).hexdigest(),
              "development_sha256": hashlib.sha256(_canonical(training).encode()).hexdigest(),
              "max_abs_scaled_feature": maximum,
              "fusion_full_equals_digital_full": True,
              "physical_bound_claim": False, "physical_readiness": False,
              "hardware_commands_issued": 0}
    # Check all serialized learned parameters before release to the caller.
    _canonical(frozen)
    return frozen


def choose_action(frozen, arm, row):
    """Return 'hold', 'raise5', or ABSTAIN under a declared domain guard.

    Malformed features raise ValueError. A domain abstention is explicit
    rather than inventing extrapolation confidence. The row's outcome and
    applied action are never read when selecting a policy action.
    """
    if not isinstance(frozen, dict) or frozen.get("schema") != SCHEMA:
        raise ValueError("Expected a frozen policy packet")
    if not isinstance(row, dict):
        raise ValueError("A policy input row must be an object")
    if arm == "constant":
        action = frozen.get("constant_action")
        if action not in ACTION_IDS:
            raise ValueError("Invalid frozen constant action")
        return action
    models = frozen.get("models")
    if not isinstance(models, dict) or arm not in models:
        raise ValueError("Unknown frozen policy arm: " + str(arm))
    model = models[arm]
    try:
        names = model["feature_names"]
        means = [_finite(v, "frozen mean") for v in model["means"]]
        scales = [_finite(v, "frozen scale") for v in model["scales"]]
        if len(names) != len(means) or len(names) != len(scales) or any(s <= 0 for s in scales):
            raise ValueError("Invalid frozen feature scaling")
        vector, z = _design(_values(row, names), means, scales)
        maximum = frozen.get("max_abs_scaled_feature")
        if maximum is not None and any(abs(v) > _finite(maximum, "frozen domain limit") for v in z):
            return ABSTAIN
        scores = {}
        for action in ACTION_IDS:
            coef = [_finite(v, "frozen coefficient") for v in model["coefficients_by_action"][action]]
            if len(coef) != len(vector):
                raise ValueError("Frozen coefficient dimension mismatch")
            prediction = math.fsum(v * c for v, c in zip(vector, coef))
            if not math.isfinite(prediction):
                raise ValueError("Policy prediction is nonfinite")
            scores[action] = min(1.0, max(0.0, prediction))
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError("Malformed frozen empirical policy") from exc
    return "hold" if scores["hold"] <= scores["raise5"] + TIE_TOLERANCE else "raise5"
