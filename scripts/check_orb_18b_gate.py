#!/usr/bin/env python3
"""
QuantOS — Candidate 18b: Pre-Registered Gate + Equity Check
──────────────────────────────────────────────────────────────────────
Reports docs/ORB_ENTRY_FILTER_METHODOLOGY.md's two prospective checks:

1. Per-index PF/Sharpe pass/fail — N>=20 new (closed) 18b trades AND
   >=8 weeks elapsed since 2026-09-22, BOTH required. ONLY reveals
   PF/Sharpe once both clear for that index, same "no peeking"
   discipline as scripts/check_orb_stopout_probe_gate.py. Compared
   against unfiltered candidate 18's own closed trades over the
   identical forward window (same index, same period) — the methodology
   doc's own verdict method.
2. The ₹50,000 combined-account equity narrative (the methodology doc's
   2026-09-22 addendum) — gated on DATE ONLY (>=2026-11-17), not N, and
   reported as a descriptive figure alongside (never instead of) #1.

Cost model note: both use Stressed (core/orb_scalping/costs.py's
stressed_trade_cost), NOT the backtest's Stratified variant — Stratified
needs an is_expiry_day classification against a real NSE trading-day
calendar, which this live-tracking checker does not build. Stressed was
the ORIGINAL pre-registered bar before Stratified was added as a later
refinement, so this is a disclosed simplification, not a weakening
introduced silently.

Reads core/orb_scalping/dry_run_log.py's two logs (18b's own, plus
unfiltered candidate 18's for the comparison baseline). Run this ON the
VM, where both logs actually accumulate.

Usage:
    python scripts/check_orb_18b_gate.py
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.backtest.parser import BacktestTrade, _compute_metrics  # noqa: E402
from core.orb_scalping.costs import stressed_trade_cost  # noqa: E402
from core.orb_scalping.dry_run_log import (  # noqa: E402
    DryRunTrade,
    ORB_DRY_RUN_LOG_FILTERED_PATH,
    ORB_DRY_RUN_LOG_PATH,
    load_dry_run_trades,
)

MIN_SAMPLE_N = 20              # reuses core/risk/trade_history.py's Kelly-sizing minimum
MIN_WEEKS = 8.0
DEPLOYED_AT = date(2026, 9, 22)     # orb_scalping_filtered.enabled flipped true
EQUITY_DATE = date(2026, 11, 17)    # DEPLOYED_AT + 8 weeks, exactly
BASE_CAPITAL = 50_000.0
UNDERLYINGS = ("NIFTY", "BANKNIFTY")


def elapsed_weeks(today: date, deployed_at: date = DEPLOYED_AT) -> float:
    return (today - deployed_at).days / 7.0


def gate_status(n: int, weeks: float, min_n: int = MIN_SAMPLE_N, min_weeks: float = MIN_WEEKS) -> dict:
    """Pure, unit-testable — both gates from docs/ORB_ENTRY_FILTER_METHODOLOGY.md."""
    n_met = n >= min_n
    time_met = weeks >= min_weeks
    return {"n": n, "n_met": n_met, "elapsed_weeks": round(weeks, 1),
            "time_met": time_met, "both_met": n_met and time_met}


def closed_only(trades: list[DryRunTrade]) -> list[DryRunTrade]:
    """Excludes any trade whose exit quote couldn't be captured — never
    treated as a zero-P&L trade, per the dry-run log's own convention."""
    return [t for t in trades if t.exit_premium is not None]


def net_pnl(t: DryRunTrade) -> float:
    """Realized P&L (INR), Stressed-cost-adjusted — used by the equity
    narrative, which needs actual net cash flow, not the gross/costs
    split BacktestTrade expects."""
    entry_date = datetime.fromisoformat(t.entry_timestamp).date()
    gross = (t.exit_premium - t.entry_premium) * t.quantity
    cost = stressed_trade_cost(t.entry_premium, t.exit_premium, t.quantity, entry_date).total
    return gross - cost


def to_backtest_trade(t: DryRunTrade, trade_num: int) -> BacktestTrade:
    """`profit` stays GROSS and `costs` stays separate — BacktestMetrics
    computes net_profit = profit - costs internally; baking the cost into
    `profit` here would double-subtract it."""
    entry_dt = datetime.fromisoformat(t.entry_timestamp)
    exit_dt = datetime.fromisoformat(t.exit_timestamp)
    profit = (t.exit_premium - t.entry_premium) * t.quantity
    notional = t.entry_premium * t.quantity
    costs = stressed_trade_cost(t.entry_premium, t.exit_premium, t.quantity, entry_dt.date()).total
    return BacktestTrade(
        trade_num=trade_num, direction="Long", qty=t.quantity,
        entry_date=entry_dt, entry_price=t.entry_premium,
        exit_date=exit_dt, exit_price=t.exit_premium,
        profit=profit, profit_pct=(profit / notional * 100 if notional else 0.0),
        cum_profit=0.0, bars_held=0, costs=costs,
    )


