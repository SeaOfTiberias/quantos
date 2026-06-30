"""
QuantOS — Options Strategy Builder
─────────────────────────────────────
US-05b: Constructs the actual option legs for each of the 8 supported
strategy templates, given an option chain snapshot and a directional bias.

Each builder function returns a list of StrategyLeg plus computed
max profit / max loss / breakeven — Claude then wraps this in
market-context rationale (regime, IVR, PCR).
"""

import logging
from datetime import date
from typing import Optional

from core.options.models import (
    OptionChainSnapshot, OptionLeg, OptionType,
    StrategyLeg, StrategyTemplate,
)

logger = logging.getLogger(__name__)


class StrategyBuildError(Exception):
    """Raised when a strategy cannot be constructed from the available chain."""
    pass


def build_strategy(
    template: StrategyTemplate,
    chain: OptionChainSnapshot,
    quantity: int = 1,
) -> tuple[list[StrategyLeg], dict]:
    """
    Build the legs for a given strategy template.

    Returns:
        (legs, metrics) where metrics contains max_profit, max_loss,
        breakeven(s), and net_premium.
    """
    builders = {
        StrategyTemplate.BULL_CALL_SPREAD: _build_bull_call_spread,
        StrategyTemplate.BEAR_PUT_SPREAD:  _build_bear_put_spread,
        StrategyTemplate.IRON_CONDOR:      _build_iron_condor,
        StrategyTemplate.COVERED_CALL:     _build_covered_call,
        StrategyTemplate.CASH_SECURED_PUT: _build_cash_secured_put,
        StrategyTemplate.DEBIT_SPREAD:     _build_bull_call_spread,  # alias
        StrategyTemplate.SHORT_STRANGLE:   _build_short_strangle,
    }

    builder = builders.get(template)
    if not builder:
        raise StrategyBuildError(f"No builder implemented for {template.value}")

    return builder(chain, quantity)


# ─── Strategy builders ─────────────────────────────────────────────────────────

def _build_bull_call_spread(chain: OptionChainSnapshot, qty: int) -> tuple[list[StrategyLeg], dict]:
    """Buy ATM call, sell OTM call above it. Bullish, defined risk."""
    atm = chain.atm_strike()
    calls = sorted(chain.calls(), key=lambda l: l.strike)
    otm_candidates = [c for c in calls if c.strike > atm]
    if not otm_candidates:
        raise StrategyBuildError("No OTM calls available for bull call spread")

    long_leg  = chain.get_leg(atm, OptionType.CALL)
    short_leg_data = otm_candidates[min(2, len(otm_candidates) - 1)]  # 2-3 strikes OTM

    if not long_leg:
        raise StrategyBuildError(f"No call found at ATM strike {atm}")

    legs = [
        StrategyLeg(action="BUY",  option_type=OptionType.CALL,
                    strike=long_leg.strike, premium=long_leg.premium, quantity=qty),
        StrategyLeg(action="SELL", option_type=OptionType.CALL,
                    strike=short_leg_data.strike, premium=short_leg_data.premium, quantity=qty),
    ]

    net_debit = long_leg.premium - short_leg_data.premium
    width = short_leg_data.strike - long_leg.strike

    metrics = {
        "net_premium": -net_debit * qty,
        "max_profit":  (width - net_debit) * qty,
        "max_loss":    net_debit * qty,
        "breakeven":   long_leg.strike + net_debit,
    }
    return legs, metrics


def _build_bear_put_spread(chain: OptionChainSnapshot, qty: int) -> tuple[list[StrategyLeg], dict]:
    """Buy ATM put, sell OTM put below it. Bearish, defined risk."""
    atm = chain.atm_strike()
    puts = sorted(chain.puts(), key=lambda l: -l.strike)
    otm_candidates = [p for p in puts if p.strike < atm]
    if not otm_candidates:
        raise StrategyBuildError("No OTM puts available for bear put spread")

    long_leg = chain.get_leg(atm, OptionType.PUT)
    short_leg_data = otm_candidates[min(2, len(otm_candidates) - 1)]

    if not long_leg:
        raise StrategyBuildError(f"No put found at ATM strike {atm}")

    legs = [
        StrategyLeg(action="BUY",  option_type=OptionType.PUT,
                    strike=long_leg.strike, premium=long_leg.premium, quantity=qty),
        StrategyLeg(action="SELL", option_type=OptionType.PUT,
                    strike=short_leg_data.strike, premium=short_leg_data.premium, quantity=qty),
    ]

    net_debit = long_leg.premium - short_leg_data.premium
    width = long_leg.strike - short_leg_data.strike

    metrics = {
        "net_premium": -net_debit * qty,
        "max_profit":  (width - net_debit) * qty,
        "max_loss":    net_debit * qty,
        "breakeven":   long_leg.strike - net_debit,
    }
    return legs, metrics


