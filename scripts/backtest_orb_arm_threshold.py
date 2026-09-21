#!/usr/bin/env python3
"""
QuantOS — ORB Options Scalping: Arm-Threshold Grid Backtest (candidate 18)
───────────────────────────────────────────────────────────────────────────
Runs docs/ORB_ARM_THRESHOLD_METHODOLOGY.md's pre-registered grid
({0.25, 0.5, 0.75, 1.0} x range-width) against real historical data, on a
time-based 80/20 mining/holdout split per index, and reports every point
against the pre-registered pass bar. Read that document before reading
this script or its output — every threshold and rule here (materiality
margin, sample-size floor, "closest-to-baseline wins a tie") is pinned
there, not decided while writing this code.

Reuses scripts/backtest_orb_scalping.py's exact data-fetch (same symbols,
same confirmed-safe per-index start dates) so this grid is measured on the
identical universe of days behind the existing Stressed/Stratified
verdicts — no new data collection needed for this question.

Usage
─────
    python scripts/backtest_orb_arm_threshold.py
    python scripts/backtest_orb_arm_threshold.py --out docs/ORB_ARM_THRESHOLD_RESULTS.md
"""

import argparse
import asyncio
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.backtest.parser import BacktestMetrics, BacktestTrade, _compute_metrics  # noqa: E402
from core.brokers.base import OHLCV  # noqa: E402
from core.orb_scalping.backtest import group_by_day, run_index_backtest  # noqa: E402
from scripts.backtest_dow_theory_trend import fetch_chunked_intraday  # noqa: E402
from scripts.backtest_orb_scalping import (  # noqa: E402
    BANKNIFTY_SYMBOL,
    BANKNIFTY_WINDOW_START,
    NIFTY_SYMBOL,
    NIFTY_WINDOW_START,
    VIX_SYMBOL,
)

# Pre-registered grid. 1.0 is the existing baseline, re-run here (not read
# from docs/ORB_SCALPING_RESULTS.md) so every point is measured on the
# identical mining/holdout split, in the same pass.
GRID = (0.25, 0.5, 0.75, 1.0)
BASELINE = 1.0

MIN_SAMPLE_SIZE = 30           # per split, per index -- docs/ORB_ARM_THRESHOLD_METHODOLOGY.md
MATERIALITY_SHARPE_DELTA = 0.10  # minimum improvement over baseline to count as "material"
MINING_FRACTION = 0.8           # earliest 80% of trading days, by calendar date


def split_days(all_days: list[date]) -> tuple[list[date], list[date]]:
    """Earliest MINING_FRACTION of days = mining; the rest = holdout. Days,
    not trades: ORB fires on ~95-98% of days, so splitting by day is the
    same split by calendar date the methodology doc specifies."""
    ordered = sorted(all_days)
    cut = round(len(ordered) * MINING_FRACTION)
    return ordered[:cut], ordered[cut:]


def filter_candles(candles: list[OHLCV], allowed_days: set) -> list[OHLCV]:
    return [c for c in candles if c.timestamp.date() in allowed_days]


def _metrics_or_none(trades: list[BacktestTrade]) -> BacktestMetrics:
    return _compute_metrics(trades)


def evaluate_multiplier(index_candles: list[OHLCV], vix_candles: list[OHLCV], *,
                        underlying: str, multiplier: float,
                        mining_days: set, holdout_days: set,
                        ) -> tuple[BacktestMetrics, BacktestMetrics, int, int]:
    """(mining_metrics, holdout_metrics, mining_n, holdout_n) for one
    (underlying, multiplier) pair, Stratified cost only -- the locked-final
    variant, same one any go/no-go decision in this project reads."""
    mining_index = filter_candles(index_candles, mining_days)
    mining_vix = filter_candles(vix_candles, mining_days)
    holdout_index = filter_candles(index_candles, holdout_days)
    holdout_vix = filter_candles(vix_candles, holdout_days)

    *_ignored_mining, mining_stratified = run_index_backtest(
        mining_index, mining_vix, underlying=underlying, arm_multiplier=multiplier)
    *_ignored_holdout, holdout_stratified = run_index_backtest(
        holdout_index, holdout_vix, underlying=underlying, arm_multiplier=multiplier)

    return (_metrics_or_none(mining_stratified), _metrics_or_none(holdout_stratified),
            len(mining_stratified), len(holdout_stratified))


