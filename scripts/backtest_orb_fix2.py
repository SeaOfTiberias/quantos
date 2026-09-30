#!/usr/bin/env python3
"""
QuantOS — Candidate 18 "fix 2": BANKNIFTY expiry day + entry lag
──────────────────────────────────────────────────────────────────
Written 2026-09-30, BEFORE any of these variants was run.

Why: on 2026-09-29 (BANKNIFTY's monthly expiry) paper 18 bought that day's
0-DTE put, which decayed 220.35 -> 2.95. The locked-final backtest trades
the same way, but prices premiums with `max(1, days_to_expiry)`, so a 0-DTE
option keeps a full day of time value all session and never decays. Its
BANKNIFTY expiry-day trades are therefore optimistic. Separately, live
entered one 5m candle late until 77c5c98.

Runs, all costed Stratified (the locked-final variant):
  A  locked-final as-is      old pricing, BN "current", no entry delay
  B  corrected pricing       intraday time-to-expiry, BN "current"
  C  B + BN "roll"           next month's contract on BN expiry day
  D  B + BN "skip"           no BN trade on its expiry day
  E  B + 1-candle entry lag  what live's late entry had been costing
A should reproduce docs/ORB_SCALPING_RESULTS.md (up to the new data, and the
2026-09-30 forward-calendar fix, which only touches the window's last weeks).

Pre-registered decision rule for BANKNIFTY (fixed before running):
  Pick whichever of C (roll) or D (skip) has the higher BANKNIFTY profit
  factor. If the two are within 0.05 PF of each other, pick D (skip): it is
  the smaller change and removes 0-DTE exposure entirely. B ("current") is not
  a candidate: it keeps the exposure the fix exists to remove. The choice is
  made on these backtest numbers only -- never on which one helps 18b's paper
  record (docs/ORB_ENTRY_FILTER_METHODOLOGY.md, 2026-09-30 addendum).
  Whichever is picked is then brought to the user before any live change.

Fyers-heavy (~3 years of 5m candles x 3 series): run ONLY after 15:30 IST.
Fetched candles are cached to data_cache/orb_fix2_candles.pkl, so reruns are
free (--refresh to refetch).

Usage:
    python scripts/backtest_orb_fix2.py [--refresh] [--out docs/ORB_FIX2_RESULTS.md]
"""
from __future__ import annotations

import argparse
import asyncio
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.backtest.parser import _compute_metrics  # noqa: E402
from core.orb_scalping.backtest import (  # noqa: E402
    group_by_day,
    is_banknifty_monthly_expiry_day,
    run_index_backtest,
)
from scripts.backtest_dow_theory_trend import fetch_chunked_intraday  # noqa: E402
from scripts.backtest_orb_scalping import (  # noqa: E402
    BANKNIFTY_SYMBOL,
    BANKNIFTY_WINDOW_START,
    NIFTY_SYMBOL,
    NIFTY_WINDOW_START,
    VIX_SYMBOL,
)

CACHE_PATH = Path("data_cache/orb_fix2_candles.pkl")
PF_TIE_BAND = 0.05

RUNS = {
    "A locked-final (old pricing)": dict(intraday_dte=False, banknifty_expiry_policy="current"),
    "B corrected pricing":          dict(intraday_dte=True, banknifty_expiry_policy="current"),
    "C corrected + BN roll":        dict(intraday_dte=True, banknifty_expiry_policy="roll"),
    "D corrected + BN skip":        dict(intraday_dte=True, banknifty_expiry_policy="skip"),
    "E corrected + 1-candle lag":   dict(intraday_dte=True, banknifty_expiry_policy="current",
                                         entry_delay_candles=1),
}


async def _fetch(broker) -> dict:
    to_dt = datetime.now(timezone.utc)
    sem = asyncio.Semaphore(2)
    n_from = datetime.combine(NIFTY_WINDOW_START, datetime.min.time(), tzinfo=timezone.utc)
    b_from = datetime.combine(BANKNIFTY_WINDOW_START, datetime.min.time(), tzinfo=timezone.utc)
    print("Fetching NIFTY / BANKNIFTY / India VIX 5m candles (chunked) ...")
    return {
        "nifty": await fetch_chunked_intraday(broker, NIFTY_SYMBOL, n_from, to_dt, sem),
        "banknifty": await fetch_chunked_intraday(broker, BANKNIFTY_SYMBOL, b_from, to_dt, sem),
        "vix": await fetch_chunked_intraday(broker, VIX_SYMBOL, b_from, to_dt, sem),
        "fetched_at": to_dt.isoformat(),
    }


