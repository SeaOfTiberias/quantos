"""
QuantOS — Event Risk Filter Service
──────────────────────────────────────
US-06: Public interface for checking event risk before signal execution.
Wired into the webhook pipeline (US-01) right after the confluence gate
and before Claude pre-trade analysis — cheapest possible filter first.

Usage:
    from core.events.service import EventFilterService

    service = EventFilterService()
    service.calendar.load_macro_calendar_2026()
    service.calendar.add_earnings("RELIANCE", date(2026, 1, 15))

    result = service.check("RELIANCE")
    if result.is_blocked and not result.override_allowed:
        # reject signal — cannot be overridden
        ...
"""

import logging
from datetime import date
from typing import Optional

from core.events.calendar import EventCalendar
from core.events.models import RiskCheckResult

logger = logging.getLogger(__name__)


class EventFilterService:
    """
    Wraps EventCalendar with a simple check() interface.
    Singleton-style — one instance shared across the app.
    """

    def __init__(self):
        self.calendar = EventCalendar()
        self.calendar.load_macro_calendar_2026()

    def check(self, symbol: str, reference_date: Optional[date] = None) -> RiskCheckResult:
        """
        Check a symbol against the event calendar.
        Returns RiskCheckResult — caller decides how to act on is_blocked.
        """
        return self.calendar.check_symbol(symbol, reference_date)

    def add_earnings_batch(self, earnings: dict[str, date]) -> None:
        """
        Bulk-add earnings dates. Used when ingesting an NSE corporate
        announcements feed or a manually curated earnings calendar.

        Args:
            earnings: dict of {symbol: earnings_date}
        """
        for symbol, edate in earnings.items():
            self.calendar.add_earnings(symbol, edate)
        logger.info("Added %d earnings dates to calendar", len(earnings))


def format_event_block_whatsapp(result: RiskCheckResult) -> str:
    """Format a blocked signal notification for WhatsApp."""
    lines = [
        "⛔ *Signal Blocked — Event Risk*",
        "━━━━━━━━━━━━━━",
        f"Symbol: *{result.symbol}*",
        "",
    ]
    for note in result.notes:
        lines.append(note)

    lines.append("━━━━━━━━━━━━━━")
    if result.override_allowed:
        lines.append("Reply *override* to trade anyway (advisory only)")
    else:
        lines.append("⚠️ Cannot be overridden — high-impact event")

    return "\n".join(lines)


def format_upcoming_events_whatsapp(events: list, days_ahead: int = 7) -> str:
    """Format upcoming events digest for the morning brief."""
    if not events:
        return f"📅 No major events in the next {days_ahead} days."

    lines = [
        f"📅 *Upcoming Events ({days_ahead}d)*",
        "━━━━━━━━━━━━━━",
    ]
    for e in events:
        scope = e.symbol if e.symbol else "Market-wide"
        impact_icon = "🔴" if e.impact.value == "HIGH" else "🟡"
        lines.append(
            f"{impact_icon} {e.event_date.strftime('%d %b')} — "
            f"{scope}: {e.description}"
        )
    return "\n".join(lines)