def _passes_bar(candidate: BacktestMetrics, baseline: BacktestMetrics, n: int) -> tuple[bool, str]:
    if n < MIN_SAMPLE_SIZE:
        return False, f"n={n} < {MIN_SAMPLE_SIZE}"
    if not candidate.has_positive_edge:
        return False, f"PF {candidate.profit_factor:.2f}/Sharpe {candidate.sharpe_ratio:.2f} fails the bar itself"
    sharpe_delta = candidate.sharpe_ratio - baseline.sharpe_ratio
    pf_delta = candidate.profit_factor - baseline.profit_factor
    if sharpe_delta < MATERIALITY_SHARPE_DELTA:
        return False, f"Sharpe delta {sharpe_delta:+.2f} < required +{MATERIALITY_SHARPE_DELTA:.2f}"
    if pf_delta <= 0:
        return False, f"PF delta {pf_delta:+.3f} is not positive"
    return True, f"Sharpe {sharpe_delta:+.2f}, PF {pf_delta:+.3f} over baseline"


def _row(multiplier: float, mining: BacktestMetrics, holdout: BacktestMetrics,
        mining_n: int, holdout_n: int) -> str:
    return (f"| {multiplier:.2f}x | {mining_n} | {mining.profit_factor:.2f} | {mining.sharpe_ratio:.2f} | "
           f"{holdout_n} | {holdout.profit_factor:.2f} | {holdout.sharpe_ratio:.2f} |")


def _section(underlying: str, index_candles: list[OHLCV], vix_candles: list[OHLCV],
            mining_days: set, holdout_days: set) -> tuple[str, list[float]]:
    """Returns (markdown, adoptable_multipliers) for one index."""
    lines = [f"## {underlying}", "",
            f"Mining: {len(mining_days)} days. Holdout: {len(holdout_days)} days.", "",
            "| Multiplier | Mining N | Mining PF | Mining Sharpe | "
            "Holdout N | Holdout PF | Holdout Sharpe |",
            "|---|---|---|---|---|---|---|"]

    results: dict[float, tuple] = {}
    for m in GRID:
        mining_m, holdout_m, mining_n, holdout_n = evaluate_multiplier(
            index_candles, vix_candles, underlying=underlying, multiplier=m,
            mining_days=mining_days, holdout_days=holdout_days)
        results[m] = (mining_m, holdout_m, mining_n, holdout_n)
        lines.append(_row(m, mining_m, holdout_m, mining_n, holdout_n))
    lines.append("")

    baseline_mining, baseline_holdout, _, _ = results[BASELINE]
    lines.append(f"Baseline ({BASELINE:.2f}x): mining PF {baseline_mining.profit_factor:.2f}/"
                f"Sharpe {baseline_mining.sharpe_ratio:.2f}, holdout PF "
                f"{baseline_holdout.profit_factor:.2f}/Sharpe {baseline_holdout.sharpe_ratio:.2f}.")
    lines.append("")

    adoptable = []
    for m in GRID:
        if m == BASELINE:
            continue
        mining_m, holdout_m, mining_n, holdout_n = results[m]
        mining_pass, mining_reason = _passes_bar(mining_m, baseline_mining, mining_n)
        holdout_pass, holdout_reason = _passes_bar(holdout_m, baseline_holdout, holdout_n)
        verdict = "ADOPTABLE" if (mining_pass and holdout_pass) else "not adoptable"
        lines.append(f"**{m:.2f}x — {verdict}.** Mining: {mining_reason}. Holdout: {holdout_reason}.")
        if mining_pass and holdout_pass:
            adoptable.append(m)
    lines.append("")

    return "\n".join(lines), adoptable


