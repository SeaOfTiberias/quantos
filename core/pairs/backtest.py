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

from core.pairs.cointegration import CointegrationResult, test_pair
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
    next_month_close: Optional[float] = None
    # ^ Same-day close of the contract that becomes near-month once this
    # one expires -- raw input to core/pairs/roll_adjust.py, not consumed
    # anywhere else. None if a second expiry wasn't listed that day.
    adj_close: Optional[float] = None
    # ^ Roll-adjusted close (core/pairs/roll_adjust.py's
    # build_adjusted_series), used ONLY for cointegration/hedge-ratio
    # estimation and trading-window z-score computation -- see
    # docs/PAIRS_TRADING_V2_METHODOLOGY.md's "what adj_close is NOT used
    # for" section. `close` (raw) remains the ONLY price ever used for
    # actual fills, P&L, and costs. None until build_adjusted_series has
    # run; simulate_pair falls back to `close` if still None (candidate
    # 12's original, unadjusted behavior).


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
    lot_size_a:     int
    lot_size_b:     int
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
        # z-score signal uses the roll-adjusted close (falls back to raw
        # `close` if no adjusted series was built) -- see
        # docs/PAIRS_TRADING_V2_METHODOLOGY.md: a roll seam mid-trading-window
        # must not manufacture a false z-spike. Fills/P&L below always use
        # da.close/db.close (raw), never the adjusted price.
        signal_a = da.adj_close if da.adj_close is not None else da.close
        signal_b = db.adj_close if db.adj_close is not None else db.close
        z = (np.log(signal_a) - pair.hedge_ratio * np.log(signal_b) - pair.spread_mean) / pair.spread_std

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
        lot_size_a=open_trade["lot_size_a"], lot_size_b=open_trade["lot_size_b"],
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
    n_pairs_excluded_corp_action: int = 0
    # ^ docs/PAIRS_TRADING_V2_METHODOLOGY.md Fix 1 -- pairs dropped this
    # fold because either leg's RAW close series had a suspected
    # unadjusted corporate-action jump in the formation or trading window.
    # Defaults to 0 so any caller building a FoldResult directly (existing
    # tests) is unaffected.


def _has_symbol_corp_action_jump(series: list[FuturesDay]) -> bool:
    """docs/PAIRS_TRADING_V2_METHODOLOGY.md Fix 1 -- reuses
    core/rotation/reconstitution_gutcheck.py's ratio-band check exactly
    (deferred import: core/pairs has no other dependency on core/rotation,
    same "import, don't reimplement" precedent core/rotation/equity_curve.py
    set importing _size_new_entrants from executor.py). Checks RAW close
    (never adj_close) -- a genuine roll-day move averages ~1.8%, nowhere
    near this check's [0.5, 2.0] ratio band, so this and the roll-adjustment
    fix catch structurally different magnitudes, never double-counting the
    same event."""
    from core.rotation.reconstitution_gutcheck import _has_corporate_action_jump

    if len(series) < 2:
        return False
    as_tuples = [(d.trade_date, d.close) for d in series]
    return _has_corporate_action_jump(as_tuples, 0, len(as_tuples) - 1)


def run_walk_forward(
    candidate_pairs: list[tuple[str, str, str]],
    price_data: dict[str, list[FuturesDay]],
    start: date, end: date,
) -> list[FoldResult]:
    """One fold per (formation_window, trading_window) step. Pairs are
    re-tested for cointegration fresh in EVERY formation window -- a pair
    that passed in one fold and fails in the next is simply not traded
    that fold, no carry-forward.

    Cointegration/hedge-ratio estimation uses each FuturesDay's adj_close
    if present (falls back to raw close otherwise, so callers that never
    built a roll-adjusted series -- e.g. existing tests -- are unaffected)
    -- see docs/PAIRS_TRADING_V2_METHODOLOGY.md Fix 2. A pair is dropped
    from a fold entirely (before cointegration is even tested) if either
    leg's RAW close series shows a suspected corporate-action jump in
    either window -- Fix 1."""
    folds = []
    for formation_start, formation_end, trading_start, trading_end in formation_trading_windows(start, end):
        close_by_date: dict[str, dict[date, float]] = {}
        formation_window: dict[str, list[FuturesDay]] = {}
        trading_window: dict[str, list[FuturesDay]] = {}
        for symbol, series in price_data.items():
            f_window = _slice(series, formation_start, formation_end)
            t_window = _slice(series, trading_start, trading_end)
            if f_window:
                formation_window[symbol] = f_window
                close_by_date[symbol] = {
                    d.trade_date: (d.adj_close if d.adj_close is not None else d.close)
                    for d in f_window
                }
            if t_window:
                trading_window[symbol] = t_window

        # Each pair gets its OWN date-intersection alignment -- a symbol can
        # appear in many candidate pairs with different counterparts, each
        # sharing a different subset of dates, so this cannot be cached
        # per-symbol (a real bug this fixed: two pairs sharing symbol "A"
        # were clobbering a single dict[symbol] -> aligned_closes entry,
        # feeding test_pair mismatched-length series from unrelated pairs).
        alignable_pairs = []
        passing: list[CointegrationResult] = []
        n_corp_action_excluded = 0
        for a, b, sector in candidate_pairs:
            if a not in close_by_date or b not in close_by_date:
                continue
            if (_has_symbol_corp_action_jump(formation_window.get(a, [])) or
                    _has_symbol_corp_action_jump(formation_window.get(b, [])) or
                    _has_symbol_corp_action_jump(trading_window.get(a, [])) or
                    _has_symbol_corp_action_jump(trading_window.get(b, []))):
                n_corp_action_excluded += 1
                continue
            common = sorted(set(close_by_date[a]) & set(close_by_date[b]))
            if len(common) < 20:
                continue
            alignable_pairs.append((a, b, sector))
            closes_a = [close_by_date[a][d] for d in common]
            closes_b = [close_by_date[b][d] for d in common]
            result = test_pair(a, b, closes_a, closes_b)
            if result is not None and result.passes:
                passing.append(result)

        fold_trades: list[PairTrade] = []
        for pair in passing:
            trading_a = trading_window.get(pair.symbol_a, [])
            trading_b = trading_window.get(pair.symbol_b, [])
            for t in simulate_pair(pair, trading_a, trading_b):
                fold_trades.append(_tag_symbols(t, pair.symbol_a, pair.symbol_b))

        folds.append(FoldResult(
            formation_start=formation_start, formation_end=formation_end,
            trading_start=trading_start, trading_end=trading_end,
            n_pairs_tested=len(alignable_pairs), n_pairs_passed=len(passing),
            n_pairs_excluded_corp_action=n_corp_action_excluded,
            trades=fold_trades,
        ))
    return folds


def _tag_symbols(trade: PairTrade, symbol_a: str, symbol_b: str) -> PairTrade:
    from dataclasses import replace
    return replace(trade, symbol_a=symbol_a, symbol_b=symbol_b)
