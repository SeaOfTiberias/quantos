"""
QuantOS — Option Strategy Chain Analysis
─────────────────────────────────────────
US-05b was originally "Claude reads regime + chain and recommends a
strategy." Disabled 2026-07-25 after Fable's review: the regime classifier
this recommendation was gated on has failed validation twice (S8-1's
VIX-threshold version, then the IV-minus-RV-spread replacement), and a
fluent Claude-written rationale + numeric confidence score wrapped around
that unvalidated label reads as grounded analysis when it isn't — a
stronger over-trust trigger than a bare unlabeled number, not a weaker one.

This module now does ONLY deterministic chain analysis: given a strategy
TEMPLATE the human has already chosen, build its legs from the real chain
and compute real Greeks/max-profit/max-loss/probability-of-profit. No
Claude call, no regime dependency, no algorithmic "pick", no narrative.
"""

import logging
from datetime import date

from core.options.models import (
    OptionChainSnapshot, StrategyTemplate, StrategyRecommendation, StrategyLeg, OptionType,
)
from core.options.strategy_builder import build_strategy, StrategyBuildError
from core.options.greeks import compute_greeks, estimate_probability_of_profit

logger = logging.getLogger(__name__)


def analyse_chain(
    chain: OptionChainSnapshot,
    template: StrategyTemplate,
) -> StrategyRecommendation:
    """
    Build the given strategy template's legs from the real option chain and
    compute its actual Greeks, max profit/loss, and probability of profit.
    The template is a human choice, passed in — this function makes no
    strategy pick of its own.

    Raises StrategyBuildError if the requested template can't be built from
    the supplied chain (e.g. missing strikes).
    """
    legs, metrics = build_strategy(template, chain)

    net_delta, net_gamma, net_theta, net_vega = _aggregate_greeks(legs, chain)

    days_to_expiry = (chain.expiry - date.today()).days
    pop = _estimate_pop(legs, metrics, chain, days_to_expiry)

    return StrategyRecommendation(
        underlying=chain.underlying,
        strategy=template,
        legs=legs,
        net_delta=net_delta,
        net_gamma=net_gamma,
        net_theta=net_theta,
        net_vega=net_vega,
        max_profit=metrics.get("max_profit", 0.0),
        max_loss=metrics.get("max_loss", 0.0),
        probability_of_profit=pop,
    )


def _aggregate_greeks(
    legs: list[StrategyLeg],
    chain: OptionChainSnapshot,
) -> tuple[float, float, float, float]:
    """
    Compute net position Greeks by looking up each leg's Greeks from the
    chain (if present) or computing via Black-Scholes as fallback.
    """
    days_to_expiry = max(1, (chain.expiry - date.today()).days)
    net_delta = net_gamma = net_theta = net_vega = 0.0

    for sl in legs:
        chain_leg = chain.get_leg(sl.strike, sl.option_type)
        if chain_leg and chain_leg.delta is not None:
            d, g, t, v = chain_leg.delta, chain_leg.gamma, chain_leg.theta, chain_leg.vega
        else:
            iv = chain_leg.implied_vol if chain_leg else 0.18
            greeks = compute_greeks(
                spot=chain.spot_price, strike=sl.strike,
                days_to_expiry=days_to_expiry, implied_vol=iv,
                option_type=sl.option_type,
            )
            d, g, t, v = greeks.delta, greeks.gamma, greeks.theta, greeks.vega

        sign = 1 if sl.action == "BUY" else -1
        net_delta += sign * d * sl.quantity
        net_gamma += sign * g * sl.quantity
        net_theta += sign * t * sl.quantity
        net_vega  += sign * v * sl.quantity

    return (round(net_delta, 4), round(net_gamma, 6),
            round(net_theta, 4), round(net_vega, 4))


def _estimate_pop(
    legs: list[StrategyLeg],
    metrics: dict,
    chain: OptionChainSnapshot,
    days_to_expiry: int,
) -> float:
    """
    Estimate probability of profit. Uses the single breakeven for
    directional strategies, or averages both breakevens for range strategies.
    """
    avg_iv = sum(
        (chain.get_leg(l.strike, l.option_type).implied_vol
         if chain.get_leg(l.strike, l.option_type) else 0.18)
        for l in legs
    ) / len(legs) if legs else 0.18

    if "breakeven" in metrics:
        is_bullish = any(l.option_type == OptionType.CALL and l.action == "BUY" for l in legs)
        return estimate_probability_of_profit(
            spot=chain.spot_price, breakeven=metrics["breakeven"],
            days_to_expiry=max(1, days_to_expiry), implied_vol=avg_iv,
            is_above_breakeven_profitable=is_bullish,
        )

    if "breakeven_upper" in metrics and "breakeven_lower" in metrics:
        # Range strategy — PoP = probability of landing between the breakevens
        prob_below_upper = estimate_probability_of_profit(
            spot=chain.spot_price, breakeven=metrics["breakeven_upper"],
            days_to_expiry=max(1, days_to_expiry), implied_vol=avg_iv,
            is_above_breakeven_profitable=False,
        )
        prob_above_lower = estimate_probability_of_profit(
            spot=chain.spot_price, breakeven=metrics["breakeven_lower"],
            days_to_expiry=max(1, days_to_expiry), implied_vol=avg_iv,
            is_above_breakeven_profitable=True,
        )
        # Probability of being inside the range (rough approximation)
        return round(max(0.0, prob_below_upper + prob_above_lower - 100), 1)

    return 50.0
