"""
QuantOS — Strategy Chain Analysis Formatting
─────────────────────────────────────────────
Formats a deterministic StrategyRecommendation (legs/Greeks/risk-reward for
a human-chosen template) as a WhatsApp/Telegram message. No "AI
recommendation" framing, no confidence score, no regime label — those were
removed 2026-07-25 (see core/options/recommender.py). This just reports
what the chosen strategy's numbers actually are.
"""

from core.options.models import StrategyRecommendation


def format_strategy_whatsapp(rec: StrategyRecommendation) -> str:
    """Format a strategy's computed legs/Greeks/risk-reward for delivery."""

    legs_str = "\n".join(
        f"  {leg.action} {leg.strike:.0f} {leg.option_type.value} @ ₹{leg.premium:.2f}"
        for leg in rec.legs
    )

    max_loss_str = (
        "Unlimited" if rec.max_loss == float("-inf")
        else f"₹{abs(rec.max_loss):,.0f}"
    )

    lines = [
        "📊 *Strategy Chain Analysis*",
        "━━━━━━━━━━━━━━",
        f"*{rec.underlying}* · {rec.strategy.value.replace('_', ' ').title()}",
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
        "No algorithmic recommendation attached — you chose this template.",
        "Reply *execute* to place this trade",
        "Reply *skip* to pass",
    ]

    return "\n".join(lines)
