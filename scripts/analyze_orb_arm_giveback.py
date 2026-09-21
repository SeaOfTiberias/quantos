#!/usr/bin/env python3
"""
QuantOS — ORB Options Scalping: how often the trailing stop never arms,
and how much of the intraday gain that costs (candidate 18)
──────────────────────────────────────────────────────────────────────
Prompted by a real live observation (2026-09-21): BankNifty's paper trade
rallied ~143 index points intraday, never reached the 1-range-width move
core/orb_scalping/signal.py requires to arm the trailing stop, and gave the
entire move back by the 15:20 IST session flatten. This script asks, over
the FULL historical sample the go/no-go backtest already used, how common
that specific shape is and how much it costs in index points.

This is a MEASUREMENT, not a tuning pass. It changes nothing about the
signal (core/orb_scalping/signal.py's arm-at-1-range-width rule, entry
logic, and stop mechanics are all untouched — this script only reads the
`armed` / `max_favorable_points` diagnostic fields IndexTrade already
carries) and proposes no new parameter. Same discipline as every prior
post-hoc read of this candidate's results: describe the data first: any
change to the arm rule itself would need its own pre-registered
methodology doc and a fresh Fable review before a backtest re-run, exactly
like every cost-model variant in docs/ORB_SCALPING_RESULTS.md's history —
this script's job is to inform whether that's worth doing, not to do it.

Reuses scripts/backtest_orb_scalping.py's exact data-fetch (same symbols,
same confirmed-safe per-index start dates) so the sample here is identical
to the one behind the pre-registered Stressed/Stratified verdicts — no new
data collection needed for this particular question.

Usage
─────
    python scripts/analyze_orb_arm_giveback.py
    python scripts/analyze_orb_arm_giveback.py --out docs/ORB_ARM_GIVEBACK_ANALYSIS.md
"""

import argparse
import asyncio
import statistics
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.orb_scalping.backtest import group_by_day  # noqa: E402
from core.orb_scalping.signal import IndexTrade, simulate_day  # noqa: E402
from scripts.backtest_dow_theory_trend import fetch_chunked_intraday  # noqa: E402
from scripts.backtest_orb_scalping import (  # noqa: E402
    BANKNIFTY_SYMBOL,
    BANKNIFTY_WINDOW_START,
    NIFTY_SYMBOL,
    NIFTY_WINDOW_START,
)

NEVER_ARMED_FLATTEN = "never-armed, rode to flatten"   # today's BankNifty shape
NEVER_ARMED_STOPPED = "never-armed, stopped out"
ARMED = "armed at some point"


@dataclass(frozen=True)
class TradeRow:
    entry_date: date
    bucket: str
    mfe_points: float
    mfe_pct: float          # mfe / entry_price, comparable across NIFTY/BankNifty
    final_move_points: float  # signed in the trade's OWN favorable direction
    given_back_points: float  # mfe - final_move; 0 for a trade that closed at its own peak


def _classify(trade: IndexTrade) -> str:
    if trade.armed:
        return ARMED
    return NEVER_ARMED_FLATTEN if trade.exit_reason == "session_flatten" else NEVER_ARMED_STOPPED


def _final_move(trade: IndexTrade) -> float:
    return (trade.exit_price - trade.entry_price if trade.direction == "CALL"
           else trade.entry_price - trade.exit_price)


def collect_trades(candles_by_day: dict) -> list[TradeRow]:
    rows: list[TradeRow] = []
    for day in sorted(candles_by_day):
        trade = simulate_day(candles_by_day[day])
        if trade is None:
            continue
        final_move = _final_move(trade)
        rows.append(TradeRow(
            entry_date=day, bucket=_classify(trade),
            mfe_points=trade.max_favorable_points,
            mfe_pct=(trade.max_favorable_points / trade.entry_price * 100.0
                    if trade.entry_price else 0.0),
            final_move_points=final_move,
            given_back_points=trade.max_favorable_points - final_move,
        ))
    return rows


