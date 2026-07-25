"""
Pairs Trading — Cointegration Test Unit Tests

Covers core/pairs/cointegration.py's pure Engle-Granger logic per
docs/PAIRS_TRADING_METHODOLOGY.md's "Cointegration test" section.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Aliased on import: "test_pair" is the real function under test, but pytest
# auto-collects any module-level callable named test_* as a test itself --
# without the alias, pytest tries to run it as a test needing fixtures named
# after its own parameters ("symbol_a" etc.) and errors at collection.
from core.pairs.cointegration import (  # noqa: E402
    ADF_PVALUE_THRESHOLD, form_pairs, hedge_ratio, spread_series,
    test_pair as run_pair_test,
)


def _cointegrated_pair(n=250, seed=1):
    """B is a random walk; A = beta*B + stationary noise -- genuinely
    cointegrated by construction."""
    rng = np.random.default_rng(seed)
    log_b = np.cumsum(rng.normal(0, 0.01, n)) + 5.0  # ~log(150)
    noise = rng.normal(0, 0.01, n)
    beta_true = 1.3
    log_a = beta_true * log_b + noise
    return list(np.exp(log_a)), list(np.exp(log_b)), beta_true


def _independent_pair(n=250, seed=0):
    """A is a random walk (unbounded, I(1)); B is a STATIONARY oscillation
    (bounded, I(0)) unrelated to A -- makes the residual overwhelmingly
    likely to inherit A's unit root, unlike two independent random walks
    (which can spuriously cointegrate more often, since a spurious-regression
    beta can partially cancel both walks' trends by chance).

    Still not certain for every seed: ADF itself has a real, if small,
    false-positive rate against ANY single finite-sample random-walk
    realization -- seed=2 (this fixture's original default, and even
    testing plain np.cumsum(...) with NO second series at all) rejected the
    unit root at p=0.004 purely by chance, confirmed by hand across 10 seeds
    (5 gave p<0.5, 1 gave p=0.004, the rest gave p>0.6). seed=0 here is
    verified non-flaky (p=0.40 for this exact construction), not a
    theoretical guarantee -- a real example of why a single-seed synthetic
    fixture needs its randomness checked, not just its construction reasoned
    about."""
    rng = np.random.default_rng(seed)
    log_a = np.cumsum(rng.normal(0, 0.01, n)) + 5.0
    log_b = 5.0 + 0.1 * np.sin(np.linspace(0, 4 * np.pi, n)) + rng.normal(0, 0.002, n)
    return list(np.exp(log_a)), list(np.exp(log_b))


def test_hedge_ratio_recovers_known_beta():
    closes_a, closes_b, beta_true = _cointegrated_pair()
    beta = hedge_ratio(np.log(closes_a), np.log(closes_b))
    assert beta == pytest.approx(beta_true, abs=0.05)


def test_spread_series_length_matches_input():
    closes_a, closes_b, beta_true = _cointegrated_pair(n=50)
    spread = spread_series(np.log(closes_a), np.log(closes_b), beta_true)
    assert len(spread) == 50


def test_cointegrated_pair_passes():
    closes_a, closes_b, _ = _cointegrated_pair()
    result = run_pair_test("A", "B", closes_a, closes_b)
    assert result is not None
    assert result.adf_pvalue < ADF_PVALUE_THRESHOLD
    assert result.passes


def test_independent_pair_fails():
    closes_a, closes_b = _independent_pair()
    result = run_pair_test("A", "B", closes_a, closes_b)
    assert result is not None
    assert not result.passes


def test_too_short_series_returns_none():
    assert run_pair_test("A", "B", [100.0] * 10, [50.0] * 10) is None


def test_mismatched_length_raises():
    with pytest.raises(ValueError):
        run_pair_test("A", "B", [100.0] * 30, [50.0] * 25)


def test_non_positive_close_returns_none():
    closes_a = [100.0] * 25
    closes_b = [50.0] * 12 + [0.0] + [50.0] * 12
    assert run_pair_test("A", "B", closes_a, closes_b) is None


def test_form_pairs_only_returns_passing():
    closes_a, closes_b, _ = _cointegrated_pair(seed=10)
    indep_a, indep_b = _independent_pair(seed=11)
    closes_by_symbol = {"A": closes_a, "B": closes_b, "C": indep_a, "D": indep_b}
    candidates = [("A", "B", "auto"), ("C", "D", "auto")]
    passing = form_pairs(candidates, closes_by_symbol)
    passing_syms = {(r.symbol_a, r.symbol_b) for r in passing}
    assert ("A", "B") in passing_syms
    assert ("C", "D") not in passing_syms


def test_form_pairs_skips_missing_symbol():
    closes_a, closes_b, _ = _cointegrated_pair()
    passing = form_pairs([("A", "MISSING", "auto")], {"A": closes_a, "B": closes_b})
    assert passing == []
