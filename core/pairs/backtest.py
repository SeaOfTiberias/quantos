"""
QuantOS — Pairs Trading: Walk-Forward Formation/Trading Simulation
────────────────────────────────────────────────────────────────
See docs/PAIRS_TRADING_METHODOLOGY.md "Walk-forward schedule" and
"Entry / exit rules" sections. Pure logic (no I/O) operating on
already-loaded per-symbol daily futures series -- the driver script
(scripts/backtest_pairs_trading.py) is responsible for building those
series from the cached bhavcopy raw zips.

Formation and trading are separated from the FIRST run, not retrofitted:
a pair's hedge ratio and spread mean/std are estimated once per formation
window and frozen for the entire following trading window -- no
re-estimation, no lookahead.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

import numpy as np

from core.pairs.cointegration import CointegrationResult, form_pairs
from core.pairs.costs import position_cost

FORMATION_MONTHS = 6
TRADING_MONTHS = 3
ENTRY_Z = 2.0
MAX_HOLD_TRADING_DAYS = 20
FORCE_CLOSE_DTE = 3          # calendar days to near-month expiry
NOTIONAL_PER_LEG = 100_000.0  # each leg independently sized to this, see methodology doc


@dataclass(frozen=True)
class FuturesDay:
    """One symbol's near-month futures contract state for one trading day."""
    trade_date: date
    close:      float
    lot_size:   int
    expiry:     date  # the near-month contract's own expiry


@dataclass(frozen=True)
class PairTrade:
    symbol_a:     str
    symbol_b:     str
    entry_date:   date
    exit_date:    date
    entry_z:      float
    exit_reason:  str   # "mean_reversion" | "max_hold" | "forced_pre_expiry"
    direction_a:  str   # "BUY" or "SELL"
    direction_b:  str
    entry_price_a: float
    exit_price_a:  float
    entry_price_b: float
    exit_price_b:  float
    lots_a:        int
    lots_b:         int
    gross_pnl:      float
    cost:           float

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.cost


# ─── Walk-forward window schedule ───────────────────────────────────────────

def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, 28)  # window boundaries don't need exact month-end precision
    return date(year, month, day)


def formation_trading_windows(
    start: date, end: date,
    formation_months: int = FORMATION_MONTHS, trading_months: int = TRADING_MONTHS,
) -> list[tuple[date, date, date, date]]:
    """(formation_start, formation_end, trading_start, trading_end) tuples,
    stepping forward by trading_months each time, until trading_end would
    exceed `end`. First formation window starts at `start`."""
    windows = []
    formation_start = start
    while True:
        formation_end = _add_months(formation_start, formation_months)
        trading_start = formation_end
        trading_end = _add_months(trading_start, trading_months)
        if trading_end > end:
            break
        windows.append((formation_start, formation_end, trading_start, trading_end))
        formation_start = _add_months(formation_start, trading_months)
    return windows


# ─── Per-window slicing ─────────────────────────────────────────────────────

def _slice(series: list[FuturesDay], start: date, end: date) -> list[FuturesDay]:
    return [d for d in series if start <= d.trade_date < end]


# ─── Single-pair trading-window simulation ──────────────────────────────────

def _lots_for_notional(price: float, lot_size: int, notional: float = NOTIONAL_PER_LEG) -> int:
    return max(1, round(notional / (price * lot_size)))


def simulate_pair(
    pair: CointegrationResult,
    trading_a: list[FuturesDay], trading_b: list[FuturesDay],
) -> list[PairTrade]:
    """Walks the trading window day by day for one already-formed pair,
    using ONLY pair.hedge_ratio / spread_mean / spread_std (frozen at
    formation) to compute z_t. One open position at a time -- no
    pyramiding, no re-entry mid-trade."""
    by_a = {d.trade_date: d for d in trading_a}
    by_b = {d.trade_date: d for d in trading_b}
    dates = sorted(set(by_a) & set(by_b))
    if len(dates) < 2:
        return []

    trades: list[PairTrade] = []
    open_trade: Optional[dict] = None

    for i, d in enumerate(dates):
        da, db = by_a[d], by_b[d]
        if da.close <= 0 or db.close <= 0:
            continue
        z = (np.log(da.close) - pair.hedge_ratio * np.log(db.close) - pair.spread_mean) / pair.spread_std

        if open_trade is None:
            if z > ENTRY_Z or z < -ENTRY_Z:
                direction_a = "SELL" if z > ENTRY_Z else "BUY"
                direction_b = "BUY" if z > ENTRY_Z else "SELL"
                open_trade = {
                    "entry_date": d, "entry_z": float(z),
                    "direction_a": direction_a, "direction_b": direction_b,
                    "entry_price_a": da.close, "entry_price_b": db.close,
                    "lots_a": _lots_for_notional(da.close, da.lot_size),
                    "lots_b": _lots_for_notional(db.close, db.lot_size),
                    "lot_size_a": da.lot_size, "lot_size_b": db.lot_size,
                    "hold_days": 0,
                }
            continue

        open_trade["hold_days"] += 1
        entry_z = open_trade["entry_z"]
        reverted = (entry_z > 0 and z <= 0.0) or (entry_z < 0 and z >= 0.0)
        forced = (da.expiry - d).days <= FORCE_CLOSE_DTE
        maxed_out = open_trade["hold_days"] >= MAX_HOLD_TRADING_DAYS
        is_last_day = i == len(dates) - 1

        if reverted or forced or maxed_out or is_last_day:
            reason = ("mean_reversion" if reverted else
                      "forced_pre_expiry" if forced else
                      "max_hold" if maxed_out else "window_end")
            trades.append(_close_trade(open_trade, d, da.close, db.close, reason))
            open_trade = None

    return trades