def _fmt(values: list[float]) -> str:
    if not values:
        return "n/a"
    return f"mean {statistics.mean(values):+.1f}, median {statistics.median(values):+.1f}"


def _section(underlying: str, rows: list[TradeRow]) -> str:
    if not rows:
        return f"## {underlying}\n\n*(zero trades generated)*\n"

    lines = [f"## {underlying}", "", f"{len(rows)} trades total.", ""]

    by_bucket: dict[str, list[TradeRow]] = {}
    for r in rows:
        by_bucket.setdefault(r.bucket, []).append(r)

    lines += [
        "| Bucket | Trades | Share | Mean/median MFE (pts) | Mean/median given back (pts) |",
        "|---|---|---|---|---|",
    ]
    for bucket in (ARMED, NEVER_ARMED_FLATTEN, NEVER_ARMED_STOPPED):
        b = by_bucket.get(bucket, [])
        share = len(b) / len(rows) * 100.0 if rows else 0.0
        mfe_str = _fmt([r.mfe_points for r in b])
        gb_str = _fmt([r.given_back_points for r in b])
        lines.append(f"| {bucket} | {len(b)} | {share:.1f}% | {mfe_str} | {gb_str} |")
    lines.append("")

    flatten_never_armed = by_bucket.get(NEVER_ARMED_FLATTEN, [])
    if flatten_never_armed:
        given_back = [r.given_back_points for r in flatten_never_armed]
        final_moves = [r.final_move_points for r in flatten_never_armed]
        pct_mfe_kept = [
            (r.final_move_points / r.mfe_points * 100.0) if r.mfe_points > 0 else 100.0
            for r in flatten_never_armed
        ]
        net_losers = sum(1 for m in final_moves if m < 0)
        lines += [
            f"**The exact shape 2026-09-21's live BankNifty trade showed** — "
            f"never armed, rode to the 15:20 flatten: {len(flatten_never_armed)} of "
            f"{len(rows)} trades ({len(flatten_never_armed) / len(rows) * 100:.1f}%).",
            "",
            f"- Given back: {_fmt(given_back)} points.",
            f"- Of the peak (MFE) reached, on average this bucket's final exit kept "
            f"{statistics.mean(pct_mfe_kept):.0f}% of it (median {statistics.median(pct_mfe_kept):.0f}%).",
            f"- {net_losers} of {len(flatten_never_armed)} ({net_losers / len(flatten_never_armed) * 100:.0f}%) "
            f"closed net NEGATIVE despite having been in profit intraday.",
            f"- Total points given back across this bucket: {sum(given_back):+.1f} "
            f"(vs. total MFE across the same bucket: {sum(r.mfe_points for r in flatten_never_armed):+.1f}).",
            "",
        ]

    armed_trades = by_bucket.get(ARMED, [])
    if armed_trades:
        pct_mfe_kept_armed = [
            (r.final_move_points / r.mfe_points * 100.0) if r.mfe_points > 0 else 100.0
            for r in armed_trades
        ]
        lines += [
            f"**Contrast — trades that DID arm**: kept "
            f"{statistics.mean(pct_mfe_kept_armed):.0f}% of their MFE on average "
            f"(median {statistics.median(pct_mfe_kept_armed):.0f}%), vs. the never-armed-flatten "
            f"bucket above.",
            "",
        ]

    return "\n".join(lines)


