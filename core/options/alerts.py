"""
QuantOS — Strategy Recommendation Alerts
─────────────────────────────────────────────
US-05b: Formats StrategyRecommendation as a WhatsApp morning brief
delivered by 9:15 AM IST.
"""

from core.options.models import StrategyRecommendation


def format_strategy_whatsapp(rec: StrategyRecommendation) -> str:
    """Format a strategy recommendation for WhatsApp delivery."""

    legs_str = "\n".join(
        f"  {leg.action} {leg.strike:.0f} {leg.option_type.value} @ ₹{leg.premium:.2f}"
        for leg in rec.legs
    )

    max_loss_str = (
        "Unlimited" if rec.max_loss == float("-inf")
        else f"₹{abs(rec.max_loss):,.0f}"
    )

    lines = [
        "🎯 *AI Strategy Recommendation*",
        "━━━━━━━━━━━━━━",
        f"*{rec.underlying}* · {rec.strategy.value.replace('_', ' ').title()}",
        f"Regime: {rec.regime_context}",
        "",
        "*Legs:*",
        legs_str,
        "",
        "*Greeks:*",
        f"  Δ Delta:  {rec.net_delta:+.3f}",
        f"  Γ Gamma:  {rec.net_gamma:+.5f}",
        f"  Θ Theta:  {rec.net_theta:+.2f}/day",
        f"  Vega:     {rec.net_vega:+.2f}",
        "",
        "*Risk/Reward:*",
        f"  Max profit:  ₹{rec.max_profit:,.0f}",
        f"  Max loss:    {max_loss_str}",
        f"  PoP:         {rec.probability_of_profit:.0f}%",
        "━━━━━━━━━━━━━━",
        f"_{rec.rationale}_",
        "━━━━━━━━━━━━━━",
        f"Confidence: {rec.confidence_score:.0f}/100",
        "Reply *execute* to place this trade",
        "Reply *skip* to pass",
    ]

    return "\n".join(lines)
