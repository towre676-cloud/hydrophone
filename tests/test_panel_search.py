"""Independent finite checks for exact grouped-protocol branch-and-bound."""
from copy import deepcopy
from fractions import Fraction as F
from itertools import combinations
import random
import unittest

from computing.object_adapter import synthetic_fixture
from computing.panel_search import optimize, verify_matching_bound


def all_subsets(items):
    items = tuple(items)
    for size in range(len(items) + 1):
        yield from combinations(items, size)


def brute_force(contract):
    """Check every nonempty state subset, without minimal-edge machinery."""
    states = [h["id"] for h in contract["hypotheses"]]
    actions = contract["actions"]
    protocols = contract["protocols"]
    best = None
    for panel in all_subsets(range(len(protocols))):
        sufficient = True
        for possible in all_subsets(states):
            if not possible:
                continue
            has_common_action = any(all(a["evaluation"][s] == "PASS_WITH_BOUND" for s in possible)
                                    for a in actions)
            if has_common_action:
                continue
            common_transcript = True
            for p in panel:
                for feature in protocols[p]["features"]:
                    intervals = [feature["intervals"][s] for s in possible]
                    if max(F(bounds[0]) for bounds in intervals) > min(F(bounds[1]) for bounds in intervals):
                        common_transcript = False
            if common_transcript:
                sufficient = False
                break
        if sufficient:
            key = (sum((F(protocols[p]["cost"]) for p in panel), F(0)), len(panel), panel)
            if best is None or key < best:
                best = key
    return best


def generated_contract(rng, protocol_count):
    state_ids = ["s" + str(i) for i in range(4)]
    actions = [{"id": "a" + str(a), "evaluation": {
        s: rng.choice(["PASS_WITH_BOUND", "FAIL_WITH_BOUND", "UNRESOLVED"])
        for s in state_ids}} for a in range(3)]
    protocols = []
    for p in range(protocol_count):
        features = []
        for f in range(rng.randrange(1, 3)):
            nominal = [F(rng.randrange(3)) for _ in state_ids]
            errors = [rng.choice([F(0), F(1, 4), F(1, 2)]) for _ in state_ids]
            features.append({"id": "f" + str(f), "unit": "V", "location_id": "toy",
                             "transfer_path_id": "toy", "calibration_id": "SYNTHETIC",
                             "clock_id": "SYNTHETIC", "intervals": {
                                 s: [str(v - e), str(v + e)]
                                 for s, v, e in zip(state_ids, nominal, errors)}})
        protocols.append({"id": "p" + str(p), "cost": str(F(rng.randrange(6), rng.randrange(1, 4))),
                          "cost_unit": "toy", "reset_semantics": "COMMON_RESET", "features": features})
    return {"schema": "unified-object/fusion-adapter/v1",
            "evidence_scope": "EXACT_SYNTHETIC_MODEL_NOT_MEASURED",
            "cost_unit": "toy", "uncertainty_geometry": "CONSERVATIVE_OUTER_PRODUCT",
            "hypotheses": [{"id": s} for s in state_ids],
            "actions": actions, "protocols": protocols}


def bit_contract(copies=1):
    states = ["s" + str(i) for i in range(6)]
    model = generated_contract(random.Random(0), 1)
    model["hypotheses"] = [{"id": s} for s in states]
    model["actions"] = [{"id": "a" + str(i), "evaluation": {
        s: "PASS_WITH_BOUND" if j == i else "FAIL_WITH_BOUND"
        for j, s in enumerate(states)}} for i in range(6)]
    protocols = []
    for copy in range(copies):
        for bit in range(3):
            feature = deepcopy(model["protocols"][0]["features"][0])
            feature["intervals"] = {s: [str((j >> bit) & 1)] * 2 for j, s in enumerate(states)}
            protocols.append({"id": "bit" + str(bit) + "_copy" + str(copy),
                              "cost": str(1 + copy), "cost_unit": "toy",
                              "reset_semantics": "COMMON_RESET", "features": [feature]})
    model["protocols"] = protocols
    return model


