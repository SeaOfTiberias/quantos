"""
QuantOS — Market Regime Classifier
────────────────────────────────────
US-05: Classifies the current NSE market regime using:
  - Nifty 50 trend (EMA crossover + slope)
  - India VIX level + trend
  - Advance / Decline ratio (market breadth)
  - Bank Nifty relative strength

Regime outputs:
  TRENDING_BULL  — Darvas breakouts green-lit, full position size
  TRENDING_BEAR  — Only short signals, reduce size
  RANGING        — Avoid breakouts; Iron Condor / mean-reversion favoured
  VOLATILE       — Reduce all position sizes 50%, options strategies only
  UNCERTAIN      — Insufficient data; human review required

ADR-04: Regime is cached for 15 minutes. Not recalculated per signal.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ─── Regime enum ─────────────────────────────────────────────────────────────

class Regime(str, Enum):
    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    RANGING       = "RANGING"
    VOLATILE      = "VOLATILE"
    UNCERTAIN     = "UNCERTAIN"


# ─── Strategy gating map ─────────────────────────────────────────────────────
# Which strategies are allowed in each regime (US-05b extension point)

STRATEGY_GATE: dict[Regime, list[str]] = {
    Regime.TRENDING_BULL: [
        "darvas_breakout",
        "bull_call_spread",
        "covered_call",
        "momentum_long",
    ],
    Regime.TRENDING_BEAR: [
        "darvas_short",
        "bear_put_spread",
        "momentum_short",
    ],
    Regime.RANGING: [
        "iron_condor",
        "short_strangle",
        "mean_reversion",
        "covered_call",
    ],
    Regime.VOLATILE: [
        "iron_condor",      # only if IV rank is very high
        "cash_secured_put", # small size
    ],
    Regime.UNCERTAIN: [],   # nothing fires
}

# Position size multiplier per regime
SIZE_MULTIPLIER: dict[Regime, float] = {
    Regime.TRENDING_BULL: 1.0,
    Regime.TRENDING_BEAR: 0.75,
    Regime.RANGING:       0.75,
    Regime.VOLATILE:      0.50,
    Regime.UNCERTAIN:     0.0,
}


# ─── Input data classes ───────────────────────────────────────────────────────

@dataclass
class NiftyData:
    """Nifty 50 metrics for regime classification."""
    ltp:             float
    ema_20:          float          # 20-period EMA
    ema_50:          float          # 50-period EMA
    ema_200:         float          # 200-period EMA (daily)
    slope_5d:        float          # % change over last 5 days
    atr_14:          float          # 14-period ATR (daily)
    atr_pct:         float          # ATR as % of price


@dataclass
class VIXData:
    """India VIX metrics."""
    current:         float
    ma_10:           float          # 10-day moving average
    trend:           str            # "RISING" | "FALLING" | "FLAT"
    percentile_52w:  float          # 0–100, where current VIX sits in 52w range


@dataclass
class BreadthData:
    """NSE market breadth metrics."""
    advance_count:   int
    decline_count:   int
    unchanged_count: int = 0

    @property
    def ad_ratio(self) -> float:
        if self.decline_count == 0:
            return float(self.advance_count)
        return self.advance_count / self.decline_count

    @property
    def breadth_pct(self) -> float:
        """% of stocks advancing."""
        total = self.advance_count + self.decline_count + self.unchanged_count
        return (self.advance_count / total * 100) if total > 0 else 50.0


@dataclass
class RegimeInputs:
    """All inputs needed for regime classification."""
    nifty:       NiftyData
    vix:         VIXData
    breadth:     BreadthData
    timestamp:   datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    bank_nifty_rs: Optional[float] = None  # Bank Nifty relative strength vs Nifty


# ─── Output ──────────────────────────────────────────────────────────────────

@dataclass
class RegimeResult:
    """Full regime classification output."""
    regime:            Regime
    confidence:        float          # 0–100
    allowed_strategies: list[str]
    size_multiplier:   float
    timestamp:         datetime

    # Detailed signal breakdown
    trend_signal:      str = ""      # BULL / BEAR / NEUTRAL
    vix_signal:        str = ""      # LOW / ELEVATED / HIGH / EXTREME
    breadth_signal:    str = ""      # STRONG / NEUTRAL / WEAK
    notes:             list[str] = field(default_factory=list)

    @property
    def is_tradeable(self) -> bool:
        return self.regime != Regime.UNCERTAIN and self.size_multiplier > 0

    @property
    def darvas_enabled(self) -> bool:
        return "darvas_breakout" in self.allowed_strategies

    def allows_strategy(self, strategy: str) -> bool:
        return strategy in self.allowed_strategies

    def summary(self) -> str:
        return (
            f"Regime: {self.regime.value} | "
            f"Confidence: {self.confidence:.0f} | "
            f"Size: {self.size_multiplier:.0%} | "
            f"Darvas: {'✅' if self.darvas_enabled else '❌'}"
        )
