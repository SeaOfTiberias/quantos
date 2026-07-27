#!/usr/bin/env python3
"""
QuantOS — ML Multi-Factor Stock Ranking Backtest (candidate 16)
──────────────────────────────────────────────────────────────────
See docs/ML_FACTOR_COMBINATION_METHODOLOGY.md for every design choice
(fixed BEFORE this script was run): Nifty 500 universe, weekly rebalance,
3-year window with a genuine 24-month-train/12-month-test time split
(train_months/test_months approximated as 730/365 calendar days — this
project's established convention, same approximation
scripts/backtest_equity_curve.py's own "--years" arithmetic uses), 4
per-stock factors (momentum, dual-momentum, mean-reversion, reconstitution
recency) combined via a single fixed logistic regression, top-quintile-
forward-return label. Must beat, on the TEST period only: CAGR>0%/
Sharpe>0.5, Nifty 500 buy-and-hold, Nifty Alpha 50 buy-and-hold, AND the
single-factor-momentum baseline run through the identical harness.

Fetch layer, universe file, cost model, and rebalance-date logic are all
reused from scripts/backtest_rs_momentum.py /
scripts/backtest_equity_curve.py (same broker calls, same
agent/universe_nifty500.txt, same DELIVERY_COST_MODEL) so this candidate's
backtest can't silently diverge from S8-3's own live-trading assumptions.
Sector mapping for the mean-reversion feature reuses
scripts/gutcheck_meanreversion_alpha50.py's real-NSE-archive sector map.

**Turnover/cost reporting, added 2026-07-27 after Fable's review of the
first cut of this candidate**: the first run reported the ML strategy
beating the single-factor baseline (CAGR +4.5% vs -2.0%) without ever
reporting HOW MANY trades each made or what each paid in transaction
costs. Fable found the ML run traded far less often (224 vs 655 trades)
and estimated the resulting cost differential alone could exceed the
entire reported gap -- a lower-turnover portfolio looks better in any
cost model that penalizes turnover, independent of whether the underlying
model has learned anything real. This run now reports total real INR
costs paid and trade counts for both strategies directly (both are
already NET of cost via DELIVERY_COST_MODEL, applied identically), AND
runs a second, GROSS (zero transaction cost) pass for both strategies —
if the gap survives at zero cost, it's not a turnover artifact; if it
collapses or reverses, Fable's confound hypothesis is confirmed.

Usage:
    python scripts/backtest_ml_factor_combination.py
    python scripts/backtest_ml_factor_combination.py --years 3 --out docs/ML_FACTOR_COMBINATION_RESULTS.md
"""

import argparse
import asyncio
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.mlfactors.dataset import build_dataset, build_symbol_precomputed  # noqa: E402
from core.mlfactors.model import evaluate_auc, fit_model, make_target_basket_fn, time_based_split  # noqa: E402
from core.regime.fetcher import ALPHA50_SYMBOL, NIFTY_SYMBOL  # noqa: E402
from core.risk.costs import CostModel  # noqa: E402
from core.rotation.equity_curve import (  # noqa: E402
    compute_alpha, simulate_index_buy_and_hold, simulate_portfolio,
)
from core.rotation.nifty500_reconstitution import EVENTS, build_point_in_time_universe  # noqa: E402
from core.rotation.ranker import LOOKBACK_DAYS, TOP_N  # noqa: E402
from scripts.backtest_rs_momentum import DELIVERY_COST_MODEL, rebalance_dates  # noqa: E402
from scripts.gutcheck_meanreversion_alpha50 import build_sector_map  # noqa: E402
from scripts.validate_regime_classifier import fetch_chunked_daily  # noqa: E402

# Zero-cost variant of DELIVERY_COST_MODEL, same fixture shape as
# tests/unit/test_equity_curve.py's own ZERO_COST -- isolates whether a
# reported gap survives with transaction costs/slippage removed entirely.
ZERO_COST = CostModel(brokerage_pct=0, brokerage_flat=0, stt_pct=0,
                       exchange_txn_pct=0, sebi_pct=0, stamp_pct=0,
                       gst_pct=0, slippage_bps=0)

TRAIN_DAYS = 730    # ~24 months, this project's day-count approximation for calendar months
TEST_DAYS = 365     # ~12 months


