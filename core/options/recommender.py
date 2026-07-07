"""
QuantOS — AI Strategy Recommender
─────────────────────────────────────
US-05b: The core of Epic 7. Claude reads regime classification, IV rank,
PCR, max pain, and the option chain, then recommends the optimal strategy
from 8 templates with full Greeks rationale.

ADR-04: Single batched Claude call per recommendation request — not
per-strategy. Claude picks ONE template, we build it, Claude explains it.
"""

import json
import logging
import os
from datetime import date

import anthropic

from core.options.models import (
    OptionChainSnapshot, StrategyTemplate, StrategyRecommendation, StrategyLeg, OptionType,
)
from core.options.strategy_builder import build_strategy, StrategyBuildError
from core.options.greeks import compute_greeks, estimate_probability_of_profit
from core.regime.models import RegimeResult

logger = logging.getLogger(__name__)

# timeout bounds /strategy/recommend latency — this call runs inside the
# HTTP request; the SDK default waits far longer than the route should (P2-3).
_claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""),
                                   timeout=30.0)
MODEL = "claude-sonnet-4-6"

# Maps regime strategy gating (from core/regime) to our StrategyTemplate enum
_STRATEGY_NAME_MAP = {
    "bull_call_spread":  StrategyTemplate.BULL_CALL_SPREAD,
    "bear_put_spread":   StrategyTemplate.BEAR_PUT_SPREAD,
    "iron_condor":       StrategyTemplate.IRON_CONDOR,
    "covered_call":      StrategyTemplate.COVERED_CALL,
    "cash_secured_put":  StrategyTemplate.CASH_SECURED_PUT,
    "short_strangle":    StrategyTemplate.SHORT_STRANGLE,
}


async def recommend_strategy(
    chain: OptionChainSnapshot,
    regime: RegimeResult,
) -> StrategyRecommendation:
    """
    Main entry point — ask Claude to pick the optimal strategy given
    current market context, then build it and compute full Greeks.

    Args:
        chain: option chain snapshot (spot, IVR, PCR, max pain, all legs)
        regime: current regime classification (from core/regime)

    Returns:
        StrategyRecommendation with legs, Greeks, max profit/loss, rationale
    """
    # Only recommend from strategies the regime allows (gating from US-05)
    allowed = [
        s for s in regime.allowed_strategies
        if s in _STRATEGY_NAME_MAP
    ]
    if not allowed:
        raise ValueError(
            f"No options strategies allowed in current regime: {regime.regime.value}"
        )

    prompt = _build_recommendation_prompt(chain, regime, allowed)

    response = await _claude.messages.create(
        model=MODEL,
        max_tokens=1200,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    choice = _parse_strategy_choice(raw, allowed)

    template = _STRATEGY_NAME_MAP[choice["strategy"]]
    logger.info("Claude recommends: %s for %s (regime=%s)",
                template.value, chain.underlying, regime.regime.value)

    # Build the actual legs from the option chain
    try:
        legs, metrics = build_strategy(template, chain)
    except StrategyBuildError as e:
        logger.error("Failed to build %s: %s — falling back to first allowed strategy",
                     template.value, e)
        # Try the next allowed strategy as fallback
        for fallback_name in allowed:
            fallback_template = _STRATEGY_NAME_MAP[fallback_name]
            try:
                legs, metrics = build_strategy(fallback_template, chain)
                template = fallback_template
                break
            except StrategyBuildError:
                continue
        else:
            raise StrategyBuildError("No strategy could be built from available chain data")

    # Compute aggregate Greeks across all legs
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
        rationale=choice.get("rationale", ""),
        regime_context=f"{regime.regime.value} (confidence {regime.confidence:.0f})",
        confidence_score=choice.get("confidence", 70.0),
    )


def _build_recommendation_prompt(
    chain: OptionChainSnapshot,
    regime: RegimeResult,
    allowed_strategies: list[str],
) -> str:
    days_to_expiry = (chain.expiry - date.today()).days

    return f"""
You are recommending an options strategy for {chain.underlying}.

## Market Context
- Regime:          {regime.regime.value} (confidence {regime.confidence:.0f}%)
- Trend signal:     {regime.trend_signal}
- VIX signal:       {regime.vix_signal}
- Spot price:       ₹{chain.spot_price:,.2f}
- Days to expiry:   {days_to_expiry}

## Options Context
- IV Rank:          {chain.iv_rank:.0f}/100
- IV Percentile:     {chain.iv_percentile:.0f}/100
- PCR (OI-based):    {chain.pcr:.2f}
- Max Pain:          ₹{chain.max_pain:,.2f}

## Allowed Strategies (regime-gated)
{', '.join(allowed_strategies)}

## Your Task
Pick the ONE strategy from the allowed list above that best fits this
market context. Consider:
- High IV Rank (>60) favours premium-selling strategies (iron_condor,
  short_strangle, covered_call, cash_secured_put)
- Low IV Rank (<40) favours premium-buying strategies (bull_call_spread,
  bear_put_spread, debit_spread)
- PCR > 1.2 suggests put-heavy positioning (potential support); PCR < 0.8
  suggests call-heavy positioning (potential resistance)
- Max pain proximity to spot suggests pin risk near expiry

Return ONLY valid JSON, no preamble:

{{
  "strategy": "<one of: {', '.join(allowed_strategies)}>",
  "confidence": <0-100>,
  "rationale": "<2-3 sentences explaining the pick, referencing the actual
                 regime, IVR, and PCR numbers above>"
}}
""".strip()


_SYSTEM_PROMPT = """
You are QuantOS, an AI options strategist for NSE Indian equity and index options.
Recommend strategies based on regime, implied volatility, and positioning data.
Always return valid JSON. Be specific in your rationale — cite actual numbers.
Never recommend a strategy outside the allowed list provided.
""".strip()


def _parse_strategy_choice(raw: str, allowed: list[str]) -> dict:
    """Parse Claude's strategy choice, with safe fallback."""
    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        if data.get("strategy") not in allowed:
            logger.warning(
                "Claude chose '%s' which is not in allowed list %s — using first allowed",
                data.get("strategy"), allowed,
            )
            data["strategy"] = allowed[0]
        return data
    except Exception as e:
        logger.error("Failed to parse Claude strategy choice: %s | raw: %s", e, raw[:300])
        return {
            "strategy": allowed[0],
            "confidence": 50.0,
            "rationale": "Fallback selection — Claude response could not be parsed",
        }


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
