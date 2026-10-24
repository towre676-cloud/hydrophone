"""Exact model-level action-relevant memory witnesses; no physical fit."""
from fractions import Fraction as F


def action_relevant_forcing(action_columns, weighted_task_delta):
    """Return D^T W N delta from supplied columns and task perturbation.

    With a positive-definite unconstrained quadratic action Hessian,
    zero vector is exactly the condition for the unique optimum to be
    invariant under this memory perturbation. Bounds/nonlinear actions
    require their own analysis.
    """
    delta = [F(x) for x in weighted_task_delta]
    if not delta or any(len(c) != len(delta) for c in action_columns):
        raise ValueError("Action columns and weighted task dimension disagree")
    return [sum((F(a) * b for a, b in zip(column, delta)), F(0)) for column in action_columns]


def witnesses():
    force_a, force_b = F(21, 50), F(9, 50)
    invisible_to_action = action_relevant_forcing([[1, 2]], [2, -1])
    visible_to_action = action_relevant_forcing([[1, 2]], [1, 1])
    return {"schema": "fusion.action-observability-witnesses/1", "evidence": "EXACT_DECLARED_MODELS_ONLY",
            "force_distinguishable_memories_N": [str(force_a), str(force_b)],
            "initial_memory_only_SLS": "fixed poles and baseline-subtracted incremental response are independent of initial memory; raw transients may retain it",
            "observable_task_delta_but_same_unconstrained_optimum": {"weighted_task_delta": ["2", "-1"], "action_direction": ["1", "2"], "forcing": [str(v) for v in invisible_to_action]},
            "action_relevant_task_delta": {"weighted_task_delta": ["1", "1"], "forcing": [str(v) for v in visible_to_action]},
            "positive_pitch_coupling": "MUST_BE_IDENTIFIED; not supplied by the SLS equation or a history label",
            "physical_readiness": False}