# ─── Cost/turnover analysis (added 2026-07-27, see module docstring) ────────

def total_costs_paid(result, cost_model: CostModel) -> float:
    """Real INR round-trip cost across every closed trade in `result`,
    recomputed directly from ClosedTrade (entry/exit price, qty) against
    `cost_model` -- ClosedTrade itself doesn't store the cost that was
    already deducted from cash during simulation, so this reconstructs it
    rather than requiring a second field threaded through equity_curve.py."""
    return sum(cost_model.cost_of(t.entry_price, t.exit_price, t.qty, "BUY") for t in result.trades)


def _append_trades_csv(path: Path, result, label: str) -> None:
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for t in result.trades:
            writer.writerow([label, t.symbol, t.entry_date.isoformat(), t.entry_price,
                              t.exit_date.isoformat(), t.exit_price, t.qty, t.exit_reason])


# ─── Report ─────────────────────────────────────────────────────────────────

def _curve_section(title: str, result, alpha=None, cost_model: Optional[CostModel] = None) -> list:
    lines = [
        f"## {title}",
        "",
        f"- Final equity: ₹{result.final_equity:,.0f}",
        f"- Total return: {result.total_return_pct:.1f}%",
        f"- CAGR: {result.cagr_pct:.1f}%",
        f"- Sharpe: {result.sharpe:.2f}",
        f"- Max drawdown: {result.max_drawdown_pct:.1f}%",
    ]
    if hasattr(result, "trades"):
        lines.append(f"- Trades: {len(result.trades)}")
        if cost_model is not None:
            lines.append(f"- Total transaction costs paid: ₹{total_costs_paid(result, cost_model):,.0f}")
    if alpha is not None:
        lines.append(f"- Alpha vs this benchmark: total return {alpha['alpha_total_return_pct']:+.1f}pts, "
                      f"CAGR {alpha['alpha_cagr_pct']:+.1f}pts, "
                      f"beats it: {'Yes' if alpha['strategy_beats_benchmark'] else 'No'}")
    lines.append("")
    return lines


