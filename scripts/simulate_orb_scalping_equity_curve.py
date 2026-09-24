#!/usr/bin/env python3
"""
QuantOS — Candidate 18 (ORB Options Scalping) Real Capital-Tracked Equity Curve
─────────────────────────────────────────────────────────────────────────────
docs/ORB_SCALPING_RESULTS.md's headline numbers are POOLED PER-TRADE stats
(core/backtest/parser.py's _compute_metrics), computed INDEPENDENTLY per
index, always at exactly 1 lot/trade, with no capital constraint at all --
they correctly answered "is there a signal edge" (the Sprint 7/8 gate), but
can't answer "what does my real ₹50,000 become," and structurally can't:
a real account trading BOTH NIFTY and BankNifty ORB signals shares ONE cash
pool, and a trade a real account can't afford on a given day simply doesn't
happen -- neither fact is visible in two indices' pooled stats computed
separately.

This script answers that instead, using core/backtest/equity_curve.py's
generic Account core (Track 2 of docs/SHARPE_SWEEP_AND_EQUITY_CURVE_PLAN.md).
Both indices' STRATIFIED trades (the locked-final cost variant per
ORB_SCALPING_RESULTS.md -- any go/no-go decision should read this one) are
merged into one chronological event stream and fed into a single Account.

Position sizing is deliberately UNCHANGED from the pre-registered backtest's
own convention: exactly 1 lot per trade, always (this script adds a
capital-sufficiency check on top of that fixed sizing -- it does not
re-litigate or introduce a new sizing policy). A trade the account can't
afford (cash < lot_size * entry_premium) is SKIPPED, not silently taken on
margin or partially filled, and counted separately so "how often did real
capital constrain this strategy" is visible on its own.

The equity curve marks EVERY trading day in the fetched window (the union
of both indices' trading calendars), not just days with a trade -- a real
account sitting in cash on a no-trade day is a real (zero-return) day in
the Sharpe/CAGR calculation, not a gap.

Fetch layer: reuses scripts/backtest_orb_scalping.py's own windows/symbols
and scripts/backtest_dow_theory_trend.py's fetch_chunked_intraday verbatim
-- no new fetch logic, no new signal logic, this is purely a capital-
tracking adapter on top of already-existing trade generation.

Usage
─────
    python scripts/simulate_orb_scalping_equity_curve.py
    python scripts/simulate_orb_scalping_equity_curve.py --capital 50000 100000 200000
"""

import argparse
import asyncio
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.backtest.equity_curve import Account, EquityCurveResult  # noqa: E402
from core.backtest.parser import BacktestTrade  # noqa: E402
from core.orb_scalping.backtest import group_by_day, run_index_backtest  # noqa: E402
from scripts.backtest_dow_theory_trend import fetch_chunked_intraday  # noqa: E402
from scripts.backtest_orb_scalping import (  # noqa: E402
    BANKNIFTY_SYMBOL, BANKNIFTY_WINDOW_START, NIFTY_SYMBOL, NIFTY_WINDOW_START, VIX_SYMBOL,
)

DEFAULT_CAPITALS = [50_000.0]


