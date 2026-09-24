#!/usr/bin/env python3
"""
QuantOS — Candidate 18 (ORB Options Scalping): Capital Allocation / Position Sizing
────────────────────────────────────────────────────────────────────────────────────
docs/ORB_SCALPING_EQUITY_CURVE_RESULTS.md answered "does starting capital X
survive" under a FIXED 1-lot/trade sizing policy (unchanged from the
original backtest's own convention). It found a hard cliff around
Rs50,000-55,000, and — separately — that MORE capital beyond the cliff
doesn't earn more under fixed sizing: every tier from Rs60,000 up nets the
IDENTICAL absolute profit, because lot count never scales with equity, so
surplus capital just sits idle.

This script asks the harder question that result raised: what SIZING RULE
actually puts available capital to work, and is there a non-overfit way to
call one "the" allocation rather than just trying numbers until one looks
good?

The overfitting trap this script exists to avoid
──────────────────────────────────────────────────
There is exactly ONE historical path for candidate 18 (BankNifty from
2021-06-01, NIFTY from 2022-06-01, to today). Trying many risk fractions
against the FULL equity curve and reporting whichever fraction produced
the best CAGR/Sharpe would fit that one path — indistinguishable in shape
from every parameter-mined result this project has already rejected
elsewhere (docs/SHARPE_SWEEP_AND_EQUITY_CURVE_PLAN.md's whole reason for
existing). So instead of a search-for-best sweep, this script:

1. Computes the Kelly-optimal fixed fraction of capital-per-trade
   (`core/backtest/equity_curve.py::kelly_fraction` — maximizes
   THEORETICAL long-run log-growth from the trade return distribution,
   not "whichever number backtested best") on a MINING window only.
2. Splits mining/holdout the same way `docs/ORB_CONDITION_MINING_METHODOLOGY.md`
   already established for this exact candidate: time-based, earliest 80%
   mining / most recent 20% holdout, computed independently per index
   (NIFTY and BankNifty have different-length windows).
3. Tests the mining-derived fraction — plus the standard, PRE-SPECIFIED
   conservative fallbacks half-Kelly and quarter-Kelly (textbook practice:
   full Kelly is known to be too volatile for real capital even when the
   edge estimate is exactly right, and it never is exactly right) — on the
   UNTOUCHED holdout window. If the mining fraction doesn't hold up out of
   sample, that is reported plainly, not re-optimized.
4. Reports the fixed-1-lot policy (previous script) as the baseline
   throughout, and the full-window (mining+holdout) number for context,
   clearly labeled IN-SAMPLE where the fraction was derived from data that
   overlaps it.

"Optimum capital allocation" in this framework means: the SIZING RULE a
mining window's own trade statistics justify theoretically AND that
survives an untouched holdout window — plus the minimum starting capital
that rule can actually execute on (percentage sizing, unlike fixed-lot,
shrinks naturally in bad times instead of hard-locking out — but it has
its OWN floor: if `fraction * capital` can't afford even 1 lot, nothing
ever trades, forever). It does NOT mean "the fraction that happened to
produce the highest number on the full backtest" — that number is shown
too, explicitly labeled so it isn't mistaken for the validated one.

Position sizing mechanics: at each signal, lots = floor(min(fraction *
current_equity, available_cash) / (1_lot_qty * entry_premium)); equity =
cash + open positions marked at their OWN entry price (no fresher
intraday mark exists — same fallback `Account.mark()` itself uses).
Costs are recomputed at the ACTUAL quantity via the locked-final
Stratified cost model (`core/orb_scalping/costs.py`), not scaled from the
1-lot backtest's own cost figure — that figure's flat-brokerage-cap
component doesn't scale linearly with quantity.

Usage
─────
    python scripts/simulate_orb_scalping_capital_allocation.py
    python scripts/simulate_orb_scalping_capital_allocation.py --capital 50000 100000 500000
"""

import argparse
import asyncio
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.backtest.equity_curve import Account, EquityCurveResult, kelly_fraction  # noqa: E402
from core.backtest.parser import BacktestTrade  # noqa: E402
from core.orb_scalping.backtest import is_banknifty_monthly_expiry_day  # noqa: E402
from core.orb_scalping.costs import stratified_spread_trade_cost  # noqa: E402
from core.orb_scalping.expiry import is_nifty_weekly_expiry_day  # noqa: E402
from scripts.backtest_orb_scalping import OrbScalpingDataError, fetch_and_run_both  # noqa: E402

DEFAULT_CAPITALS = [50_000.0, 100_000.0, 500_000.0]
MINING_FRACTION = 0.8   # matches docs/ORB_CONDITION_MINING_METHODOLOGY.md's own 80/20 split


