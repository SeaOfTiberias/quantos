"""
QuantOS — Correlation Engine
────────────────────────────────
US-08: Computes pairwise price correlation between symbols to prevent
sector over-concentration. Before adding a new position, check its
correlation against every open position — reject if too correlated.

Uses Pearson correlation coefficient on daily returns (not raw prices —
correlation on returns is the statistically correct approach since
raw price series are non-stationary and produce spurious high correlations).
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────

CORRELATION_THRESHOLD = 0.75   # reject new position if correlation exceeds this
MIN_DATA_POINTS       = 20     # minimum overlapping daily returns needed
LOOKBACK_DAYS         = 60     # how many days of price history to use


@dataclass
class CorrelationResult:
    """Correlation between two symbols."""
    symbol_a:     str
    symbol_b:     str
    correlation:  float          # -1.0 to +1.0
    data_points:  int
    is_reliable:  bool           # False if data_points < MIN_DATA_POINTS

    @property
    def is_high_correlation(self) -> bool:
        return self.is_reliable and abs(self.correlation) >= CORRELATION_THRESHOLD

    @property
    def abs_correlation(self) -> float:
        return abs(self.correlation)


@dataclass
class PortfolioCheckResult:
    """Result of checking a candidate symbol against the full open portfolio."""
    candidate_symbol:      str
    is_blocked:             bool
    max_correlation:        float
    correlated_with:        list[CorrelationResult] = field(default_factory=list)
    all_correlations:       list[CorrelationResult] = field(default_factory=list)
    notes:                  list[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        if not self.is_blocked:
            return "No correlation conflict"
        names = ", ".join(
            f"{c.symbol_b} ({c.correlation:+.2f})" for c in self.correlated_with
        )
        return f"High correlation with: {names}"


def daily_returns(prices: list[float]) -> list[float]:
    """Convert a price series into daily % returns."""
    if len(prices) < 2:
        return []
    return [
        (prices[i] - prices[i - 1]) / prices[i - 1]
        for i in range(1, len(prices))
        if prices[i - 1] != 0
    ]


def pearson_correlation(series_a: list[float], series_b: list[float]) -> tuple[float, int]:
    """
    Compute Pearson correlation coefficient between two return series.
    Returns (correlation, n_overlapping_points).

    Series are aligned by truncating to the shorter length, assuming
    both series end on the same date (most recent N trading days).
    """
    n = min(len(series_a), len(series_b))
    if n < 2:
        return 0.0, n

    a = series_a[-n:]
    b = series_b[-n:]

    mean_a = sum(a) / n
    mean_b = sum(b) / n

    cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((x - mean_b) ** 2 for x in b)

    denom = math.sqrt(var_a * var_b)
    if denom == 0:
        return 0.0, n

    corr = cov / denom
    return max(-1.0, min(1.0, corr)), n   # clamp for float precision safety


def compute_correlation(
    symbol_a: str,
    prices_a: list[float],
    symbol_b: str,
    prices_b: list[float],
) -> CorrelationResult:
    """Compute correlation between two symbols from their price histories."""
    returns_a = daily_returns(prices_a)
    returns_b = daily_returns(prices_b)

    corr, n = pearson_correlation(returns_a, returns_b)
    is_reliable = n >= MIN_DATA_POINTS

    return CorrelationResult(
        symbol_a=symbol_a,
        symbol_b=symbol_b,
        correlation=round(corr, 4),
        data_points=n,
        is_reliable=is_reliable,
    )


def check_portfolio_correlation(
    candidate_symbol: str,
    candidate_prices: list[float],
    open_positions: dict[str, list[float]],
    threshold: float = CORRELATION_THRESHOLD,
) -> PortfolioCheckResult:
    """
    Check a candidate symbol's correlation against all open positions.

    Args:
        candidate_symbol: symbol being considered for a new position
        candidate_prices: daily close prices for the candidate
        open_positions: dict of {symbol: price_series} for currently open positions
        threshold: correlation level above which to flag (default 0.75)

    Returns:
        PortfolioCheckResult — is_blocked=True if max correlation exceeds threshold
    """
    if not open_positions:
        return PortfolioCheckResult(
            candidate_symbol=candidate_symbol,
            is_blocked=False,
            max_correlation=0.0,
            notes=["No open positions — no correlation risk"],
        )

    all_correlations = []
    for symbol, prices in open_positions.items():
        if symbol.upper() == candidate_symbol.upper():
            continue   # skip self-comparison
        result = compute_correlation(candidate_symbol, candidate_prices, symbol, prices)
        all_correlations.append(result)

    if not all_correlations:
        return PortfolioCheckResult(
            candidate_symbol=candidate_symbol,
            is_blocked=False,
            max_correlation=0.0,
            notes=["No comparable positions"],
        )

    # Sort by absolute correlation descending
    all_correlations.sort(key=lambda c: c.abs_correlation, reverse=True)
    max_corr = all_correlations[0].abs_correlation

    correlated_with = [c for c in all_correlations if c.abs_correlation >= threshold and c.is_reliable]
    is_blocked = len(correlated_with) > 0

    notes = []
    if is_blocked:
        for c in correlated_with:
            notes.append(
                f"⚠️ {candidate_symbol} vs {c.symbol_b}: "
                f"correlation {c.correlation:+.2f} (threshold {threshold:.2f})"
            )
    else:
        notes.append(
            f"Max correlation: {max_corr:.2f} with {all_correlations[0].symbol_b} "
            f"(below {threshold:.2f} threshold)"
        )

    unreliable = [c for c in all_correlations if not c.is_reliable]
    if unreliable:
        notes.append(
            f"⚠️ {len(unreliable)} position(s) had insufficient data "
            f"(<{MIN_DATA_POINTS} days) — correlation unreliable"
        )

    logger.info(
        "Correlation check: %s → blocked=%s, max_corr=%.2f",
        candidate_symbol, is_blocked, max_corr,
    )

    return PortfolioCheckResult(
        candidate_symbol=candidate_symbol,
        is_blocked=is_blocked,
        max_correlation=max_corr,
        correlated_with=correlated_with,
        all_correlations=all_correlations,
        notes=notes,
    )
