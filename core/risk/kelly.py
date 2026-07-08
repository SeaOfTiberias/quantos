"""
QuantOS — Kelly Criterion Position Sizing
────────────────────────────────────────────
US-07: Replaces fixed 2% risk-per-trade with a rolling Kelly fraction
computed from the last N closed trades.

Kelly formula:  f* = W - (1 - W) / R

Where:
  W = win rate (fraction of winning trades)
  R = win/loss ratio (avg win size / avg loss size)
  f* = fraction of capital to risk on the next trade

QuantOS uses HALF-KELLY by default — full Kelly is mathematically optimal
for long-run growth but produces violent equity swings. Half-Kelly trades
some growth for materially lower variance, which is the right tradeoff
for a system with WhatsApp-confirmed (not fully automated) execution.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from core.risk.costs import DEFAULT_COST_MODEL


# ─── Config ──────────────────────────────────────────────────────────────────

MIN_TRADES_FOR_KELLY = 20     # below this, fall back to fixed risk
LOOKBACK_TRADES      = 50     # rolling window size
KELLY_FRACTION       = 0.5    # half-Kelly (0.5) vs full Kelly (1.0)
MIN_SIZE_PCT         = 0.005  # 0.5% floor — never risk less than this
MAX_SIZE_PCT         = 0.04   # 4% ceiling — never risk more than this regardless of Kelly
FALLBACK_SIZE_PCT    = 0.02   # fixed 2% used when insufficient trade history


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class ClosedTrade:
    """A completed trade used as input to the Kelly calculation."""
    trade_id:     str
    symbol:       str
    entry_price:  float
    exit_price:   float
    quantity:     int
    direction:    str            # "BUY" or "SELL"
    entry_date:   datetime
    exit_date:    datetime
    strategy:     str = ""

    @property
    def gross_pnl(self) -> float:
        """P&L before transaction costs — raw price move × quantity."""
        if self.direction == "BUY":
            return (self.exit_price - self.entry_price) * self.quantity
        else:  # SELL / short
            return (self.entry_price - self.exit_price) * self.quantity

    @property
    def costs(self) -> float:
        """Round-trip transaction cost (brokerage/STT/GST/etc.) in INR.

        Computed from the DEFAULT_COST_MODEL (Fyers NSE intraday). Costs are
        deterministic from the stored price/qty/direction fields, so a reloaded
        trade reproduces the identical net figure — nothing extra is persisted.
        """
        return DEFAULT_COST_MODEL.cost_of(
            self.entry_price, self.exit_price, self.quantity, self.direction,
        )

    @property
    def pnl(self) -> float:
        """NET P&L — gross move minus round-trip costs. This is the number that
        feeds Kelly/expectancy, the daily-loss guard, and outcome reporting, so
        every downstream statistic is net-of-cost (S5-1)."""
        return self.gross_pnl - self.costs

    @property
    def gross_pnl_pct(self) -> float:
        """Return % before costs, on entry notional."""
        if self.entry_price == 0:
            return 0.0
        raw = (self.exit_price - self.entry_price) / self.entry_price
        return raw if self.direction == "BUY" else -raw

    @property
    def pnl_pct(self) -> float:
        """NET return %, on entry notional — gross % less costs as a fraction of
        that notional."""
        if self.entry_price == 0 or self.quantity == 0:
            return 0.0
        notional = abs(self.entry_price) * abs(self.quantity)
        return self.gross_pnl_pct - (self.costs / notional)

    @property
    def is_win(self) -> bool:
        """A trade wins only if it clears its own transaction costs."""
        return self.pnl > 0


@dataclass
class KellyStats:
    """Computed statistics feeding the Kelly formula."""
    sample_size:     int
    win_rate:        float          # 0.0–1.0
    avg_win_pct:     float          # average % gain on winning trades
    avg_loss_pct:    float          # average % loss on losing trades (positive number)
    win_loss_ratio:  float          # avg_win_pct / avg_loss_pct
    raw_kelly:       float          # uncapped f* value
    has_sufficient_data: bool

    @property
    def is_positive_edge(self) -> bool:
        """True if the system shows a statistical edge (positive Kelly)."""
        return self.raw_kelly > 0


@dataclass
class SizingResult:
    """Final position sizing recommendation."""
    symbol:           str
    capital:          float
    size_pct:         float         # fraction of capital to risk (post-guardrails)
    risk_amount:      float         # absolute INR amount
    method:           str           # "KELLY" | "FIXED_FALLBACK" | "ZERO_EDGE"
    kelly_stats:      Optional[KellyStats] = None
    notes:            list[str] = field(default_factory=list)
    timestamp:        datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def position_quantity(self, entry_price: float, stop_loss_price: float) -> int:
        """
        Convert risk_amount into a share quantity given entry and stop-loss.
        risk_amount = quantity * abs(entry_price - stop_loss_price)
        """
        risk_per_share = abs(entry_price - stop_loss_price)
        if risk_per_share <= 0:
            return 0
        return int(self.risk_amount / risk_per_share)
