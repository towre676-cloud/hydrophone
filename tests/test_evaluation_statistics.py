from decimal import Decimal, localcontext
from fractions import Fraction as F
import unittest

from evaluation.statistics import (lower_mean_test, upper_mean_test, binomial_worsening_test,
                                   exacthistory_discordance_test)


class FixedHorizonStatisticsTests(unittest.TestCase):
    def test_zero_improvement_and_negative_differences_fail(self):
        for values in ([F(0)] * 64, [F(-1, 2)] * 64):
            result = lower_mean_test(values)
            self.assertFalse(result["passed"])
            self.assertEqual(result["tail_bound_upper"], "1")

    def test_strong_fixed_horizon_improvement_passes(self):
        result = lower_mean_test([F(1, 2)] * 64)
        self.assertEqual(result["n"], 64)
        self.assertEqual(result["mean_difference"], "1/2")
        self.assertEqual(result["comparison_alpha"], "1/60")
        self.assertEqual(result["hoeffding_exponent"], "128/25")
        self.assertTrue(result["passed"])
        self.assertLessEqual(F(result["tail_enclosure_width"]), F(1, 10**15))

    def test_independent_high_precision_tail_reference(self):
        result = lower_mean_test(["0.5"] * 64)
        with localcontext() as ctx:
            ctx.prec = 100
            reference = (-Decimal(128) / Decimal(25)).exp()
            low = F(result["tail_bound_lower"])
            high = F(result["tail_bound_upper"])
            self.assertLessEqual(Decimal(low.numerator) / Decimal(low.denominator), reference)
            self.assertGreaterEqual(Decimal(high.numerator) / Decimal(high.denominator), reference)

    def test_small_sample_and_exact_margin_do_not_pass(self):
        self.assertFalse(lower_mean_test([F(1, 2)] * 8)["passed"])
        result = lower_mean_test([F(1, 10)] * 100)
        self.assertFalse(result["passed"])
        self.assertEqual(result["hoeffding_exponent"], "0")

    def test_multiplicity_is_applied_exactly(self):
        self.assertTrue(lower_mean_test([F(1, 2)] * 40, comparisons=1)["passed"])
        self.assertFalse(lower_mean_test([F(1, 2)] * 40, comparisons=3)["passed"])

    def test_noninferiority_uses_upper_difference_direction(self):
        result = upper_mean_test([F(-1, 2)] * 64)
        self.assertTrue(result["passed"])
        self.assertEqual(result["direction"], "UPPER_MEAN_BELOW_MARGIN")
        self.assertFalse(upper_mean_test([F(1, 10)] * 64)["passed"])
        self.assertFalse(upper_mean_test([F(1, 20)] * 64)["passed"])

    def test_exact_fraction_and_decimal_inputs_agree(self):
        fraction = lower_mean_test([F(1, 2)] * 64)
        decimal = lower_mean_test(["0.50"] * 64, margin="0.10", alpha="0.05")
        self.assertEqual(fraction, decimal)

    def test_invalid_inputs_rejected(self):
        for values in ([], "0.5", {}, [0.5], [True], ["NaN"], ["1/0"], [F(11, 10)], [F(-11, 10)]):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    lower_mean_test(values)
        for kwargs in ({"alpha": 0}, {"alpha": 1}, {"alpha": "NaN"},
                       {"comparisons": 0}, {"comparisons": True}, {"comparisons": F(3)},
                       {"margin": "2"}, {"margin": "-2"}, {"margin": 0.1}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    lower_mean_test([F(0)], **kwargs)


class BinomialWorseningTests(unittest.TestCase):
    def test_no_worsening_at_sixty_four_blocks_passes_exactly(self):
        result = binomial_worsening_test([F(0)] * 64)
        self.assertEqual(result["worsening_blocks"], 0)
        self.assertEqual(F(result["tail_bound_upper"]), F(9, 10) ** 64)
        self.assertEqual(result["comparison_alpha"], "1/100")
        self.assertEqual(result["tail_enclosure_width"], "0")
        self.assertTrue(result["passed"])
        self.assertFalse(result["anytime_valid"])

    def test_positive_upper_endpoint_counts_ambiguous_block_as_worsening(self):
        result = binomial_worsening_test([F(0)] * 63 + [F(1, 100)])
        self.assertEqual(result["worsening_blocks"], 1)
        expected = F(9, 10) ** 64 + 64 * F(1, 10) * F(9, 10) ** 63
        self.assertEqual(F(result["tail_bound_upper"]), expected)
        self.assertTrue(result["passed"])

    def test_negative_improvements_do_not_cancel_worsening_indicators(self):
        values = [F(-1)] * 44 + [F(1, 1000)] * 20
        result = binomial_worsening_test(values)
        self.assertLess(F(result["mean_upper_difference"]), 0)
        self.assertEqual(result["worsening_blocks"], 20)
        self.assertFalse(result["passed"])

    def test_small_sample_is_insufficient_even_with_zero_worsening(self):
        result = binomial_worsening_test([F(0)] * 4)
        self.assertEqual(F(result["tail_bound_upper"]), F(9, 10) ** 4)
        self.assertFalse(result["passed"])

    def test_small_exact_cdf_and_strict_positive_count(self):
        result = binomial_worsening_test(["-1/2", "0", "1/4"], margin="1/4")
        self.assertEqual(result["worsening_blocks"], 1)
        self.assertEqual(F(result["tail_bound_upper"]), F(27, 32))
        self.assertFalse(result["passed"])

    def test_probability_margins_and_other_invalid_inputs(self):
        for margin in (0, 1, "-1/10", "11/10", 0.1, True):
            with self.subTest(margin=margin):
                with self.assertRaises(ValueError):
                    binomial_worsening_test([F(0)], margin=margin)
        for differences in ([], [True], ["NaN"], [F(11, 10)]):
            with self.subTest(differences=differences):
                with self.assertRaises(ValueError):
                    binomial_worsening_test(differences)


class HistoryDiscordanceTests(unittest.TestCase):
    def test_strong_definite_discordance_passes_exactly(self):
        result = exacthistory_discordance_test(8, 8)
        self.assertEqual(F(result["tail_bound_upper"]), F(1, 256))
        self.assertEqual(result["comparison_alpha"], "1/120")
        self.assertTrue(result["passed"])
        self.assertFalse(result["identical_probabilities_across_units_required"])
        self.assertFalse(result["useful_tuning_established_by_this_test_alone"])

    def test_typical_and_zero_discordance_are_insufficient(self):
        result = exacthistory_discordance_test(4, 8)
        self.assertEqual(F(result["tail_bound_upper"]), F(163, 256))
        self.assertFalse(result["passed"])
        zero = exacthistory_discordance_test(0, 64)
        self.assertEqual(zero["tail_bound_upper"], "1")
        self.assertFalse(zero["passed"])

    def test_retaining_ambiguous_units_is_conservative(self):
        # Eight definite discordances among eight pairs reject. If eight
        # more predeclared pairs have ambiguous outcomes, they remain in n
        # while adding nothing to k; they cannot be silently discarded.
        self.assertTrue(exacthistory_discordance_test(8, 8)["passed"])
        self.assertFalse(exacthistory_discordance_test(8, 16)["passed"])
        result = exacthistory_discordance_test(8, 16)
        self.assertIn("retain_in_eligible_denominator", result["ambiguous_pairs_policy"])

    def test_invalid_counts_and_levels_are_rejected(self):
        for k, n in ((-1, 8), (9, 8), (0, 0), (True, 8), (1, True), (F(1), 8), (1, F(8))):
            with self.subTest(k=k, n=n):
                with self.assertRaises(ValueError):
                    exacthistory_discordance_test(k, n)
        for kwargs in ({"alpha": 0}, {"alpha": 1}, {"alpha": "NaN"},
                       {"comparisons": 0}, {"comparisons": True}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    exacthistory_discordance_test(1, 8, **kwargs)


if __name__ == "__main__":
    unittest.main()