def _build_iron_condor(chain: OptionChainSnapshot, qty: int) -> tuple[list[StrategyLeg], dict]:
    """
    Sell OTM call + OTM put, buy further OTM call + put as protection.
    Range-bound strategy — profits if price stays between short strikes.
    """
    atm = chain.atm_strike()
    calls = sorted(chain.calls(), key=lambda l: l.strike)
    puts  = sorted(chain.puts(), key=lambda l: -l.strike)

    otm_calls = [c for c in calls if c.strike > atm]
    otm_puts  = [p for p in puts if p.strike < atm]

    if len(otm_calls) < 2 or len(otm_puts) < 2:
        raise StrategyBuildError("Insufficient OTM strikes for iron condor")

    short_call = otm_calls[1]   # ~2 strikes OTM
    long_call  = otm_calls[min(3, len(otm_calls) - 1)]   # further OTM
    short_put  = otm_puts[1]
    long_put   = otm_puts[min(3, len(otm_puts) - 1)]

    legs = [
        StrategyLeg(action="SELL", option_type=OptionType.CALL,
                    strike=short_call.strike, premium=short_call.premium, quantity=qty),
        StrategyLeg(action="BUY",  option_type=OptionType.CALL,
                    strike=long_call.strike, premium=long_call.premium, quantity=qty),
        StrategyLeg(action="SELL", option_type=OptionType.PUT,
                    strike=short_put.strike, premium=short_put.premium, quantity=qty),
        StrategyLeg(action="BUY",  option_type=OptionType.PUT,
                    strike=long_put.strike, premium=long_put.premium, quantity=qty),
    ]

    net_credit = (
        short_call.premium - long_call.premium
        + short_put.premium - long_put.premium
    )
    call_width = long_call.strike - short_call.strike
    put_width  = short_put.strike - long_put.strike
    max_width  = max(call_width, put_width)

    metrics = {
        "net_premium": net_credit * qty,
        "max_profit":  net_credit * qty,
        "max_loss":    (max_width - net_credit) * qty,
        "breakeven_upper": short_call.strike + net_credit,
        "breakeven_lower": short_put.strike - net_credit,
    }
    return legs, metrics


def _build_covered_call(chain: OptionChainSnapshot, qty: int) -> tuple[list[StrategyLeg], dict]:
    """
    Sell OTM call against existing stock holding (assumed already owned).
    Income strategy. Only the option leg is tracked here — stock position
    is assumed to exist separately in the portfolio.
    """
    atm = chain.atm_strike()
    calls = sorted(chain.calls(), key=lambda l: l.strike)
    otm_calls = [c for c in calls if c.strike > atm]

    if not otm_calls:
        raise StrategyBuildError("No OTM calls available for covered call")

    short_leg_data = otm_calls[min(1, len(otm_calls) - 1)]  # 1 strike OTM

    legs = [
        StrategyLeg(action="SELL", option_type=OptionType.CALL,
                    strike=short_leg_data.strike, premium=short_leg_data.premium, quantity=qty),
    ]

    metrics = {
        "net_premium": short_leg_data.premium * qty,
        "max_profit":  (short_leg_data.strike - chain.spot_price + short_leg_data.premium) * qty,
        "max_loss":    float("-inf"),   # stock downside is theoretically unlimited (own the stock separately)
        "breakeven":   chain.spot_price - short_leg_data.premium,
        "note": "Assumes existing stock holding — option leg only",
    }
    return legs, metrics


def _build_cash_secured_put(chain: OptionChainSnapshot, qty: int) -> tuple[list[StrategyLeg], dict]:
    """Sell OTM put, holding cash to cover assignment. Income / entry strategy."""
    atm = chain.atm_strike()
    puts = sorted(chain.puts(), key=lambda l: -l.strike)
    otm_puts = [p for p in puts if p.strike < atm]

    if not otm_puts:
        raise StrategyBuildError("No OTM puts available for cash-secured put")

    short_leg_data = otm_puts[min(1, len(otm_puts) - 1)]

    legs = [
        StrategyLeg(action="SELL", option_type=OptionType.PUT,
                    strike=short_leg_data.strike, premium=short_leg_data.premium, quantity=qty),
    ]

    metrics = {
        "net_premium": short_leg_data.premium * qty,
        "max_profit":  short_leg_data.premium * qty,
        "max_loss":    (short_leg_data.strike - short_leg_data.premium) * qty,  # if stock goes to 0
        "breakeven":   short_leg_data.strike - short_leg_data.premium,
        "cash_required": short_leg_data.strike * qty * 75,  # approx lot size — adjust per symbol
    }
    return legs, metrics


def _build_short_strangle(chain: OptionChainSnapshot, qty: int) -> tuple[list[StrategyLeg], dict]:
    """Sell OTM call + OTM put, no protection. High premium, undefined risk."""
    atm = chain.atm_strike()
    calls = sorted(chain.calls(), key=lambda l: l.strike)
    puts  = sorted(chain.puts(), key=lambda l: -l.strike)

    otm_calls = [c for c in calls if c.strike > atm]
    otm_puts  = [p for p in puts if p.strike < atm]

    if not otm_calls or not otm_puts:
        raise StrategyBuildError("Insufficient OTM strikes for short strangle")

    short_call = otm_calls[min(2, len(otm_calls) - 1)]
    short_put  = otm_puts[min(2, len(otm_puts) - 1)]

    legs = [
        StrategyLeg(action="SELL", option_type=OptionType.CALL,
                    strike=short_call.strike, premium=short_call.premium, quantity=qty),
        StrategyLeg(action="SELL", option_type=OptionType.PUT,
                    strike=short_put.strike, premium=short_put.premium, quantity=qty),
    ]

    net_credit = short_call.premium + short_put.premium

    metrics = {
        "net_premium": net_credit * qty,
        "max_profit":  net_credit * qty,
        "max_loss":    float("-inf"),   # undefined risk both sides
        "breakeven_upper": short_call.strike + net_credit,
        "breakeven_lower": short_put.strike - net_credit,
    }
    return legs, metrics
