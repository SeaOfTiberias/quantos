"""
QuantOS — Morning Intelligence Brief
─────────────────────────────────────────
US-14: Assembles and sends the 8:30 AM IST morning brief.

Single batched operation (ADR-04) — one Claude call covering:
  1. Market regime classification
  2. Top Darvas/screener candidates for the day
  3. Upcoming event risk (RBI, earnings, index rebalance)
  4. Kelly sizing update (post last close)
  5. Previous day P&L summary

Delivered to WhatsApp by 8:30 AM IST (03:00 UTC).
Archived as JSON to GitHub (via strategy versioning pattern).
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

_claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
MODEL = "claude-sonnet-4-6"


@dataclass
class MorningBriefData:
    """All data inputs assembled before Claude generates the narrative."""
    date:                 date

    # Regime (from US-05)
    regime:               str           # e.g. "TRENDING_BULL"
    regime_confidence:    float
    trend_signal:         str
    vix_signal:           str
    darvas_enabled:       bool
    allowed_strategies:   list[str]

    # Screener top picks (from US-03)
    top_candidates:       list[dict]    # [{symbol, score, rationale}, ...]

    # Event risk (from US-06)
    upcoming_events:      list[dict]    # [{event_type, date, impact, description}, ...]

    # Kelly sizing (from US-07)
    kelly_size_pct:       float
    kelly_method:         str           # "KELLY" | "FIXED_FALLBACK"
    trade_history_count:  int

    # Previous day P&L
    prev_day_pnl:         float = 0.0
    prev_day_trades:      int   = 0
    open_positions:       list[str] = field(default_factory=list)

    # Options context (from US-05b, if available)
    iv_rank:              Optional[float] = None
    pcr:                  Optional[float] = None


@dataclass
class MorningBrief:
    """The assembled morning brief — data + Claude narrative + WhatsApp message."""
    data:                 MorningBriefData
    narrative:            str           # Claude-generated 3-4 sentence summary
    whatsapp_message:     str
    generated_at:         datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


async def generate_morning_brief(data: MorningBriefData) -> MorningBrief:
    """
    Generate the morning intelligence brief from assembled data.
    Single Claude call (ADR-04 batching) for the narrative.
    """
    narrative = await _generate_narrative(data)
    whatsapp_msg = _format_whatsapp(data, narrative)

    return MorningBrief(
        data=data,
        narrative=narrative,
        whatsapp_message=whatsapp_msg,
    )


async def _generate_narrative(data: MorningBriefData) -> str:
    """Ask Claude for a concise morning narrative (batched with all context)."""
    candidates_str = ", ".join(
        f"{c.get('symbol', '?')} ({c.get('score', 0):.0f})"
        for c in data.top_candidates[:5]
    ) or "None identified"

    events_str = ", ".join(
        f"{e.get('description', e.get('event_type', '?'))} on {e.get('event_date', '?')}"
        for e in data.upcoming_events[:3]
    ) or "None in 7-day window"

    prompt = f"""
Write a concise 3-4 sentence morning intelligence brief for a quant trader.
Tone: direct, data-driven, practitioner. No fluff.

## Today's Data ({data.date.strftime('%d %b %Y')})
- Regime: {data.regime} (confidence {data.regime_confidence:.0f}%)
- Trend: {data.trend_signal} | VIX: {data.vix_signal}
- Darvas scanner: {'ENABLED' if data.darvas_enabled else 'GATED (wrong regime)'}
- Top candidates: {candidates_str}
- Event risk: {events_str}
- Position sizing: {data.kelly_size_pct:.1%} of capital ({data.kelly_method})
- Prev day P&L: {'₹' + f'{data.prev_day_pnl:+,.0f}' if data.prev_day_pnl != 0 else 'No trades'}
- Open positions: {', '.join(data.open_positions) or 'None'}

Write the brief now — 3-4 sentences, no headings, no bullets.
""".strip()

    try:
        response = await _claude.messages.create(
            model=MODEL, max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error("Claude morning narrative failed: %s", e)
        return (
            f"Market regime: {data.regime} (confidence {data.regime_confidence:.0f}%). "
            f"Darvas scanner {'active' if data.darvas_enabled else 'gated'}. "
            f"Top candidate: {data.top_candidates[0].get('symbol', 'none') if data.top_candidates else 'none'}. "
            f"Position sizing: {data.kelly_size_pct:.1%}."
        )


def _format_whatsapp(data: MorningBriefData, narrative: str) -> str:
    """Format the full WhatsApp morning brief message."""
    regime_emoji = {
        "TRENDING_BULL": "🟢", "TRENDING_BEAR": "🔴",
        "RANGING": "🟡", "VOLATILE": "🟠", "UNCERTAIN": "⚪",
    }.get(data.regime, "•")

    lines = [
        f"☀️ <b>QuantOS Morning Brief</b>",
        f"_{data.date.strftime('%A, %d %b %Y')}_",
        "━━━━━━━━━━━━━━",
        f"{regime_emoji} <b>{data.regime.replace('_', ' ')}</b> ({data.regime_confidence:.0f}%)",
        f"Trend: {data.trend_signal}  |  VIX: {data.vix_signal}",
        f"Darvas: {'✅ Active' if data.darvas_enabled else '❌ Gated'}",
        "",
    ]

    # Top candidates
    if data.top_candidates:
        lines.append("📋 <b>Top Candidates</b>")
        for i, c in enumerate(data.top_candidates[:5], 1):
            lines.append(f"  {i}. <b>{c.get('symbol', '?')}</b>  score={c.get('score', 0):.0f}")
    else:
        lines.append("📋 <b>Top Candidates:</b> None today")

    lines.append("")

    # Event risk
    if data.upcoming_events:
        lines.append("📅 <b>Event Risk (7d)</b>")
        for e in data.upcoming_events[:3]:
            impact_icon = "🔴" if e.get("impact") == "HIGH" else "🟡"
            lines.append(
                f"  {impact_icon} {e.get('event_date', '?')}: {e.get('description', e.get('event_type', '?'))}"
            )
        lines.append("")

    # Sizing & P&L
    lines += [
        f"💰 <b>Sizing:</b> {data.kelly_size_pct:.1%} ({data.kelly_method})",
    ]
    if data.prev_day_pnl != 0:
        pnl_icon = "✅" if data.prev_day_pnl > 0 else "🔻"
        lines.append(f"{pnl_icon} <b>Prev Day P&L:</b> ₹{data.prev_day_pnl:+,.0f} ({data.prev_day_trades} trade(s))")

    if data.open_positions:
        lines.append(f"📦 <b>Open:</b> {', '.join(data.open_positions)}")

    lines += [
        "",
        "━━━━━━━━━━━━━━",
        f"_{narrative}_",
        "━━━━━━━━━━━━━━",
        "QuantOS · 8:30 AM IST",
    ]

    return "\n".join(lines)
