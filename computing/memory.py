"""Rigorous finite-hold bounds for an illustrative passive memory element.

All numbers are exact rationals. This module does not identify a physical
clay pad or map a plunger stroke onto material deformation. The model is

    F = k0*e + k1*(e-z),      dz/dt = (e-z)/tau.

During a constant-deformation hold, its exact solution is

    z(t) = (1-d)*e + d*z0,   F(t) = k0*e + k1*(e-z0)*d,
    d = exp(-t/tau).

The stored energy E=(k0*e**2+k1*(e-z)**2)/2 satisfies
E_dot=F*e_dot-(k1/tau)*(e-z)**2. Nonnegative stiffness and positive tau
therefore give a passive declared element. Outputs remain model-only.
"""
from __future__ import annotations

from fractions import Fraction
from itertools import product
from typing import Any

F = Fraction


def _exact(value: Any) -> F:
    if isinstance(value, bool) or not isinstance(value, (str, int, F)):
        raise ValueError("Use integer or rational/decimal-string values, not floats")
    try:
        return F(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("Invalid exact rational value") from exc


def _box(value: Any, name: str) -> tuple[F, F]:
    if isinstance(value, (list, tuple)):
        if len(value) != 2:
            raise ValueError(f"{name} must have exactly two endpoints")
        lo, hi = map(_exact, value)
    else:
        lo = hi = _exact(value)
    if lo > hi:
        raise ValueError(f"{name} endpoints are reversed")
    return lo, hi


def exp_neg_bounds(x: Any, tolerance: Any = F(1, 10**12)) -> tuple[F, F]:
    """Enclose exp(-x), for exact x>=0, to an absolute rational width.

    Scale y=x/2**s into [0,1]. The alternating Taylor sums for exp(-y)
    give odd lower/even upper bounds. Obtain base width <=tol/2**s,
    then square both nonnegative endpoints s times. Since b*b-a*a <=
    2*(b-a) on [0,1], final width is <=tol. No floating approximation
    enters the enclosure.

    Large x has a cheaper rigorous bound: e>=2 implies exp(-x)<=2**-k
    whenever x>=k. This also prevents rational squaring from producing
    needlessly huge integers far below the requested tolerance.
    """
    x, tolerance = _exact(x), _exact(tolerance)
    if x < 0 or tolerance <= 0:
        raise ValueError("x must be nonnegative and tolerance strictly positive")
    if x == 0:
        return F(1), F(1)
    power, k = F(1), 0
    while power > tolerance:
        power /= 2
        k += 1
    if x >= k:
        return F(0), power

    y, scale = x, 0
    while y > 1:
        y /= 2
        scale += 1
    base_tolerance = tolerance / (2**scale)
    lower, upper, total, term, n = F(0), F(1), F(1), F(1), 0
    while upper - lower > base_tolerance:
        n += 1
        term *= -y / n
        total += term
        if n % 2:
            lower = total
        else:
            upper = total
    for _ in range(scale):
        lower, upper = lower * lower, upper * upper
    if not (0 <= lower <= upper <= 1 and upper - lower <= tolerance):
        raise ArithmeticError("Internal exponential enclosure invariant failed")
    return lower, upper


def hold_bounds(model: dict[str, Any]) -> dict[str, Any]:
    """Bound every instantaneous snapshot in a declared hold-epoch box.

    Required parameters (each exact scalar or [lower,upper]):
    k0_N_per_m, k1_N_per_m, deformation_m, initial_memory_m,
    hold_time_s, tau_s, readout_error_N. Optional exp_tolerance sets the
    absolute width of each exponential endpoint enclosure.

    The epoch and tau give t/tau in [t_lo/tau_hi,t_hi/tau_lo]. Since exp
    is decreasing, rational enclosures at these endpoints bound all decay
    factors. State and force formulas are multiaffine in their independent
    box variables; their extrema over the enclosing box occur at vertices.
    Enumerating those vertices is therefore a continuous-box guarantee,
    not a sampled-grid claim. Outer boxes may include correlations that
    the actual parameters cannot attain and are conservative.

    Deformation is held constant throughout each trajectory. The epoch
    box covers unknown snapshot time. No finite-window average, moving
    stroke, changing geometry, or physical calibration is inferred.
    """
    if not isinstance(model, dict):
        raise ValueError("model must be an object")
    required = ("k0_N_per_m", "k1_N_per_m", "deformation_m", "initial_memory_m",
                "hold_time_s", "tau_s", "readout_error_N")
    missing = [name for name in required if name not in model]
    if missing:
        raise ValueError("Missing model parameter(s): " + ", ".join(missing))
    k0, k1, e, z0, epoch, tau, error = [_box(model[name], name) for name in required]
    if k0[0] < 0 or k1[0] < 0:
        raise ValueError("Stiffnesses must be nonnegative for this passive model")
    if epoch[0] < 0 or tau[0] <= 0 or error[0] < 0:
        raise ValueError("Hold time/error must be nonnegative and tau strictly positive")
    tolerance = _exact(model.get("exp_tolerance", F(1, 10**12)))
    if tolerance <= 0:
        raise ValueError("exp_tolerance must be strictly positive")
    ratio = epoch[0] / tau[1], epoch[1] / tau[0]
    decay_lower = exp_neg_bounds(ratio[1], tolerance)[0]
    decay_upper = exp_neg_bounds(ratio[0], tolerance)[1]
    decay = decay_lower, decay_upper

    state_vertices = [(1 - d) * ev + d * zv for ev, zv, d in product(e, z0, decay)]
    force_vertices = [k0v * ev + k1v * (ev - zv) * d
                      for k0v, k1v, ev, zv, d in product(k0, k1, e, z0, decay)]
    force = min(force_vertices) - error[1], max(force_vertices) + error[1]

    def encoded(interval):
        return [str(v) for v in interval]

    return {
        "schema": "hydrophone/memory-hold/v1",
        "evidence_scope": "DECLARED_MODEL_BOUNDS_NOT_PHYSICALLY_QUALIFIED",
        "physical_readiness": False,
        "hardware_command_issued": False,
        "evaluation": "ALL_INSTANTANEOUS_SNAPSHOTS_IN_HOLD_EPOCH_INTERVAL",
        "constant_deformation_assumed": True,
        "finite_window_average_computed": False,
        "epoch_s": encoded(epoch),
        "decay": encoded(decay),
        "state_m": encoded((min(state_vertices), max(state_vertices))),
        "force_without_readout_N": encoded((min(force_vertices), max(force_vertices))),
        "force_N": encoded(force),
        "readout_error_radius_N": str(error[1]),
        "exp_tolerance": str(tolerance),
        "proof": "alternating-series enclosure, exact squaring, multiaffine box vertices",
    }
