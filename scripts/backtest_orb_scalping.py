#!/usr/bin/env python3
"""
QuantOS — ORB Options Scalping Backtest (candidate 18)
─────────────────────────────────────────────────────────
See docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md for every design choice
(fixed BEFORE this script was run): 5-minute NIFTY/BankNifty opening-range
breakout, broker-side trailing stop + 25% secondary premium stop, DTE
floor on NIFTY's weekly contracts, Clean/Stressed(+15bps/leg) cost split,
NIFTY and BankNifty reported independently (never pooled).

Fetch layer: Fyers 5-minute candles for NIFTY 50, NIFTY BANK, and India
VIX, chunked to the confirmed ~100-day intraday limit (reuses
scripts/backtest_dow_theory_trend.py's fetch_chunked_intraday unchanged).
Needs a fresh Fyers auth token (agent/config.yaml's configured broker).

Usage
─────
    python scripts/backtest_orb_scalping.py
    python scripts/backtest_orb_scalping.py --out docs/ORB_SCALPING_RESULTS.md
"""

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.backtest.parser import BacktestMetrics, BacktestTrade, _compute_metrics  # noqa: E402
from core.brokers.base import OHLCV  # noqa: E402
from core.orb_scalping.backtest import group_by_day, run_index_backtest  # noqa: E402
from scripts.backtest_dow_theory_trend import fetch_chunked_intraday  # noqa: E402

logger = logging.getLogger(__name__)

NIFTY_SYMBOL = "NIFTY 50"
BANKNIFTY_SYMBOL = "NIFTY BANK"
VIX_SYMBOL = "INDIA VIX"

# Confirmed-safe start dates per index (see methodology doc's Data sources
# section) -- NIFTY's own confirmed 5m depth is the shallower of the two,
# so VIX is fetched from BankNifty's earlier start and sliced per index.
NIFTY_WINDOW_START = date(2022, 6, 1)      # candidate 14's confirmed depth
BANKNIFTY_WINDOW_START = date(2021, 6, 1)  # candidate 15's confirmed depth

REQUEST_TIMEOUT_SECS = 30.0


# ─── Report ───────────────────────────────────────────────────────────────

def _metrics_row(label: str, m: BacktestMetrics) -> str:
    return (f"| {label} | {m.total_trades} | {m.win_rate:.1%} | {m.profit_factor:.2f} | "
            f"{m.sharpe_ratio:.2f} | {m.net_profit_pct:+.1f}% | {m.max_drawdown_pct:.1f}% |")


def _section(underlying: str, clean: list, stressed: list) -> str:
    lines = [f"## {underlying}", ""]
    if not clean:
        lines += ["*(zero trades generated)*", ""]
        return "\n".join(lines)

    lines += [
        "| Variant | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |",
        "|---|---|---|---|---|---|---|",
        _metrics_row("Clean", _compute_metrics(clean)),
        _metrics_row("Stressed (+15bps/leg)", _compute_metrics(stressed)),
        "",
        "### Per-year breakdown (Stressed)",
        "",
        "| Year | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |",
        "|---|---|---|---|---|---|---|",
    ]
    by_year: dict[int, list[BacktestTrade]] = {}
    for t in stressed:
        by_year.setdefault(t.exit_date.year, []).append(t)
    for year in sorted(by_year):
        year_trades = by_year[year]
        if len(year_trades) < 3:
            lines.append(f"| {year} | {len(year_trades)} | *(too few for a metric)* | | | | |")
            continue
        lines.append(_metrics_row(str(year), _compute_metrics(year_trades)))

    stressed_metrics = _compute_metrics(stressed)
    lines += [
        "",
        f"**Verdict ({underlying}, gates on Stressed per methodology doc)**: "
        f"{'PASS' if stressed_metrics.has_positive_edge else 'FAIL'} "
        f"(PF {stressed_metrics.profit_factor:.2f}, Sharpe {stressed_metrics.sharpe_ratio:.2f}, "
        f"bar is PF > 1.0 AND Sharpe > 0.5).",
        "",
    ]
    return "\n".join(lines)


def summarize(
    nifty_clean, nifty_stressed, banknifty_clean, banknifty_stressed,
    nifty_window: tuple, banknifty_window: tuple,
) -> str:
    lines = [
        "# ORB Options Scalping — Backtest Results (Candidate 18)",
        "",
        "Methodology: docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md. NIFTY and "
        "BankNifty reported independently below -- never pooled.",
        "",
        f"NIFTY window: {nifty_window[0]} to {nifty_window[1]} "
        f"({len(nifty_clean)} trades). BankNifty window: {banknifty_window[0]} to "
        f"{banknifty_window[1]} ({len(banknifty_clean)} trades).",
        "",
        _section("NIFTY", nifty_clean, nifty_stressed),
        _section("BankNifty", banknifty_clean, banknifty_stressed),
        "## Overall read",
        "",
        "Read each index's own per-year table before trusting the pooled row "
        "-- same discipline every prior candidate's per-fold/per-year "
        "breakdown has used. A pass on Clean that fails on Stressed is a "
        "real finding (the edge is an artifact of synthetic pricing with no "
        "real spread), not something to average away.",
    ]
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

    print(f"Fetching NIFTY 5m candles {nifty_from_dt.date()} -> {to_dt.date()} (chunked) ...")
    nifty_candles = await fetch_chunked_intraday(broker, NIFTY_SYMBOL, nifty_from_dt, to_dt, sem)
    print(f"  {len(nifty_candles)} candles fetched")

    print(f"Fetching BankNifty 5m candles {banknifty_from_dt.date()} -> {to_dt.date()} (chunked) ...")
    banknifty_candles = await fetch_chunked_intraday(broker, BANKNIFTY_SYMBOL, banknifty_from_dt, to_dt, sem)
    print(f"  {len(banknifty_candles)} candles fetched")

    print(f"Fetching India VIX 5m candles {banknifty_from_dt.date()} -> {to_dt.date()} (chunked, "
          f"covers both indices' windows) ...")
    vix_candles = await fetch_chunked_intraday(broker, VIX_SYMBOL, banknifty_from_dt, to_dt, sem)
    print(f"  {len(vix_candles)} candles fetched")

    if not nifty_candles or not banknifty_candles or not vix_candles:
        print("ERROR: one or more series returned zero candles.")
        return 1

    print("Running NIFTY backtest ...")
    nifty_clean, nifty_stressed = run_index_backtest(nifty_candles, vix_candles, underlying="NIFTY")
    print(f"  {len(nifty_clean)} NIFTY trades")

    print("Running BankNifty backtest ...")
    banknifty_clean, banknifty_stressed = run_index_backtest(
        banknifty_candles, vix_candles, underlying="BANKNIFTY",
    )
    print(f"  {len(banknifty_clean)} BankNifty trades")

    if not nifty_clean and not banknifty_clean:
        print("ERROR: zero trades generated for both indices -- check data/logic before trusting an empty result.")
        return 1

    nifty_by_day = group_by_day(nifty_candles)
    banknifty_by_day = group_by_day(banknifty_candles)
    nifty_window = (min(nifty_by_day), max(nifty_by_day))
    banknifty_window = (min(banknifty_by_day), max(banknifty_by_day))

    report = summarize(
        nifty_clean, nifty_stressed, banknifty_clean, banknifty_stressed,
        nifty_window, banknifty_window,
    )
    out_path = Path(args.out)
    out_path.write_text(report + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--out", default="docs/ORB_SCALPING_RESULTS.md")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
