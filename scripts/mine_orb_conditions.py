#!/usr/bin/env python3
"""
QuantOS — ORB Condition-Mining Extraction (candidate 18 follow-up)
────────────────────────────────────────────────────────────────────
See docs/ORB_CONDITION_MINING_METHODOLOGY.md for the pre-registered
design: five candidate conditions (index trend stage, day-of-week,
opening-range-width ratio, gap at open, DTE bucket) plus exit reason as a
diagnostic-only sixth, mined against the Stratified (locked-final) variant
of candidate 18's real trades, with a time-based 80/20 mining/holdout
split per index and a three-step pass bar.

This script does the joining, not the analysis: it reuses
core/orb_scalping/backtest.py's `run_index_backtest` UNCHANGED for the
actual trade list (so it can never drift from what
scripts/backtest_orb_scalping.py already produces), and walks the same
day-by-day loop a second time -- same skip conditions, same order -- to
compute each trade's six condition values. An alignment assertion checks
the two passes produced the same trades in the same order before writing
anything, rather than trusting they did.

Needs a fresh Fyers token (agent/config.yaml's configured broker) -- same
dependency every other ORB script in this project has.

Usage
─────
    python scripts/mine_orb_conditions.py
    python scripts/mine_orb_conditions.py --out docs/ORB_CONDITION_MINING_RESULTS.md
"""

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers.base import OHLCV  # noqa: E402
from core.brokers.history import fetch_daily  # noqa: E402
from core.orb_scalping.backtest import (  # noqa: E402
    group_by_day,
    is_banknifty_monthly_expiry_day,
    is_nifty_weekly_expiry_day,
    resolve_banknifty_expiry,
    resolve_nifty_expiry,
    run_index_backtest,
)
from core.orb_scalping.conditions import (  # noqa: E402
    RANGE_TRAILING_WINDOW,
    TradeConditions,
    bucket_dte,
    day_of_week,
    gap_pct,
    index_stage_at,
    load_weinstein_clauses,
    opening_range_width,
    range_width_ratio,
)
from core.orb_scalping.condition_mining import (  # noqa: E402
    ConditionedTrade,
    evaluate_condition,
    time_based_split,
)
from core.orb_scalping.premium import reconstruct_premium  # noqa: E402
from core.orb_scalping.signal import simulate_day  # noqa: E402
from core.vault.models import Stage  # noqa: E402
from scripts.backtest_dow_theory_trend import fetch_chunked_intraday  # noqa: E402
from scripts.backtest_orb_scalping import (  # noqa: E402
    BANKNIFTY_SYMBOL,
    BANKNIFTY_WINDOW_START,
    NIFTY_SYMBOL,
    NIFTY_WINDOW_START,
    VIX_SYMBOL,
)

logger = logging.getLogger(__name__)

# Daily NIFTY 50 / NIFTY BANK index symbols -- Fyers spot-index naming,
# same as core/orb_scalping's own precedent (candidate 14/15's Darvas and
# ORB probes fetch the same two names for daily bars).
NIFTY_DAILY_SYMBOL = "NIFTY 50"
BANKNIFTY_DAILY_SYMBOL = "NIFTY BANK"

# sma(150)[100] needs 250 warmed-up daily bars (core/vault/stages.py) --
# fetch well before each index's own intraday window starts so the
# earliest trades are still classifiable, not silently unclassified.
STAGE_WARMUP_DAYS = 500


# ─── Per-day condition computation (mirrors run_index_backtest's own loop) ──

def _resolve(underlying: str):
    if underlying == "NIFTY":
        return resolve_nifty_expiry, is_nifty_weekly_expiry_day
    if underlying == "BANKNIFTY":
        return resolve_banknifty_expiry, is_banknifty_monthly_expiry_day
    raise ValueError(f"unsupported underlying: {underlying!r}")