def simulate(nifty_trades: list[BacktestTrade], banknifty_trades: list[BacktestTrade],
             trading_days: list[date], initial_capital: float,
             ) -> tuple[EquityCurveResult, list[dict]]:
    """Merges both indices' trades into one Account, processing each
    trade's OPEN and CLOSE as separate chronologically-ordered events (not
    open-then-immediately-close in entry order) -- a NIFTY signal held
    9:20am-3:00pm and a BankNifty signal opening at 10am genuinely overlap
    in time and must both hold real capital simultaneously; collapsing a
    trade to a single instant would silently free its capital early and
    understate how often two same-day signals actually compete for the
    same cash pool. Marks every trading day (not just trade days) so a
    real account sitting in cash on a no-trade day is a zero-return day in
    the curve, not a gap. Returns the finalized result plus a list of
    trades skipped for insufficient cash at open time."""
    OPEN, CLOSE = 0, 1
    events: list[tuple[datetime, int, str, BacktestTrade]] = []
    for underlying, trades in (("NIFTY", nifty_trades), ("BANKNIFTY", banknifty_trades)):
        for t in trades:
            events.append((t.entry_date, OPEN, underlying, t))
            events.append((t.exit_date, CLOSE, underlying, t))

    events_by_day: dict[date, list[tuple]] = {}
    for ev in events:
        events_by_day.setdefault(ev[0].date(), []).append(ev)
    for day_events in events_by_day.values():
        # Ties (identical timestamp) resolve opens before closes -- a
        # conservative choice, since a caller can't rely on capital being
        # freed at the exact instant it's needed for a new entry.
        day_events.sort(key=lambda e: (e[0], e[1]))

    acct = Account(initial_capital=initial_capital)
    skipped: list[dict] = []
    open_pos_ids: dict[tuple, int] = {}   # (underlying, trade_num) -> position id

    for day in sorted(trading_days):
        for _ts, kind, underlying, trade in events_by_day.get(day, []):
            key = (underlying, trade.trade_num)
            if kind == OPEN:
                instrument_id = f"{underlying}_{trade.entry_date.isoformat()}_{trade.trade_num}"
                pos_id = acct.open(instrument_id, trade.qty, trade.entry_price,
                                    trade.entry_date, strict=False)
                if pos_id is None:
                    skipped.append({
                        "underlying": underlying, "date": day,
                        "needed": round(trade.qty * trade.entry_price, 2),
                        "cash_available": round(acct.cash, 2),
                    })
                else:
                    open_pos_ids[key] = pos_id
            else:  # CLOSE
                pos_id = open_pos_ids.pop(key, None)
                if pos_id is None:
                    continue   # this trade's open was skipped for insufficient cash
                acct.close(pos_id, trade.exit_price, trade.exit_date, costs=trade.costs,
                           exit_reason=f"{underlying.lower()}_orb_exit")
        # One mark per calendar day, at end-of-day (the placeholder time
        # only feeds days_span/CAGR/Sharpe via its DATE; every position is
        # closed same-day, so nothing is ever still open across a mark).
        acct.mark(datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc), mark_prices={})

    return acct.finalize(), skipped


