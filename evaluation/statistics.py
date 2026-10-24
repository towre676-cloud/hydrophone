"""Fixed-horizon, bounded-block comparison tests with exact tail enclosures.

Each input is ONE independent confirmation-block difference in [-1,1].
Adjacent frames, repeated trials from one block, or shared-cartridge/day
records do not automatically provide independent observations. The caller
must define and qualify its statistical units before data collection.

For independent X_b in [-1,1], Hoeffding gives

    P(mean(X)-mean(E[X]) >= t) <= exp(-n*t**2/2).

Identical distributions are unnecessary, but the target is then the
average expected loss difference of the predeclared block population.
This module uses rational arithmetic and a rigorous rational enclosure
of exp(-x); it never rounds a tail probability downward to obtain a pass.
The input may be a conservative lower endpoint on baseline-policy loss
differences for a superiority test, or an upper endpoint on reduced-full
loss differences for a noninferiority test. Those endpoints must themselves
be valid and remain in [-1,1].

The alpha/comparisons adjustment is a union-bound allocation for a fixed,
predeclared family. These are not anytime-valid tests: peeking, selecting
the best endpoint, or increasing the horizon after inspecting results
requires a separately valid procedure. No physical origin, calibration,
independence, randomization or contract freeze is authenticated here.
"""
from __future__ import annotations

from fractions import Fraction
from math import comb
from typing import Any

from computing.memory import exp_neg_bounds


F = Fraction
TAIL_ENCLOSURE_TOLERANCE = F(1, 10**15)


