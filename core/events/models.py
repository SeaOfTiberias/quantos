"""
QuantOS — Event Risk Models
─────────────────────────────
US-06: Data structures for earnings and macro event risk filtering.

Two event categories:
  1. Symbol-specific: quarterly earnings, AGM, board meetings
  2. Market-wide: RBI policy, index rebalancing, budget, Fed decisions

A signal is paused if it falls within RISK_WINDOW_DAYS of either type.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Optional


RISK_WINDOW_DAYS = 3   # days before/after event to pause trading


class EventType(str, Enum):
    EARNINGS          = "EARNINGS"
    AGM                = "AGM"
    BOARD_MEETING      = "BOARD_MEETING"
    RBI_POLICY         = "RBI_POLICY"
    UNION_BUDGET       = "UNION_BUDGET"
    INDEX_REBALANCE    = "INDEX_REBALANCE"
    FED_DECISION       = "FED_DECISION"
    OTHER_MACRO        = "OTHER_MACRO"


class EventImpact(str, Enum):
    HIGH    = "HIGH"      # always pause (earnings, RBI, budget)
    MEDIUM  = "MEDIUM"    # pause unless explicitly overridden
    LOW     = "LOW"       # advisory only, does not block


@dataclass
class MarketEvent:
    """A single scheduled event (earnings or macro)."""
    event_type:   EventType
    event_date:   date
    impact:       EventImpact
    symbol:       Optional[str] = None    # None = market-wide event
    description:  str = ""
    source:       str = ""                # e.g. "NSE corporate announcements"

    @property
    def is_market_wide(self) -> bool:
        return self.symbol is None

    def days_until(self, reference: Optional[date] = None) -> int:
        ref = reference or datetime.now(timezone.utc).date()
        return (self.event_date - ref).days

    def is_within_risk_window(self, reference: Optional[date] = None) -> bool:
        return abs(self.days_until(reference)) <= RISK_WINDOW_DAYS


@dataclass
class RiskCheckResult:
    """Result of checking a symbol against the event calendar."""
    symbol:           str
    is_blocked:       bool
    triggered_events:  list[MarketEvent] = field(default_factory=list)
    override_allowed: bool = True   # HIGH impact events cannot be overridden
    notes:            list[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        if not self.is_blocked:
            return "No event risk detected"
        descriptions = [
            f"{e.event_type.value} on {e.event_date.isoformat()}"
            f"{f' ({e.symbol})' if e.symbol else ' (market-wide)'}"
            for e in self.triggered_events
        ]
        return "; ".join(descriptions)