class PanelSearchTests(unittest.TestCase):
    def assert_matches_brute(self, contract):
        expected = brute_force(contract)
        result = optimize(contract)
        self.assertFalse(result["physical_readiness"])
        if expected is None:
            self.assertFalse(result["optimal_for_declared_table"])
            self.assertIn("obstruction_witnesses", result)
        else:
            cost, _, panel = expected
            self.assertEqual(F(result["cost"]), cost)
            self.assertEqual(result["protocols"], [contract["protocols"][p]["id"] for p in panel])
            self.assertLessEqual(F(result["root_lower_bound"]), cost)
            self.assertTrue(result["optimality"]["search_complete"])

    def test_native_units_grouped_fixture_and_matching_bound(self):
        contract = synthetic_fixture()
        self.assert_matches_brute(contract)
        result = optimize(contract)
        self.assertEqual(result["protocols"], ["slow_plunger_acquisition"])
        self.assertEqual(result["cost"], "2")
        self.assertTrue(result["optimality"]["compact_matching_bound_available"])
        self.assertTrue(verify_matching_bound(contract, result))
        corrupted = deepcopy(result)
        corrupted["cost"] = "0"
        self.assertFalse(verify_matching_bound(contract, corrupted))
        corrupted = deepcopy(result)
        corrupted["optimality"]["root_disjoint_obstruction_packing"][0]["minimum_protocol_cost"] = "0"
        self.assertFalse(verify_matching_bound(contract, corrupted))

    def test_empty_panel_for_common_action(self):
        contract = synthetic_fixture()
        for action in contract["actions"]:
            action["evaluation"] = {s["id"]: "PASS_WITH_BOUND" for s in contract["hypotheses"]}
        self.assert_matches_brute(contract)
        self.assertEqual(optimize(contract)["protocols"], [])

    def test_closed_endpoint_and_incomplete_evidence_statuses(self):
        contract = synthetic_fixture()
        contract["protocols"][1]["features"][0]["intervals"] = {
            "low_memory": ["0", "1"], "high_memory": ["1", "2"]}
        self.assert_matches_brute(contract)
        self.assertEqual(optimize(contract)["status"], "INFEASIBLE_FOR_COMPLETE_DECLARED_ACTION_TABLE")
        contract["actions"][0]["evaluation"]["high_memory"] = "UNRESOLVED"
        self.assertEqual(optimize(contract)["status"], "NO_CERTIFIED_PANEL_WITH_CURRENT_EVIDENCE")

    def test_fractional_and_zero_cost_ties(self):
        contract = synthetic_fixture()
        duplicate = deepcopy(contract["protocols"][1])
        duplicate["id"] = "duplicate"
        duplicate["cost"] = "0"
        contract["protocols"][1]["cost"] = "0"
        contract["protocols"].append(duplicate)
        self.assert_matches_brute(contract)
        self.assertEqual(optimize(contract)["protocols"], ["slow_plunger_acquisition"])

    def test_seeded_random_models_against_exhaustive_panels(self):
        rng = random.Random(20261024)
        for i in range(90):
            with self.subTest(case=i):
                self.assert_matches_brute(generated_contract(rng, 1 + i % 7))

    def test_nontrivial_feasible_menus_against_exhaustive_panels(self):
        rng = random.Random(20261025)
        for i in range(18):
            contract = bit_contract()
            for p in range(4):
                feature = deepcopy(contract["protocols"][0]["features"][0])
                feature["intervals"] = {s["id"]: [str(rng.randrange(2))] * 2
                                        for s in contract["hypotheses"]}
                contract["protocols"].append({"id": "random" + str(p),
                    "cost": str(F(rng.randrange(7), 3)), "cost_unit": "toy",
                    "reset_semantics": "COMMON_RESET", "features": [feature]})
            with self.subTest(case=i):
                self.assert_matches_brute(contract)

    def test_large_redundant_menu_has_matching_lower_bound(self):
        contract = bit_contract(copies=12)  # 36 protocols: 2^36 panel menu.
        result = optimize(contract)
        self.assertEqual(result["cost"], "3")
        self.assertEqual(result["protocols"], ["bit0_copy0", "bit1_copy0", "bit2_copy0"])
        self.assertEqual(result["root_lower_bound"], "3")
        self.assertTrue(result["optimality"]["compact_matching_bound_available"])
        self.assertTrue(verify_matching_bound(contract, result))
        self.assertLess(result["search_stats"]["nodes_visited"], 2000)

    def test_weaker_packing_is_not_a_standalone_optimality_certificate(self):
        contract = bit_contract()
        states = ["s0", "s1", "s2"]
        contract["hypotheses"] = [{"id": s} for s in states]
        contract["actions"] = [{"id": "a" + str(i), "evaluation": {
            s: "PASS_WITH_BOUND" if j == i else "FAIL_WITH_BOUND"
            for j, s in enumerate(states)}} for i in range(3)]
        for i, protocol in enumerate(contract["protocols"]):
            protocol["features"][0]["intervals"] = {
                s: [str(int(j == i))] * 2 for j, s in enumerate(states)}
        self.assert_matches_brute(contract)
        result = optimize(contract)
        self.assertEqual(result["cost"], "2")
        self.assertEqual(result["root_lower_bound"], "1")
        self.assertFalse(result["optimality"]["compact_matching_bound_available"])
        self.assertFalse(verify_matching_bound(contract, result))


if __name__ == "__main__":
    unittest.main()
