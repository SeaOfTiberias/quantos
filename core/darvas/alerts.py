"""
QuantOS — Darvas Scanner Alerts
────────────────────────────────
Formats MultiTimeframeResult into WhatsApp messages
and hooks into the cloud scheduler for periodic scanning.
"""

import logging
from core.darvas.box import MultiTimeframeResult, DarvasSignal

logger = logging.getLogger(__name__)


def format_signal_alert(result: MultiTimeframeResult) -> str:
    """
    Format a MultiTimeframeResult as a WhatsApp-ready message.
    Called after a confluence score >= 70 is detected.
    """
    p = result.primary_signal
    if not p:
        return f"QuantOS: {result.symbol} signal (score {result.confluence_score:.0f})"

    tf_emoji = {"1d": "📅", "1h": "⏱️", "15m": "⚡"}
    tfs_str = "  ".join(
        f"{tf_emoji.get(tf, '•')} {tf.upper()}"
        for tf in result.timeframes_triggered
    )

    lines = [
        f"📦 <b>Darvas Breakout</b>",
        f"━━━━━━━━━━━━━━",
        f"🟢 <b>{result.symbol}</b>",
        f"Price:      ₹{p.breakout_price:,.2f}",
        f"Box top:    ₹{p.box_top:,.2f}",
        f"Box bottom: ₹{p.box_bottom:,.2f}",
        f"Box width:  {p.box_width_pct:.1f}%",
        f"Volume:     {p.volume_ratio:.1f}× avg",
        f"━━━━━━━━━━━━━━",
        f"Timeframes: {tfs_str}",
        f"Confluence: <b>{result.confluence_score:.0f}/100</b>",
    ]

    if result.notes:
        lines.append("━━━━━━━━━━━━━━")
        for note in result.notes:
            lines.append(f"  {note}")

    lines += [
        "━━━━━━━━━━━━━━",
        "Reply <b>execute</b> to trade",
        "Reply <b>skip</b> to ignore",
    ]

    return "\n".join(lines)


def format_watchlist_summary(results: list[MultiTimeframeResult]) -> str:
    """
    Format a watchlist scan summary (top candidates).
    Used by the morning screener (US-03).
    """
    if not results:
        return "📊 <b>QuantOS Morning Scan</b>\nNo Darvas breakouts found today."

    lines = [
        "📊 <b>QuantOS Morning Scan</b>",
        f"Top {len(results)} Darvas setups:",
        "━━━━━━━━━━━━━━",
    ]

    for i, r in enumerate(results[:10], 1):
        p = r.primary_signal
        price_str = f"₹{p.breakout_price:,.2f}" if p else "—"
        tfs = "+".join(r.timeframes_triggered)
        lines.append(
            f"{i}. <b>{r.symbol}</b> {price_str}  "
            f"[{tfs}] score={r.confluence_score:.0f}"
        )

    lines.append("━━━━━━━━━━━━━━")
    lines.append("QuantOS · Reply symbol name for details")
    return "\n".join(lines)
