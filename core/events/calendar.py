"""
QuantOS — Event Calendar
───────────────────────────
US-06: In-memory event calendar with NSE earnings + macro events.

Data sources (production):
  - NSE corporate announcements API for earnings dates
  - RBI monetary policy calendar (published annually)
  - NSE index rebalancing schedule (quarterly, published in advance)

For now this ships with a manually-curated calendar that's easy to
extend. Sprint 3+ can wire a live NSE corporate announcements feed.
"""

import logging
from datetime import date, datetime, timezone
from typing import Optional

from core.events.models import (
    MarketEvent, EventType, EventImpact, RiskCheckResult, RISK_WINDOW_DAYS,
)

logger = logging.getLogger(__name__)


class EventCalendar:
    """
    Holds all known events and answers risk queries.
    One instance shared across the app — refreshed periodically
    from external sources (NSE feed, RBI calendar).
    """

    def __init__(self):
        self._events: list[MarketEvent] = []

    def add_event(self, event: MarketEvent) -> None:
        self._events.append(event)

    def add_events(self, events: list[MarketEvent]) -> None:
        self._events.extend(events)

    def clear(self) -> None:
        self._events = []

    def load_macro_calendar_2026(self) -> None:
        """
        Seed known 2026 macro events.
        RBI MPC dates are published well in advance — update annually.
        """
        macro_events = [
            MarketEvent(
                event_type=EventType.RBI_POLICY,
                event_date=date(2026, 2, 6),
                impact=EventImpact.HIGH,
                description="RBI Monetary Policy Committee — Feb 2026",
                source="RBI calendar",
            ),
            MarketEvent(
                event_type=EventType.RBI_POLICY,
                event_date=date(2026, 4, 8),
                impact=EventImpact.HIGH,
                description="RBI Monetary Policy Committee — Apr 2026",
                source="RBI calendar",
            ),
            MarketEvent(
                event_type=EventType.RBI_POLICY,
                event_date=date(2026, 6, 5),
                impact=EventImpact.HIGH,
                description="RBI Monetary Policy Committee — Jun 2026",
                source="RBI calendar",
            ),
            MarketEvent(
                event_type=EventType.RBI_POLICY,
                event_date=date(2026, 8, 6),
                impact=EventImpact.HIGH,
                description="RBI Monetary Policy Committee — Aug 2026",
                source="RBI calendar",
            ),
            MarketEvent(
                event_type=EventType.RBI_POLICY,
                event_date=date(2026, 10, 7),
                impact=EventImpact.HIGH,
                description="RBI Monetary Policy Committee — Oct 2026",
                source="RBI calendar",
            ),
            MarketEvent(
                event_type=EventType.RBI_POLICY,
                event_date=date(2026, 12, 4),
                impact=EventImpact.HIGH,
                description="RBI Monetary Policy Committee — Dec 2026",
                source="RBI calendar",
            ),
            MarketEvent(
                event_type=EventType.UNION_BUDGET,
                event_date=date(2027, 2, 1),
                impact=EventImpact.HIGH,
                description="Union Budget 2027",
                source="Govt of India calendar",
            ),
            MarketEvent(
                event_type=EventType.INDEX_REBALANCE,
                event_date=date(2026, 3, 27),
                impact=EventImpact.MEDIUM,
                description="Nifty 50 / Bank Nifty quarterly rebalance",
                source="NSE indices",
            ),
            MarketEvent(
                event_type=EventType.INDEX_REBALANCE,
                event_date=date(2026, 9, 25),
                impact=EventImpact.MEDIUM,
                description="Nifty 50 / Bank Nifty quarterly rebalance",
                source="NSE indices",
            ),
        ]
        self.add_events(macro_events)
        logger.info("Loaded %d macro calendar events for 2026", len(macro_events))

    def add_earnings(
        self,
        symbol: str,
        earnings_date: date,
        impact: EventImpact = EventImpact.HIGH,
        source: str = "manual",
    ) -> None:
        """Add a single symbol's earnings date to the calendar."""
        self.add_event(MarketEvent(
            event_type=EventType.EARNINGS,
            event_date=earnings_date,
            impact=impact,
            symbol=symbol.upper(),
            description=f"{symbol.upper()} quarterly earnings",
            source=source,
        ))

    def check_symbol(
        self,
        symbol: str,
        reference_date: Optional[date] = None,
    ) -> RiskCheckResult:
        """
        Check if a symbol has any blocking events within the risk window.
        Checks both symbol-specific events AND market-wide events.
        """
        ref = reference_date or datetime.now(timezone.utc).date()
        symbol_upper = symbol.upper()

        triggered = []
        for event in self._events:
            if event.is_market_wide or event.symbol == symbol_upper:
                if event.is_within_risk_window(ref):
                    triggered.append(event)

        if not triggered:
            return RiskCheckResult(symbol=symbol_upper, is_blocked=False)

        # HIGH impact events cannot be overridden; MEDIUM can be
        has_high_impact = any(e.impact == EventImpact.HIGH for e in triggered)
        override_allowed = not has_high_impact

        notes = [
            f"{'🔴 BLOCKING' if e.impact == EventImpact.HIGH else '🟡 ADVISORY'}: "
            f"{e.event_type.value} in {e.days_until(ref)} day(s) — {e.description}"
            for e in triggered
        ]

        logger.info(
            "Event risk check: %s → BLOCKED (%d events, override=%s)",
            symbol_upper, len(triggered), override_allowed,
        )

        return RiskCheckResult(
            symbol=symbol_upper,
            is_blocked=True,
            triggered_events=triggered,
            override_allowed=override_allowed,
            notes=notes,
        )

    def upcoming_events(self, days_ahead: int = 7) -> list[MarketEvent]:
        """Get all events in the next N days, sorted by date."""
        ref = datetime.now(timezone.utc).date()
        upcoming = [
            e for e in self._events
            if 0 <= e.days_until(ref) <= days_ahead
        ]
        upcoming.sort(key=lambda e: e.event_date)
        return upcoming
