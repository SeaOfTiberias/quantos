"""
QuantOS — ORB Options Scalping Backtest Orchestration (candidate 18)
──────────────────────────────────────────────────────────────────────
Wires core/orb_scalping/{signal,premium,costs,expiry}.py together into
BacktestTrade rows core/backtest/parser.py's metrics machinery can
consume. Runs NIFTY and BankNifty independently (never pooled — see
docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md) and produces BOTH a Clean and a
Stressed (+15bps/leg slippage) trade list per index, per the doc's Cost
model section — same day's IndexTrade/PremiumTrade, costed twice.

Pure except for `resolve_*_expiry`'s reliance on an already-fetched
trading-day set (no I/O of its own — callers, e.g.
scripts/backtest_orb_scalping.py, own the broker fetch), same separation
as candidate 15's core/breakout1010/backtest.py.
"""

from __future__ import annotations

from datetime import date, datetime

from core.backtest.parser import BacktestTrade
from core.brokers.base import OHLCV
from core.orb_scalping.costs import clean_trade_cost, stressed_trade_cost
from core.orb_scalping.expiry import next_nifty_weekly_expiry, nifty_weekly_expiry
from core.orb_scalping.premium import reconstruct_premium
from core.orb_scalping.signal import simulate_day
from scripts.gutcheck_expiry_day_effect import adjust_for_holiday, calendar_expiry_date

NIFTY_LOT_SIZE = 65               # confirmed live 2026-07-28
NIFTY_STRIKE_INTERVAL = 50.0      # confirmed live 2026-07-28
BANKNIFTY_LOT_SIZE = 30           # confirmed live 2026-07-27 (candidate 15)
BANKNIFTY_STRIKE_INTERVAL = 100.0  # confirmed live 2026-07-27 (candidate 15)
DTE_FLOOR_DAYS = 2                 # methodology doc's DTE floor: NIFTY only


def group_by_day(candles: list[OHLCV]) -> dict[date, list[OHLCV]]:
    """UTC calendar date == IST trading-session date here: the whole
    03:45-10:00 UTC session sits inside one UTC day, never crossing
    midnight, same convention as candidates 14/15."""
    by_day: dict[date, list[OHLCV]] = {}
    for c in candles:
        by_day.setdefault(c.timestamp.date(), []).append(c)
    for day_candles in by_day.values():
        day_candles.sort(key=lambda c: c.timestamp)
    return by_day


def resolve_banknifty_expiry(entry_date: date, trading_days: set) -> date:
    """Nearest calendar-month BankNifty monthly expiry on/after
    entry_date — identical rule to candidate 15, no DTE floor (BankNifty's
    monthly contracts are never within 2 days of expiry at entry)."""
    year, month = entry_date.year, entry_date.month
    this_month_expiry = adjust_for_holiday(calendar_expiry_date(year, month), trading_days)
    if this_month_expiry >= entry_date:
        return this_month_expiry
    year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return adjust_for_holiday(calendar_expiry_date(year, month), trading_days)


def resolve_nifty_expiry(entry_date: date, trading_days: set) -> date:
    """Nearest NIFTY weekly expiry on/after entry_date, with the
    methodology doc's DTE floor applied: if the nearest weekly's own
    days-to-expiry from entry_date is <2, roll to the NEXT weekly
    instead."""
    expiry = nifty_weekly_expiry(entry_date, trading_days)
    if (expiry - entry_date).days < DTE_FLOOR_DAYS:
        expiry = next_nifty_weekly_expiry(expiry, trading_days)
    return expiry


def _to_backtest_trade(entry_dt: datetime, exit_dt: datetime, entry_premium: float,
                        exit_premium: float, lot_size: int, trade_num: int,
                        bars_held: int, stressed: bool) -> BacktestTrade:
    """Every trade here is a BUY-to-open (long option, CALL or PUT alike —
    both are a long premium position), so profit = (exit - entry) *
    lot_size, same as candidate 15."""
    profit = (exit_premium - entry_premium) * lot_size
    notional = entry_premium * lot_size
    profit_pct = (profit / notional * 100) if notional else 0.0
    cost_fn = stressed_trade_cost if stressed else clean_trade_cost
    costs = cost_fn(entry_premium=entry_premium, exit_premium=exit_premium,
                     lot_size=lot_size, entry_date=entry_dt.date()).total

    return BacktestTrade(
        trade_num=trade_num, direction="Long", qty=lot_size,
        entry_date=entry_dt, entry_price=entry_premium,
        exit_date=exit_dt, exit_price=exit_premium,
        profit=profit, profit_pct=profit_pct, cum_profit=0.0,
        bars_held=bars_held, costs=costs,
    )


def run_index_backtest(
    index_candles: list[OHLCV], vix_candles: list[OHLCV], *, underlying: str,
) -> tuple[list[BacktestTrade], list[BacktestTrade]]:
    """Full per-day simulation for ONE index (underlying: "NIFTY" |
    "BANKNIFTY") across an already-fetched index + India VIX 5m candle
    set. Returns (clean_trades, stressed_trades) — the same day's
    IndexTrade/PremiumTrade, costed twice per the Clean/Stressed split."""
    if underlying == "NIFTY":
        lot_size, strike_interval = NIFTY_LOT_SIZE, NIFTY_STRIKE_INTERVAL
        resolve_expiry = resolve_nifty_expiry
    elif underlying == "BANKNIFTY":
        lot_size, strike_interval = BANKNIFTY_LOT_SIZE, BANKNIFTY_STRIKE_INTERVAL
        resolve_expiry = resolve_banknifty_expiry
    else:
        raise ValueError(f"unsupported underlying: {underlying!r}")

    idx_by_day = group_by_day(index_candles)
    vix_by_day = group_by_day(vix_candles)
    trading_days = set(idx_by_day.keys())

    clean_trades: list[BacktestTrade] = []
    stressed_trades: list[BacktestTrade] = []
    trade_num = 0

    for day in sorted(idx_by_day):
        day_candles = idx_by_day[day]
        vix_day_candles = vix_by_day.get(day)
        if not vix_day_candles:
            continue

        index_trade = simulate_day(day_candles)
        if index_trade is None:
            continue

        expiry = resolve_expiry(day, trading_days)
        premium_trade = reconstruct_premium(
            index_trade, day_candles, vix_day_candles, expiry, strike_interval,
        )

        trade_num += 1
        bars_held = index_trade.exit_index - index_trade.entry_index
        common = dict(
            entry_dt=premium_trade.entry_timestamp, exit_dt=premium_trade.exit_timestamp,
            entry_premium=premium_trade.entry_premium, exit_premium=premium_trade.exit_premium,
            lot_size=lot_size, trade_num=trade_num, bars_held=bars_held,
        )
        clean_trades.append(_to_backtest_trade(**common, stressed=False))
        stressed_trades.append(_to_backtest_trade(**common, stressed=True))

    return clean_trades, stressed_trades
