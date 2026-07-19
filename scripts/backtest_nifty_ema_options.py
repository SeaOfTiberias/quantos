#!/usr/bin/env python3
"""
QuantOS — S8-4: NIFTY EMA9/21 Options Strategy Backtest
──────────────────────────────────────────────────────────
Backtests the user's Fyers-automated strategy (5-min EMA9/EMA21 crossover on
NIFTY -> buy ATM/near-ATM CE on bullish cross, PE on bearish cross) over
real NIFTY 5-min history, comparing the live baseline exit rule (fixed
+/-Rs2000 P&L cap or 3:10pm) against two candidates the user asked about:
a trailing stop, and a faster exit when the crossover itself invalidates.

Option premium approximation
─────────────────────────────
No historical NIFTY option chain/IV data exists in this repo (confirmed
2026-07-19). P&L is approximated as `delta * underlying_point_move *
LOT_SIZE`, held at a CONSTANT delta for the life of each trade -- a real
first pass, not a pricing model (gamma/theta/vega are all ignored).

The delta was NOT hand-guessed: it was checked against S8-2's real trades
(real premiums from the tradebook, real underlying moves from a NIFTY 5-min
fetch) first. That check came back n=8, mean=-0.004, one point with
|implied delta|>1 -- i.e. short-hold option P&L is dominated by bid-ask/
gamma/IV noise, not a clean linear relationship to the underlying's move.
Trying to fit a "calibrated" delta to 8 noisy points would be fitting noise,
not signal, so this uses a standard near-ATM weekly-option delta instead
(APPROX_DELTA below) -- honest about being a textbook number, not a fitted
one. LOT_SIZE=65 IS grounded in real data (every trade in S8-2's tradebook
used qty=65, not the stale 75 placeholder found elsewhere in this repo).

Cost model
──────────
core/risk/costs.py's CostModel is equity-intraday-only by its own docstring.
Options costs differ (STT 0.1% on sell PREMIUM, different exchange/SEBI
rates) -- OPTIONS_COST_MODEL below instantiates the same CostModel dataclass
with options parameters, exactly as S8-4's backlog story specifies. Since
this harness doesn't track an absolute premium level (only point-move-
implied P&L), a fixed PREMIUM_PROXY approximates the entry premium purely
for computing percentage-based costs -- not claimed as the real premium.

Usage:
    python scripts/backtest_nifty_ema_options.py
    python scripts/backtest_nifty_ema_options.py --years 2 --out docs/S8_4_BACKTEST_RESULTS.md
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.backtest.parser import BacktestTrade, _compute_metrics  # noqa: E402
from core.brokers.base import BrokerAdapter, OHLCV  # noqa: E402
from core.regime.fetcher import _ema, _atr  # noqa: E402
from core.risk.costs import CostModel  # noqa: E402

_IST = timezone(timedelta(hours=5, minutes=30))
MAX_CHUNK_DAYS = 95            # Fyers rejects 5m-resolution requests spanning >100 days

LOT_SIZE = 65                   # grounded in S8-2's real tradebook (every fill used qty=65)
APPROX_DELTA = 0.45             # standard near-ATM weekly-option delta (NOT calibrated -- see module docstring)
PREMIUM_PROXY = 140.0           # for cost calc only; median-ish of S8-2's observed entry premiums

PNL_CAP = 2000.0                # the live strategy's stated +/- P&L exit
TIME_EXIT = "15:10"             # IST, matches the live strategy
NO_NEW_ENTRIES_AFTER = "15:00"  # IST -- no time left to develop a trade before the time-exit
ATR_TRAIL_MULT = 1.5            # trailing-stop distance in underlying ATRs (5-min, 14-period)
ATR_TRAIL_ACTIVATE_PTS = 15.0   # underlying must move this far favourably before the trail engages

OPTIONS_COST_MODEL = CostModel(
    brokerage_pct=0.0003, brokerage_flat=20.0,   # same Fyers brokerage cap as equity
    stt_pct=0.001,          # 0.1% on SELL premium (options rate, vs equity's 0.025%)
    exchange_txn_pct=0.0003503,  # NSE F&O exchange transaction charge on premium (approx, both legs)
    sebi_pct=0.000001,      # same SEBI rate as equity, both legs
    stamp_pct=0.00003,      # same stamp duty class as equity intraday, buy leg
    gst_pct=0.18,
    slippage_bps=0.0,
)


# ─── Signal detection (pure, no I/O) ───────────────────────────────────────────

@dataclass
class Signal:
    index:     int           # candle index in the full series
    direction: str            # "BULL" | "BEAR"
    timestamp: datetime


def detect_crossovers(candles: list[OHLCV]) -> tuple[list[Signal], list[float], list[float]]:
    """EMA9/EMA21 crossovers computed CONTINUOUSLY across the whole series
    (not reset daily -- matches how a live charting EMA behaves; the
    strategy's "monitoring starts at 9:15am" describes when it ACTS on
    signals, not a daily indicator reset). Only signals during market hours
    with enough runway before the time-exit are kept."""
    closes = [c.close for c in candles]
    ema9 = [_ema(closes[: i + 1], 9) for i in range(len(closes))]
    ema21 = [_ema(closes[: i + 1], 21) for i in range(len(closes))]

    cutoff = datetime.strptime(NO_NEW_ENTRIES_AFTER, "%H:%M").time()
    open_time = datetime.strptime("09:15", "%H:%M").time()

    signals = []
    for i in range(1, len(candles)):
        ts_ist = candles[i].timestamp.astimezone(_IST)
        if not (open_time <= ts_ist.time() <= cutoff):
            continue
        was_bull, now_bull = ema9[i - 1] > ema21[i - 1], ema9[i] > ema21[i]
        if not was_bull and now_bull:
            signals.append(Signal(index=i, direction="BULL", timestamp=candles[i].timestamp))
        elif was_bull and not now_bull:
            signals.append(Signal(index=i, direction="BEAR", timestamp=candles[i].timestamp))
    return signals, ema9, ema21


# ─── Position simulation ───────────────────────────────────────────────────────

ExitCheck = Callable[[list[OHLCV], list[float], list[float], int, int, str, float], Optional[tuple[int, str]]]
# (candles, ema9, ema21, entry_idx, current_idx, direction, entry_underlying) -> (exit_idx, reason) | None


def _pnl_at(direction: str, underlying_entry: float, underlying_now: float) -> float:
    move = (underlying_now - underlying_entry) if direction == "BULL" else (underlying_entry - underlying_now)
    return APPROX_DELTA * move * LOT_SIZE


def _time_exit_check(candles, ema9, ema21, entry_idx, i, direction, underlying_entry) -> Optional[tuple[int, str]]:
    ts = candles[i].timestamp.astimezone(_IST)
    if ts.time() >= datetime.strptime(TIME_EXIT, "%H:%M").time():
        return i, "TIME"
    return None


def baseline_exit_check(candles, ema9, ema21, entry_idx, i, direction, underlying_entry) -> Optional[tuple[int, str]]:
    """Matches the live strategy: +/-Rs2000 cap, else 3:10pm."""
    pnl = _pnl_at(direction, underlying_entry, candles[i].close)
    if abs(pnl) >= PNL_CAP:
        return i, "PNL_CAP"
    return _time_exit_check(candles, ema9, ema21, entry_idx, i, direction, underlying_entry)


def invalidation_exit_check(candles, ema9, ema21, entry_idx, i, direction, underlying_entry) -> Optional[tuple[int, str]]:
    """Exit the moment the crossover that triggered entry reverses, instead
    of riding to the P&L cap regardless."""
    bullish_now = ema9[i] > ema21[i]
    if direction == "BULL" and not bullish_now:
        return i, "INVALIDATION"
    if direction == "BEAR" and bullish_now:
        return i, "INVALIDATION"
    return _time_exit_check(candles, ema9, ema21, entry_idx, i, direction, underlying_entry)


def make_trailing_exit_check(atr_mult: float = ATR_TRAIL_MULT, activate_pts: float = ATR_TRAIL_ACTIVATE_PTS) -> ExitCheck:
    """ATR-based trailing stop on the underlying: once the favourable move
    exceeds `activate_pts`, trail at (peak - atr_mult * local ATR). Adapts
    to volatility rather than a fixed point buffer."""
    peak_state: dict[int, float] = {}   # entry_idx -> best favourable underlying level so far

    def check(candles, ema9, ema21, entry_idx, i, direction, underlying_entry) -> Optional[tuple[int, str]]:
        now = candles[i].close
        fav = (now - underlying_entry) if direction == "BULL" else (underlying_entry - now)
        best_fav = peak_state.get(entry_idx, 0.0)
        if fav > best_fav:
            peak_state[entry_idx] = fav
            best_fav = fav

        if best_fav >= activate_pts:
            local_atr = _atr(candles[max(0, i - 14): i + 1], period=14)
            trail_buffer = atr_mult * local_atr if local_atr > 0 else activate_pts * 0.5
            giveback = best_fav - fav
            if giveback >= trail_buffer:
                return i, "TRAILING_STOP"
        return _time_exit_check(candles, ema9, ema21, entry_idx, i, direction, underlying_entry)

    return check


def simulate(candles: list[OHLCV], signals: list[Signal], ema9: list[float], ema21: list[float],
             exit_check: ExitCheck, cost_model: CostModel) -> list[BacktestTrade]:
    """Single position at a time: enter on a signal while flat, ignore new
    signals while in a trade (matches the sequential, non-overlapping
    pattern observed in S8-2's real fills), run until exit_check fires."""
    trades = []
    trade_num = 0
    i = 0
    signal_by_idx = {s.index: s for s in signals}

    while i < len(candles):
        sig = signal_by_idx.get(i)
        if sig is None:
            i += 1
            continue

        entry_idx = i
        underlying_entry = candles[entry_idx].close
        exit_idx, reason = None, None
        for j in range(entry_idx + 1, len(candles)):
            result = exit_check(candles, ema9, ema21, entry_idx, j, sig.direction, underlying_entry)
            if result:
                exit_idx, reason = result
                break
        if exit_idx is None:
            exit_idx = len(candles) - 1  # ran off the end of history — close at last known price

        underlying_exit = candles[exit_idx].close
        pnl_per_unit = _pnl_at(sig.direction, underlying_entry, underlying_exit) / LOT_SIZE
        entry_premium = PREMIUM_PROXY
        exit_premium = PREMIUM_PROXY + pnl_per_unit
        cost_direction = "BUY"  # always long premium (buy CE or buy PE), never short
        costs = cost_model.cost_of(entry_premium, exit_premium, LOT_SIZE, cost_direction)

        trade_num += 1
        trades.append(BacktestTrade(
            trade_num=trade_num, direction="Long", qty=LOT_SIZE,
            entry_date=candles[entry_idx].timestamp, entry_price=entry_premium,
            exit_date=candles[exit_idx].timestamp, exit_price=exit_premium,
            profit=pnl_per_unit * LOT_SIZE, profit_pct=(pnl_per_unit / entry_premium * 100 if entry_premium else 0),
            cum_profit=0.0, bars_held=exit_idx - entry_idx, costs=costs,
        ))
        i = exit_idx + 1  # flat again from here

    # Backfill cumulative GROSS profit now that the full sequence is known
    # (matches BacktestTrade.cum_profit's own convention -- gross, not net).
    cum = 0.0
    for t in trades:
        cum += t.profit
        t.cum_profit = cum
    return trades


# ─── Fetch layer ────────────────────────────────────────────────────────────────

async def fetch_chunked_5m(broker: BrokerAdapter, symbol: str, from_date: datetime, to_date: datetime,
                            sem: asyncio.Semaphore, delay: float = 0.5, max_retries: int = 3) -> list[OHLCV]:
    loop = asyncio.get_event_loop()
    all_candles: list[OHLCV] = []
    chunk_start = from_date
    while chunk_start < to_date:
        chunk_end = min(chunk_start + timedelta(days=MAX_CHUNK_DAYS), to_date)
        for attempt in range(max_retries):
            async with sem:
                try:
                    candles = await loop.run_in_executor(
                        None,
                        lambda cs=chunk_start, ce=chunk_end: broker.get_historical_data(symbol, "5m", cs, ce),
                    )
                    await asyncio.sleep(delay)
                    all_candles.extend(candles)
                    break
                except Exception as e:
                    if "429" in str(e) and attempt < max_retries - 1:
                        await asyncio.sleep(3.0 * (attempt + 1))
                        continue
                    print(f"  Failed chunk {chunk_start.date()}..{chunk_end.date()}: {e}")
                    break
        chunk_start = chunk_end

    dedup = {c.timestamp: c for c in all_candles}
    return [dedup[k] for k in sorted(dedup)]


# ─── Report ─────────────────────────────────────────────────────────────────────

def summarize(variants: dict[str, list[BacktestTrade]]) -> str:
    lines = [
        "# S8-4 NIFTY EMA9/21 Options Strategy Backtest",
        "",
        f"Option P&L approximated as `delta({APPROX_DELTA}) x underlying point move x "
        f"LOT_SIZE({LOT_SIZE})`, held at constant delta for each trade's life — a real "
        f"first pass, not an options pricing model (no historical NIFTY option chain/IV "
        f"data exists in this repo). Delta was checked against S8-2's real trades first "
        f"(came back too noisy at n=8 to calibrate — see module docstring) rather than "
        f"hand-picked with no grounding. Lot size IS grounded in real data (every S8-2 "
        f"fill used qty=65). Costs use a new options-rate `CostModel` instance "
        f"(STT 0.1% on sell premium vs equity's 0.025%).",
        "",
        "## Comparison",
        "",
        "| Variant | Trades | Win rate | Profit factor | Sharpe | Net profit % | Avg bars held |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, trades in variants.items():
        if not trades:
            lines.append(f"| {name} | 0 | - | - | - | - | - |")
            continue
        m = _compute_metrics(trades)
        lines.append(
            f"| {name} | {m.total_trades} | {m.win_rate:.0%} | {m.profit_factor:.2f} | "
            f"{m.sharpe_ratio:.2f} | {m.net_profit_pct:.1f}% | {m.avg_bars_held:.1f} |"
        )

    lines += [
        "",
        "## Caveats",
        "",
        "- Delta-approximated P&L, not real option pricing (see header) — read the "
        "RELATIVE comparison between variants as the signal, not the absolute rupee figures.",
        "- Single position at a time, no pyramiding — matches the sequential pattern "
        "observed in S8-2's real fills.",
        "- This is one backtest run over one historical window, not a pre-committed "
        "sample of independent instruments like S7-3/S8-3 — NIFTY is the only "
        "underlying the live strategy trades, so there's no universe to sample from. "
        "The overfitting risk here is in the EXIT RULE PARAMETERS (trailing ATR "
        "multiplier, activation threshold), not instrument selection — these were "
        "chosen as standard defaults before running, not grid-searched for the best look.",
    ]
    return "\n".join(lines)


async def main_async(args) -> int:
    config = load_config(args.config)
    from core.brokers import get_broker
    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')} ...")
    broker.connect()

    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=365 * args.years)
    sem = asyncio.Semaphore(2)

    print(f"Fetching NIFTY 5m candles {from_date.date()} -> {to_date.date()} (chunked, throttled) ...")
    candles = await fetch_chunked_5m(broker, "NIFTY 50", from_date, to_date, sem)
    print(f"  {len(candles)} candles")
    if len(candles) < 100:
        print("ERROR: not enough candles for a meaningful backtest.")
        return 1

    signals, ema9, ema21 = detect_crossovers(candles)
    print(f"  {len(signals)} crossover signals detected")

    variants = {
        "Baseline (+/-Rs2000 or 3:10pm, live strategy)": simulate(candles, signals, ema9, ema21, baseline_exit_check, OPTIONS_COST_MODEL),
        "Trailing stop (ATR-based)": simulate(candles, signals, ema9, ema21, make_trailing_exit_check(), OPTIONS_COST_MODEL),
        "Faster invalidation exit": simulate(candles, signals, ema9, ema21, invalidation_exit_check, OPTIONS_COST_MODEL),
    }
    for name, trades in variants.items():
        print(f"  {name}: {len(trades)} trades")

    report = summarize(variants)
    Path(args.out).write_text(report + "\n", encoding="utf-8")
    print(f"\nWrote {args.out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--years", type=float, default=2.0)
    parser.add_argument("--out", default="docs/S8_4_BACKTEST_RESULTS.md")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
