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
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from core.events.calendar import EventCalendar
from core.events.models import RiskCheckResult

logger = logging.getLogger(__name__)


class EventFilterService:
    """
    Wraps EventCalendar with a simple check() interface.
    Singleton-style — one instance shared across the app.
    """

    def __init__(self, results_path: Optional[Path] = None, fetcher=None):
        """results_path: the NSE results calendar cache (core/ideas/events.py), loaded now and
        re-read when older than its refresh interval. None = no feed (manual earnings only)."""
        self.calendar = EventCalendar()
        self.calendar.load_macro_calendar_2026()
        self.results_path = results_path
        self._fetcher = fetcher
        self._results_checked: Optional[datetime] = None
        self.results_status = "off"
        if results_path is not None:
            self.refresh_results()

    @classmethod
    def from_env(cls) -> "EventFilterService":
        """The API's instance: the NSE results feed at ~/.quantos/events.json, unless
        QUANTOS_EVENTS_FEED=off (tests/conftest.py sets that so importing the app never calls NSE)."""
        import os
        from core.ideas.events import DEFAULT_PATH
        return cls(results_path=None if os.getenv("QUANTOS_EVENTS_FEED", "").lower() == "off" else DEFAULT_PATH)

    def refresh_results(self, now: Optional[datetime] = None) -> None:
        """(Re)load the NSE results calendar. A failure keeps whatever was loaded before."""
        from core.ideas import events
        now = now or datetime.now()
        self._results_checked = now
        try:
            kw = {"fetcher": self._fetcher} if self._fetcher else {}
            cal = events.refresh(self.results_path, now, **kw)
            results = {s: [date.fromisoformat(d) for d in days] for s, days in (cal.get("results") or {}).items()}
            if results:
                n = self.calendar.replace_results(results)
                self.results_status = f"{n} results dates from NSE, fetched {cal.get('fetched')}"
            if cal.get("error") or not results:
                self.results_status = f"{cal.get('error') or 'empty calendar'}; {self.results_status}"
            logger.info("Event calendar: %s", self.results_status)
        except Exception as e:
            self.results_status = f"load failed: {type(e).__name__}; {self.results_status}"
            logger.error("Results calendar load failed: %s", e)

    def check(self, symbol: str, reference_date: Optional[date] = None) -> RiskCheckResult:
        """
        Check a symbol against the event calendar.
        Returns RiskCheckResult — caller decides how to act on is_blocked.
        """
        from core.ideas.events import MAX_AGE_HOURS
        if self.results_path is not None and (
                self._results_checked is None or datetime.now() - self._results_checked > timedelta(hours=MAX_AGE_HOURS)):
            self.refresh_results()
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
        "⛔ Signal Blocked — Event Risk",
        "--------------------",
        f"Symbol: {result.symbol}",
        "",
    ]
    for note in result.notes:
        lines.append(note)

    lines.append("--------------------")
    if result.override_allowed:
        lines.append("Reply override to trade anyway (advisory only)")
    else:
        lines.append("⚠️ Cannot be overridden — high-impact event")

    return "\n".join(lines)


def format_upcoming_events_whatsapp(events: list, days_ahead: int = 7) -> str:
    """Format upcoming events digest for the morning brief."""
    if not events:
        return f"📅 No major events in the next {days_ahead} days."

    lines = [
        f"📅 Upcoming Events ({days_ahead}d)",
        "--------------------",
    ]
    for e in events:
        scope = e.symbol if e.symbol else "Market-wide"
        impact_icon = "🔴" if e.impact.value == "HIGH" else "🟡"
        lines.append(
            f"{impact_icon} {e.event_date.strftime('%d %b')} — "
            f"{scope}: {e.description}"
        )
    return "\n".join(lines)
