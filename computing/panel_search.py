"""Exact branch-and-bound selection of grouped acquisition protocols.

The returned optimum is scoped to the finite hypothesis/action table and
rectangular outer observation bounds. It does not qualify physical data.
Minimal-obstruction generation remains exponential in the hypothesis and
action populations; branch-and-bound removes exhaustive panel enumeration,
not that separate source of complexity.
"""
from __future__ import annotations

from fractions import Fraction

from .object_adapter import exact, excludes, prepared


def _bits(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit


def optimize(contract):
    """Return the exact minimum-cost fixed acquisition panel.

    Ties use fewer protocols, then original protocol order. A complete
    exact search establishes optimality. When the initial disjoint-demand
    packing matches the panel cost, the result additionally carries a
    compact matching lower-bound witness.
    """
    ids, actions, good, edges = prepared(contract)
    protocols = contract["protocols"]
    costs = [exact(p["cost"]) for p in protocols]
    unresolved = any(v == "UNRESOLVED" for a in contract["actions"]
                     for v in a["evaluation"].values())
    scope = {
        "physical_readiness": False,
        "hardware_command_issued": False,
        "evidence_scope": contract["evidence_scope"],
        "metadata_validation": "IDENTIFIER_CONSISTENCY_ONLY",
        "optimization_scope": "FIXED_PROTOCOLS_FINITE_HYPOTHESES_RECTANGULAR_OUTER_BOUNDS",
        "cost_unit": contract["cost_unit"],
        "declared_action_table_has_unresolved_entries": unresolved,
    }
    stats = {"minimal_obstructions": len(edges), "cover_constraints": 0,
             "redundant_constraints_removed": 0, "nodes_visited": 0,
             "bound_prunes": 0, "memo_prunes": 0, "incumbent_updates": 0}

    # A demand mask lists protocols capable of excluding one obstruction.
    demands = []
    impossible = []
    for edge_index, edge in enumerate(edges):
        mask = sum(1 << p for p, protocol in enumerate(protocols)
                   if excludes(protocol, edge, ids))
        if not mask:
            impossible.append(edge_index)
        demands.append((mask, edge_index))
    if impossible:
        return {**scope,
                "status": "NO_CERTIFIED_PANEL_WITH_CURRENT_EVIDENCE" if unresolved else
                          "INFEASIBLE_FOR_COMPLETE_DECLARED_ACTION_TABLE",
                "optimal_for_declared_table": False,
                "reason": "Some incompatible hypothesis collection has a common possible transcript under every available protocol",
                "obstruction_witnesses": [[ids[i] for i in sorted(edges[e])] for e in impossible],
                "search_stats": stats}

    # Hitting a smaller demand also hits every superset demand. Preserve an
    # original obstruction index for a human-readable lower-bound witness.
    reduced = []
    for mask, edge_index in sorted(demands, key=lambda pair: (pair[0].bit_count(), pair[0], pair[1])):
        if not any(previous & mask == previous for previous, _ in reduced):
            reduced.append((mask, edge_index))
    stats["cover_constraints"] = len(reduced)
    stats["redundant_constraints_removed"] = len(demands) - len(reduced)
    all_remaining = (1 << len(reduced)) - 1
    coverage = [sum(1 << d for d, (mask, _) in enumerate(reduced) if mask & (1 << p))
                for p in range(len(protocols))]

    def packing_bound(remaining):
        # Disjoint candidate-protocol sets require distinct purchases.
        # Summing their individual cheapest costs is therefore a lower bound.
        candidates = []
        for d in _bits(remaining):
            mask, edge_index = reduced[d]
            minimum = min(costs[p] for p in _bits(mask))
            candidates.append((minimum, mask.bit_count(), mask, edge_index))
        candidates.sort(key=lambda row: (-row[0], row[1], row[2], row[3]))
        used, bound, witnesses = 0, Fraction(0), []
        for minimum, _, mask, edge_index in candidates:
            if not used & mask:
                used |= mask
                bound += minimum
                witnesses.append({"hypotheses": [ids[i] for i in sorted(edges[edge_index])],
                                  "candidate_protocols": [protocols[p]["id"] for p in _bits(mask)],
                                  "minimum_protocol_cost": str(minimum)})
        return bound, witnesses

    root_lower_bound, root_packing = packing_bound(all_remaining)

    # A greedy solution supplies an upper bound only; exact search follows.
    remaining, chosen = all_remaining, set()
    while remaining:
        p = min((p for p, c in enumerate(coverage) if c & remaining),
                key=lambda p: (costs[p] / (coverage[p] & remaining).bit_count(), costs[p], p))
        chosen.add(p)
        remaining &= ~coverage[p]
    for p in sorted(chosen, key=lambda p: (costs[p], p), reverse=True):
        others = chosen - {p}
        union = 0
        for q in others:
            union |= coverage[q]
        if union == all_remaining:
            chosen = others
    first_panel = tuple(sorted(chosen))
    best = (sum((costs[p] for p in first_panel), Fraction(0)), len(first_panel), first_panel)
    stats["incumbent_updates"] = 1
    memo = {}

    def search(remaining, panel, cost):
        nonlocal best
        stats["nodes_visited"] += 1
        panel = tuple(sorted(panel))
        key = (cost, len(panel), panel)
        if not remaining:
            if key < best:
                best = key
                stats["incumbent_updates"] += 1
            return
        if cost > best[0] or cost == best[0] and len(panel) >= best[1]:
            stats["bound_prunes"] += 1
            return
        previous = memo.get(remaining)
        if previous is not None and previous <= key:
            stats["memo_prunes"] += 1
            return
        memo[remaining] = key
        bound, _ = packing_bound(remaining)
        if cost + bound > best[0]:
            stats["bound_prunes"] += 1
            return
        # Every completion must buy at least one protocol from this demand.
        demand = min(_bits(remaining),
                     key=lambda d: (reduced[d][0].bit_count(), -min(costs[p] for p in _bits(reduced[d][0])), d))
        alternatives = sorted(_bits(reduced[demand][0]),
                              key=lambda p: (costs[p] / (coverage[p] & remaining).bit_count(),
                                             costs[p], -(coverage[p] & remaining).bit_count(), p))
        for p in alternatives:
            search(remaining & ~coverage[p], panel + (p,), cost + costs[p])

    search(all_remaining, (), Fraction(0))
    cost, _, panel = best
    panel_ids = [protocols[p]["id"] for p in panel]
    compact = cost == root_lower_bound
    return {**scope, "status": "OPTIMAL_PANEL_FOR_DECLARED_MODEL",
            "optimal_for_declared_table": True,
            "protocols": panel_ids, "selected_protocols": panel_ids,
            "cost": str(cost),
            "root_lower_bound": str(root_lower_bound),
            "optimality": {
                "method": "EXACT_BRANCH_AND_BOUND",
                "search_complete": True,
                "lower_bound_at_completion": str(cost),
                "upper_bound_at_completion": str(cost),
                "compact_matching_bound_available": compact,
                "root_disjoint_obstruction_packing": root_packing,
                "note": "The root packing is independently interpretable; when it does not match the panel cost, optimality relies on completed exact search, not this packing alone."
            },
            "search_stats": stats}


def verify_matching_bound(contract, result):
    """Verify a matching panel/packing certificate without running search.

    Return False when the root packing does not attain the panel cost, even
    if a completed branch-and-bound search separately proved optimality.
    Hypothesis/action-table validity and physical model qualification remain
    separate from this finite mathematical certificate.
    """
    try:
        ids, actions, good, edges = prepared(contract)
        protocols = contract["protocols"]
        by_id = {p["id"]: p for p in protocols}
        selected = result["protocols"]
        if len(selected) != len(set(selected)) or any(p not in by_id for p in selected):
            return False
        if not all(any(excludes(by_id[p], edge, ids) for p in selected) for edge in edges):
            return False
        panel_cost = sum((exact(by_id[p]["cost"]) for p in selected), Fraction(0))
        if panel_cost != exact(result["cost"]):
            return False
        used, lower = set(), Fraction(0)
        for witness in result["optimality"]["root_disjoint_obstruction_packing"]:
            state_names = witness["hypotheses"]
            if not state_names or len(state_names) != len(set(state_names)):
                return False
            if any(state not in ids for state in state_names):
                return False
            edge = {ids.index(state) for state in state_names}
            common = set(actions)
            for i in edge:
                common.intersection_update(good[i])
            if common:
                return False
            candidates = {p["id"] for p in protocols if excludes(p, edge, ids)}
            if not candidates or candidates != set(witness["candidate_protocols"]) or used & candidates:
                return False
            minimum = min(exact(by_id[p]["cost"]) for p in candidates)
            if minimum != exact(witness["minimum_protocol_cost"]):
                return False
            used.update(candidates)
            lower += minimum
        return lower == panel_cost == exact(result["root_lower_bound"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False