def load_candles(config_path: str, refresh: bool) -> dict:
    if CACHE_PATH.exists() and not refresh:
        print(f"Using cached candles {CACHE_PATH}")
        return pickle.loads(CACHE_PATH.read_bytes())
    from core.brokers import get_broker
    broker = get_broker(load_config(config_path))
    if not broker.connect():
        raise SystemExit("ERROR: broker connect() failed -- refresh the Fyers token.")
    data = asyncio.run(_fetch(broker))
    if not (data["nifty"] and data["banknifty"] and data["vix"]):
        raise SystemExit("ERROR: a series came back empty.")
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_bytes(pickle.dumps(data))
    return data


def _row(label: str, trades: list) -> str:
    m = _compute_metrics(trades)
    net = sum(t.profit - t.costs for t in trades)
    return (f"| {label} | {m.total_trades} | {m.win_rate:.0%} | {m.profit_factor:.2f} | "
            f"{m.sharpe_ratio:.2f} | {net:,.0f} | {'PASS' if m.has_positive_edge else 'FAIL'} |")


def _stratified(candles, vix, underlying, **kw) -> list:
    return run_index_backtest(candles, vix, underlying=underlying, **kw)[5]


def decide(pf_roll: float, pf_skip: float) -> str:
    """The pre-registered rule above. Pure, unit-tested."""
    if abs(pf_roll - pf_skip) < PF_TIE_BAND:
        return "skip"
    return "roll" if pf_roll > pf_skip else "skip"


def run(data: dict) -> str:
    header = "| Run | N | Win | PF | Sharpe | Net Rs (1 lot) | Bar |\n|---|---|---|---|---|---|---|"
    out = ["# Candidate 18 — fix 2 results (BANKNIFTY expiry day + entry lag)", "",
           f"Data fetched {data['fetched_at']}. Stratified costs, 1 lot per trade. "
           f"Bar = PF > 1.0 and Sharpe > 0.5. Method, runs and the decision rule: "
           f"`scripts/backtest_orb_fix2.py` docstring (committed before this run).", ""]
    bn_results = {}
    for underlying, key in (("NIFTY", "nifty"), ("BANKNIFTY", "banknifty")):
        out += [f"## {underlying}", "", header]
        for label, kw in RUNS.items():
            if underlying == "NIFTY" and kw.get("banknifty_expiry_policy") in ("roll", "skip"):
                continue   # the policy only applies to BANKNIFTY
            trades = _stratified(data[key], data["vix"], underlying, **kw)
            out.append(_row(label, trades))
            if underlying == "BANKNIFTY":
                bn_results[label[0]] = trades
        out.append("")

    # How much the old clamp flattered BANKNIFTY's expiry-day trades.
    days = set(group_by_day(data["banknifty"]))

    def expiry_only(trades):
        return [t for t in trades if is_banknifty_monthly_expiry_day(t.entry_date.date(), days)]

    out += ["## BANKNIFTY expiry-day trades only (A vs B)", "", header,
            _row("A old pricing", expiry_only(bn_results["A"])),
            _row("B corrected pricing", expiry_only(bn_results["B"])), ""]

    pf = {k: _compute_metrics(v).profit_factor for k, v in bn_results.items()}
    choice = decide(pf["C"], pf["D"])
    out += ["## Pre-registered BANKNIFTY decision", "",
            f"roll PF {pf['C']:.2f} vs skip PF {pf['D']:.2f} (tie band {PF_TIE_BAND}) -> **{choice}**. "
            f"To be brought to the user before any live rule change.", ""]
    return "\n".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default="agent/config.yaml")
    p.add_argument("--out", default="docs/ORB_FIX2_RESULTS.md")
    p.add_argument("--refresh", action="store_true")
    args = p.parse_args(argv)
    report = run(load_candles(args.config, args.refresh))
    Path(args.out).write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