CostFn = Callable[[str, float, float, int, date], float]


def mining_holdout_split(trades: list[BacktestTrade], window: tuple,
                          mining_fraction: float = MINING_FRACTION) -> tuple[list, list, date]:
    """Time-based split (not by trade count) matching this project's own
    established convention for candidate 18 -- earliest `mining_fraction`
    of the window is Mining, the rest is Holdout."""
    start, end = window
    boundary = start + timedelta(days=round((end - start).days * mining_fraction))
    mining = [t for t in trades if t.entry_date.date() < boundary]
    holdout = [t for t in trades if t.entry_date.date() >= boundary]
    return mining, holdout, boundary


def default_cost_fn(nifty_trading_days: set, banknifty_trading_days: set) -> CostFn:
    """Real cost function: recomputes the locked-final Stratified cost at
    the ACTUAL quantity a sizing policy decided to trade, using each
    index's own real expiry calendar."""
    def _fn(underlying: str, entry_premium: float, exit_premium: float, qty: int, day: date) -> float:
        trading_days = nifty_trading_days if underlying == "NIFTY" else banknifty_trading_days
        is_expiry_fn = is_nifty_weekly_expiry_day if underlying == "NIFTY" else is_banknifty_monthly_expiry_day
        is_expiry_day = is_expiry_fn(day, trading_days)
        return stratified_spread_trade_cost(entry_premium, exit_premium, qty, day, underlying, is_expiry_day).total
    return _fn


def size_lots(equity: float, cash: float, fraction: float, entry_premium: float, base_lot_size: int) -> int:
    """Whole lots such that lots * base_lot_size * entry_premium is
    approximately `fraction` of `equity`, capped by what's actually
    spendable (`cash` — equity can exceed spendable cash when other
    positions are already open). Returns 0 if even 1 lot isn't
    affordable at this fraction/equity/cash combination."""
    if fraction <= 0 or entry_premium <= 0 or base_lot_size <= 0:
        return 0
    target_notional = fraction * equity
    spendable = min(target_notional, cash)
    lot_cost = base_lot_size * entry_premium
    return max(0, int(spendable // lot_cost))


def simulate_equity_fraction(
    nifty_trades: list[BacktestTrade], banknifty_trades: list[BacktestTrade],
    trading_days: list[date], initial_capital: float, fraction: float, cost_fn: CostFn,
) -> tuple[EquityCurveResult, list[dict]]:
    """Same event-driven open/close scheduling as
    scripts/simulate_orb_scalping_equity_curve.py's `simulate()`, but sizes
    each trade to `fraction` of the account's current equity (rounded down
    to whole lots) instead of a fixed 1 lot, and recomputes costs at the
    actual quantity via `cost_fn` rather than reusing the 1-lot backtest's
    own cost figure."""
    OPEN, CLOSE = 0, 1
    events: list[tuple] = []
    for underlying, trades in (("NIFTY", nifty_trades), ("BANKNIFTY", banknifty_trades)):
        for t in trades:
            events.append((t.entry_date, OPEN, underlying, t))
            events.append((t.exit_date, CLOSE, underlying, t))

    events_by_day: dict[date, list[tuple]] = {}
    for ev in events:
        events_by_day.setdefault(ev[0].date(), []).append(ev)
    for day_events in events_by_day.values():
        day_events.sort(key=lambda e: (e[0], e[1]))

    acct = Account(initial_capital=initial_capital)
    skipped: list[dict] = []
    open_pos_ids: dict[tuple, int] = {}
    open_costs: dict[tuple, float] = {}

    for day in sorted(trading_days):
        for _ts, kind, underlying, trade in events_by_day.get(day, []):
            key = (underlying, trade.trade_num)
            if kind == OPEN:
                equity = acct.cash + sum(p.qty * p.entry_price for p in acct.open_positions.values())
                n_lots = size_lots(equity, acct.cash, fraction, trade.entry_price, trade.qty)
                if n_lots < 1:
                    skipped.append({
                        "underlying": underlying, "date": day,
                        "equity": round(equity, 2), "cash": round(acct.cash, 2),
                        "one_lot_cost": round(trade.qty * trade.entry_price, 2),
                    })
                    continue
                actual_qty = n_lots * trade.qty
                cost = cost_fn(underlying, trade.entry_price, trade.exit_price, actual_qty, day)
                instrument_id = f"{underlying}_{trade.entry_date.isoformat()}_{trade.trade_num}"
                pos_id = acct.open(instrument_id, actual_qty, trade.entry_price, trade.entry_date, strict=False)
                if pos_id is None:
                    skipped.append({
                        "underlying": underlying, "date": day,
                        "equity": round(equity, 2), "cash": round(acct.cash, 2),
                        "one_lot_cost": round(trade.qty * trade.entry_price, 2),
                    })
                    continue
                open_pos_ids[key] = pos_id
                open_costs[key] = cost
            else:  # CLOSE
                pos_id = open_pos_ids.pop(key, None)
                if pos_id is None:
                    continue   # this trade's open was skipped
                cost = open_costs.pop(key, 0.0)
                acct.close(pos_id, trade.exit_price, trade.exit_date, costs=cost,
                           exit_reason=f"{underlying.lower()}_orb_exit")
        acct.mark(datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc), mark_prices={})

    return acct.finalize(), skipped


def simulate_fixed_lot(
    nifty_trades: list[BacktestTrade], banknifty_trades: list[BacktestTrade],
    trading_days: list[date], initial_capital: float,
) -> tuple[EquityCurveResult, list[dict]]:
    """Baseline for comparison: exactly 1 lot/trade, unchanged from the
    original backtest's own convention and from
    scripts/simulate_orb_scalping_equity_curve.py's `simulate()` (same
    event-driven open/close scheduling, duplicated here rather than
    imported since that script's `simulate()` returns a different skip-
    record shape than `simulate_equity_fraction`'s -- keeping the two
    fixed/fraction engines side by side in this file makes the size-vs-cost
    difference between them easier to audit than importing one and
    reimplementing the other)."""
    OPEN, CLOSE = 0, 1
    events: list[tuple] = []
    for underlying, trades in (("NIFTY", nifty_trades), ("BANKNIFTY", banknifty_trades)):
        for t in trades:
            events.append((t.entry_date, OPEN, underlying, t))
            events.append((t.exit_date, CLOSE, underlying, t))
    events_by_day: dict[date, list[tuple]] = {}
    for ev in events:
        events_by_day.setdefault(ev[0].date(), []).append(ev)
    for day_events in events_by_day.values():
        day_events.sort(key=lambda e: (e[0], e[1]))

    acct = Account(initial_capital=initial_capital)
    skipped: list[dict] = []
    open_pos_ids: dict[tuple, int] = {}

    for day in sorted(trading_days):
        for _ts, kind, underlying, trade in events_by_day.get(day, []):
            key = (underlying, trade.trade_num)
            if kind == OPEN:
                pos_id = acct.open(f"{underlying}_{trade.entry_date.isoformat()}_{trade.trade_num}",
                                    trade.qty, trade.entry_price, trade.entry_date, strict=False)
                if pos_id is None:
                    skipped.append({"underlying": underlying, "date": day,
                                     "needed": round(trade.qty * trade.entry_price, 2),
                                     "cash_available": round(acct.cash, 2)})
                    continue
                open_pos_ids[key] = pos_id
            else:
                pos_id = open_pos_ids.pop(key, None)
                if pos_id is None:
                    continue
                acct.close(pos_id, trade.exit_price, trade.exit_date, costs=trade.costs,
                           exit_reason=f"{underlying.lower()}_orb_exit")
        acct.mark(datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc), mark_prices={})

    return acct.finalize(), skipped


