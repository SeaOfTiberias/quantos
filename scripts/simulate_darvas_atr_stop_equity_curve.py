#!/usr/bin/env python3
"""
QuantOS — Darvas ATR-Stop: Real Capital-Tracked Equity Curve & Position Sizing
────────────────────────────────────────────────────────────────────────────
docs/DARVAS_ATR_STOP_BACKTEST_RESULTS.md's headline numbers are POOLED
PER-TRADE stats (core/backtest/parser.py's _compute_metrics) on Bucket B
(35% < box width <= 50%) trades, sized at a fixed Rs100,000 notional per
trade regardless of real account size (scripts/backtest_darvas_box_width.py's
NOTIONAL_PER_TRADE) -- exactly the same gap candidate 18's real-capital
work exposed: this answers "is there a signal edge" (the pre-registered
gate this candidate cleared 2026-09-24), not "what does my real capital
become." This script builds that second answer, reusing
core/backtest/equity_curve.py's generic Account core (Track 2 of
docs/SHARPE_SWEEP_AND_EQUITY_CURVE_PLAN.md) -- the same machinery
candidate 18's two equity-curve scripts already use.

No new backtest is run and no Fyers data is fetched: this is pure post-
processing of Bucket B's ALREADY-COMMITTED trades from
scripts/backtest_darvas_atr_stop.py's own local cache
(~/.quantos/darvas_atr_stop_results.json). Bucket B is the only bucket
that cleared this candidate's pre-registered bar (mining/Stressed PASS,
holdout/Stressed PASS, control bucket does NOT clear holdout) -- using
any other bucket here would validate capital-readiness for a signal that
was never found to have an edge in the first place.

Equities, not options: position sizing here is a SHARE COUNT, not a lot
count -- Darvas trades individual NSE stocks, no lot-size granularity.
Four sizing policies tested, same discipline as
scripts/simulate_orb_scalping_capital_allocation.py:
  - Fixed-notional: reproduces the original backtest's own convention
    (Rs100,000/trade), capped by actually available cash.
  - Full/Half/Quarter Kelly: a fraction of CURRENT equity per trade,
    derived on trades before this candidate's own pre-registered
    Mining/Holdout boundary (MINING_HOLDOUT_SPLIT, 2026-02-15,
    scripts/backtest_darvas_box_width.py) and VALIDATED on the untouched
    Holdout trades -- not fit and reported on the same data (the
    overfitting trap docs/SHARPE_SWEEP_AND_EQUITY_CURVE_PLAN.md exists to
    avoid, same as candidate 18's Kelly analysis).

Costs: the real STRESSED_COST_MODEL (this candidate's own gating cost
model), recomputed at the ACTUAL sized share count for every trade, not
reused from the backtest's own fixed-notional cost figure (a flat
brokerage cap doesn't scale linearly with quantity -- same lesson as
candidate 18's capital-allocation script).

Equity marking: every REAL NSE trading day (core/reference/calendar.py),
unioned with every trade's own entry/exit date (the calendar reference's
coverage currently ends 2026-08-18, short of this window's tail -- the
union guarantees no trade event is ever missed even where the calendar
itself is stale). Between a trade's own entry and exit, its mark-to-
market carries the ENTRY price forward (no daily price series is loaded
here, only the trade list) -- the same disclosed fallback convention
`Account.mark()` uses for any day with no fresher price. This UNDERSTATES
intra-trade drawdown for positions that dip hard before recovering to
their eventual exit price; it does not affect realized P&L, which is
booked in full at each trade's own exit.

"Still-open" trades (reason == "still-open" in the cache) are a mark-to-
market as of the backtest's own run date, not a real close -- included
here exactly as the original backtest includes them (excluding them
would discard the still-running winners this ATR-trail variant is meant
to capture), with the same caveat that applies to the original backtest.

Usage:
    python scripts/simulate_darvas_atr_stop_equity_curve.py
    python scripts/simulate_darvas_atr_stop_equity_curve.py --capital 25000 50000 75000 100000 250000 500000
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.backtest.equity_curve import Account, EquityCurveResult, kelly_fraction  # noqa: E402
from core.reference.calendar import coverage as calendar_coverage  # noqa: E402
from core.reference.calendar import trading_days as nse_trading_days  # noqa: E402
from scripts.backtest_darvas_atr_stop import CACHE_DEFAULT  # noqa: E402
from scripts.backtest_darvas_box_width import (  # noqa: E402
    BUCKETS, MINING_HOLDOUT_SPLIT, STRESSED_COST_MODEL, all_trades, load_results,
)

BUCKET_B_LABEL = "35-50%"
DEFAULT_CAPITALS = [25_000.0, 50_000.0, 75_000.0, 100_000.0, 250_000.0, 500_000.0]
FIXED_NOTIONAL_PER_TRADE = 100_000.0   # matches the original backtest's own convention


def bucket_b_trades(results: dict) -> list[dict]:
    pred = dict(BUCKETS)[BUCKET_B_LABEL]
    return [t for t in all_trades(results) if pred(t["width_pct"])]


def mining_holdout_split(trades: list[dict]) -> tuple[list[dict], list[dict]]:
    """Time-based, on `breakout_date` -- reuses this candidate's OWN
    already-pre-registered boundary (MINING_HOLDOUT_SPLIT), the same
    split scripts/backtest_darvas_atr_stop.py's own verdict is built on,
    rather than inventing a new one."""
    cutoff = MINING_HOLDOUT_SPLIT.isoformat()
    mining = [t for t in trades if t["breakout_date"] < cutoff]
    holdout = [t for t in trades if t["breakout_date"] >= cutoff]
    return mining, holdout


def trade_fractional_return(entry_price: float, exit_price: float, qty: int) -> float:
    """Net-of-cost fractional return on the notional ACTUALLY allocated to
    one share's worth of this trade (qty-invariant, same property
    core/backtest/parser.py's net_profit_pct has) -- what kelly_fraction
    needs."""
    if entry_price <= 0 or qty <= 0:
        return 0.0
    gross = (exit_price - entry_price) * qty
    costs = STRESSED_COST_MODEL.cost_of(entry_price, exit_price, qty, "BUY")
    notional = entry_price * qty
    return (gross - costs) / notional


def build_trading_days(trades: list[dict], window_end: date) -> list[date]:
    """Real NSE trading days over the window, unioned with every trade's
    own entry/exit date -- guards against the calendar reference's
    coverage ending before this window's tail (see module docstring)."""
    cal_start, cal_end = calendar_coverage()
    effective_end = min(window_end, cal_end)
    days = set(nse_trading_days(cal_start, effective_end))
    for t in trades:
        days.add(datetime.fromisoformat(t["entry_date"]).date())
        days.add(datetime.fromisoformat(t["exit_date"]).date())
    return sorted(days)


