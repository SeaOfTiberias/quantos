"""
QuantOS — S8-3 52-Week-High RS Momentum: shared ranking/diff logic
───────────────────────────────────────────────────────────────────
Pure, no-I/O logic — no broker calls, no filesystem. Both
`scripts/backtest_rs_momentum.py` (backtest) and `core/rotation/executor.py`
(live) import from here, so live execution can never silently drift from
what was actually backtested (`docs/S8_3_BACKTEST_RESULTS.md`) — there is
exactly one ranking function, not a live re-implementation that could diverge
from the tested one.

Methodology is pre-committed in `docs/S8_3_MOMENTUM_METHODOLOGY.md`. Do not
tune TOP_N, LOOKBACK_DAYS, or the ranking formula after seeing a result —
that becomes a new, separately pre-registered run.
"""

import bisect
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.brokers.base import OHLCV

LOOKBACK_DAYS = 252   # trading days for the 52-week-high window
TOP_N = 20            # pre-committed, docs/S8_3_MOMENTUM_METHODOLOGY.md


@dataclass
class SymbolSeries:
    dates:  list[datetime]
    closes: list[float]
    highs:  list[Optional[float]]   # rolling LOOKBACK_DAYS-day high, None until warmed up


def rolling_high_series(daily: list[OHLCV], window: int = LOOKBACK_DAYS) -> list[Optional[float]]:
    highs = [c.high for c in daily]
    result: list[Optional[float]] = []
    for i in range(len(highs)):
        if i + 1 < window:
            result.append(None)
        else:
            result.append(max(highs[i - window + 1: i + 1]))
    return result


def build_symbol_series(daily: list[OHLCV]) -> SymbolSeries:
    return SymbolSeries(
        dates=[c.timestamp for c in daily],
        closes=[c.close for c in daily],
        highs=rolling_high_series(daily),
    )


def value_as_of(series: SymbolSeries, target_date: datetime) -> Optional[tuple[float, float]]:
    """Most recent (close, rolling_52w_high) at or before target_date, or
    None if the symbol has no data yet or isn't warmed up. Handles
    individual listing gaps/halts by using the last available bar."""
    idx = bisect.bisect_right(series.dates, target_date) - 1
    if idx < 0 or series.highs[idx] is None:
        return None
    return series.closes[idx], series.highs[idx]


def rank_universe(
    symbol_series: dict[str, SymbolSeries], as_of_date: datetime, top_n: int = TOP_N,
    eligible: Optional[frozenset] = None,
) -> list[str]:
    """Top-N symbols by nearness-to-52-week-high (close / rolling_high) as of
    the most recent bar at or before as_of_date, highest score first.
    Symbols with no warmed-up data as of that date are excluded — this is
    the exact same scoring rule used throughout S8-3's backtest.

    `eligible`, if given, restricts scoring to symbols in that set (e.g. the
    true point-in-time Nifty 500 membership for as_of_date, so a backtest
    doesn't rank against constituents that hadn't joined yet or had already
    been dropped — see core/rotation/nifty500_reconstitution.py). Omitting it
    reproduces the original behavior exactly: every symbol in symbol_series
    is eligible every week."""
    scores = []
    for symbol, series in symbol_series.items():
        if eligible is not None and symbol not in eligible:
            continue
        v = value_as_of(series, as_of_date)
        if v is None:
            continue
        close, high = v
        if high > 0:
            scores.append((symbol, close / high))
    scores.sort(key=lambda x: -x[1])
    return [s for s, _ in scores[:top_n]]


@dataclass
class RebalancePlan:
    buys: list[str]
    sells: list[str]


def diff_target_basket(current_holdings, target_basket: list[str]) -> RebalancePlan:
    """buys = target - current, sells = current - target.

    `buys` preserves target_basket's rank order (best-first, as returned by
    rank_universe) so a capital-constrained executor can size the
    highest-conviction new entrants first. `sells` order is arbitrary (a set
    difference) so it's sorted for deterministic output."""
    current = set(current_holdings)
    target = set(target_basket)
    buys = [s for s in target_basket if s not in current]
    sells = sorted(current - target)
    return RebalancePlan(buys=buys, sells=sells)
