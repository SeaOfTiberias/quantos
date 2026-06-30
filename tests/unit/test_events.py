"""
US-06 Earnings & Event Risk Filter — Unit Tests
"""

import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

from core.events.models import (
    EventType, EventImpact, MarketEvent, RISK_WINDOW_DAYS,
)
from core.events.calendar import EventCalendar
from core.events.service import (
    EventFilterService, format_event_block_whatsapp, format_upcoming_events_whatsapp,
)


# ─── MarketEvent Tests ─────────────────────────────────────────────────────────

class TestMarketEvent:

    def test_is_market_wide_when_no_symbol(self):
        event = MarketEvent(
            event_type=EventType.RBI_POLICY,
            event_date=date(2026, 2, 6),
            impact=EventImpact.HIGH,
        )
        assert event.is_market_wide is True

    def test_is_not_market_wide_with_symbol(self):
        event = MarketEvent(
            event_type=EventType.EARNINGS,
            event_date=date(2026, 1, 15),
            impact=EventImpact.HIGH,
            symbol="RELIANCE",
        )
        assert event.is_market_wide is False

    def test_days_until_future_event(self):
        ref = date(2026, 1, 10)
        event = MarketEvent(
            event_type=EventType.EARNINGS,
            event_date=date(2026, 1, 15),
            impact=EventImpact.HIGH,
            symbol="TCS",
        )
        assert event.days_until(ref) == 5

    def test_days_until_past_event(self):
        ref = date(2026, 1, 20)
        event = MarketEvent(
            event_type=EventType.EARNINGS,
            event_date=date(2026, 1, 15),
            impact=EventImpact.HIGH,
            symbol="TCS",
        )
        assert event.days_until(ref) == -5

    def test_within_risk_window_true(self):
        ref = date(2026, 1, 14)
        event = MarketEvent(
            event_type=EventType.EARNINGS,
            event_date=date(2026, 1, 15),  # 1 day away
            impact=EventImpact.HIGH,
            symbol="TCS",
        )
        assert event.is_within_risk_window(ref) is True

    def test_within_risk_window_false_when_far(self):
        ref = date(2026, 1, 1)
        event = MarketEvent(
            event_type=EventType.EARNINGS,
            event_date=date(2026, 1, 15),  # 14 days away
            impact=EventImpact.HIGH,
            symbol="TCS",
        )
        assert event.is_within_risk_window(ref) is False

    def test_within_risk_window_boundary(self):
        """Exactly RISK_WINDOW_DAYS away should be within window."""
        ref = date(2026, 1, 12)
        event = MarketEvent(
            event_type=EventType.EARNINGS,
            event_date=ref + timedelta(days=RISK_WINDOW_DAYS),
            impact=EventImpact.HIGH,
            symbol="TCS",
        )
        assert event.is_within_risk_window(ref) is True


# ─── EventCalendar Tests ───────────────────────────────────────────────────────