def summarize(nifty_rows: list[TradeRow], banknifty_rows: list[TradeRow],
             nifty_window: tuple, banknifty_window: tuple) -> str:
    return "\n".join([
        "# ORB Options Scalping — Arm-Threshold Give-Back Analysis (Candidate 18)",
        "",
        "MEASUREMENT ONLY. See this script's own module docstring: the signal "
        "(core/orb_scalping/signal.py) is untouched, no parameter changed, no "
        "new backtest variant. Prompted by a real 2026-09-21 live paper trade "
        "(BankNifty, +143pt intraday rally, never armed, gave it all back by "
        "the 15:20 flatten) -- this asks how common that shape is across the "
        "full historical sample already behind the pre-registered verdict.",
        "",
        f"NIFTY window: {nifty_window[0]} to {nifty_window[1]} ({len(nifty_rows)} trades). "
        f"BankNifty window: {banknifty_window[0]} to {banknifty_window[1]} "
        f"({len(banknifty_rows)} trades).",
        "",
        _section("NIFTY", nifty_rows),
        _section("BankNifty", banknifty_rows),
        "## Reading this",
        "",
        "\"Given back\" is MFE minus the trade's own final signed move -- 0 for a "
        "trade that closed at its own best moment, positive for one that pulled "
        "back before exit. A NEVER-ARMED trade that stops out has already, by "
        "construction, given back little (the stop caps the loss near the "
        "initial level) -- the bucket that matters for \"are we leaving money "
        "on the table\" is NEVER-ARMED + session_flatten, reported above with "
        "its own detail. This does not by itself say the 1-range-width arm "
        "threshold is wrong -- the whole historical sample using this exact "
        "rule already cleared the pre-registered PF/Sharpe bar (see "
        "docs/ORB_SCALPING_RESULTS.md) -- only how much of the strategy's real "
        "profile this specific behaviour accounts for.",
    ])


# ─── Orchestration ────────────────────────────────────────────────────────

async def main_async(args) -> int:
    config = load_config(args.config)
    from core.brokers import get_broker
    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')} ...")
    if not broker.connect():
        print("ERROR: broker connect() returned False -- check the Fyers token "
              "(python agent/auth/fyers_auth.py).")
        return 1

    to_dt = datetime.now(timezone.utc)
    nifty_from_dt = datetime.combine(NIFTY_WINDOW_START, datetime.min.time(), tzinfo=timezone.utc)
    banknifty_from_dt = datetime.combine(BANKNIFTY_WINDOW_START, datetime.min.time(), tzinfo=timezone.utc)
    sem = asyncio.Semaphore(2)

    print(f"Fetching NIFTY 5m candles {nifty_from_dt.date()} -> {to_dt.date()} (chunked) ...")
    nifty_candles = await fetch_chunked_intraday(broker, NIFTY_SYMBOL, nifty_from_dt, to_dt, sem)
    print(f"  {len(nifty_candles)} candles fetched")

    print(f"Fetching BankNifty 5m candles {banknifty_from_dt.date()} -> {to_dt.date()} (chunked) ...")
    banknifty_candles = await fetch_chunked_intraday(broker, BANKNIFTY_SYMBOL, banknifty_from_dt, to_dt, sem)
    print(f"  {len(banknifty_candles)} candles fetched")

    if not nifty_candles or not banknifty_candles:
        print("ERROR: one or more series returned zero candles.")
        return 1

    nifty_by_day = group_by_day(nifty_candles)
    banknifty_by_day = group_by_day(banknifty_candles)

    print("Simulating NIFTY days ...")
    nifty_rows = collect_trades(nifty_by_day)
    print(f"  {len(nifty_rows)} NIFTY trades")

    print("Simulating BankNifty days ...")
    banknifty_rows = collect_trades(banknifty_by_day)
    print(f"  {len(banknifty_rows)} BankNifty trades")

    if not nifty_rows and not banknifty_rows:
        print("ERROR: zero trades generated for both indices.")
        return 1

    nifty_window = (min(nifty_by_day), max(nifty_by_day))
    banknifty_window = (min(banknifty_by_day), max(banknifty_by_day))

    report = summarize(nifty_rows, banknifty_rows, nifty_window, banknifty_window)
    out_path = Path(args.out)
    out_path.write_text(report + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--out", default="docs/ORB_ARM_GIVEBACK_ANALYSIS.md")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
