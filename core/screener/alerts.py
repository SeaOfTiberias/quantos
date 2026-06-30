"""
QuantOS — Screener Shortlist Formatter
─────────────────────────────────────────
US-03: Formats Claude's ranked candidates into a WhatsApp-ready
morning shortlist message. Scheduled for 8:45 AM IST delivery.
"""

import logging

logger = logging.getLogger(__name__)


def format_shortlist_whatsapp(rankings: list[dict], total_scanned: int) -> str:
    """
    Format ranked candidates as a WhatsApp message.

    Args:
        rankings: list of {symbol, rank, score, rationale} from rank_candidates()
        total_scanned: total candidates that went through the pre-filter,
                       shown for context (e.g. "Top 10 of 47 scanned")
    """
    if not rankings:
        return (
            "📋 *QuantOS Morning Shortlist*\n"
            "━━━━━━━━━━━━━━\n"
            "No qualifying candidates today.\n"
            f"({total_scanned} stocks scanned, none passed filters)"
        )

    lines = [
        "📋 *QuantOS Morning Shortlist*",
        f"Top {len(rankings)} of {total_scanned} scanned",
        "━━━━━━━━━━━━━━",
    ]

    medal = {1: "🥇", 2: "🥈", 3: "🥉"}

    for r in rankings:
        rank_marker = medal.get(r["rank"], f"{r['rank']}.")
        lines.append(
            f"{rank_marker} *{r['symbol']}*  (score: {r['score']:.0f})"
        )
        lines.append(f"   _{r['rationale']}_")

    lines += [
        "━━━━━━━━━━━━━━",
        "QuantOS · Reply symbol for live chart",
    ]

    return "\n".join(lines)


def format_shortlist_summary_line(rankings: list[dict]) -> str:
    """Short one-liner for logging / dashboard display."""
    if not rankings:
        return "No candidates today"
    top3 = ", ".join(r["symbol"] for r in rankings[:3])
    return f"Top {len(rankings)} ranked — leaders: {top3}"