def _report(results_by_capital: dict[float, tuple[EquityCurveResult, list[dict]]],
            nifty_window: tuple, banknifty_window: tuple,
            nifty_n: int, banknifty_n: int) -> str:
    lines = [
        "# Candidate 18 (ORB Options Scalping) — Real Capital-Tracked Equity Curve",
        "",
        "Methodology: docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md. This report "
        "answers a different question than docs/ORB_SCALPING_RESULTS.md's "
        "pooled per-trade stats -- see this script's own module docstring "
        "(scripts/simulate_orb_scalping_equity_curve.py) for why those can't "
        "answer \"what does real capital become.\" Uses the Stratified cost "
        "variant (locked-final, per ORB_SCALPING_RESULTS.md) for both indices, "
        "merged into ONE account sharing ONE cash pool, exactly 1 lot/trade "
        "(unchanged sizing), skipping any trade the account can't afford.",
        "",
        f"NIFTY window: {nifty_window[0]} to {nifty_window[1]} ({nifty_n} signals). "
        f"BankNifty window: {banknifty_window[0]} to {banknifty_window[1]} ({banknifty_n} signals).",
        "",
        "## Results by starting capital",
        "",
        "| Starting capital | Final equity | Total return % | CAGR % | Sharpe (daily) | Max DD % | Max DD ₹ | Trades taken | Trades skipped (insufficient cash) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for capital, (result, skipped) in sorted(results_by_capital.items()):
        taken = len(result.closed_positions)
        lines.append(
            f"| ₹{capital:,.0f} | ₹{result.final_equity:,.2f} | {result.total_return_pct:.1f}% | "
            f"{result.cagr_pct:.1f}% | {result.sharpe:.2f} | {result.max_drawdown_pct:.1f}% | "
            f"₹{result.max_drawdown_rs:,.2f} | {taken} | {len(skipped)} |"
        )
    lines += [
        "",
        "Sharpe here is the DAILY equity-curve calculation (sqrt(252) "
        "annualization over every trading day in the window, zero-return "
        "days included) -- NOT `core/backtest/parser.py`'s pooled per-trade "
        "annualization (see docs/SHARPE_SWEEP_AND_EQUITY_CURVE_PLAN.md's "
        "Track 1 finding that these are two genuinely separate calculations, "
        "same convention `core/rotation/equity_curve.py` and "
        "docs/S1_DUAL_MOMENTUM_BACKTEST_RESULTS.md's \"equity-curve daily "
        "returns\" line already use).",
        "",
        "Max drawdown is bounded to [0, 100]% by construction (a real "
        "compounding account, not a sum of independent trade percentages) "
        "-- contrast docs/ORB_SCALPING_RESULTS.md's own trades, whose pooled "
        "stats don't report a drawdown at all for exactly this reason.",
    ]

    smallest_capital = min(results_by_capital)
    _, smallest_skipped = results_by_capital[smallest_capital]
    if smallest_skipped:
        lines += [
            "",
            f"## Skipped trades at ₹{smallest_capital:,.0f} starting capital "
            f"(first 20 of {len(smallest_skipped)})",
            "",
            "| Date | Underlying | Premium needed | Cash available |",
            "|---|---|---|---|",
        ]
        for s in smallest_skipped[:20]:
            lines.append(f"| {s['date']} | {s['underlying']} | ₹{s['needed']:,.2f} | ₹{s['cash_available']:,.2f} |")

    return "\n".join(lines)


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

    print(f"Fetching India VIX 5m candles {banknifty_from_dt.date()} -> {to_dt.date()} (chunked) ...")
    vix_candles = await fetch_chunked_intraday(broker, VIX_SYMBOL, banknifty_from_dt, to_dt, sem)
    print(f"  {len(vix_candles)} candles fetched")

    if not nifty_candles or not banknifty_candles or not vix_candles:
        print("ERROR: one or more series returned zero candles.")
        return 1

    print("Running NIFTY backtest ...")
    (*_nifty_others, nifty_stratified) = run_index_backtest(nifty_candles, vix_candles, underlying="NIFTY")
    print(f"  {len(nifty_stratified)} NIFTY signals")

    print("Running BankNifty backtest ...")
    (*_bn_others, banknifty_stratified) = run_index_backtest(banknifty_candles, vix_candles, underlying="BANKNIFTY")
    print(f"  {len(banknifty_stratified)} BankNifty signals")

    if not nifty_stratified and not banknifty_stratified:
        print("ERROR: zero trades generated for both indices.")
        return 1

    nifty_by_day = group_by_day(nifty_candles)
    banknifty_by_day = group_by_day(banknifty_candles)
    nifty_window = (min(nifty_by_day), max(nifty_by_day))
    banknifty_window = (min(banknifty_by_day), max(banknifty_by_day))
    trading_days = sorted(set(nifty_by_day) | set(banknifty_by_day))

    results_by_capital = {}
    for capital in args.capital:
        print(f"Simulating equity curve at ₹{capital:,.0f} starting capital ...")
        result, skipped = simulate(nifty_stratified, banknifty_stratified, trading_days, capital)
        results_by_capital[capital] = (result, skipped)
        print(f"  final equity ₹{result.final_equity:,.2f}, {len(skipped)} trades skipped for insufficient cash")

    report = _report(results_by_capital, nifty_window, banknifty_window,
                      len(nifty_stratified), len(banknifty_stratified))
    out_path = Path(args.out)
    out_path.write_text(report + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


def main() -> int:
    # Windows consoles default to cp1252, which can't encode the Rupee sign
    # this script prints throughout -- force utf-8 so stdout doesn't crash
    # after several minutes of data fetching.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--out", default="docs/ORB_SCALPING_EQUITY_CURVE_RESULTS.md")
    parser.add_argument("--capital", type=float, nargs="+", default=DEFAULT_CAPITALS)
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