def _close_trade(open_trade: dict, exit_date: date, exit_price_a: float, exit_price_b: float, reason: str) -> PairTrade:
    pnl_a = ((exit_price_a - open_trade["entry_price_a"]) if open_trade["direction_a"] == "BUY"
             else (open_trade["entry_price_a"] - exit_price_a)) * open_trade["lot_size_a"] * open_trade["lots_a"]
    pnl_b = ((exit_price_b - open_trade["entry_price_b"]) if open_trade["direction_b"] == "BUY"
             else (open_trade["entry_price_b"] - exit_price_b)) * open_trade["lot_size_b"] * open_trade["lots_b"]

    cost_a = position_cost(
        open_trade["entry_price_a"], exit_price_a, open_trade["lot_size_a"], open_trade["lots_a"],
        open_trade["direction_a"], open_trade["entry_date"], exit_date,
    )
    cost_b = position_cost(
        open_trade["entry_price_b"], exit_price_b, open_trade["lot_size_b"], open_trade["lots_b"],
        open_trade["direction_b"], open_trade["entry_date"], exit_date,
    )

    return PairTrade(
        symbol_a="", symbol_b="",  # filled by caller (run_walk_forward), which knows the pair identity
        entry_date=open_trade["entry_date"], exit_date=exit_date, entry_z=open_trade["entry_z"],
        exit_reason=reason, direction_a=open_trade["direction_a"], direction_b=open_trade["direction_b"],
        entry_price_a=open_trade["entry_price_a"], exit_price_a=exit_price_a,
        entry_price_b=open_trade["entry_price_b"], exit_price_b=exit_price_b,
        lots_a=open_trade["lots_a"], lots_b=open_trade["lots_b"],
        gross_pnl=pnl_a + pnl_b, cost=cost_a + cost_b,
    )


# ─── Full walk-forward orchestration ────────────────────────────────────────

@dataclass(frozen=True)
class FoldResult:
    formation_start: date
    formation_end:   date
    trading_start:   date
    trading_end:     date
    n_pairs_tested:   int
    n_pairs_passed:   int
    trades:           list[PairTrade]


def run_walk_forward(
    candidate_pairs: list[tuple[str, str, str]],
    price_data: dict[str, list[FuturesDay]],
    start: date, end: date,
) -> list[FoldResult]:
    """One fold per (formation_window, trading_window) step. Pairs are
    re-tested for cointegration fresh in EVERY formation window -- a pair
    that passed in one fold and fails in the next is simply not traded
    that fold, no carry-forward."""
    folds = []
    for formation_start, formation_end, trading_start, trading_end in formation_trading_windows(start, end):
        close_by_date: dict[str, dict[date, float]] = {}
        for symbol, series in price_data.items():
            window = _slice(series, formation_start, formation_end)
            if window:
                close_by_date[symbol] = {d.trade_date: d.close for d in window}

        # Only test pairs whose two legs actually share >=20 formation-window
        # dates (see cointegration.test_pair's own alignment requirement).
        alignable_pairs = []
        aligned_closes: dict[str, list[float]] = {}
        for a, b, sector in candidate_pairs:
            if a not in close_by_date or b not in close_by_date:
                continue
            common = sorted(set(close_by_date[a]) & set(close_by_date[b]))
            if len(common) < 20:
                continue
            aligned_closes[a] = [close_by_date[a][d] for d in common]
            aligned_closes[b] = [close_by_date[b][d] for d in common]
            alignable_pairs.append((a, b, sector))

        passing = form_pairs(alignable_pairs, aligned_closes)

        fold_trades: list[PairTrade] = []
        for pair in passing:
            trading_a = _slice(price_data[pair.symbol_a], trading_start, trading_end)
            trading_b = _slice(price_data[pair.symbol_b], trading_start, trading_end)
            for t in simulate_pair(pair, trading_a, trading_b):
                fold_trades.append(_tag_symbols(t, pair.symbol_a, pair.symbol_b))

        folds.append(FoldResult(
            formation_start=formation_start, formation_end=formation_end,
            trading_start=trading_start, trading_end=trading_end,
            n_pairs_tested=len(alignable_pairs), n_pairs_passed=len(passing),
            trades=fold_trades,
        ))
    return folds


def _tag_symbols(trade: PairTrade, symbol_a: str, symbol_b: str) -> PairTrade:
    from dataclasses import replace
    return replace(trade, symbol_a=symbol_a, symbol_b=symbol_b)