def simulate(trades: list[dict], trading_days: list[date], initial_capital: float,
             sizing: str, fraction: float = 0.0) -> tuple[EquityCurveResult, list[dict]]:
    """Event-driven open/close scheduling generalized from
    scripts/simulate_orb_scalping_capital_allocation.py to multiple
    concurrent SYMBOLS and multi-day holds (Darvas positions are held for
    days-to-weeks, not intraday). `sizing`: "fixed_notional" or
    "fraction" (equity-proportional, `fraction` required)."""
    OPEN, CLOSE = 0, 1
    events: list[tuple] = []
    for t in trades:
        entry_dt = datetime.fromisoformat(t["entry_date"])
        exit_dt = datetime.fromisoformat(t["exit_date"])
        events.append((entry_dt, OPEN, t))
        events.append((exit_dt, CLOSE, t))

    events_by_day: dict[date, list[tuple]] = {}
    for ev in events:
        events_by_day.setdefault(ev[0].date(), []).append(ev)
    for day_events in events_by_day.values():
        day_events.sort(key=lambda e: (e[0], e[1]))

    acct = Account(initial_capital=initial_capital)
    skipped: list[dict] = []
    open_pos: dict[int, int] = {}      # id(trade dict) -> position id
    open_costs: dict[int, float] = {}

    for day in sorted(trading_days):
        for _ts, kind, t in events_by_day.get(day, []):
            key = id(t)
            entry_price = t["entry_price"]
            if kind == OPEN:
                if sizing == "fixed_notional":
                    target_notional = FIXED_NOTIONAL_PER_TRADE
                else:
                    equity = acct.cash + sum(p.qty * p.entry_price for p in acct.open_positions.values())
                    target_notional = fraction * equity
                spendable = min(target_notional, acct.cash)
                qty = int(spendable // entry_price) if entry_price > 0 else 0
                if qty < 1:
                    skipped.append({"symbol": t["symbol"], "date": day,
                                     "needed": round(entry_price, 2), "cash": round(acct.cash, 2)})
                    continue
                cost = STRESSED_COST_MODEL.cost_of(entry_price, t["exit_price"], qty, "BUY")
                pos_id = acct.open(t["symbol"], qty, entry_price, datetime.fromisoformat(t["entry_date"]),
                                    strict=False)
                if pos_id is None:
                    skipped.append({"symbol": t["symbol"], "date": day,
                                     "needed": round(entry_price, 2), "cash": round(acct.cash, 2)})
                    continue
                open_pos[key] = pos_id
                open_costs[key] = cost
            else:  # CLOSE
                pos_id = open_pos.pop(key, None)
                if pos_id is None:
                    continue   # this trade's open was skipped for insufficient cash
                cost = open_costs.pop(key, 0.0)
                acct.close(pos_id, t["exit_price"], datetime.fromisoformat(t["exit_date"]),
                           costs=cost, exit_reason=t.get("reason", ""))
        acct.mark(datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc), mark_prices={})

    return acct.finalize(), skipped


