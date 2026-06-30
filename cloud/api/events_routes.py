"""
QuantOS — Event Calendar API Routes
───────────────────────────────────────
US-06: Endpoints to view upcoming events and manually add earnings dates.
"""

import logging
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from core.events.service import EventFilterService, format_upcoming_events_whatsapp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])

# Shared instance — same one used by the webhook pipeline in main.py
_event_filter = EventFilterService()


class EarningsEntry(BaseModel):
    symbol: str
    earnings_date: date


@router.get("/upcoming")
async def upcoming_events(days_ahead: int = 7):
    """List all events in the next N days."""
    events = _event_filter.calendar.upcoming_events(days_ahead=days_ahead)
    return {
        "days_ahead": days_ahead,
        "count": len(events),
        "events": [
            {
                "event_type":  e.event_type.value,
                "event_date":  e.event_date.isoformat(),
                "impact":      e.impact.value,
                "symbol":      e.symbol,
                "description": e.description,
            }
            for e in events
        ],
        "whatsapp_preview": format_upcoming_events_whatsapp(events, days_ahead),
    }


@router.post("/earnings")
async def add_earnings(entry: EarningsEntry):
    """Manually add a symbol's earnings date to the calendar."""
    _event_filter.calendar.add_earnings(entry.symbol, entry.earnings_date)
    return {
        "symbol": entry.symbol.upper(),
        "earnings_date": entry.earnings_date.isoformat(),
        "status": "added",
    }


@router.get("/check/{symbol}")
async def check_symbol_risk(symbol: str):
    """Check a symbol's current event risk status."""
    result = _event_filter.check(symbol)
    return {
        "symbol": result.symbol,
        "is_blocked": result.is_blocked,
        "override_allowed": result.override_allowed,
        "reason": result.reason,
    }
