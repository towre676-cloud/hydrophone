#!/usr/bin/env python3
"""Exact research demonstrator: observations sufficient for a common action.

Python 3.10+, standard library only. All examples are mathematical models.
Run: python fusion_engine.py --out results.json

The hyperedge checker is cross-checked against a separate enumeration of
the complete closed-interval observation arrangement. No physical trial
or performance improvement is asserted.
"""
from __future__ import annotations

import argparse
from fractions import Fraction as F
from itertools import combinations, product
import json
from pathlib import Path
import random


def subsets(items):
    items = tuple(items)
    for size in range(len(items) + 1):
        yield from combinations(items, size)


def common_actions(indices, good, actions):
    result = set(actions)
    for i in indices:
        result.intersection_update(good[i])
    return result


def validate(states, actions, good, probes):
    if not states or not actions:
        raise ValueError("A nonempty hypothesis population and action universe are required")
    if len(states) != len(set(states)) or len(actions) != len(set(actions)):
        raise ValueError("Hypothesis and action identifiers must be unique")
    if len(good) != len(states) or any(not set(g) <= set(actions) for g in good):
        raise ValueError("Action table is incomplete or contains an unknown action")
    for p in probes:
        if len(p["values"]) != len(states) or p["cost"] < 0:
            raise ValueError("Probe coverage or cost is invalid")


def obstruction_edges(good, actions):
    """Inclusion-minimal state sets with no common successful action."""
    edges = []
    # Every minimal obstruction has cardinality <= number of actions.
    for size in range(1, min(len(good), len(actions)) + 1):
        for candidate in combinations(range(len(good)), size):
            s = frozenset(candidate)
            if any(e <= s for e in edges):
                continue
            if not common_actions(s, good, actions):
                edges.append(s)
    return edges


def separating_probes(edge, probes, epsilon):
    """Closed symmetric intervals: STRICT separation at the endpoint."""
    return frozenset(
        p for p, probe in enumerate(probes)
        if max(probe["values"][i] - epsilon for i in edge)
        > min(probe["values"][i] + epsilon for i in edge)
    )


def sufficient_by_edges(panel, edges, probes, epsilon):
    panel = frozenset(panel)
    return all(panel & separating_probes(edge, probes, epsilon) for edge in edges)


def observation_cells(panel, probes, epsilon, n):
    """Independent checker via arrangement, without using obstruction edges.

    Membership in a finite family of closed intervals is constant on each
    open gap and at each endpoint. Enumerate those memberships for each
    coordinate, then intersect them across the selected coordinates.
    """
    coordinate_masks = []
    for p in panel:
        values = probes[p]["values"]
        endpoints = sorted({v - epsilon for v in values} | {v + epsilon for v in values})
        representatives = endpoints + [(a + b) / 2 for a, b in zip(endpoints, endpoints[1:])]
        masks = {
            frozenset(i for i, value in enumerate(values) if abs(y - value) <= epsilon)
            for y in representatives
        }
        coordinate_masks.append(masks)
    cells = set()
    for memberships in product(*coordinate_masks):
        cell = frozenset(range(n))
        for membership in memberships:
            cell &= membership
        if cell:
            cells.add(cell)
    return cells


def sufficient_by_arrangement(panel, good, actions, probes, epsilon):
    return all(common_actions(cell, good, actions)
               for cell in observation_cells(panel, probes, epsilon, len(good)))


def optimal_panel(good, actions, probes, epsilon, purpose="action", task_labels=None):
    validate(tuple(range(len(good))), actions, good, probes)
    if epsilon < 0:
        raise ValueError("Observation error radius must be nonnegative")
    if purpose not in ("action", "task", "state"):
        raise ValueError("Unknown panel purpose")
    if purpose == "task" and (task_labels is None or len(task_labels) != len(good)):
        raise ValueError("Task labels must cover every hypothesis")
    edges = obstruction_edges(good, actions)
    candidates = []
    for panel in subsets(range(len(probes))):
        if purpose == "action":
            ok = sufficient_by_edges(panel, edges, probes, epsilon)
        else:
            labels = task_labels if purpose == "task" else list(range(len(good)))
            ok = all(len({labels[i] for i in c}) == 1
                     for c in observation_cells(panel, probes, epsilon, len(good)))
        if ok:
            candidates.append((sum(probes[p]["cost"] for p in panel), len(panel), panel))
    if not candidates:
        return {"status": "INFEASIBLE_FOR_DECLARED_MODEL"}
    cost, _, panel = min(candidates)
    return {"status": "CERTIFIED_FOR_DECLARED_MODEL", "cost": cost,
            "panel": [probes[p]["name"] for p in panel]}


