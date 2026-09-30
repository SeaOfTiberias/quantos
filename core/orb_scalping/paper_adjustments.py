"""
QuantOS — ORB paper-log adjustments pre-registered 2026-09-30
──────────────────────────────────────────────────────────────
Mechanical, symmetric views over core/orb_scalping/dry_run_log.py's
append-only logs, so candidate 18's go-live call and candidate 18b's
2026-11-17 verdict are not tilted by a paper-mode defect. Rules and
reasoning: docs/ORB_ENTRY_FILTER_METHODOLOGY.md, "Addendum, pre-registered
2026-09-30". Fixed BEFORE anyone looked at 18b's P&L.

Rule 1 (enforce_premium_stop): until 2026-09-30 dry_run never enforced the
25% premium stop (live, a resting SL_M does; the backtest does too). A
pre-fix row that fell past it is re-marked at the trigger -- what live and
the backtest would both have recorded. Applied identically to 18 and 18b.

Rule 3 (is_banknifty_expiry_day_trade): BANKNIFTY bought the 0-DTE monthly
contract on its own expiry day, a case the backtest's `max(1, dte)`
pricing never modelled. Used to report a symmetric sensitivity view with
those trades excluded from BOTH arms.

The logs themselves are never rewritten; these return new views only.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

from core.orb_scalping.dry_run_log import DryRunTrade
from core.orb_scalping.premium import PREMIUM_STOP_PCT

# First session on which dry_run enforced the premium stop itself (39e6cbc).
PREMIUM_STOP_ENFORCED_FROM = date(2026, 9, 30)
RETRO_STOP_REASON = "premium_stop_retro"


def _entry_date(t: DryRunTrade) -> date:
    return datetime.fromisoformat(t.entry_timestamp).date()


def premium_stop_trigger(entry_premium: float) -> float:
    """Same rounding as run_orb_scalping_live.py's protective_stop_trigger."""
    return round(entry_premium * (1 - PREMIUM_STOP_PCT), 4)


def enforce_premium_stop(t: DryRunTrade) -> DryRunTrade:
    """Rule 1. Unchanged unless the row predates enforcement, has an exit
    quote, and exited below its trigger by some other route."""
    if (t.exit_premium is None
            or _entry_date(t) >= PREMIUM_STOP_ENFORCED_FROM
            or t.exit_reason == "premium_stop"):
        return t
    trigger = premium_stop_trigger(t.entry_premium)
    if t.exit_premium >= trigger:
        return t
    return replace(t, exit_premium=trigger, exit_reason=RETRO_STOP_REASON)


def enforce_premium_stop_all(trades: list[DryRunTrade]) -> list[DryRunTrade]:
    return [enforce_premium_stop(t) for t in trades]


def is_banknifty_expiry_day_trade(t: DryRunTrade) -> bool:
    """Rule 3. True for a BANKNIFTY trade entered on BANKNIFTY's own
    (holiday-adjusted) monthly expiry day."""
    if t.underlying != "BANKNIFTY":
        return False
    from core.orb_scalping.backtest import is_banknifty_monthly_expiry_day
    d = _entry_date(t)
    # Plain weekdays, same as cloud/api/reports_routes.py: the derived NSE
    # calendar (core/reference/calendar.py) currently stops at 2026-08-18.
    # A weekday-only set misses exchange holidays, so a holiday-shifted
    # expiry could be misdated; acceptable for a sensitivity view.
    lo = d - timedelta(days=45)
    sessions = {lo + timedelta(i) for i in range(91) if (lo + timedelta(i)).weekday() < 5}
    return is_banknifty_monthly_expiry_day(d, sessions)


def exclude_banknifty_expiry_days(trades: list[DryRunTrade]) -> list[DryRunTrade]:
    return [t for t in trades if not is_banknifty_expiry_day_trade(t)]
