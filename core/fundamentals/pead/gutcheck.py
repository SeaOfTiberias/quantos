"""
QuantOS — PEAD Gut-Check: Forward-Return vs Earnings-Surprise Correlation
────────────────────────────────────────────────────────────────────────────
Fable's explicit recommendation (2026-07-23, see memory:
quantos-pead-earnings-feasibility) before committing to Phase 2 backtest
infrastructure: pull forward returns for the point-in-time PAT rows
core.fundamentals.pead.pipeline already builds, and eyeball whether return
sign/magnitude after `broadcast_date` correlates with `yoy_surprise_pct`
sign at all.

Deliberately minimal -- descriptive statistics and a correlation
coefficient only. NOT a backtest: no transaction costs, no position
sizing, no Sharpe/profit-factor, no signal threshold. If this comes back
flat, that's the answer Fable said should stop the search for a fifth
strategy candidate, not something to keep tuning until it looks better.

**Entry/exit convention, a deliberate simplification for a quick look, NOT
the eventual Phase 2 entry rule**: entry = close on the first trading day
STRICTLY AFTER `broadcast_date`'s calendar date (daily bhavcopy only, no
intraday data, so same-day-close-vs-next-day-open timing -- which Fable
flagged as a real Phase 2 design question given NSE broadcasts land up to
after-hours -- is not resolved here, just sidestepped with the simplest
honest choice). Exit = close N TRADING days after entry (not calendar
days), for a small fixed set of horizons.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from core.fundamentals.pead.eq_bhavcopy import EqCloseRow
from core.fundamentals.pead.pipeline import PeadSignalRow

# Short + intermediate horizons for a robustness eyeball, not a parameter
# sweep -- this is a diagnostic, not signal design (see module docstring).
DEFAULT_HORIZONS_TRADING_DAYS = (5, 10, 20)

PriceIndex = dict[str, list[tuple[date, float]]]


def build_price_index(rows: list[EqCloseRow]) -> PriceIndex:
    """symbol -> chronologically sorted (trade_date, close) list."""
    by_symbol: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for r in rows:
        by_symbol[r.symbol].append((r.trade_date, r.close))
    for symbol in by_symbol:
        by_symbol[symbol].sort()
    return dict(by_symbol)


@dataclass(frozen=True)
class ForwardReturn:
    symbol: str
    entry_date: date
    exit_date: date
    horizon_trading_days: int
    entry_close: float
    exit_close: float
    return_pct: float


def compute_forward_return(
    price_index: PriceIndex, symbol: str, broadcast_date: date, horizon_trading_days: int,
) -> Optional[ForwardReturn]:
    """None (not zero-filled) when the symbol has no cached price series,
    entry has no trading day at/after broadcast_date+1 within the cached
    range, or the horizon runs past the end of the cached series --
    missing data, not "no return"."""
    series = price_index.get(symbol)
    if not series:
        return None

    entry_cutoff = broadcast_date + timedelta(days=1)
    entry_idx = next((i for i, (d, _) in enumerate(series) if d >= entry_cutoff), None)
    if entry_idx is None:
        return None

    exit_idx = entry_idx + horizon_trading_days
    if exit_idx >= len(series):
        return None

    entry_date, entry_close = series[entry_idx]
    exit_date, exit_close = series[exit_idx]
    if entry_close == 0:
        return None
    return ForwardReturn(
        symbol=symbol, entry_date=entry_date, exit_date=exit_date,
        horizon_trading_days=horizon_trading_days, entry_close=entry_close, exit_close=exit_close,
        return_pct=(exit_close - entry_close) / entry_close * 100,
    )


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    denom = math.sqrt(var_x * var_y)
    return cov / denom if denom > 0 else None


@dataclass(frozen=True)
class HorizonSummary:
    horizon_trading_days: int
    n: int
    correlation: Optional[float]  # Pearson(yoy_surprise_pct, forward_return_pct)
    positive_surprise_n: int
    positive_surprise_mean_return_pct: Optional[float]
    positive_surprise_win_rate: Optional[float]
    negative_surprise_n: int
    negative_surprise_mean_return_pct: Optional[float]
    negative_surprise_win_rate: Optional[float]
    market_return_pct: Optional[float] = None  # only set when market_adjusted=True


def summarize(
    pead_rows: list[PeadSignalRow], price_index: PriceIndex,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS_TRADING_DAYS,
    *, market_adjusted: bool = False,
) -> list[HorizonSummary]:
    """One summary row per horizon. "Positive/negative surprise" splits on
    yoy_surprise_pct sign (>0 / <0) -- exact zero is vanishingly unlikely
    with real PAT data and isn't specially handled.

    `market_adjusted=True` demeans each horizon's returns by the
    EQUAL-WEIGHTED CROSS-SECTIONAL MEAN return of every matched row at
    that horizon (not a dedicated benchmark index series) before computing
    correlation/group stats -- a cheap, standard way to strip out a shared
    market-wide/beta move over the sample's own window when a proper
    benchmark isn't already loaded. Useful for telling "no PEAD effect"
    apart from "the whole window was a broad selloff/rally and every stock
    moved together regardless of earnings," which raw absolute returns
    alone can't distinguish -- but this is still a diagnostic, not
    something a real strategy would trade on as-is (a live PEAD strategy
    would go long/short vs an index or peer group directly, not vs its own
    backtest sample's average)."""
    out = []
    for h in horizons:
        pairs: list[tuple[float, float]] = []
        for row in pead_rows:
            fr = compute_forward_return(price_index, row.symbol, row.broadcast_date.date(), h)
            if fr is not None:
                pairs.append((row.yoy_surprise_pct, fr.return_pct))

        market_return = statistics.mean([r for _, r in pairs]) if (pairs and market_adjusted) else None
        if market_adjusted and market_return is not None:
            pairs = [(surprise, ret - market_return) for surprise, ret in pairs]

        pos_returns = [ret for surprise, ret in pairs if surprise > 0]
        neg_returns = [ret for surprise, ret in pairs if surprise < 0]
        out.append(HorizonSummary(
            horizon_trading_days=h,
            n=len(pairs),
            correlation=_pearson([p[0] for p in pairs], [p[1] for p in pairs]) if pairs else None,
            positive_surprise_n=len(pos_returns),
            positive_surprise_mean_return_pct=statistics.mean(pos_returns) if pos_returns else None,
            positive_surprise_win_rate=(sum(1 for r in pos_returns if r > 0) / len(pos_returns)) if pos_returns else None,
            negative_surprise_n=len(neg_returns),
            negative_surprise_mean_return_pct=statistics.mean(neg_returns) if neg_returns else None,
            negative_surprise_win_rate=(sum(1 for r in neg_returns if r > 0) / len(neg_returns)) if neg_returns else None,
            market_return_pct=market_return,
        ))
    return out