def squared_distance(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


def six_state_model():
    states = [(i, n) for i in range(3) for n in range(2)]
    actions = ("a", "b", "c")
    targets = [(F(0), F(0)), (F(2), F(0)), (F(1), F(2))]
    points = {"a": (F(1, 2), F(1)), "b": (F(1), F(0)), "c": (F(3, 2), F(1))}
    tolerance = F(5, 4)
    losses = [[squared_distance(points[a], target) for a in actions] for target in targets]
    good = [{a for a in actions if squared_distance(points[a], targets[i]) <= tolerance}
            for i, _ in states]
    probes = [
        {"name": "decision", "cost": 1, "values": [F(i == 2) for i, _ in states]},
        {"name": "task", "cost": 2, "values": [F(i == 1) for i, _ in states]},
        {"name": "nuisance", "cost": 4, "values": [F(n) for _, n in states]},
    ]
    validate(states, actions, good, probes)
    return states, actions, targets, points, losses, good, probes


def fraction_matrix(rows):
    return [[F(x) for x in row] for row in rows]


def rank(rows):
    a = fraction_matrix(rows)
    if not a:
        return 0
    r = 0
    for c in range(len(a[0])):
        pivot = next((i for i in range(r, len(a)) if a[i][c]), None)
        if pivot is None:
            continue
        a[r], a[pivot] = a[pivot], a[r]
        scale = a[r][c]
        a[r] = [v / scale for v in a[r]]
        for i in range(len(a)):
            if i != r:
                factor = a[i][c]
                a[i] = [v - factor * w for v, w in zip(a[i], a[r])]
        r += 1
        if r == len(a):
            break
    return r


def integer_determinant(matrix):
    """Fraction-free Bareiss elimination, including row exchanges."""
    a = [list(row) for row in matrix]
    if not a:
        return 1
    previous, sign = 1, 1
    for k in range(len(a) - 1):
        pivot_row = next((i for i in range(k, len(a)) if a[i][k]), None)
        if pivot_row is None:
            return 0
        if pivot_row != k:
            a[k], a[pivot_row] = a[pivot_row], a[k]
            sign *= -1
        pivot = a[k][k]
        for i in range(k + 1, len(a)):
            for j in range(k + 1, len(a)):
                numerator = a[i][j] * pivot - a[i][k] * a[k][j]
                assert numerator % previous == 0
                a[i][j] = numerator // previous
        for i in range(k + 1, len(a)):
            a[i][k] = 0
        previous = pivot
    return sign * a[-1][-1]


def linear_and_music_checks():
    O = [[1, 0, 0, 0], [1, 1, 2, 0]]
    T = [[0, 1, 2, 0]]
    assert rank(O) == rank(O + T) == 2
    for v in ([0, -2, 1, 0], [0, 0, 0, 1]):
        assert all(sum(a * b for a, b in zip(row, v)) == 0 for row in O + T)
    # r=(a,a)+(1,2)u; check the stationarity and orthogonal residual exactly.
    a = F(1)
    u = -3 * a / 5
    residual = (a + u, a + 2 * u)
    assert residual == (F(2, 5), F(-1, 5))
    assert residual[0] + 2 * residual[1] == 0
    assert sum(v * v for v in residual) == F(1, 5)
    # Endpoint-average loss is 2+5u^2 for a in {-1,+1}; minimum is 2.
    for candidate_u in (F(-2), F(-1, 3), F(0), F(1, 4), F(2)):
        endpoint_losses = [(s + candidate_u) ** 2 + (s + 2 * candidate_u) ** 2
                           for s in (F(-1), F(1))]
        assert sum(endpoint_losses) / 2 == 2 + 5 * candidate_u ** 2
    assert max(s ** 2 + s ** 2 for s in (F(-1), F(1))) == 2
    assert 2 * 1 - 1 * 2 == 0  # dual missing-actuation witness
    controls = (-2 * a / 3, -a / 3)
    assert a + controls[0] + controls[1] == 0
    assert a + 2 * controls[0] - controls[1] == 0
    # Reconstruct the archived 36 x 12 interval matrix.
    J = []
    for step in (4, 3, 7):
        for start in range(12):
            row = [0] * 12
            row[start] = -1
            row[(start + step) % 12] = 1
            J.append(row)
    R = [row[1:] for row in J]
    gram = [[sum(row[i] * row[j] for row in R) for j in range(11)] for i in range(11)]
    determinant = integer_determinant(gram)
    assert determinant == 52002816 and rank(R) == 11
    assert all(sum(R[i][j] for i in range(12 * family, 12 * (family + 1))) == 0
               for family in range(3) for j in range(11))
    # Familywise targets AND arbitrary familywise priorities still cancel.
    b = [F(-3, 2)] * 12 + [F(7, 3)] * 12 + [F(5, 7)] * 12
    weights = [F(3)] * 12 + [F(5)] * 12 + [F(11)] * 12
    forcing = [sum(R[i][j] * weights[i] * b[i] for i in range(36)) for j in range(11)]
    assert all(v == 0 for v in forcing)
    return {"linear": {"state_dimension": 4, "observation_rank": 2,
                       "task_identified": True, "one_actuator_squared_residual_at_a1": F(1, 5),
                       "unobserved_robust_squared_loss_a_in_unit_interval": F(2),
                       "two_actuators_squared_residual": F(0)},
            "music": {"interval_rows": 36, "free_pitch_offsets": 11,
                      "gram_determinant": determinant, "familywise_forcing_exactly_zero": True}}


def cross_check():
    states, actions, _, _, _, good, probes = six_state_model()
    count = 0
    for epsilon in (F(0), F(1, 10), F(1, 2)):
        edges = obstruction_edges(good, actions)
        for panel in subsets(range(3)):
            assert sufficient_by_edges(panel, edges, probes, epsilon) == sufficient_by_arrangement(
                panel, good, actions, probes, epsilon)
            count += 1
    rng = random.Random(20261024)
    for _ in range(72):
        actions = tuple(range(3))
        good = [{a for a in actions if rng.randrange(2)} for _ in range(4)]
        probes = [{"name": str(p), "cost": rng.randrange(1, 6),
                   "values": [F(rng.randrange(3)) for _ in range(4)]} for p in range(3)]
        epsilon = rng.choice((F(0), F(1, 4), F(1, 2)))
        edges = obstruction_edges(good, actions)
        for panel in subsets(range(3)):
            assert sufficient_by_edges(panel, edges, probes, epsilon) == sufficient_by_arrangement(
                panel, good, actions, probes, epsilon)
            count += 1
    assert count == 600
    try:
        validate([], ["a"], [], [])
    except ValueError:
        pass
    else:
        raise AssertionError("Empty population must not count as verified coverage")
    for invalid_call in (lambda: optimal_panel([], ["a"], [], F(0)),
                         lambda: optimal_panel([{"a"}], ["a"], [], F(-1))):
        try:
            invalid_call()
        except ValueError:
            pass
        else:
            raise AssertionError("Public panel optimizer accepted an invalid contract")
    return count


def run():
    states, actions, targets, points, losses, good, probes = six_state_model()
    edges = obstruction_edges(good, actions)
    assert len(edges) == 8 and all(len(e) == 3 for e in edges)
    assert all(common_actions(pair, good, actions) for pair in combinations(range(6), 2))
    cases = []
    for epsilon in (F(0), F(1, 10), F(1, 2)):
        case = {"noise_radius": epsilon}
        for purpose in ("action", "task", "state"):
            case[purpose] = optimal_panel(good, actions, probes, epsilon, purpose,
                                          [i for i, _ in states])
        if epsilon < F(1, 2):
            assert [case[p]["cost"] for p in ("action", "task", "state")] == [1, 3, 7]
        else:
            assert all(case[p]["status"] == "INFEASIBLE_FOR_DECLARED_MODEL"
                       for p in ("action", "task", "state"))
        cases.append(case)
    center = (F(1), F(3, 4))
    assert all(squared_distance(center, t) == F(25, 16) for t in targets)
    # Exact lower bound: positive barycentric weights express center as
    # convex combination of targets, hence max loss >= weighted mean loss.
    barycentric = [F(5, 16), F(5, 16), F(3, 8)]
    assert all(sum(w * t[d] for w, t in zip(barycentric, targets)) == center[d]
               for d in range(2))
    assert sum(barycentric) == 1
    finite_minimax = min(max(row[j] for row in losses) for j in range(len(actions)))
    assert finite_minimax == F(13, 4)
    checks = linear_and_music_checks()
    count = cross_check()
    return {"title": "Fusion: certified decisions from incomplete observations",
            "date": "2026-10-24", "evidence": "EXACT_SYNTHETIC_MODELS_NO_PHYSICAL_TRIALS",
            "states": states, "actions": points, "targets": targets,
            "squared_loss_budget": F(5, 4), "squared_losses": losses,
            "successful_actions": [sorted(g) for g in good],
            "probes": probes, "minimal_obstruction_count": len(edges),
            "minimal_obstructions": [sorted(e) for e in edges],
            "every_pair_compatible": True, "noise_cases": cases,
            "continuous_no_probe_minimax_squared_loss": F(25, 16),
            "continuous_minimax_center": center,
            "finite_action_no_probe_minimax_squared_loss": finite_minimax,
            "independent_panel_cross_checks": count,
            "observation_arrangement_includes_closed_endpoints": True,
            "empty_population_rejected": True, **checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="Write complete exact results as JSON")
    args = parser.parse_args()
    result = run()
    encoded = json.dumps(result, indent=2, default=lambda x: str(x) if isinstance(x, F) else list(x))
    if args.out:
        args.out.write_text(encoded + "\n", encoding="utf-8")
    print(json.dumps({"checks": result["independent_panel_cross_checks"],
                      "obstructions": result["minimal_obstruction_count"],
                      "action_task_state_costs": [result["noise_cases"][1][p]["cost"]
                                                   for p in ("action", "task", "state")],
                      "noise_endpoint": result["noise_cases"][2]["action"]["status"],
                      "music_determinant": result["music"]["gram_determinant"]}))


if __name__ == "__main__":
    main()