def format_pf_sharpe_report(underlying: str, filtered: list[DryRunTrade],
                             unfiltered: list[DryRunTrade], today: date) -> str:
    status = gate_status(len(filtered), elapsed_weeks(today))
    lines = [
        f"=== {underlying}: PF/Sharpe gate ===",
        f"  N={status['n']} (need >= {MIN_SAMPLE_N}): {'MET' if status['n_met'] else 'WAITING'}",
        f"  elapsed={status['elapsed_weeks']} weeks (need >= {MIN_WEEKS}): "
        f"{'MET' if status['time_met'] else 'WAITING'}",
    ]
    if not status["both_met"]:
        lines.append("  Gate NOT yet met -- per docs/ORB_ENTRY_FILTER_METHODOLOGY.md, "
                     "no PF/Sharpe conclusion should be drawn yet. Do not peek.")
        return "\n".join(lines)

    filtered_bt = [to_backtest_trade(t, i) for i, t in enumerate(filtered)]
    fm = _compute_metrics(filtered_bt)
    lines.append(f"  Gate MET -- 18b: PF {fm.profit_factor:.2f} Sharpe {fm.sharpe_ratio:.2f} "
                f"({'PASS' if fm.has_positive_edge else 'FAIL'}, n={len(filtered_bt)})")

    if unfiltered:
        unfiltered_bt = [to_backtest_trade(t, i) for i, t in enumerate(unfiltered)]
        um = _compute_metrics(unfiltered_bt)
        lines.append(f"  Unfiltered 18 over the SAME window: PF {um.profit_factor:.2f} "
                    f"Sharpe {um.sharpe_ratio:.2f} (n={len(unfiltered_bt)})")
    else:
        lines.append("  Unfiltered 18 has zero comparable closed trades over this window.")
    return "\n".join(lines)


def format_equity_report(filtered_by_underlying: dict[str, list[DryRunTrade]], today: date) -> str:
    if today < EQUITY_DATE:
        return (f"=== Rs{BASE_CAPITAL:,.0f} equity narrative ===\n"
               f"  Not due until {EQUITY_DATE} -- per docs/ORB_ENTRY_FILTER_METHODOLOGY.md's "
               f"addendum, no running total is reported before then.")

    rows: list[tuple[datetime, str, float]] = []
    excluded_unknown = 0
    for underlying, trades in filtered_by_underlying.items():
        for t in trades:
            if t.exit_premium is None:
                excluded_unknown += 1
                continue
            rows.append((datetime.fromisoformat(t.exit_timestamp), underlying, net_pnl(t)))
    rows.sort(key=lambda r: r[0])

    equity = BASE_CAPITAL
    by_underlying_pnl = {u: 0.0 for u in UNDERLYINGS}
    for _, underlying, pnl in rows:
        equity += pnl
        by_underlying_pnl[underlying] = by_underlying_pnl.get(underlying, 0.0) + pnl

    total_return_pct = (equity - BASE_CAPITAL) / BASE_CAPITAL * 100
    lines = [
        f"=== Rs{BASE_CAPITAL:,.0f} equity narrative (as of {EQUITY_DATE}) ===",
        f"  Trades counted: {len(rows)} (excluded {excluded_unknown} with no captured exit quote)",
        f"  Final equity: Rs{equity:,.2f} ({total_return_pct:+.1f}%)",
    ]
    for u in UNDERLYINGS:
        lines.append(f"  {u} contribution: Rs{by_underlying_pnl.get(u, 0.0):+,.2f}")
    return "\n".join(lines)


def _by_underlying_from_log(path, since: date = None) -> dict[str, list[DryRunTrade]]:
    out: dict[str, list[DryRunTrade]] = {u: [] for u in UNDERLYINGS}
    for t in load_dry_run_trades(path=path):
        if t.underlying not in out:
            continue
        if since is not None and datetime.fromisoformat(t.entry_timestamp).date() < since:
            continue
        out[t.underlying].append(t)
    return out


def main() -> int:
    today = date.today()
    filtered_by_underlying = _by_underlying_from_log(ORB_DRY_RUN_LOG_FILTERED_PATH)
    unfiltered_by_underlying = _by_underlying_from_log(ORB_DRY_RUN_LOG_PATH, since=DEPLOYED_AT)

    for underlying in UNDERLYINGS:
        print(format_pf_sharpe_report(
            underlying, closed_only(filtered_by_underlying[underlying]),
            closed_only(unfiltered_by_underlying[underlying]), today,
        ))
        print()

    closed_filtered = {u: closed_only(v) for u, v in filtered_by_underlying.items()}
    print(format_equity_report(closed_filtered, today))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