def _exact(value: Any, label: str) -> F:
    if isinstance(value, bool) or not isinstance(value, (str, int, F)):
        raise ValueError(label + " must be an integer or exact rational/decimal string")
    try:
        return F(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(label + " is not a finite exact rational") from exc


def _inputs(values, margin, alpha, comparisons):
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError("Supply a nonempty array of independent block differences")
    observed = [_exact(x, "block difference") for x in values]
    if any(x < -1 or x > 1 for x in observed):
        raise ValueError("Each block difference must lie in [-1,1]")
    threshold, level = _exact(margin, "margin"), _exact(alpha, "alpha")
    if threshold < -1 or threshold > 1:
        raise ValueError("The difference margin must lie in [-1,1]")
    if not 0 < level < 1:
        raise ValueError("alpha must be strictly between zero and one")
    if isinstance(comparisons, bool) or not isinstance(comparisons, int) or comparisons <= 0:
        raise ValueError("comparisons must be a positive integer fixed before confirmation")
    return observed, threshold, level, comparisons


def _mean_test(values, margin, alpha, comparisons, lower):
    observed, threshold, level, family_size = _inputs(values, margin, alpha, comparisons)
    n = len(observed)
    mean = sum(observed, F(0)) / n
    gap = mean - threshold if lower else threshold - mean
    exponent = F(n, 2) * gap * gap if gap > 0 else F(0)
    if gap > 0:
        tail_lower, tail_upper = exp_neg_bounds(exponent, TAIL_ENCLOSURE_TOLERANCE)
    else:
        tail_lower = tail_upper = F(1)
    comparison_alpha = level / family_size
    passed = gap > 0 and tail_upper <= comparison_alpha
    return {
        "schema": "fusion.fixed-horizon-bounded-block-test/1",
        "direction": "LOWER_MEAN_ABOVE_MARGIN" if lower else "UPPER_MEAN_BELOW_MARGIN",
        "null_hypothesis": "average_expected_difference_at_most_margin" if lower
                           else "average_expected_difference_at_least_margin",
        "n": n,
        "mean_difference": str(mean),
        "margin": str(threshold),
        "gap": str(gap),
        "alpha": str(level),
        "comparisons": family_size,
        "comparison_alpha": str(comparison_alpha),
        "hoeffding_exponent": str(exponent),
        "tail_bound_lower": str(tail_lower),
        "tail_bound_upper": str(tail_upper),
        "tail_enclosure_width": str(tail_upper - tail_lower),
        "passed": passed,
        "status": "PREDECLARED_MARGIN_TEST_PASSED" if passed
                  else "INSUFFICIENT_FINITE_SAMPLE_EVIDENCE",
        "method": "one_sided_Hoeffding_with_rigorous_rational_exponential_upper_bound",
        "assumptions": [
            "independent_confirmation_blocks",
            "each_difference_bounded_in_minus_one_to_one",
            "fixed_horizon_and_comparison_family_before_confirmation",
            "frozen_policies_and_scoring_rule",
            "valid_support_endpoints_if_interval_losses_are_supplied",
        ],
        "independence_authenticated": False,
        "physical_calibration_authenticated": False,
        "anytime_valid": False,
    }


def lower_mean_test(values, margin=F("0.10"), alpha=F("0.05"), comparisons=3):
    """Test that the average expected difference is greater than margin.

    For material-information superiority, differences are baseline loss
    minus the history-aware policy loss. If losses have certified intervals,
    supply baseline_lower-policy_upper for each independent block. A pass
    applies only under the declared sampling and measurement assumptions.
    """
    return _mean_test(values, margin, alpha, comparisons, lower=True)


def upper_mean_test(values, margin=F("0.05"), alpha=F("0.05"), comparisons=3):
    """Test that the average expected difference is less than margin.

    For reduced-measurement noninferiority, differences are reduced-policy
    loss minus full-policy loss. With loss intervals, supply reduced_upper
    minus full_lower. Cost reduction needs an additional predeclared cost
    comparison; this function establishes no acquisition saving by itself.
    """
    return _mean_test(values, margin, alpha, comparisons, lower=False)


def binomial_worsening_test(differences, margin=F("0.10"), alpha=F("0.05"), comparisons=5):
    """Sufficient loss noninferiority through a stricter worsening criterion.

    Each supplied difference is a conservative UPPER bound on one
    independent confirmation block's reduced-minus-full loss difference
    and lies in [-1,1]. Count a block as worsening whenever this upper
    bound is strictly positive; ambiguity that permits worsening counts.

    Pointwise D <= 1{D>0} for D in [-1,1]. Thus a worsening probability
    below margin is sufficient for average loss increase below margin,
    even though it can be much stronger than mean noninferiority. Negative
    improvements cannot compensate for worsening blocks in this test.

    The indicators must be independent with a COMMON worsening probability
    p, as from identically sampled independent block units. Under H0:
    p>=margin, the probability of X<=k is bounded by the exact binomial
    CDF at p=margin. This common-probability assumption cannot be replaced
    by merely independent heterogeneous Bernoulli probabilities here.
    The fixed horizon and comparison family must be predeclared.
    """
    observed, threshold, level, family_size = _inputs(
        differences, margin, alpha, comparisons)
    if not 0 < threshold < 1:
        raise ValueError("The worsening-probability margin must be strictly between zero and one")
    n = len(observed)
    k = sum(value > 0 for value in observed)
    tail = sum((F(comb(n, j)) * threshold ** j * (1 - threshold) ** (n - j)
                for j in range(k + 1)), F(0))
    comparison_alpha = level / family_size
    passed = tail <= comparison_alpha
    return {
        "schema": "fusion.fixed-horizon-binomial-worsening-test/1",
        "direction": "UPPER_WORSENING_PROBABILITY_BELOW_MARGIN",
        "null_hypothesis": "worsening_probability_at_least_margin",
        "n": n,
        "worsening_blocks": k,
        "observed_worsening_fraction": str(F(k, n)),
        "mean_upper_difference": str(sum(observed, F(0)) / n),
        "margin": str(threshold),
        "alpha": str(level),
        "comparisons": family_size,
        "comparison_alpha": str(comparison_alpha),
        "tail_bound_lower": str(tail),
        "tail_bound_upper": str(tail),
        "tail_enclosure_width": "0",
        "passed": passed,
        "status": "PREDECLARED_MARGIN_TEST_PASSED" if passed
                  else "INSUFFICIENT_FINITE_SAMPLE_EVIDENCE",
        "method": "exact_one_sided_binomial_CDF_at_null_boundary",
        "loss_noninferiority_basis": "E[true_difference] <= E[upper_difference] <= P[upper_difference>0]",
        "scope": "sufficient_worsening_probability_criterion_not_general_mean_test",
        "assumptions": [
            "independent_confirmation_blocks",
            "common_worsening_probability_from_identically_sampled_block_units",
            "valid_upper_bounds_on_reduced_minus_full_loss",
            "each_difference_bounded_in_minus_one_to_one",
            "fixed_horizon_and_comparison_family_before_confirmation",
            "frozen_policies_and_scoring_rule",
        ],
        "independence_authenticated": False,
        "common_probability_authenticated": False,
        "physical_calibration_authenticated": False,
        "anytime_valid": False,
    }


def exacthistory_discordance_test(k, n, alpha=F("0.05"), comparisons=6):
    """Exact conservative upper-tail test for a strong no-history null.

    In EACH predeclared independent unit, use one predeclared H0/H1 pair
    of fresh independently prepared trials with the same constant-policy
    action. Under the null, their binary failure probabilities are equal
    within that unit, p0_b=p1_b=p_b. Their true discordance probability is
    2*p_b*(1-p_b)<=1/2. The p_b may differ between units. Independence
    between units therefore makes the discordance count stochastically
    dominated by Binomial(n,1/2), without an identically distributed-unit
    assumption.

    k counts only DEFINITE binary discordances. An ambiguous interval
    cannot increase k. Such units must remain in the predeclared eligible
    denominator n, rather than being removed after seeing the outcome.
    Count construction, trial independence, preparation, matching and
    randomization are the caller's qualified experimental obligations.

    This tests a strong within-unit no-history null, not a homogeneous
    causal average effect or useful tuning performance by itself.
    Equal marginal probabilities without within-unit independent fresh
    trials are insufficient: anticorrelated outcomes can be discordant
    with probability one even when both marginals equal one half.
    """
    if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
        raise ValueError("n must be a positive predeclared eligible-unit count")
    if isinstance(k, bool) or not isinstance(k, int) or not 0 <= k <= n:
        raise ValueError("k must be an integer discordance count between zero and n")
    level = _exact(alpha, "alpha")
    if not 0 < level < 1:
        raise ValueError("alpha must be strictly between zero and one")
    if isinstance(comparisons, bool) or not isinstance(comparisons, int) or comparisons <= 0:
        raise ValueError("comparisons must be a positive integer fixed before confirmation")
    tail = F(sum(comb(n, j) for j in range(k, n + 1)), 2 ** n)
    comparison_alpha = level / comparisons
    passed = tail <= comparison_alpha
    return {
        "schema": "fusion.fixed-horizon-history-discordance-test/1",
        "direction": "DEFINITE_HISTORY_DISCORDANCE_EXCEEDS_NO_HISTORY_BOUND",
        "null_hypothesis": "within_unit_equal_binary_failure_probabilities_under_independent_fresh_preparations",
        "n": n,
        "discordant_units": k,
        "observed_discordance_fraction": str(F(k, n)),
        "worst_case_null_discordance_probability": "1/2",
        "alpha": str(level),
        "comparisons": comparisons,
        "comparison_alpha": str(comparison_alpha),
        "tail_bound_lower": str(tail),
        "tail_bound_upper": str(tail),
        "tail_enclosure_width": "0",
        "passed": passed,
        "status": "PREDECLARED_HISTORY_NULL_REJECTED" if passed
                  else "INSUFFICIENT_FINITE_SAMPLE_EVIDENCE",
        "method": "exact_Binomial_n_one_half_upper_tail_stochastic_domination",
        "ambiguous_pairs_policy": "count_as_non_discordant_and_retain_in_eligible_denominator",
        "assumptions": [
            "independence_between_confirmation_units",
            "one_predeclared_constant_action_H0_H1_pair_per_unit",
            "independent_fresh_preparations_within_each_unit",
            "equal_within_unit_binary_failure_probability_under_null",
            "valid_intervals_and_only_definite_binary_discordances_counted",
            "fixed_eligible_units_horizon_and_comparison_family_before_confirmation",
        ],
        "identical_probabilities_across_units_required": False,
        "homogeneous_history_effect_direction_established": False,
        "useful_tuning_established_by_this_test_alone": False,
        "independence_authenticated": False,
        "physical_calibration_authenticated": False,
        "anytime_valid": False,
    }