def summarize(nifty_section: str, banknifty_section: str,
             nifty_adoptable: list[float], banknifty_adoptable: list[float]) -> str:
    both_adoptable = sorted(set(nifty_adoptable) & set(banknifty_adoptable))
    if both_adoptable:
        chosen = min(both_adoptable, key=lambda m: abs(m - BASELINE))
        verdict = (f"**{chosen:.2f}x clears the pre-registered bar on BOTH indices** "
                  f"(candidates clearing both: {[f'{m:.2f}x' for m in both_adoptable]} — "
                  f"{chosen:.2f}x chosen as closest to the {BASELINE:.2f}x baseline, per the "
                  f"methodology doc's parsimony rule). This is a PROPOSED change, not an "
                  f"applied one — see docs/ORB_ARM_THRESHOLD_METHODOLOGY.md's \"What this "
                  f"does NOT produce\" section: Fable review of these actual numbers, then "
                  f"the user's own explicit go-ahead, before anything in "
                  f"scripts/run_orb_scalping_live.py or agent/config.yaml changes.")
    else:
        verdict = ("**No grid point clears the pre-registered bar on both indices.** Per "
                  "the methodology doc, the current 1.0x arm threshold stays as-is -- this "
                  "is reported as a real, legitimate negative result, not grounds to widen "
                  "the grid or lower the materiality bar after the fact.")

    return "\n".join([
        "# ORB Options Scalping — Arm-Threshold Grid Results (Candidate 18)",
        "",
        "Methodology: docs/ORB_ARM_THRESHOLD_METHODOLOGY.md, pre-registered "
        "2026-09-21 before this backtest ran. Grid, materiality bar, mining/"
        "holdout split, and the tie-break rule were all fixed there -- "
        "nothing below was decided after seeing a result.",
        "",
        nifty_section,
        banknifty_section,
        "## Verdict",
        "",
        verdict,
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

    print("Fetching India VIX 5m candles (covers both indices' windows) ...")
    vix_candles = await fetch_chunked_intraday(broker, VIX_SYMBOL, banknifty_from_dt, to_dt, sem)
    print(f"  {len(vix_candles)} candles fetched")

    if not nifty_candles or not banknifty_candles or not vix_candles:
        print("ERROR: one or more series returned zero candles.")
        return 1

    nifty_by_day = group_by_day(nifty_candles)
    banknifty_by_day = group_by_day(banknifty_candles)

    nifty_mining_days, nifty_holdout_days = split_days(list(nifty_by_day.keys()))
    banknifty_mining_days, banknifty_holdout_days = split_days(list(banknifty_by_day.keys()))
    print(f"NIFTY split: {len(nifty_mining_days)} mining days / {len(nifty_holdout_days)} holdout days "
          f"(cutoff {nifty_holdout_days[0]})")
    print(f"BankNifty split: {len(banknifty_mining_days)} mining days / {len(banknifty_holdout_days)} "
          f"holdout days (cutoff {banknifty_holdout_days[0]})")

    print("Evaluating NIFTY grid ...")
    nifty_section, nifty_adoptable = _section(
        "NIFTY", nifty_candles, vix_candles, set(nifty_mining_days), set(nifty_holdout_days))

    print("Evaluating BankNifty grid ...")
    banknifty_section, banknifty_adoptable = _section(
        "BANKNIFTY", banknifty_candles, vix_candles, set(banknifty_mining_days), set(banknifty_holdout_days))

    report = summarize(nifty_section, banknifty_section, nifty_adoptable, banknifty_adoptable)
    out_path = Path(args.out)
    out_path.write_text(report + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--out", default="docs/ORB_ARM_THRESHOLD_RESULTS.md")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
