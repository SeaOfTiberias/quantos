"""
QuantOS Local Agent — Portfolio Kill Switch (S4-2 / P0-2)
──────────────────────────────────────────────────────────
Refuses new entries once the account crosses defined loss/exposure
limits — an additional refusal layer that sits in front of order
placement and overrides even a human "execute" confirmation (ADR-05 is
the *default* gate; this halt is a *hard* gate on top of it).

Two independent kinds of protection:

  1. A persistent halt flag (~/.quantos/halt, same Path.home()/.quantos
     convention as the rest of the agent's local state). It is SET
     automatically when an automatic trigger fires — a daily-loss breach
     or `CONSECUTIVE_LOSS_LIMIT` losing trades in a row — and is only
     ever CLEARED by a human deleting the file. The agent never
     auto-clears it. Checked every poll tick.

  2. A concurrent-position cap (max_open_positions). Unlike the halt
     flag this is not persisted — it simply refuses a new entry while
     too many positions are already open and lifts on its own as
     positions close.

Halting refuses ENTRIES only. Exit management (_manage_open_positions,
the trailing SL_M loop) must keep running while halted — halting must
never abandon an open position. The real dead-man protection is that
stops are broker-resident SL_M orders that survive agent death (see the
dead-man note in agent/main.py); this module never flattens anything.

The pure calculations here (realized_pnl_today, consecutive_losses,
positions_mtm, evaluate_halt_triggers) take plain inputs and touch no
files, so they're unit-testable in isolation.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("quantos.agent.risk")

# Persistent halt flag. Its presence = halted; its contents are a
# human-readable "why + when" line for the operator who has to clear it.
HALT_FLAG_PATH = Path.home() / ".quantos" / "halt"

# Losing trades in a row that trip the halt flag automatically.
CONSECUTIVE_LOSS_LIMIT = 3

# NSE trading calendar is IST — "today" for the daily-loss window is an
# IST calendar day, not a UTC one.
IST = timezone(timedelta(hours=5, minutes=30))


# ─── Persistent halt flag ─────────────────────────────────────────────────────

def is_halted() -> bool:
    """True if the persistent halt flag is set."""
    return HALT_FLAG_PATH.exists()


def read_halt_reason() -> str | None:
    """The halt reason line if halted, else None. Never raises — an
    unreadable-but-present flag still counts as halted (fail safe)."""
    if not HALT_FLAG_PATH.exists():
        return None
    try:
        return HALT_FLAG_PATH.read_text().strip() or "halted (no reason recorded)"
    except OSError:
        return "halted (flag unreadable)"


def set_halt(reason: str) -> None:
    """Set the persistent halt flag. Idempotent-safe to call repeatedly —
    the caller is responsible for only notifying once (see is_halted()
    gate in agent/main.py). Never auto-cleared by the agent."""
    HALT_FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(IST).isoformat(timespec="seconds")
    HALT_FLAG_PATH.write_text(f"{stamp} IST — {reason}\n")
    logger.critical("TRADING HALTED — %s (clear manually: delete %s)",
                    reason, HALT_FLAG_PATH)


def clear_halt() -> None:
    """Remove the halt flag. Operator/test use only — the agent itself
    NEVER calls this; a halt is cleared only by a human deleting the
    file. Provided here so ops tooling and tests share one code path."""
    try:
        HALT_FLAG_PATH.unlink()
    except FileNotFoundError:
        pass


# ─── Pure risk calculations ───────────────────────────────────────────────────

def _trade_date(dt: datetime) -> date:
    """IST calendar date a trade's exit timestamp falls on. Aware
    timestamps are converted to IST; naive ones (some broker order
    histories) are taken at face value."""
    if dt.tzinfo is not None:
        return dt.astimezone(IST).date()
    return dt.date()


def realized_pnl_today(trades, *, now: datetime | None = None) -> float:
    """Sum of P&L over closed trades that exited today (IST). `trades` is
    any iterable of objects exposing `.pnl` and `.exit_date` — i.e.
    core.risk.kelly.ClosedTrade, as returned by
    TradeHistoryService.get_trade_history()."""
    now = now or datetime.now(IST)
    today = now.astimezone(IST).date() if now.tzinfo else now.date()
    return sum(t.pnl for t in trades if _trade_date(t.exit_date) == today)


def consecutive_losses(trades) -> int:
    """Number of losing trades at the tail of the (chronological) history.
    Stops at the first win. `trades` items expose `.is_win`."""
    n = 0
    for t in reversed(list(trades)):
        if t.is_win:
            break
        n += 1
    return n


def positions_mtm(open_positions, ltp: dict) -> float:
    """Mark-to-market unrealized P&L across open positions given a
    symbol→last-price map. Positions whose symbol is absent from `ltp`
    are skipped (a missing quote can't be marked). `open_positions` is
    the {signal_id: OpenPosition} dict the agent keeps."""
    total = 0.0
    for pos in open_positions.values():
        price = ltp.get(pos.symbol)
        if price is None:
            continue
        if pos.direction == "BUY":
            total += (price - pos.entry_price) * pos.quantity
        else:  # short
            total += (pos.entry_price - price) * pos.quantity
    return total


def evaluate_halt_triggers(
    *,
    trades,
    open_positions,
    capital: float,
    max_daily_loss_pct: float,
    ltp: dict | None = None,
    consecutive_limit: int = CONSECUTIVE_LOSS_LIMIT,
    now: datetime | None = None,
) -> str | None:
    """Return a human-readable reason if an automatic kill-switch trigger
    has fired, else None. Pure — does NOT touch the flag file (the caller
    sets the flag, so it can notify exactly once).

    Triggers:
      • `consecutive_limit` losing trades in a row.
      • today's day P&L (realized closed-trade P&L + open-position MTM)
        at or below -(max_daily_loss_pct × capital).

    `ltp` (symbol→price) enables the open-position MTM term; omit it for a
    realized-only check (cheaper, and conservative — MTM of a losing open
    position only makes the day look worse, so realized-only can never
    over-halt)."""
    losses = consecutive_losses(trades)
    if losses >= consecutive_limit:
        return f"{losses} consecutive losing trades (limit {consecutive_limit})"

    realized = realized_pnl_today(trades, now=now)
    unrealized = positions_mtm(open_positions, ltp) if ltp else 0.0
    day_pnl = realized + unrealized
    loss_limit = max_daily_loss_pct * capital
    if capital > 0 and day_pnl <= -loss_limit:
        return (
            f"daily loss {day_pnl:,.2f} breached limit -{loss_limit:,.2f} "
            f"({max_daily_loss_pct:.1%} of {capital:,.2f}) "
            f"[realized {realized:,.2f} + open MTM {unrealized:,.2f}]"
        )
    return None


def entry_refusal_reason(open_positions, *, max_open_positions: int) -> str | None:
    """Reason to refuse a NEW entry right now, or None to allow it.

    Checks the persistent halt flag first, then the concurrent-position
    cap. This gates ENTRIES only — exit management is never routed through
    here, so a halted agent keeps trailing and closing its open
    positions."""
    reason = read_halt_reason()
    if reason:
        return f"trading halted ({reason})"
    count = len(open_positions)
    if count >= max_open_positions:
        return f"max open positions reached ({count}/{max_open_positions})"
    return None