def compute_conditions(
    index_candles: list[OHLCV], vix_candles: list[OHLCV], daily_bars: list[OHLCV],
    *, underlying: str, weinstein_clauses,
) -> list[TradeConditions]:
    """Walks the SAME day loop run_index_backtest uses internally (sorted
    days, skip if no VIX candles that day, skip if simulate_day finds no
    trade) so the resulting list lines up 1:1 with its stratified_trades
    output. Trailing opening-range widths accumulate day by day, entry day
    excluded -- no lookahead."""
    resolve_expiry, is_expiry_day_fn = _resolve(underlying)
    idx_by_day = group_by_day(index_candles)
    vix_by_day = group_by_day(vix_candles)
    trading_days = set(idx_by_day.keys())
    daily_close_by_date = {b.timestamp.date(): b.close for b in daily_bars}
    sorted_daily_dates = sorted(daily_close_by_date)

    trailing_widths: list[float] = []
    out: list[TradeConditions] = []

    for day in sorted(idx_by_day):
        day_candles = idx_by_day[day]
        vix_day_candles = vix_by_day.get(day)
        if not vix_day_candles:
            continue

        index_trade = simulate_day(day_candles)
        if index_trade is None:
            # Still accumulate this day's own range width into the
            # trailing history even on a no-trade day -- the ratio is
            # about the RANGE, not about whether a trade happened.
            trailing_widths.append(opening_range_width(day_candles))
            trailing_widths[:] = trailing_widths[-RANGE_TRAILING_WINDOW:]
            continue

        expiry, _liquidity_tier = resolve_expiry(day, trading_days)
        premium_trade = reconstruct_premium(
            index_trade, day_candles, vix_day_candles, expiry,
            strike_interval=(50.0 if underlying == "NIFTY" else 100.0),
        )
        dte = (expiry - day).days

        prior_dates = [d for d in sorted_daily_dates if d < day]
        prior_close = daily_close_by_date[prior_dates[-1]] if prior_dates else None

        out.append(TradeConditions(
            entry_date=day,
            stage=index_stage_at(daily_bars, day, weinstein_clauses),
            day_of_week=day_of_week(day),
            range_width_ratio=range_width_ratio(day_candles, trailing_widths),
            gap_pct=gap_pct(day_candles[0].open, prior_close),
            days_to_expiry=dte,
            dte_bucket=bucket_dte(dte),
            exit_reason=premium_trade.exit_reason,
        ))

        trailing_widths.append(opening_range_width(day_candles))
        trailing_widths[:] = trailing_widths[-RANGE_TRAILING_WINDOW:]

    return out


# ─── Report ───────────────────────────────────────────────────────────────

CONDITIONS = [
    ("stage2", lambda c: None if c.stage is None else c.stage is Stage.ADVANCING),
    ("monday_or_friday", lambda c: c.day_of_week in ("Monday", "Friday")),
    ("wide_range", lambda c: None if c.range_width_ratio is None else c.range_width_ratio > 1.25),
    ("narrow_range", lambda c: None if c.range_width_ratio is None else c.range_width_ratio < 0.75),
    ("big_gap", lambda c: None if c.gap_pct is None else abs(c.gap_pct) > 0.3),
    ("dte_0_1", lambda c: c.dte_bucket == "0-1"),
    ("dte_10_plus", lambda c: c.dte_bucket == "10+"),
]


def _verdict_row(v) -> str:
    return (
        f"| {v.name} | {v.mining_true_n} | {v.mining_true_metrics.profit_factor:.2f} | "
        f"{v.mining_true_metrics.sharpe_ratio:.2f} | {v.holdout_true_n} | "
        f"{v.holdout_true_metrics.profit_factor:.2f} | {v.holdout_true_metrics.sharpe_ratio:.2f} | "
        f"{'YES' if v.informative else 'no'} | {v.reason} |"
    )