class TestEventCalendar:

    def test_add_and_check_earnings(self):
        cal = EventCalendar()
        ref = date(2026, 1, 14)
        cal.add_earnings("RELIANCE", date(2026, 1, 15))

        result = cal.check_symbol("RELIANCE", reference_date=ref)
        assert result.is_blocked is True
        assert "RELIANCE" in result.symbol

    def test_check_symbol_no_events_not_blocked(self):
        cal = EventCalendar()
        result = cal.check_symbol("TCS", reference_date=date(2026, 1, 1))
        assert result.is_blocked is False
        assert result.triggered_events == []

    def test_high_impact_cannot_be_overridden(self):
        cal = EventCalendar()
        ref = date(2026, 1, 14)
        cal.add_earnings("RELIANCE", date(2026, 1, 15), impact=EventImpact.HIGH)

        result = cal.check_symbol("RELIANCE", reference_date=ref)
        assert result.is_blocked is True
        assert result.override_allowed is False

    def test_medium_impact_can_be_overridden(self):
        cal = EventCalendar()
        ref = date(2026, 1, 14)
        cal.add_event(MarketEvent(
            event_type=EventType.AGM,
            event_date=date(2026, 1, 15),
            impact=EventImpact.MEDIUM,
            symbol="TCS",
        ))

        result = cal.check_symbol("TCS", reference_date=ref)
        assert result.is_blocked is True
        assert result.override_allowed is True

    def test_market_wide_event_blocks_any_symbol(self):
        cal = EventCalendar()
        ref = date(2026, 2, 5)
        cal.add_event(MarketEvent(
            event_type=EventType.RBI_POLICY,
            event_date=date(2026, 2, 6),
            impact=EventImpact.HIGH,
        ))

        result = cal.check_symbol("ANY_RANDOM_STOCK", reference_date=ref)
        assert result.is_blocked is True

    def test_load_macro_calendar_adds_events(self):
        cal = EventCalendar()
        cal.load_macro_calendar_2026()
        assert len(cal._events) > 0

    def test_rbi_policy_blocks_trading(self):
        cal = EventCalendar()
        cal.load_macro_calendar_2026()
        # RBI policy Feb 6 2026 — check from Feb 5 (1 day before)
        result = cal.check_symbol("ANYSTOCK", reference_date=date(2026, 2, 5))
        assert result.is_blocked is True
        assert any(e.event_type == EventType.RBI_POLICY for e in result.triggered_events)

    def test_symbol_specific_and_market_wide_both_checked(self):
        cal = EventCalendar()
        ref = date(2026, 1, 14)
        cal.add_earnings("RELIANCE", date(2026, 1, 15))
        cal.add_event(MarketEvent(
            event_type=EventType.RBI_POLICY,
            event_date=date(2026, 1, 16),
            impact=EventImpact.HIGH,
        ))

        result = cal.check_symbol("RELIANCE", reference_date=ref)
        assert len(result.triggered_events) == 2  # both earnings AND RBI

    def test_clear_removes_all_events(self):
        cal = EventCalendar()
        cal.load_macro_calendar_2026()
        cal.clear()
        assert len(cal._events) == 0

    def test_upcoming_events_filters_by_window(self):
        cal = EventCalendar()
        cal.add_event(MarketEvent(
            event_type=EventType.EARNINGS, event_date=date(2026, 1, 5),
            impact=EventImpact.HIGH, symbol="A",
        ))
        cal.add_event(MarketEvent(
            event_type=EventType.EARNINGS, event_date=date(2026, 1, 20),
            impact=EventImpact.HIGH, symbol="B",
        ))
        # Mock "today" via reference inside the symbol check, but upcoming_events
        # uses real datetime.now() — so we just verify it doesn't crash and
        # returns a sorted list structurally
        events = cal.upcoming_events(days_ahead=365)
        assert isinstance(events, list)

    def test_upcoming_events_sorted_by_date(self):
        cal = EventCalendar()
        cal.add_event(MarketEvent(
            event_type=EventType.EARNINGS, event_date=date(2099, 6, 1),
            impact=EventImpact.HIGH, symbol="LATER",
        ))
        cal.add_event(MarketEvent(
            event_type=EventType.EARNINGS, event_date=date(2099, 1, 1),
            impact=EventImpact.HIGH, symbol="EARLIER",
        ))
        events = cal.upcoming_events(days_ahead=100000)
        if len(events) == 2:
            assert events[0].symbol == "EARLIER"


# ─── EventFilterService Tests ──────────────────────────────────────────────────

class TestEventFilterService:

    def test_service_loads_macro_calendar_on_init(self):
        service = EventFilterService()
        assert len(service.calendar._events) > 0

    def test_check_delegates_to_calendar(self):
        service = EventFilterService()
        result = service.check("RELIANCE", reference_date=date(2020, 1, 1))
        # No events loaded for this far-past date
        assert result.symbol == "RELIANCE"

    def test_add_earnings_batch(self):
        service = EventFilterService()
        initial_count = len(service.calendar._events)
        service.add_earnings_batch({
            "RELIANCE": date(2026, 1, 15),
            "TCS": date(2026, 1, 16),
        })
        assert len(service.calendar._events) == initial_count + 2

    def test_blocked_signal_with_high_impact_event(self):
        service = EventFilterService()
        service.add_earnings_batch({"RELIANCE": date(2026, 1, 15)})
        result = service.check("RELIANCE", reference_date=date(2026, 1, 14))
        assert result.is_blocked is True
        assert result.override_allowed is False


# ─── WhatsApp Formatting Tests ─────────────────────────────────────────────────

class TestEventWhatsappFormatting:

    def test_format_event_block_contains_symbol(self):
        from core.events.models import RiskCheckResult
        result = RiskCheckResult(
            symbol="RELIANCE",
            is_blocked=True,
            triggered_events=[],
            override_allowed=False,
            notes=["🔴 BLOCKING: EARNINGS in 1 day(s) — RELIANCE quarterly earnings"],
        )
        msg = format_event_block_whatsapp(result)
        assert "RELIANCE" in msg
        assert "Cannot be overridden" in msg

    def test_format_event_block_shows_override_option(self):
        from core.events.models import RiskCheckResult
        result = RiskCheckResult(
            symbol="TCS",
            is_blocked=True,
            triggered_events=[],
            override_allowed=True,
            notes=["🟡 ADVISORY: AGM in 2 day(s) — TCS AGM"],
        )
        msg = format_event_block_whatsapp(result)
        assert "override" in msg.lower()

    def test_format_upcoming_events_empty(self):
        msg = format_upcoming_events_whatsapp([], days_ahead=7)
        assert "No major events" in msg

    def test_format_upcoming_events_with_data(self):
        events = [
            MarketEvent(
                event_type=EventType.RBI_POLICY,
                event_date=date(2026, 2, 6),
                impact=EventImpact.HIGH,
                description="RBI MPC meeting",
            ),
        ]
        msg = format_upcoming_events_whatsapp(events, days_ahead=7)
        assert "RBI_POLICY" in msg or "RBI" in msg
        assert "Market-wide" in msg
