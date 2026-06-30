"""
QuantOS — Options Data Models
─────────────────────────────────
US-05b: Core data structures for options strategy recommendation.

Covers:
  - Single option leg (strike, type, premium, Greeks)
  - Option chain snapshot (full chain for an underlying + expiry)
  - Strategy templates (the 8 supported strategies)
  - Strategy recommendation output (Claude's pick + full rationale)
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class OptionType(str, Enum):
    CALL = "CE"
    PUT  = "PE"


class StrategyTemplate(str, Enum):
    BULL_CALL_SPREAD   = "bull_call_spread"
    BEAR_PUT_SPREAD    = "bear_put_spread"
    IRON_CONDOR        = "iron_condor"
    COVERED_CALL       = "covered_call"
    CASH_SECURED_PUT   = "cash_secured_put"
    DEBIT_SPREAD       = "debit_spread"
    CALENDAR_SPREAD    = "calendar_spread"
    SHORT_STRANGLE     = "short_strangle"


# ─── Option chain primitives ───────────────────────────────────────────────────

@dataclass
class OptionLeg:
    """A single option contract — one strike, one type, one expiry."""
    strike:           float
    option_type:      OptionType
    expiry:            date
    premium:          float          # last traded price / theoretical price
    open_interest:    int
    volume:           int
    implied_vol:      float          # as a decimal, e.g. 0.18 = 18% IV

    # Greeks — populated by compute_greeks() or pulled from broker if available
    delta:            Optional[float] = None
    gamma:            Optional[float] = None
    theta:            Optional[float] = None   # per-day decay, typically negative
    vega:             Optional[float] = None

    @property
    def is_call(self) -> bool:
        return self.option_type == OptionType.CALL

    @property
    def is_put(self) -> bool:
        return self.option_type == OptionType.PUT


@dataclass
class OptionChainSnapshot:
    """Full option chain for one underlying + expiry at a point in time."""
    underlying:        str
    spot_price:        float
    expiry:             date
    legs:              list[OptionLeg]
    iv_rank:            float           # 0-100, where current IV sits in 1yr range
    iv_percentile:      float           # 0-100, % of days IV was lower than now
    pcr:                float           # Put-Call Ratio (OI based)
    max_pain:           float           # strike with max pain for option writers

    def get_leg(self, strike: float, option_type: OptionType) -> Optional[OptionLeg]:
        for leg in self.legs:
            if leg.strike == strike and leg.option_type == option_type:
                return leg
        return None

    def calls(self) -> list[OptionLeg]:
        return [l for l in self.legs if l.is_call]

    def puts(self) -> list[OptionLeg]:
        return [l for l in self.legs if l.is_put]

    def atm_strike(self) -> float:
        """Find the at-the-money strike (closest to spot)."""
        all_strikes = sorted(set(l.strike for l in self.legs))
        if not all_strikes:
            return self.spot_price
        return min(all_strikes, key=lambda s: abs(s - self.spot_price))

    def strikes_near(self, target: float, count: int = 5) -> list[float]:
        """Get N strikes nearest to a target price, sorted ascending."""
        all_strikes = sorted(set(l.strike for l in self.legs))
        sorted_by_dist = sorted(all_strikes, key=lambda s: abs(s - target))
        return sorted(sorted_by_dist[:count])


# ─── Strategy output ─────────────────────────────────────────────────────────

@dataclass
class StrategyLeg:
    """One leg of a recommended multi-leg strategy."""
    action:        str            # "BUY" or "SELL"
    option_type:   OptionType
    strike:        float
    premium:       float
    quantity:      int = 1        # in lots

    @property
    def cash_flow(self) -> float:
        """Positive = credit received, negative = debit paid."""
        sign = 1 if self.action == "SELL" else -1
        return sign * self.premium * self.quantity


@dataclass
class StrategyRecommendation:
    """
    Full strategy recommendation — Claude's output after analyzing
    regime, IV, PCR, max pain, and the option chain.
    """
    underlying:        str
    strategy:          StrategyTemplate
    legs:              list[StrategyLeg]

    # Aggregate Greeks (sum across all legs, position-weighted)
    net_delta:         float
    net_gamma:         float
    net_theta:         float
    net_vega:          float

    max_profit:        float
    max_loss:           float
    probability_of_profit: float   # 0-100

    rationale:          str
    regime_context:      str
    confidence_score:    float       # 0-100

    @property
    def net_premium(self) -> float:
        """Net cash flow: positive = credit strategy, negative = debit strategy."""
        return sum(leg.cash_flow for leg in self.legs)

    @property
    def is_credit_strategy(self) -> bool:
        return self.net_premium > 0

    @property
    def risk_reward_ratio(self) -> float:
        if self.max_loss == 0:
            return float("inf")
        return abs(self.max_profit / self.max_loss)