def summarize(underlying: str, conditioned: list[ConditionedTrade]) -> str:
    mining, holdout = time_based_split(conditioned)
    base_mining = mining[0].trade.entry_date.date() if mining else None
    base_holdout_start = holdout[0].trade.entry_date.date() if holdout else None
    lines = [
        f"## {underlying}",
        "",
        f"{len(conditioned)} trades total. Mining set: {len(mining)} trades "
        f"({base_mining} onward). Holdout set: {len(holdout)} trades "
        f"({base_holdout_start} onward).",
        "",
        "| Condition | Mining n | Mining PF | Mining Sharpe | Holdout n | Holdout PF | "
        "Holdout Sharpe | Informative | Reason |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, predicate in CONDITIONS:
        v = evaluate_condition(name, underlying, mining, holdout, predicate)
        lines.append(_verdict_row(v))
    lines.append("")
    return "\n".join(lines)


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

    print("Fetching 5-minute NIFTY/BankNifty/VIX candles (chunked) ...")
    nifty_candles = await fetch_chunked_intraday(broker, NIFTY_SYMBOL, nifty_from_dt, to_dt, sem)
    banknifty_candles = await fetch_chunked_intraday(broker, BANKNIFTY_SYMBOL, banknifty_from_dt, to_dt, sem)
    vix_candles = await fetch_chunked_intraday(broker, VIX_SYMBOL, banknifty_from_dt, to_dt, sem)
    if not nifty_candles or not banknifty_candles or not vix_candles:
        print("ERROR: one or more 5m series returned zero candles.")
        return 1
    print(f"  NIFTY {len(nifty_candles)}, BankNifty {len(banknifty_candles)}, VIX {len(vix_candles)}")

    print("Fetching daily NIFTY/BankNifty candles for stage classification ...")
    daily_from = datetime.combine(
        NIFTY_WINDOW_START - timedelta(days=STAGE_WARMUP_DAYS), datetime.min.time(), tzinfo=timezone.utc)
    nifty_daily = fetch_daily(broker, NIFTY_DAILY_SYMBOL, daily_from, to_dt)
    banknifty_daily = fetch_daily(broker, BANKNIFTY_DAILY_SYMBOL, daily_from, to_dt)
    if not nifty_daily or not banknifty_daily:
        print("ERROR: daily series returned zero candles.")
        return 1
    print(f"  NIFTY daily {len(nifty_daily)}, BankNifty daily {len(banknifty_daily)}")

    weinstein_clauses = load_weinstein_clauses()

    print("Running NIFTY backtest + condition extraction ...")
    *_, nifty_stratified = run_index_backtest(nifty_candles, vix_candles, underlying="NIFTY")
    nifty_conditions = compute_conditions(
        nifty_candles, vix_candles, nifty_daily, underlying="NIFTY",
        weinstein_clauses=weinstein_clauses,
    )
    _assert_aligned(nifty_stratified, nifty_conditions, "NIFTY")
    nifty_joined = [ConditionedTrade(t, c) for t, c in zip(nifty_stratified, nifty_conditions)]

    print("Running BankNifty backtest + condition extraction ...")
    *_, banknifty_stratified = run_index_backtest(banknifty_candles, vix_candles, underlying="BANKNIFTY")
    banknifty_conditions = compute_conditions(
        banknifty_candles, vix_candles, banknifty_daily, underlying="BANKNIFTY",
        weinstein_clauses=weinstein_clauses,
    )
    _assert_aligned(banknifty_stratified, banknifty_conditions, "BANKNIFTY")
    banknifty_joined = [ConditionedTrade(t, c) for t, c in zip(banknifty_stratified, banknifty_conditions)]

    report = "\n".join([
        "# ORB Condition-Mining — Results",
        "",
        "Methodology: docs/ORB_CONDITION_MINING_METHODOLOGY.md. Every row below "
        "reports the pre-registered three-step pass bar (min sample size, "
        "mining-set improvement, holdout confirmation) -- an 'Informative: no' "
        "row is a legitimate, reportable result, not an error.",
        "",
        summarize("NIFTY", nifty_joined),
        summarize("BANKNIFTY", banknifty_joined),
    ])
    out_path = Path(args.out)
    out_path.write_text(report + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


def _assert_aligned(trades, conditions, underlying: str) -> None:
    if len(trades) != len(conditions):
        raise AssertionError(
            f"{underlying}: {len(trades)} stratified trades but {len(conditions)} "
            f"condition records -- the two passes over the day loop diverged, "
            f"refusing to join misaligned data"
        )
    for t, c in zip(trades, conditions):
        if t.entry_date.date() != c.entry_date:
            raise AssertionError(
                f"{underlying}: trade entry_date {t.entry_date.date()} != "
                f"condition entry_date {c.entry_date} -- misaligned join"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--out", default="docs/ORB_CONDITION_MINING_RESULTS.md")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
