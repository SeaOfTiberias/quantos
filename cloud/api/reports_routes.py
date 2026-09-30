"""
QuantOS — Paper Strategy Reports Route
────────────────────────────────────────
GET /reports/paper-strategies: per-trade table, summary stats and a
cost-adjusted equity curve for the paper runs of candidate 18 (ORB options
scalping) and the Darvas ATR-stop (Bucket B), read from the executors' own
dry-run logs in ~/.quantos on this same box.

Deliberately NOT candidate 18b. Its 2026-11-17 gate verdict is decided on
P&L, and its protocol forbids looking at running P&L before then
(docs/STRATEGY_WATCH_KICKOFF_PROMPT.md). Nothing here reads
orb_dry_run_trades_filtered.jsonl. The user decided on 2026-09-28 to keep it
off this page entirely.

Net P&L uses each candidate's own research cost model, so the paper curve is
on the same basis as the backtest it's compared against:
  - ORB: core/orb_scalping/costs.py's stratified_spread_trade_cost (the
    LOCKED FINAL variant), expiry-day flag computed over a weekday calendar
    (core/reference/calendar.py doesn't cover recent dates; an NSE holiday
    in an expiry week can misflag that one day's spread tier).
  - Darvas: scripts/backtest_darvas_box_width.py's STRESSED_COST_MODEL, the
    model scripts/simulate_darvas_atr_stop_equity_curve.py sized with.
Both imports are deferred into the handler: they pull in backtest modules
that cost several seconds, which the API shouldn't pay at boot.

Equity = starting capital + cumulative net P&L of CLOSED trades, one point
per exit. A trade the logger couldn't price (exit_premium null, the Fyers 429
case) is excluded from the curve and counted in `unpriced`, never guessed.
Paper sample sizes are tiny next to the backtests; the cockpit says so.
"""

import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])


def _quantos_dir() -> Path:
    override = os.getenv("QUANTOS_HOME_DIR")
    return Path(override) if override else Path.home() / ".quantos"


def _config_path() -> Path:
    return Path(os.getenv("QUANTOS_AGENT_CONFIG", "agent/config.yaml"))


def _config_block(name: str) -> dict:
    try:
        raw = yaml.safe_load(_config_path().read_text(encoding="utf-8")) or {}
        return raw.get(name) or {}
    except (OSError, yaml.YAMLError, AttributeError) as e:
        logger.warning("Could not read %s config: %s", name, e)
        return {}


def _summary(trades: list[dict], starting_capital: float) -> dict:
    nets = [t["net_pnl"] for t in trades]
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n <= 0]
    equity, peak, max_dd = starting_capital, starting_capital, 0.0
    for n in nets:
        equity += n
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    gross_loss = -sum(losses)
    return {
        "trades":           len(trades),
        "wins":             len(wins),
        "win_rate_pct":     round(len(wins) / len(trades) * 100, 1) if trades else None,
        "gross_pnl":        round(sum(t["gross_pnl"] for t in trades), 2),
        "costs":            round(sum(t["costs"] for t in trades), 2),
        "net_pnl":          round(sum(nets), 2),
        "profit_factor":    round(sum(wins) / gross_loss, 2) if gross_loss > 0 else None,
        "max_drawdown":     round(max_dd, 2),
        "starting_capital": starting_capital,
        "equity":           round(starting_capital + sum(nets), 2),
        "return_pct":       round(sum(nets) / starting_capital * 100, 2) if starting_capital else None,
    }


def _curve(trades: list[dict], starting_capital: float) -> list[dict]:
    """One point per closed trade (by exit time), plus a start point at the
    first entry, so the line always begins at starting capital."""
    if not trades:
        return []
    points = [{"t": trades[0]["entry_timestamp"], "equity": starting_capital, "label": "start"}]
    equity = starting_capital
    for t in trades:
        equity += t["net_pnl"]
        points.append({"t": t["exit_timestamp"], "equity": round(equity, 2), "label": t["label"]})
    return points


def _weekdays_around(days: list[date]) -> set:
    lo, hi = min(days) - timedelta(days=45), max(days) + timedelta(days=45)
    return {lo + timedelta(i) for i in range((hi - lo).days + 1) if (lo + timedelta(i)).weekday() < 5}


