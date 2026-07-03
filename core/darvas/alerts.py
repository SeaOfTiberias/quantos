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
        f"📦 Darvas Breakout",
        f"--------------------",
        f"🟢 {result.symbol}",
        f"Price:      INR {p.breakout_price:,.2f}",
        f"Box top:    INR {p.box_top:,.2f}",
        f"Box bottom: INR {p.box_bottom:,.2f}",
        f"Box width:  {p.box_width_pct:.1f}%",
        f"Volume:     {p.volume_ratio:.1f}× avg",
        f"--------------------",
        f"Timeframes: {tfs_str}",
        f"Confluence: {result.confluence_score:.0f}/100",
    ]

    if result.notes:
        lines.append("--------------------")
        for note in result.notes:
            lines.append(f"  {note}")

    lines += [
        "--------------------",
        "Reply execute to trade",
        "Reply skip to ignore",
    ]

    return "\n".join(lines)


def format_watchlist_summary(results: list[MultiTimeframeResult]) -> str:
    """
    Format a watchlist scan summary (top candidates).
    Used by the morning screener (US-03).
    """
    if not results:
        return "📊 QuantOS Morning Scan\nNo Darvas breakouts found today."

    lines = [
        "📊 QuantOS Morning Scan",
        f"Top {len(results)} Darvas setups:",
        "--------------------",
    ]

    for i, r in enumerate(results[:10], 1):
        p = r.primary_signal
        price_str = f"INR {p.breakout_price:,.2f}" if p else "—"
        tfs = "+".join(r.timeframes_triggered)
        lines.append(
            f"{i}. {r.symbol} {price_str}  "
            f"[{tfs}] score={r.confluence_score:.0f}"
        )

    lines.append("--------------------")
    lines.append("QuantOS · Reply symbol name for details")
    return "\n".join(lines)