def summarize(
    ml_test, baseline_test, nifty_bench_test, alpha50_bench_test,
    ml_vs_nifty, ml_vs_alpha50,
    ml_test_gross, baseline_test_gross,
    train_auc: float, test_auc: float, model_c: float,
    n_train_rows: int, n_test_rows: int, split_date: datetime,
    n_symbols_used: int, n_symbols_total: int,
) -> str:
    passes = {
        "cagr_sharpe": ml_test.cagr_pct > 0 and ml_test.sharpe > 0.5,
        "beats_nifty500": ml_vs_nifty["strategy_beats_benchmark"],
        "beats_alpha50": ml_vs_alpha50["strategy_beats_benchmark"],
        "beats_baseline": ml_test.total_return_pct > baseline_test.total_return_pct,
    }
    overall_pass = all(passes.values())

    ml_cost = total_costs_paid(ml_test, DELIVERY_COST_MODEL)
    baseline_cost = total_costs_paid(baseline_test, DELIVERY_COST_MODEL)
    gross_gap = ml_test_gross.total_return_pct - baseline_test_gross.total_return_pct
    net_gap = ml_test.total_return_pct - baseline_test.total_return_pct
    gross_survives = ml_test_gross.total_return_pct > baseline_test_gross.total_return_pct
    if gross_survives:
        gross_verdict = "this is evidence of a real stock-selection difference, not just a turnover artifact."
    else:
        gross_verdict = (
            "the ML strategy only \"wins\" once its lower turnover is rewarded by the cost "
            "model -- with costs removed, the single-factor baseline is AT LEAST AS GOOD, "
            "meaning the whole net-of-cost \"win\" in this report is a turnover artifact, "
            "not evidence of a real predictive edge."
        )

    lines = [
        "# ML Multi-Factor Stock Ranking — Backtest Results (Candidate 16)",
        "",
        f"Methodology: docs/ML_FACTOR_COMBINATION_METHODOLOGY.md. Nifty 500 universe, "
        f"{n_symbols_used}/{n_symbols_total} symbols had enough history to ever be scored. "
        f"Split date: {split_date.date()} (train before, test on/after). "
        f"Train rows: {n_train_rows}, test rows: {n_test_rows}. "
        f"Selected C={model_c}. Train AUC: {train_auc:.3f}, Test AUC: {test_auc:.3f}.",
        "",
        "## Turnover/cost check (added after Fable's review of the first cut of this "
        "candidate) — is the net gap below a real signal, or a turnover-cost artifact?",
        "",
        f"| | ML | Baseline |",
        f"|---|---|---|",
        f"| Trades (test period) | {len(ml_test.trades)} | {len(baseline_test.trades)} |",
        f"| Real transaction costs paid (NET run) | ₹{ml_cost:,.0f} | ₹{baseline_cost:,.0f} |",
        f"| Total return, NET of costs | {ml_test.total_return_pct:.1f}% | {baseline_test.total_return_pct:.1f}% |",
        f"| Total return, GROSS (zero-cost re-run) | {ml_test_gross.total_return_pct:.1f}% | {baseline_test_gross.total_return_pct:.1f}% |",
        "",
        f"NET gap (ML − baseline): {net_gap:+.1f}pts. GROSS gap (ML − baseline, zero-cost): "
        f"{gross_gap:+.1f}pts. **The gap "
        f"{'SURVIVES' if gross_survives else 'DOES NOT SURVIVE'} "
        f"removing transaction costs entirely** — {gross_verdict}",
        "",
        "## ML-ranked strategy (test period only, fresh capital-tracked run)",
        "",
    ]
    lines += _curve_section("ML model", ml_test, cost_model=DELIVERY_COST_MODEL)
    lines += ["## Single-factor-momentum baseline (test period only, fresh run, same harness)", ""]
    lines += _curve_section("Baseline (rank_universe)", baseline_test, cost_model=DELIVERY_COST_MODEL)
    lines += _curve_section("vs. Nifty 500 buy-and-hold (test period)", nifty_bench_test, ml_vs_nifty)
    lines += _curve_section("vs. Nifty Alpha 50 buy-and-hold (test period)", alpha50_bench_test, ml_vs_alpha50)

    lines += [
        "## Verdict",
        "",
        f"Per docs/ML_FACTOR_COMBINATION_METHODOLOGY.md's bar — ALL FOUR required, test period only:",
        f"1. CAGR>0% and Sharpe>0.5: {'PASS' if passes['cagr_sharpe'] else 'FAIL'} "
        f"(CAGR {ml_test.cagr_pct:.1f}%, Sharpe {ml_test.sharpe:.2f})",
        f"2. Beats Nifty 500 buy-and-hold: {'PASS' if passes['beats_nifty500'] else 'FAIL'}",
        f"3. Beats Nifty Alpha 50 buy-and-hold: {'PASS' if passes['beats_alpha50'] else 'FAIL'}",
        f"4. Beats single-factor-momentum baseline "
        f"({ml_test.total_return_pct:.1f}% vs {baseline_test.total_return_pct:.1f}%): "
        f"{'PASS' if passes['beats_baseline'] else 'FAIL'} "
        f"— **but see the turnover/cost check above before trusting this criterion**: "
        f"{'the gap survives at zero cost.' if gross_survives else 'the gap DOES NOT survive at zero cost, i.e. this PASS is a turnover artifact, not a stock-selection edge.'}",
        "",
        f"**Overall: {'PASS' if overall_pass else 'FAIL'}** (all four required, mechanical bar only — "
        f"{'' if gross_survives else 'and criterion 4 above is disclosed as untrustworthy regardless of this mechanical result — '}"
        f"read the turnover/cost check, not just this line).",
        "",
        "Single held-out test period, not a distribution — no confidence interval on any "
        "of the above. Treat as one realization, not an expected value, same caveat "
        "S8-3's own equity-curve report carries.",
    ]
    return "\n".join(lines)


# ─── Orchestration ────────────────────────────────────────────────────────