def orb_report() -> dict:
    from core.orb_scalping.backtest import is_banknifty_monthly_expiry_day
    from core.orb_scalping.costs import stratified_spread_trade_cost
    from core.orb_scalping.dry_run_log import load_dry_run_trades
    from core.orb_scalping.expiry import is_nifty_weekly_expiry_day
    from core.orb_scalping.premium import PREMIUM_STOP_PCT

    cfg = _config_block("orb_scalping")
    capital = float(cfg.get("starting_capital") or 0.0)
    raw = load_dry_run_trades(_quantos_dir() / "orb_dry_run_trades.jsonl")
    priced = [t for t in raw if t.exit_premium is not None]
    unpriced = len(raw) - len(priced)

    trades = []
    if priced:
        entry_days = [datetime.fromisoformat(t.entry_timestamp).date() for t in priced]
        calendar = _weekdays_around(entry_days)
        for t, d in zip(priced, entry_days):
            expiry_fn = is_nifty_weekly_expiry_day if t.underlying == "NIFTY" else is_banknifty_monthly_expiry_day
            is_expiry = expiry_fn(d, calendar)
            costs = stratified_spread_trade_cost(
                t.entry_premium, t.exit_premium, t.quantity, d, t.underlying, is_expiry,
            ).total
            gross = (t.exit_premium - t.entry_premium) * t.quantity
            # Paper exits before 2026-09-30 never enforced the 25% premium
            # stop (live, a resting SL_M does). Flag rows that fell through
            # it rather than rewrite the append-only log.
            stop_missed = (t.exit_reason != "premium_stop"
                           and t.exit_premium < t.entry_premium * (1 - PREMIUM_STOP_PCT))
            trades.append({
                "label":           f"{t.underlying} {t.direction}",
                "underlying":      t.underlying,
                "direction":       t.direction,
                "entry_timestamp": t.entry_timestamp,
                "exit_timestamp":  t.exit_timestamp,
                "exit_reason":     t.exit_reason,
                "quantity":        t.quantity,
                "entry_price":     t.entry_premium,
                "exit_price":      t.exit_premium,
                "expiry_day":      is_expiry,
                "premium_stop_missed": stop_missed,
                "gross_pnl":       round(gross, 2),
                "costs":           round(costs, 2),
                "net_pnl":         round(gross - costs, 2),
            })
    trades.sort(key=lambda t: t["exit_timestamp"])
    return {
        "name":     "Candidate 18 — ORB options scalping",
        "dry_run":  cfg.get("dry_run", True),
        "cost_basis": "Stratified spread (locked-final research cost variant)",
        "backtest": BACKTEST_REFERENCE["orb"],
        "sizing_changes": SIZING_CHANGES["orb"],
        "premium_stop_missed": sum(1 for t in trades if t["premium_stop_missed"]),
        "unpriced": unpriced,
        "summary":  _summary(trades, capital),
        "curve":    _curve(trades, capital),
        "trades":   list(reversed(trades)),
    }


def darvas_report() -> dict:
    from core.darvas_atr_stop.dry_run_log import load_dry_run_trades
    from scripts.backtest_darvas_box_width import STRESSED_COST_MODEL

    cfg = _config_block("darvas_atr_stop")
    capital = float(cfg.get("starting_capital") or 0.0)
    trades = []
    for t in load_dry_run_trades(_quantos_dir() / "darvas_atr_stop_dry_run_trades.jsonl"):
        gross = (t.boundary_price - t.entry_price) * t.quantity
        costs = STRESSED_COST_MODEL.cost_of(t.entry_price, t.boundary_price, t.quantity, "BUY")
        trades.append({
            "label":           t.symbol,
            "symbol":          t.symbol,
            "entry_timestamp": t.entry_timestamp,
            "exit_timestamp":  t.exit_timestamp,
            "exit_reason":     t.exit_reason,
            "quantity":        t.quantity,
            "entry_price":     t.entry_price,
            "exit_price":      t.boundary_price,
            "box_width_pct":   t.box_width_pct,
            "gross_pnl":       round(gross, 2),
            "costs":           round(costs, 2),
            "net_pnl":         round(gross - costs, 2),
        })
    trades.sort(key=lambda t: t["exit_timestamp"])
    return {
        "name":     "Darvas ATR-stop — Bucket B",
        "dry_run":  cfg.get("dry_run", True),
        "cost_basis": "Stressed delivery cost model (research basis)",
        "backtest": BACKTEST_REFERENCE["darvas"],
        "sizing_changes": SIZING_CHANGES["darvas"],
        "unpriced": 0,
        "summary":  _summary(trades, capital),
        "curve":    _curve(trades, capital),
        "trades":   list(reversed(trades)),
    }


# Backtest baselines shown beside the paper numbers, copied from the locked
# result docs (update only if those docs change). Win rates and PFs are
# the research's own; paper results will scatter widely around them at
# small N.
BACKTEST_REFERENCE = {
    "orb": {
        "source": "docs/ORB_SCALPING_RESULTS.md (Stratified, locked final)",
        "trades": 2304,
        "rows": [
            {"label": "NIFTY", "trades": 1036, "win_rate_pct": 47.6, "profit_factor": 1.23},
            {"label": "BANKNIFTY", "trades": 1268, "win_rate_pct": 45.7, "profit_factor": 1.16},
        ],
    },
    "darvas": {
        "source": "docs/DARVAS_ATR_STOP_BACKTEST_RESULTS.md (Bucket B, Stressed)",
        "trades": 277,
        "rows": [
            {"label": "Mining", "trades": 210, "win_rate_pct": 43.8, "profit_factor": 1.15},
            {"label": "Holdout", "trades": 67, "win_rate_pct": 43.3, "profit_factor": 1.16},
        ],
    },
}


# Sizing regime changes, drawn as markers on the curve so trades at
# different sizes aren't read as one series. Dates are the first session the
# new sizing could trade (the VM config itself is untracked).
SIZING_CHANGES = {
    "orb": [{"date": "2026-09-30", "label": "2 lots · Rs5L (was 1 lot · Rs70k)"}],
    "darvas": [],
}


def _safe(fn) -> dict:
    try:
        return fn()
    except Exception as e:  # one broken report must not blank the other
        logger.exception("Report %s failed", fn.__name__)
        return {"error": f"{type(e).__name__}: {e}"}


@router.get("/paper-strategies")
async def paper_strategies():
    return {"orb": _safe(orb_report), "darvas": _safe(darvas_report)}