def _fmt_row(label: str, capital: float, result: EquityCurveResult, skipped: list[dict], n_trades: int) -> str:
    taken = len(result.closed_positions)
    return (f"| {label} | ₹{capital:,.0f} | ₹{result.final_equity:,.2f} | {result.total_return_pct:.1f}% | "
            f"{result.cagr_pct:.1f}% | {result.sharpe:.2f} | {result.sortino:.2f} | {result.calmar:.2f} | "
            f"{result.ulcer_index:.2f} | {result.max_drawdown_pct:.1f}% | ₹{result.max_drawdown_rs:,.2f} | "
            f"{result.max_drawdown_duration_days}d | {taken}/{n_trades} | {len(skipped)} |")


def capital_floor_threshold(trades: list[dict], trading_days: list[date],
                             sizing: str, fraction: float, candidates: list[float]) -> float | None:
    """Smallest tested starting capital for which zero trades were skipped
    for insufficient cash -- an empirical "this is where the cliff ends"
    reading, not a theoretical minimum. Returns None if no tested capital
    cleared it."""
    for capital in sorted(candidates):
        _result, skipped = simulate(trades, trading_days, capital, sizing, fraction)
        if not skipped:
            return capital
    return None


def main_report(cache_path: Path, capitals: list[float]) -> str:
    results = load_results(cache_path)
    trades = bucket_b_trades(results)
    if not trades:
        return "No Bucket B trades found in the cache -- nothing to simulate."

    mining, holdout = mining_holdout_split(trades)
    mining_returns = [trade_fractional_return(t["entry_price"], t["exit_price"],
                                               max(1, round(FIXED_NOTIONAL_PER_TRADE / t["entry_price"])))
                       for t in mining]
    f_full = kelly_fraction(mining_returns)
    f_half = round(f_full / 2, 4)
    f_quarter = round(f_full / 4, 4)

    window_end = max(datetime.fromisoformat(t["exit_date"]).date() for t in trades)
    trading_days = build_trading_days(trades, window_end)
    lockout_capacity_days = len(trading_days)

    policies = [("Fixed Rs100k/trade", "fixed_notional", 0.0),
                (f"Full Kelly ({f_full:.4f})", "fraction", f_full),
                (f"Half Kelly ({f_half:.4f})", "fraction", f_half),
                (f"Quarter Kelly ({f_quarter:.4f})", "fraction", f_quarter)]

    lines = [
        "# Darvas ATR-Stop (Bucket B) — Real Capital-Tracked Equity Curve & Position Sizing",
        "",
        "Methodology: this script's own module docstring "
        "(scripts/simulate_darvas_atr_stop_equity_curve.py). Bucket B "
        "(35% < box width <= 50%) trades only -- the only bucket that "
        "cleared this candidate's pre-registered bar "
        "(docs/DARVAS_ATR_STOP_BACKTEST_RESULTS.md). No new backtest run, "
        "no Fyers data fetched -- pure post-processing of the already-"
        f"committed cache ({cache_path}).",
        "",
        f"Mining/Holdout boundary: {MINING_HOLDOUT_SPLIT.date()} "
        f"({len(mining)} mining / {len(holdout)} holdout trades, {len(trades)} total).",
        f"Mining-derived Kelly fraction (n={len(mining_returns)}): "
        f"full={f_full:.4f} ({f_full*100:.2f}% of equity/trade), half={f_half:.4f}, quarter={f_quarter:.4f}.",
        "",
        "## Full-window results by starting capital and sizing policy",
        "",
        "| Sizing policy | Starting capital | Final equity | Total return % | CAGR % | Sharpe | Sortino | Calmar | Ulcer Index | Max DD % | Max DD ₹ | Max DD duration | Trades taken | Trades skipped (insufficient cash) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for label, sizing, fraction in policies:
        for capital in capitals:
            result, skipped = simulate(trades, trading_days, capital, sizing, fraction)
            lines.append(_fmt_row(label, capital, result, skipped, len(trades)))

    lines += [
        "",
        "## Holdout-only results (the real out-of-sample test for the Kelly fractions)",
        "",
        "The Kelly fractions were derived from the Mining trades only; this "
        "table applies them to the untouched Holdout trades, same "
        "discipline as candidate 18's own capital-allocation analysis.",
        "",
        "| Sizing policy | Starting capital | Final equity | Total return % | CAGR % | Sharpe | Sortino | Calmar | Ulcer Index | Max DD % | Max DD ₹ | Max DD duration | Trades taken | Trades skipped (insufficient cash) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    holdout_start = min(datetime.fromisoformat(t["entry_date"]).date() for t in holdout) if holdout else window_end
    holdout_days = [d for d in trading_days if d >= holdout_start]
    for label, sizing, fraction in policies:
        for capital in capitals:
            result, skipped = simulate(holdout, holdout_days, capital, sizing, fraction)
            lines.append(_fmt_row(label, capital, result, skipped, len(holdout)))

    floor = capital_floor_threshold(trades, trading_days, "fixed_notional", 0.0, capitals)
    lines += [
        "",
        f"## Capital floor threshold (Fixed Rs100k/trade policy)",
        "",
        f"Smallest tested starting capital with ZERO trades skipped for "
        f"insufficient cash: **{'₹{:,.0f}'.format(floor) if floor else 'none of the tested tiers cleared it'}**. "
        "This is an empirical reading against the tested capital tiers "
        "only, not a theoretical minimum -- see the full table above for "
        "every tier's actual skip count.",
    ]

    return "\n".join(lines) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache", default=CACHE_DEFAULT)
    parser.add_argument("--out", default="docs/DARVAS_ATR_STOP_EQUITY_CURVE_RESULTS.md")
    parser.add_argument("--capital", type=float, nargs="+", default=DEFAULT_CAPITALS)
    args = parser.parse_args()

    cache_path = Path(args.cache)
    if not cache_path.exists():
        print(f"ERROR: cache not found at {cache_path} -- run scripts/backtest_darvas_atr_stop.py first.")
        return 1

    report = main_report(cache_path, args.capital)
    out_path = Path(args.out)
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