def _fmt_row(label: str, capital: float, result: EquityCurveResult, skipped: list[dict], n_signals: int) -> str:
    taken = len(result.closed_positions)
    return (f"| {label} | ₹{capital:,.0f} | ₹{result.final_equity:,.2f} | {result.total_return_pct:.1f}% | "
            f"{result.cagr_pct:.1f}% | {result.sharpe:.2f} | {result.max_drawdown_pct:.1f}% | "
            f"₹{result.max_drawdown_rs:,.2f} | {taken}/{n_signals} | {len(skipped)} |")


async def main_async(args) -> int:
    config = load_config(args.config)
    from core.brokers import get_broker
    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')} ...")
    if not broker.connect():
        print("ERROR: broker connect() returned False -- check the Fyers token "
              "(python agent/auth/fyers_auth.py).")
        return 1

    try:
        data = await fetch_and_run_both(broker)
    except OrbScalpingDataError as e:
        print(f"ERROR: {e}.")
        return 1

    nifty_stratified = data["nifty_trades"]["stratified"]
    banknifty_stratified = data["banknifty_trades"]["stratified"]
    nifty_days = set(data["nifty_by_day"].keys())
    banknifty_days = set(data["banknifty_by_day"].keys())

    nifty_mining, nifty_holdout, nifty_boundary = mining_holdout_split(nifty_stratified, data["nifty_window"])
    bn_mining, bn_holdout, bn_boundary = mining_holdout_split(banknifty_stratified, data["banknifty_window"])
    print(f"NIFTY mining/holdout boundary: {nifty_boundary} ({len(nifty_mining)} mining / {len(nifty_holdout)} holdout)")
    print(f"BankNifty mining/holdout boundary: {bn_boundary} ({len(bn_mining)} mining / {len(bn_holdout)} holdout)")

    mining_returns = [t.net_profit_pct / 100 for t in nifty_mining] + [t.net_profit_pct / 100 for t in bn_mining]
    f_full = kelly_fraction(mining_returns)
    f_half = round(f_full / 2, 4)
    f_quarter = round(f_full / 4, 4)
    print(f"Mining-derived Kelly fraction: full={f_full:.4f}, half={f_half:.4f}, quarter={f_quarter:.4f}")

    # Every trading day in the holdout period for EITHER index, not just
    # days a trade actually fired -- a no-trade day sitting in cash is a
    # real zero-return day in the Sharpe/CAGR calculation, same convention
    # as scripts/simulate_orb_scalping_equity_curve.py.
    holdout_days = sorted({d for d in nifty_days if d >= nifty_boundary} |
                           {d for d in banknifty_days if d >= bn_boundary})
    full_days = data["trading_days"]

    cost_fn = default_cost_fn(nifty_days, banknifty_days)

    policies = [("Fixed 1 lot", None), (f"Full Kelly ({f_full:.4f})", f_full),
                (f"Half Kelly ({f_half:.4f})", f_half), (f"Quarter Kelly ({f_quarter:.4f})", f_quarter)]

    lines = [
        "# Candidate 18 (ORB Options Scalping) — Capital Allocation / Position Sizing",
        "",
        "Methodology: this script's own module docstring "
        "(scripts/simulate_orb_scalping_capital_allocation.py) — Kelly fraction "
        "derived on a Mining window ONLY, tested on an untouched Holdout window, "
        "same 80/20 time-based split docs/ORB_CONDITION_MINING_METHODOLOGY.md "
        "already established for this candidate.",
        "",
        f"NIFTY mining/holdout boundary: {nifty_boundary} ({len(nifty_mining)} mining / {len(nifty_holdout)} holdout signals).",
        f"BankNifty mining/holdout boundary: {bn_boundary} ({len(bn_mining)} mining / {len(bn_holdout)} holdout signals).",
        "",
        f"**Mining-derived Kelly fraction (pooled NIFTY+BankNifty mining returns, n={len(mining_returns)})**: "
        f"full={f_full:.4f} ({f_full*100:.2f}% of equity/trade), half={f_half:.4f}, quarter={f_quarter:.4f}.",
        "",
        "## Holdout window only (the real, out-of-sample test)",
        "",
        "| Sizing policy | Starting capital | Final equity | Total return % | CAGR % | Sharpe | Max DD % | Max DD ₹ | Signals taken | Signals skipped |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    n_holdout_signals = len(nifty_holdout) + len(bn_holdout)
    for label, frac in policies:
        for capital in args.capital:
            if frac is None:
                result, skipped = simulate_fixed_lot(nifty_holdout, bn_holdout, holdout_days, capital)
            else:
                result, skipped = simulate_equity_fraction(nifty_holdout, bn_holdout, holdout_days, capital, frac, cost_fn)
            lines.append(_fmt_row(label, capital, result, skipped, n_holdout_signals))

    lines += [
        "",
        "## Full window (mining + holdout) — IN-SAMPLE for the Kelly fractions above, context only",
        "",
        "The Kelly fractions were derived FROM the mining portion of this same "
        "window, so any Kelly row below is not an independent test — it is "
        "shown only to see full-history compounding behavior, not as evidence "
        "for or against the sizing rule. The Holdout-only table above is the "
        "actual validation.",
        "",
        "| Sizing policy | Starting capital | Final equity | Total return % | CAGR % | Sharpe | Max DD % | Max DD ₹ | Signals taken | Signals skipped |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    n_full_signals = len(nifty_stratified) + len(banknifty_stratified)
    for label, frac in policies:
        for capital in args.capital:
            if frac is None:
                result, skipped = simulate_fixed_lot(nifty_stratified, banknifty_stratified, full_days, capital)
            else:
                result, skipped = simulate_equity_fraction(
                    nifty_stratified, banknifty_stratified, full_days, capital, frac, cost_fn)
            lines.append(_fmt_row(label, capital, result, skipped, n_full_signals))

    report = "\n".join(lines) + "\n"
    out_path = Path(args.out)
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--out", default="docs/ORB_SCALPING_CAPITAL_ALLOCATION_RESULTS.md")
    parser.add_argument("--capital", type=float, nargs="+", default=DEFAULT_CAPITALS)
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
