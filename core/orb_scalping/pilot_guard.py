"""
QuantOS — ORB live pilot breaker
────────────────────────────────
Stops the 1-lot live pilot opening NEW trades when it shows a live-only
defect or spends its loss budget. Agreed with the user 2026-09-30, after a
simulation showed P&L-only triggers (losing streaks, small drawdown limits)
trip in most healthy months at 1 lot, so they cannot tell "broken" from
"unlucky". The main triggers therefore watch execution, not P&L:

  - any anomaly from core/orb_scalping/pilot_review.py (no stop resting,
    exit with no entry, manual/unknown exit, missing fill);
  - a single trade whose shortfall vs paper 18 exceeds SHORTFALL_LIMIT_RS;
  - the budget backstop: pilot net P&L since the last reset <= -BUDGET_RS.

Deliberately separate from agent/risk_guard.py's global ~/.quantos/halt:
that flag also stops paper 18, whose dry-run log is candidate 18b's verdict
baseline. This flag (~/.quantos/halt_pilot) is read by the pilot only.

A halt refuses NEW entries only. It never cancels resting stops or touches
open positions: they are still managed to their exit, the same "refuse
entries, keep managing exits" rule as risk_guard.

Reset (after reviewing the Reports card): `python scripts/pilot_guard.py
--reset`. It clears the flag and records an acknowledgement time; only
events after that time count again, so an already-reviewed anomaly does not
re-trip on the next fire, and the budget restarts from zero.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.orb_scalping.dry_run_log import DryRunTrade
from core.orb_scalping.live_trade_log import LiveTradeEvent
from core.orb_scalping.pilot_review import review

BUDGET_RS = 15_000.0
SHORTFALL_LIMIT_RS = 1_500.0


def _dir(base: Optional[Path]) -> Path:
    return base or Path.home() / ".quantos"


def halt_path(base: Optional[Path] = None) -> Path:
    return _dir(base) / "halt_pilot"


def ack_path(base: Optional[Path] = None) -> Path:
    return _dir(base) / "pilot_guard_ack"


def read_pilot_halt(base: Optional[Path] = None) -> Optional[str]:
    p = halt_path(base)
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8").strip() or "pilot halted (no reason recorded)"


def set_pilot_halt(reason: str, base: Optional[Path] = None) -> None:
    p = halt_path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    p.write_text(f"{stamp} UTC -- {reason}\n", encoding="utf-8")


def reset(base: Optional[Path] = None, now: Optional[datetime] = None) -> None:
    """Clear the flag and acknowledge everything up to now."""
    halt_path(base).unlink(missing_ok=True)
    a = ack_path(base)
    a.parent.mkdir(parents=True, exist_ok=True)
    a.write_text((now or datetime.now(timezone.utc)).isoformat(), encoding="utf-8")


def acknowledged_until(base: Optional[Path] = None) -> Optional[str]:
    a = ack_path(base)
    return a.read_text(encoding="utf-8").strip() or None if a.exists() else None


def evaluate(events: list[LiveTradeEvent], paper: list[DryRunTrade],
             acknowledged: Optional[str] = None,
             budget_rs: float = BUDGET_RS,
             shortfall_limit_rs: float = SHORTFALL_LIMIT_RS) -> Optional[str]:
    """Pure. The reason the pilot should halt, or None. Only events after
    `acknowledged` (ISO timestamp) count."""
    ack = datetime.fromisoformat(acknowledged) if acknowledged else None

    def after_ack(ts: str) -> bool:
        return ack is None or datetime.fromisoformat(ts) > ack

    r = review(events, paper)
    fresh_anomalies = [a for a in r.anomalies if after_ack(a.timestamp)]
    if fresh_anomalies:
        return f"live-only defect signal: {fresh_anomalies[0].message}"

    fresh_trades = [t for t in r.trades if after_ack(t["exit_timestamp"])]
    for t in fresh_trades:
        sf = t["shortfall_vs_paper"]
        if sf is not None and sf > shortfall_limit_rs:
            return (f"{t['exit_timestamp'][:10]} {t['label']}: shortfall vs paper Rs{sf:,.0f} "
                    f"exceeds Rs{shortfall_limit_rs:,.0f} -- fills or stop far from paper's")

    net = sum(t["net_pnl"] for t in fresh_trades)
    if net <= -budget_rs:
        return (f"loss budget spent: pilot net Rs{net:,.0f} since the last reset "
                f"(budget -Rs{budget_rs:,.0f})")
    return None
