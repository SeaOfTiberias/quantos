"""
QuantOS — 10:10 Breakout Backtest Orchestration (candidate 15)
────────────────────────────────────────────────────────────────
Wires core/breakout1010/{signal,premium,costs}.py together into
BacktestTrade rows core/backtest/parser.py's metrics machinery can consume.
Pure except for `resolve_expiry`'s reliance on an already-fetched trading-
day set (no I/O of its own — callers, e.g. scripts/backtest_breakout1010.py,
own the broker fetch).
"""

from __future__ import annotations

from datetime import date, datetime

from core.backtest.parser import BacktestTrade
from core.breakout1010.costs import trade_cost
from core.breakout1010.premium import reconstruct_premium
from core.breakout1010.signal import simulate_day
from core.brokers.base import OHLCV
from scripts.gutcheck_expiry_day_effect import adjust_for_holiday, calendar_expiry_date

LOT_SIZE = 30    # confirmed live 2026-07-27 from the current BANKNIFTY symbol master


def group_by_day(candles: list[OHLCV]) -> dict[date, list[OHLCV]]:
    """UTC calendar date == IST trading-session date here: the whole
    03:45-10:00 UTC session sits inside one UTC day, never crossing
    midnight, same convention as scripts/backtest_dow_theory_trend.py."""
    by_day: dict[date, list[OHLCV]] = {}
    for c in candles:
        by_day.setdefault(c.timestamp.date(), []).append(c)
    for day_candles in by_day.values():
        day_candles.sort(key=lambda c: c.timestamp)
    return by_day


def resolve_expiry(entry_date: date, trading_days: set) -> date:
    """The nearest-calendar-month BankNifty monthly expiry on/after
    `entry_date` — this backtest's contract-selection rule (see
    docs/BREAKOUT_1010_METHODOLOGY.md's "Contract selection" section).
    Rolls to next month if this month's own expiry has already passed."""
    year, month = entry_date.year, entry_date.month
    this_month_expiry = adjust_for_holiday(calendar_expiry_date(year, month), trading_days)
    if this_month_expiry >= entry_date:
        return this_month_expiry
    year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return adjust_for_holiday(calendar_expiry_date(year, month), trading_days)


def to_backtest_trade(entry_dt: datetime, exit_dt: datetime, entry_premium: float,
                       exit_premium: float, trade_num: int, bars_held: int) -> BacktestTrade:
    """Every trade here is a BUY-to-open (long option, CALL or PUT alike —
    both are a long premium position), so direction-in-INR is always the
    same sign: profit = (exit - entry) * lot_size."""
    profit = (exit_premium - entry_premium) * LOT_SIZE
    notional = entry_premium * LOT_SIZE
    profit_pct = (profit / notional * 100) if notional else 0.0
    costs = trade_cost(entry_premium=entry_premium, exit_premium=exit_premium,
                        lot_size=LOT_SIZE, entry_date=entry_dt.date()).total

    return BacktestTrade(
        trade_num=trade_num, direction="Long", qty=LOT_SIZE,
        entry_date=entry_dt, entry_price=entry_premium,
        exit_date=exit_dt, exit_price=exit_premium,
        profit=profit, profit_pct=profit_pct, cum_profit=0.0,
        bars_held=bars_held, costs=costs,
    )


def run_backtest(bn_candles: list[OHLCV], vix_candles: list[OHLCV]) -> list[BacktestTrade]:
    """Full per-day simulation across an already-fetched BankNifty + India
    VIX 5m candle set. Days missing from either series, or with no
    breakout, contribute no trade."""
    bn_by_day = group_by_day(bn_candles)
    vix_by_day = group_by_day(vix_candles)
    trading_days = set(bn_by_day.keys())

    trades: list[BacktestTrade] = []
    trade_num = 0
    for day in sorted(bn_by_day):
        day_candles = bn_by_day[day]
        vix_day_candles = vix_by_day.get(day)
        if not vix_day_candles:
            continue

        index_trade = simulate_day(day_candles)
        if index_trade is None:
            continue

        expiry = resolve_expiry(day, trading_days)
        premium_trade = reconstruct_premium(index_trade, day_candles, vix_day_candles, expiry)

        trade_num += 1
        trades.append(to_backtest_trade(
            entry_dt=premium_trade.entry_timestamp, exit_dt=premium_trade.exit_timestamp,
            entry_premium=premium_trade.entry_premium, exit_premium=premium_trade.exit_premium,
            trade_num=trade_num,
            bars_held=index_trade.exit_index - index_trade.entry_index,
        ))

    return trades
