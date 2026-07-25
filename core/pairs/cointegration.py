"""
QuantOS — Pairs Trading: Engle-Granger Cointegration Test
─────────────────────────────────────────────────────────
See docs/PAIRS_TRADING_METHODOLOGY.md "Cointegration test" section. Pure
logic, no I/O -- operates on two aligned daily close-price series for a
formation window.

Two-step Engle-Granger: OLS-regress log(A) on log(B) to get a hedge ratio,
then Augmented Dickey-Fuller test the residual spread for stationarity.
Uses statsmodels' adfuller (new project dependency, see requirements.txt)
rather than a hand-rolled ADF implementation -- same "reuse a well-tested
library" precedent as core/options/greeks.py's bisection IV solver.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
from statsmodels.tsa.stattools import adfuller

# Pre-registered pass bar -- see methodology doc's disclosed multiple-testing
# limitation. Not tuned after seeing results.
ADF_PVALUE_THRESHOLD = 0.05


@dataclass(frozen=True)
class CointegrationResult:
    symbol_a:       str
    symbol_b:       str
    hedge_ratio:    float   # beta in spread = log(A) - beta * log(B)
    spread_mean:    float   # over the formation window
    spread_std:     float   # over the formation window
    adf_pvalue:     float
    n_obs:          int

    @property
    def passes(self) -> bool:
        return self.adf_pvalue < ADF_PVALUE_THRESHOLD


def hedge_ratio(log_a: np.ndarray, log_b: np.ndarray) -> float:
    """OLS slope of log_a on log_b (with intercept) -- np.polyfit degree-1,
    not a new dependency for a one-line regression."""
    beta, _intercept = np.polyfit(log_b, log_a, 1)
    return float(beta)


def spread_series(log_a: np.ndarray, log_b: np.ndarray, beta: float) -> np.ndarray:
    return log_a - beta * log_b


def test_pair(
    symbol_a: str, symbol_b: str,
    closes_a: list[float], closes_b: list[float],
) -> Optional[CointegrationResult]:
    """None if either series has fewer than 20 observations (too short for
    a meaningful ADF test) or contains a non-positive close (log undefined
    -- a real data-quality gap, skipped not zero-filled). closes_a/closes_b
    must already be aligned (same trade dates, same length, same order) by
    the caller -- this function does no date reconciliation itself."""
    if len(closes_a) != len(closes_b):
        raise ValueError(f"{symbol_a}/{symbol_b}: unaligned series ({len(closes_a)} vs {len(closes_b)})")
    if len(closes_a) < 20:
        return None
    if any(c <= 0 for c in closes_a) or any(c <= 0 for c in closes_b):
        return None

    log_a = np.log(np.asarray(closes_a, dtype=float))
    log_b = np.log(np.asarray(closes_b, dtype=float))
    beta = hedge_ratio(log_a, log_b)
    spread = spread_series(log_a, log_b, beta)

    adf_stat, pvalue, *_ = adfuller(spread)
    mean = float(np.mean(spread))
    std = float(np.std(spread, ddof=1))
    if std == 0 or math.isnan(std):
        return None

    return CointegrationResult(
        symbol_a=symbol_a, symbol_b=symbol_b, hedge_ratio=beta,
        spread_mean=mean, spread_std=std, adf_pvalue=float(pvalue),
        n_obs=len(closes_a),
    )


def form_pairs(
    candidate_pairs: list[tuple[str, str, str]],
    closes_by_symbol: dict[str, list[float]],
) -> list[CointegrationResult]:
    """Runs test_pair for every (symbol_a, symbol_b, sector) candidate whose
    both legs have price data, returning only the passing results (see
    CointegrationResult.passes). Sector is not carried into the result --
    it only mattered for candidate generation (core/pairs/universe.py), not
    for the test itself."""
    passing = []
    for symbol_a, symbol_b, _sector in candidate_pairs:
        closes_a = closes_by_symbol.get(symbol_a)
        closes_b = closes_by_symbol.get(symbol_b)
        if not closes_a or not closes_b:
            continue
        result = test_pair(symbol_a, symbol_b, closes_a, closes_b)
        if result is not None and result.passes:
            passing.append(result)
    return passing
