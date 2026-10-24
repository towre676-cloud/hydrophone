from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction as F
import unittest

from computing.memory import exp_neg_bounds, hold_bounds


def decimal_fraction(value):
    value = F(value)
    return Decimal(value.numerator) / Decimal(value.denominator)


def base_model(memory="1/5000", time="0"):
    return {"k0_N_per_m": ["99", "101"], "k1_N_per_m": ["396", "404"],
            "deformation_m": ["99/100000", "101/100000"],
            "initial_memory_m": memory, "hold_time_s": time, "tau_s": "10",
            "readout_error_N": "1/100"}


class ExponentialEnclosureTests(unittest.TestCase):
    def test_independent_high_precision_exponential(self):
        with localcontext() as context:
            context.prec = 100
            for x in (F(0), F(1, 1000), F(1, 2), F(1), F(2), F(15), F(40), F(10000)):
                with self.subTest(x=x):
                    lo, hi = exp_neg_bounds(x, F(1, 10**30))
                    reference = (-decimal_fraction(x)).exp()
                    self.assertLessEqual(decimal_fraction(lo), reference)
                    self.assertGreaterEqual(decimal_fraction(hi), reference)
                    self.assertLessEqual(hi - lo, F(1, 10**30))
                    self.assertTrue(0 <= lo <= hi <= 1)

    def test_zero_exact_and_large_argument_shortcut(self):
        self.assertEqual(exp_neg_bounds(0), (F(1), F(1)))
        lo, hi = exp_neg_bounds("1000000")
        self.assertEqual(lo, 0)
        self.assertLessEqual(hi, F(1, 10**12))

    def test_invalid_inputs(self):
        for x, tol in ((-1, "1/10"), (1, 0), (1, -1), (True, 1), (0.5, 1), ("1/0", 1)):
            with self.subTest(x=x, tol=tol), self.assertRaises(ValueError):
                exp_neg_bounds(x, tol)


class FiniteHoldTests(unittest.TestCase):
    def test_original_zero_time_force_boxes(self):
        low = hold_bounds(base_model())
        high = hold_bounds(base_model("1/1250"))
        self.assertEqual(list(map(F, low["force_N"])), [F(8017, 20000), F(1757, 4000)])
        self.assertEqual(list(map(F, high["force_N"])), [F(653, 4000), F(3937, 20000)])
        self.assertEqual(low["decay"], ["1", "1"])
        self.assertEqual(low["state_m"], ["1/5000", "1/5000"])
        self.assertEqual(F(low["force_N"][0]) - F(high["force_N"][1]), F(51, 250))

    def test_known_force_contrast_decays(self):
        model = {"k0_N_per_m": "100", "k1_N_per_m": "400", "deformation_m": "1/1000",
                 "initial_memory_m": "1/5000", "hold_time_s": "10", "tau_s": "10",
                 "readout_error_N": "0", "exp_tolerance": "1/100000000000000000000"}
        low = hold_bounds(model)
        other = deepcopy(model)
        other["initial_memory_m"] = "1/1250"
        high = hold_bounds(other)
        dlo, dhi = map(F, low["decay"])
        # Difference interval encloses exact 0.24*exp(-1), independently checked.
        contrast = F(low["force_N"][0]) - F(high["force_N"][1]), F(low["force_N"][1]) - F(high["force_N"][0])
        with localcontext() as context:
            context.prec = 80
            reference = Decimal("0.24") * Decimal(-1).exp()
            self.assertLessEqual(decimal_fraction(contrast[0]), reference)
            self.assertGreaterEqual(decimal_fraction(contrast[1]), reference)
        self.assertLess(contrast[1], F(6, 25))
        self.assertEqual(F(low["force_without_readout_N"][0]), F(1, 10) + F(8, 25) * dlo)
        self.assertEqual(F(low["force_without_readout_N"][1]), F(1, 10) + F(8, 25) * dhi)

    def test_continuous_epoch_and_signed_coordinate_box(self):
        model = {"k0_N_per_m": ["0", "3"], "k1_N_per_m": ["2", "5"],
                 "deformation_m": ["-1/10", "1/5"], "initial_memory_m": ["-1/5", "3/10"],
                 "hold_time_s": ["1/5", "2"], "tau_s": ["1/2", "3"],
                 "readout_error_N": ["0", "1/20"]}
        result = hold_bounds(model)
        flo, fhi = map(F, result["force_N"])
        zlo, zhi = map(F, result["state_m"])
        with localcontext() as context:
            context.prec = 80
            for k0 in (F(0), F(3, 2), F(3)):
                for k1 in (F(2), F(7, 2), F(5)):
                    for e in (F(-1, 10), F(1, 20), F(1, 5)):
                        for z0 in (F(-1, 5), F(1, 20), F(3, 10)):
                            for t in (F(1, 5), F(11, 10), F(2)):
                                for tau in (F(1, 2), F(7, 4), F(3)):
                                    decay = (-decimal_fraction(t / tau)).exp()
                                    state = decimal_fraction(e) + decimal_fraction(z0 - e) * decay
                                    force = decimal_fraction(k0 * e) + decimal_fraction(k1 * (e - z0)) * decay
                                    self.assertLessEqual(decimal_fraction(zlo), state)
                                    self.assertGreaterEqual(decimal_fraction(zhi), state)
                                    self.assertLessEqual(decimal_fraction(flo), force)
                                    self.assertGreaterEqual(decimal_fraction(fhi), force)
        self.assertFalse(result["physical_readiness"])
        self.assertFalse(result["finite_window_average_computed"])

    def test_invalid_models(self):
        cases = []
        for field, value in (("tau_s", "0"), ("tau_s", ["-1", "2"]),
                             ("hold_time_s", "-1"), ("k0_N_per_m", "-1"),
                             ("readout_error_N", "-1/100"), ("exp_tolerance", "0"),
                             ("deformation_m", ["2", "1"]), ("k1_N_per_m", ["1", "2", "3"]),
                             ("hold_time_s", float("nan"))):
            invalid = base_model()
            invalid[field] = value
            cases.append(invalid)
        missing = base_model()
        del missing["initial_memory_m"]
        cases.append(missing)
        cases.append([])
        for invalid in cases:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                hold_bounds(invalid)


if __name__ == "__main__":
    unittest.main()