async def main_async(args) -> int:
    config = load_config(args.config)
    from core.brokers import get_broker
    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')} ...")
    broker.connect()

    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=365 * args.years + 400)   # +400d warmup for the 252d momentum window
    sem = asyncio.Semaphore(2)

    print(f"Fetching NIFTY daily candles {from_date.date()} -> {to_date.date()} ...")
    nifty_candles = await fetch_chunked_daily(broker, NIFTY_SYMBOL, from_date, to_date, sem)
    print(f"  {len(nifty_candles)} candles")

    print(f"Fetching NIFTY ALPHA 50 daily candles ...")
    alpha50_candles = await fetch_chunked_daily(broker, ALPHA50_SYMBOL, from_date, to_date, sem)
    print(f"  {len(alpha50_candles)} candles")

    current_universe = frozenset(
        ln.strip() for ln in Path(args.universe).read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#"))
    universe_snapshots = build_point_in_time_universe(current_universe)
    fetch_universe = sorted(frozenset().union(*(s.symbols for s in universe_snapshots)))
    print(f"Building sector map for {len(fetch_universe)} symbols from real NSE archive lists ...")
    sector_map = build_sector_map(fetch_universe)
    needed_sectors = sorted(set(sector_map.values()))
    print(f"  {len(sector_map)}/{len(fetch_universe)} mapped to a real sectoral index, "
          f"sectors in use: {needed_sectors}")

    sector_candles: dict[str, list] = {NIFTY_SYMBOL: nifty_candles}
    for sector in needed_sectors:
        print(f"Fetching {sector} daily candles ...")
        sector_candles[sector] = await fetch_chunked_daily(broker, sector, from_date, to_date, sem)

    print(f"Fetching {len(fetch_universe)} universe symbols (throttled 2-concurrent, "
          f"this is the slow part) ...")
    symbol_precomputed = {}
    for n, symbol in enumerate(fetch_universe, 1):
        candles = await fetch_chunked_daily(broker, symbol, from_date, to_date, sem)
        if len(candles) >= LOOKBACK_DAYS:
            sector = sector_map.get(symbol)
            sec_candles = sector_candles[sector] if sector else sector_candles[NIFTY_SYMBOL]
            symbol_precomputed[symbol] = build_symbol_precomputed(
                candles, sec_candles, sector_mapped=sector is not None)
        if n % 50 == 0:
            print(f"  {n}/{len(fetch_universe)} fetched, {len(symbol_precomputed)} usable so far")
    print(f"  {len(symbol_precomputed)}/{len(fetch_universe)} symbols have enough history")

    if len(nifty_candles) <= LOOKBACK_DAYS:
        print("ERROR: not enough NIFTY history for even one rebalance after warmup.")
        return 1

    all_rebal_dates = rebalance_dates(nifty_candles)
    print(f"  {len(all_rebal_dates)} total rebalance dates")

    print("Building feature dataset (point-in-time, all rebalance dates) ...")
    rows = build_dataset(symbol_precomputed, all_rebal_dates, universe_snapshots, EVENTS)
    print(f"  {len(rows)} (symbol, date) rows")
    if not rows:
        print("ERROR: zero dataset rows -- check warmup/eligibility gating before trusting an empty result.")
        return 1

    split_date = min(r.date for r in rows) + timedelta(days=TRAIN_DAYS)
    train_rows, test_rows = time_based_split(rows, split_date)
    print(f"  split date {split_date.date()}: {len(train_rows)} train rows, {len(test_rows)} test rows")
    if len(train_rows) < 100 or len(test_rows) < 20:
        print("ERROR: not enough rows for a meaningful train/test split.")
        return 1

    print("Fitting model (train-only CV for hyperparameter selection) ...")
    model = fit_model(train_rows)
    train_auc = evaluate_auc(model, train_rows)
    test_auc = evaluate_auc(model, test_rows)
    print(f"  selected C={model.c}, train AUC={train_auc:.3f}, test AUC={test_auc:.3f}")

    # Test-period-only daily/rebal dates, for a FRESH capital-tracked run
    # starting at the test period's own first date.
    test_daily_dates = [c.timestamp for c in nifty_candles if c.timestamp >= split_date]
    test_rebal_dates = set(d for d in all_rebal_dates if d >= split_date)
    if not test_daily_dates or not test_rebal_dates:
        print("ERROR: no trading days/rebalance dates in the test period.")
        return 1

    symbol_series = {sym: p.series for sym, p in symbol_precomputed.items()}

    print("Running ML-ranked strategy over the test period ...")
    target_basket_fn = make_target_basket_fn(model, symbol_precomputed, EVENTS)
    ml_test = simulate_portfolio(
        test_daily_dates, test_rebal_dates, symbol_series, top_n=args.top_n,
        initial_capital=args.capital, position_size=args.position_size,
        cost_model=DELIVERY_COST_MODEL, exit_rule="rank_only",
        universe_snapshots=universe_snapshots, target_basket_fn=target_basket_fn,
    )
    print(f"  ML: final equity ₹{ml_test.final_equity:,.0f}  CAGR {ml_test.cagr_pct:.1f}%  "
          f"Sharpe {ml_test.sharpe:.2f}")

    print("Running single-factor-momentum baseline over the test period ...")
    baseline_test = simulate_portfolio(
        test_daily_dates, test_rebal_dates, symbol_series, top_n=args.top_n,
        initial_capital=args.capital, position_size=args.position_size,
        cost_model=DELIVERY_COST_MODEL, exit_rule="rank_only",
        universe_snapshots=universe_snapshots,   # target_basket_fn omitted -> defaults to rank_universe
    )
    print(f"  Baseline: final equity ₹{baseline_test.final_equity:,.0f}  "
          f"CAGR {baseline_test.cagr_pct:.1f}%  Sharpe {baseline_test.sharpe:.2f}")

    print("Re-running both strategies GROSS (zero transaction cost) to test the turnover-cost "
          "confound Fable's review flagged ...")
    ml_test_gross = simulate_portfolio(
        test_daily_dates, test_rebal_dates, symbol_series, top_n=args.top_n,
        initial_capital=args.capital, position_size=args.position_size,
        cost_model=ZERO_COST, exit_rule="rank_only",
        universe_snapshots=universe_snapshots, target_basket_fn=target_basket_fn,
    )
    baseline_test_gross = simulate_portfolio(
        test_daily_dates, test_rebal_dates, symbol_series, top_n=args.top_n,
        initial_capital=args.capital, position_size=args.position_size,
        cost_model=ZERO_COST, exit_rule="rank_only",
        universe_snapshots=universe_snapshots,
    )
    print(f"  GROSS: ML total return {ml_test_gross.total_return_pct:.1f}%  "
          f"Baseline total return {baseline_test_gross.total_return_pct:.1f}%")

    trades_csv_path = Path(args.out).with_suffix(".trades.csv")
    with trades_csv_path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["run", "symbol", "entry_date", "entry_price", "exit_date",
                                 "exit_price", "qty", "exit_reason"])
    _append_trades_csv(trades_csv_path, ml_test, "ml_net")
    _append_trades_csv(trades_csv_path, baseline_test, "baseline_net")
    print(f"  Wrote {trades_csv_path} ({len(ml_test.trades)} ML + {len(baseline_test.trades)} "
          f"baseline trade rows, for independent verification)")

    nifty_test_closes = [(c.timestamp, c.close) for c in nifty_candles if c.timestamp >= split_date]
    nifty_bench_test = simulate_index_buy_and_hold(nifty_test_closes, initial_capital=args.capital)
    ml_vs_nifty = compute_alpha(ml_test, nifty_bench_test)

    alpha50_test_closes = [(c.timestamp, c.close) for c in alpha50_candles if c.timestamp >= split_date]
    alpha50_bench_test = simulate_index_buy_and_hold(alpha50_test_closes, initial_capital=args.capital)
    ml_vs_alpha50 = compute_alpha(ml_test, alpha50_bench_test)

    report = summarize(
        ml_test, baseline_test, nifty_bench_test, alpha50_bench_test,
        ml_vs_nifty, ml_vs_alpha50,
        ml_test_gross, baseline_test_gross,
        train_auc, test_auc, model.c, len(train_rows), len(test_rows), split_date,
        len(symbol_precomputed), len(fetch_universe),
    )
    Path(args.out).write_text(report + "\n", encoding="utf-8")
    print(f"\nWrote {args.out}")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--years", type=float, default=3.0)
    parser.add_argument("--universe", default="agent/universe_nifty500.txt")
    parser.add_argument("--top-n", type=int, default=TOP_N)
    parser.add_argument("--capital", type=float, default=1_000_000.0)
    parser.add_argument("--position-size", type=float, default=50_000.0)
    parser.add_argument("--out", default="docs/ML_FACTOR_COMBINATION_RESULTS.md")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
