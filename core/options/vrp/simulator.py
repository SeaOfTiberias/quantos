"""
QuantOS — VRP Phase 3: Strangle P&L Simulator (pooled per-trade stats, no costs)
──────────────────────────────────────────────────────────────────────────────
Runs docs/VRP_METHODOLOGY.md's short-strangle rule over every entry cycle
Phase 2 (core/options/vrp/strikes.py) reconstructs, using ONLY real recorded
bhavcopy prices — no Black-Scholes-simulated payoff. Entry premium is a
leg's real `close` on the entry date (the price a fill at that day's close
would have paid).

Exit value is NOT read directly from each contract's own `settle_price` row
on its expiry date -- a real NSE bhavcopy gotcha, confirmed by direct
inspection (both schema generations): on a contract's OWN expiry date,
`settle_price` (and, in the new-format schema, `underlying_close`) is
overwritten with the UNDERLYING's final settlement value, identically
across every strike and both CE/PE for that expiry -- not each contract's
own intrinsic payout. (On every other day of a contract's life, including
its own entry date, `settle_price` behaves normally as that contract's own
per-strike value.) This module reads the shared underlying settlement value
off any row for that expiry on its expiry date, then derives each leg's
true cash-settlement payout as intrinsic value from the STRIKE Phase 2
already selected -- max(0, settlement - strike) for a call, max(0, strike -
settlement) for a put -- exactly how NSE index options actually cash-settle.

Scope, pre-committed in docs/VRP_METHODOLOGY.md: this is a GROSS, pre-cost
read (pooled per-trade profit factor/Sharpe/win rate), matching how
S7-3/S8-3/S8-4 all started before a cost model or capital-tracked equity
curve was layered on. Do not read a positive number here as a verdict —
Phase 4 (transaction costs, still blocked on resolving lot size across the
legacy/new-format schema gap — see the methodology doc) has not run yet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from core.options.vrp.bhavcopy import DEFAULT_PARSED_CACHE_DIR, load_cached_range
from core.options.vrp.strikes import StrangleSelection

WEEKLY_ANNUALIZATION = 52  # cycles are weekly per the methodology's entry rule


@dataclass(frozen=True)
class StrangleTrade:
    entry_date:         date
    expiry_date:        date
    dte:                int
    spot_estimate:      float
    call_strike:        float
    call_entry_premium: float
    call_delta:         float
    call_method:        str
    put_strike:         float
    put_entry_premium:  float
    put_delta:          float
    put_method:         str
    call_exit_value:    Optional[float]
    put_exit_value:     Optional[float]

    @property
    def entry_credit(self) -> float:
        return self.call_entry_premium + self.put_entry_premium

    @property
    def pnl_points(self) -> Optional[float]:
        if self.call_exit_value is None or self.put_exit_value is None:
            return None
        return self.entry_credit - (self.call_exit_value + self.put_exit_value)

    @property
    def pnl_pct_of_credit(self) -> Optional[float]:
        pnl = self.pnl_points
        if pnl is None or self.entry_credit <= 0:
            return None
        return pnl / self.entry_credit * 100.0


def _underlying_settlement(rows: list, expiry_date) -> Optional[float]:
    """The shared underlying settlement value on one contract's own expiry
    date (see module docstring). CRITICAL: only rows whose OWN expiry is
    `expiry_date` carry this override -- a day's cache file also contains
    still-live rows from OTHER, later expiries, and those retain their
    normal per-contract settle_price that same day (confirmed by direct
    inspection: on 2024-01-11, the 2024-01-11-expiry rows all show
    settle_price==underlying_close, while 2024-01-18/01-25/02-01-expiry
    rows on that same date show distinct, normal-looking option premiums).
    Prefers `underlying_close` (only present in the new-format schema, but
    unambiguous when it is) and falls back to `settle_price` (present in
    both, and equal to `underlying_close` whenever both exist)."""
    same_expiry = [r for r in rows if r.expiry == expiry_date]
    for r in same_expiry:
        if r.underlying_close is not None:
            return r.underlying_close
    for r in same_expiry:
        if r.settle_price is not None:
            return r.settle_price
    return None


def simulate(
    selections: list[StrangleSelection], parsed_cache_dir: Path = DEFAULT_PARSED_CACHE_DIR,
) -> list[StrangleTrade]:
    """Turn each Phase 2 strike selection into a priced trade by deriving
    each leg's true cash-settlement payout from the underlying's final
    settlement value on the shared expiry date (see module docstring for
    why this can't be read directly off each contract's own settle_price
    row). A cycle whose expiry date has no cached data (shouldn't happen
    inside the fetched window, but the fetch has documented holiday/error
    gaps) comes back with exit values of None rather than raising, so the
    caller can count it as "missing settlement" instead of silently
    dropping it."""
    trades = []
    for sel in selections:
        expiry_rows = list(load_cached_range(sel.expiry_date, sel.expiry_date, parsed_cache_dir))
        settlement = _underlying_settlement(expiry_rows, sel.expiry_date)
        if settlement is None:
            call_exit = put_exit = None
        else:
            call_exit = max(0.0, settlement - sel.call.strike)
            put_exit = max(0.0, sel.put.strike - settlement)
        trades.append(StrangleTrade(
            entry_date=sel.entry_date, expiry_date=sel.expiry_date, dte=sel.dte,
            spot_estimate=sel.spot_estimate,
            call_strike=sel.call.strike, call_entry_premium=sel.call.row.close,
            call_delta=sel.call.delta, call_method=sel.call.method,
            put_strike=sel.put.strike, put_entry_premium=sel.put.row.close,
            put_delta=sel.put.delta, put_method=sel.put.method,
            call_exit_value=call_exit, put_exit_value=put_exit,
        ))
    return trades


@dataclass(frozen=True)
class BacktestStats:
    n_trades:             int
    n_missing_settlement: int
    win_rate:             float
    avg_pnl_pct:          float
    profit_factor:        float
    sharpe:               float
    max_drawdown_pct:     float


def stats_from_pcts(pnls: list[float], n_missing: int) -> BacktestStats:
    """Pooled per-trade stats from a plain list of %-of-credit P&L values.
    Factored out of compute_stats() so Phase 4's NET stats (see
    core/options/vrp/costs.py) reuse the exact same math instead of a
    parallel, driftable copy of it."""
    if not pnls:
        return BacktestStats(0, n_missing, 0.0, 0.0, 0.0, 0.0, 0.0)

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    win_rate = len(wins) / len(pnls)
    avg_pnl = sum(pnls) / len(pnls)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

    if len(pnls) >= 2:
        std = math.sqrt(sum((p - avg_pnl) ** 2 for p in pnls) / (len(pnls) - 1))
        sharpe = (avg_pnl / std) * math.sqrt(WEEKLY_ANNUALIZATION) if std > 0 else 0.0
    else:
        sharpe = 0.0

    cum = peak = max_dd = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    return BacktestStats(
        n_trades=len(pnls), n_missing_settlement=n_missing,
        win_rate=round(win_rate, 4), avg_pnl_pct=round(avg_pnl, 2),
        profit_factor=round(profit_factor, 3), sharpe=round(sharpe, 3),
        max_drawdown_pct=round(max_dd, 2),
    )


def compute_stats(trades: list[StrangleTrade]) -> BacktestStats:
    missing = sum(1 for t in trades if t.pnl_pct_of_credit is None)
    pnls = [t.pnl_pct_of_credit for t in trades if t.pnl_pct_of_credit is not None]
    return stats_from_pcts(pnls, missing)
