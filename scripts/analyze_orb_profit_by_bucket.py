#!/usr/bin/env python3
"""
QuantOS — ORB Options Scalping: net profit contribution by arm bucket
(candidate 18)
──────────────────────────────────────────────────────────────────────
Follow-up to docs/ORB_ARM_GIVEBACK_ANALYSIS.md, which measured give-back
in INDEX POINTS, and docs/ORB_ARM_THRESHOLD_RESULTS.md, which found
lowering the arm threshold makes the strategy worse. The remaining
question: does the strategy's real, cost-adjusted edge actually come from
the ARMED bucket (the trades that reach a full range-width move), with
the never-armed buckets closer to a wash or a net drag?

Joins the same bucket classification (armed / never-armed-flatten /
never-armed-stopped) used by scripts/analyze_orb_arm_giveback.py to the
Stratified (locked-final) COST-ADJUSTED net profit per trade — the same
number any go/no-go verdict in this project reads
(docs/ORB_SCALPING_RESULTS.md) — rather than raw index points. Pure
measurement: no parameter changed, reuses core/orb_scalping/backtest.py's
own cost/premium pipeline unmodified.

Usage
─────
    python scripts/analyze_orb_profit_by_bucket.py
    python scripts/analyze_orb_profit_by_bucket.py --out docs/ORB_PROFIT_BY_BUCKET_ANALYSIS.md
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.backtest.parser import BacktestTrade, _compute_metrics  # noqa: E402
from core.brokers.base import OHLCV  # noqa: E402
from core.orb_scalping.backtest import (  # noqa: E402
    BANKNIFTY_LOT_SIZE,
    BANKNIFTY_STRIKE_INTERVAL,
    NIFTY_LOT_SIZE,
    NIFTY_STRIKE_INTERVAL,
    _to_backtest_trade,
    group_by_day,
    is_banknifty_monthly_expiry_day,
    resolve_banknifty_expiry,
    resolve_nifty_expiry,
)
from core.orb_scalping.expiry import is_nifty_weekly_expiry_day  # noqa: E402
from core.orb_scalping.premium import reconstruct_premium  # noqa: E402
from core.orb_scalping.signal import simulate_day  # noqa: E402
from scripts.analyze_orb_arm_giveback import ARMED, NEVER_ARMED_FLATTEN, NEVER_ARMED_STOPPED, _classify  # noqa: E402
from scripts.backtest_dow_theory_trend import fetch_chunked_intraday  # noqa: E402
from scripts.backtest_orb_scalping import (  # noqa: E402
    BANKNIFTY_SYMBOL,
    BANKNIFTY_WINDOW_START,
    NIFTY_SYMBOL,
    NIFTY_WINDOW_START,
    VIX_SYMBOL,
)


def bucketed_stratified_trades(
    index_candles: list[OHLCV], vix_candles: list[OHLCV], *, underlying: str,
) -> dict[str, list[BacktestTrade]]:
    """Same per-day walk as run_index_backtest, but tags each resulting
    Stratified BacktestTrade with its arm bucket instead of discarding
    that information -- run_index_backtest's own return type has no room
    for it (see docs/ORB_CONDITION_MINING_METHODOLOGY.md's Data Extraction
    section for the same "BacktestTrade drops what we need" reasoning)."""
    if underlying == "NIFTY":
        lot_size, strike_interval = NIFTY_LOT_SIZE, NIFTY_STRIKE_INTERVAL
        resolve_expiry = resolve_nifty_expiry
        is_expiry_day_fn = is_nifty_weekly_expiry_day
    elif underlying == "BANKNIFTY":
        lot_size, strike_interval = BANKNIFTY_LOT_SIZE, BANKNIFTY_STRIKE_INTERVAL
        resolve_expiry = resolve_banknifty_expiry
        is_expiry_day_fn = is_banknifty_monthly_expiry_day
    else:
        raise ValueError(f"unsupported underlying: {underlying!r}")

    idx_by_day = group_by_day(index_candles)
    vix_by_day = group_by_day(vix_candles)
    trading_days = set(idx_by_day.keys())

    by_bucket: dict[str, list[BacktestTrade]] = {ARMED: [], NEVER_ARMED_FLATTEN: [], NEVER_ARMED_STOPPED: []}
    trade_num = 0

    for day in sorted(idx_by_day):
        day_candles = idx_by_day[day]
        vix_day_candles = vix_by_day.get(day)
        if not vix_day_candles:
            continue

        index_trade = simulate_day(day_candles)
        if index_trade is None:
            continue

        expiry, liquidity_tier = resolve_expiry(day, trading_days)
        is_expiry_day = is_expiry_day_fn(day, trading_days)
        premium_trade = reconstruct_premium(
            index_trade, day_candles, vix_day_candles, expiry, strike_interval,
        )

        trade_num += 1
        bars_held = index_trade.exit_index - index_trade.entry_index
        bt = _to_backtest_trade(
            entry_dt=premium_trade.entry_timestamp, exit_dt=premium_trade.exit_timestamp,
            entry_premium=premium_trade.entry_premium, exit_premium=premium_trade.exit_premium,
            lot_size=lot_size, trade_num=trade_num, bars_held=bars_held,
            variant="stratified", underlying=underlying, is_expiry_day=is_expiry_day,
        )
        by_bucket[_classify(index_trade)].append(bt)

    return by_bucket


def _fmt_metrics(trades: list[BacktestTrade]) -> str:
    if len(trades) < 3:
        return f"{len(trades)} trades (too few for a metric)"
    m = _compute_metrics(trades)
    return f"{len(trades)} trades, PF {m.profit_factor:.2f}, Sharpe {m.sharpe_ratio:.2f}"


def _section(underlying: str, by_bucket: dict[str, list[BacktestTrade]]) -> str:
    all_trades = [t for trades in by_bucket.values() for t in trades]
    total_net_profit = sum(t.profit for t in all_trades)
    overall = _compute_metrics(all_trades)

    lines = [f"## {underlying}", "",
            f"All {len(all_trades)} trades: PF {overall.profit_factor:.2f}, "
            f"Sharpe {overall.sharpe_ratio:.2f}, total net profit "
            f"{total_net_profit:+,.0f} (arbitrary premium units x lot size, "
            f"same convention as docs/ORB_SCALPING_RESULTS.md).",
            "",
            "| Bucket | Trades | Share of trades | Net profit | Share of total net profit | Bucket's own PF/Sharpe |",
            "|---|---|---|---|---|---|"]

    for bucket in (ARMED, NEVER_ARMED_FLATTEN, NEVER_ARMED_STOPPED):
        trades = by_bucket.get(bucket, [])
        bucket_profit = sum(t.profit for t in trades)
        trade_share = len(trades) / len(all_trades) * 100 if all_trades else 0.0
        # Share of total net profit is only meaningful when total_net_profit
        # isn't ~zero -- reported regardless, but flagged if the denominator
        # is degenerate (near-zero total makes any ratio wildly unstable,
        # same class of trap as the mean-of-ratio bug this candidate's own
        # arm-giveback analysis already caught once, see that script).
        profit_share = (bucket_profit / total_net_profit * 100) if abs(total_net_profit) > 1e-6 else float("nan")
        profit_share_str = f"{profit_share:+.0f}%" if profit_share == profit_share else "n/a (total ~0)"
        lines.append(f"| {bucket} | {len(trades)} | {trade_share:.1f}% | {bucket_profit:+,.0f} | "
                    f"{profit_share_str} | {_fmt_metrics(trades)} |")
    lines.append("")

    armed_trades = by_bucket.get(ARMED, [])
    non_armed_trades = by_bucket.get(NEVER_ARMED_FLATTEN, []) + by_bucket.get(NEVER_ARMED_STOPPED, [])
    if armed_trades and non_armed_trades:
        non_armed_metrics = _compute_metrics(non_armed_trades)
        non_armed_profit = sum(t.profit for t in non_armed_trades)
        lines += [
            f"**Non-armed trades alone** (never-armed-flatten + never-armed-stopped, "
            f"{len(non_armed_trades)} trades): net profit {non_armed_profit:+,.0f}, "
            f"PF {non_armed_metrics.profit_factor:.2f}, Sharpe {non_armed_metrics.sharpe_ratio:.2f} "
            f"-- {'this subset alone clears the PF>1/Sharpe>0.5 bar' if non_armed_metrics.has_positive_edge else 'this subset alone does NOT clear the PF>1/Sharpe>0.5 bar on its own'}.",
            "",
        ]

    return "\n".join(lines)


def summarize(nifty_by_bucket, banknifty_by_bucket) -> str:
    return "\n".join([
        "# ORB Options Scalping — Net Profit by Arm Bucket (Candidate 18)",
        "",
        "MEASUREMENT ONLY, same discipline as "
        "docs/ORB_ARM_GIVEBACK_ANALYSIS.md and "
        "docs/ORB_ARM_THRESHOLD_METHODOLOGY.md: no parameter changed, no "
        "new backtest variant. Answers whether the strategy's real, "
        "Stratified-cost-adjusted edge is concentrated in the ARMED "
        "bucket (trades reaching a full range-width move) or shared "
        "across all three buckets.",
        "",
        _section("NIFTY", nifty_by_bucket),
        _section("BANKNIFTY", banknifty_by_bucket),
    ])


# ─── Orchestration ────────────────────────────────────────────────────────

async def main_async(args) -> int:
    config = load_config(args.config)
    from core.brokers import get_broker
    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')} ...")
    if not broker.connect():
        print("ERROR: broker connect() returned False -- check the Fyers token.")
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

    print("Fetching India VIX 5m candles (covers both indices' windows) ...")
    vix_candles = await fetch_chunked_intraday(broker, VIX_SYMBOL, banknifty_from_dt, to_dt, sem)
    print(f"  {len(vix_candles)} candles fetched")

    if not nifty_candles or not banknifty_candles or not vix_candles:
        print("ERROR: one or more series returned zero candles.")
        return 1

    print("Computing NIFTY bucketed trades ...")
    nifty_by_bucket = bucketed_stratified_trades(nifty_candles, vix_candles, underlying="NIFTY")

    print("Computing BankNifty bucketed trades ...")
    banknifty_by_bucket = bucketed_stratified_trades(banknifty_candles, vix_candles, underlying="BANKNIFTY")

    report = summarize(nifty_by_bucket, banknifty_by_bucket)
    out_path = Path(args.out)
    out_path.write_text(report + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--out", default="docs/ORB_PROFIT_BY_BUCKET_ANALYSIS.md")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
