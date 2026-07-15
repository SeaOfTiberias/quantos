"""
QuantOS — Claude Cockpit Analyst Chat
────────────────────────────────────────
Freeform Q&A for the cockpit dashboard, backed by the same server-held
ANTHROPIC_API_KEY pattern as pre_trade.py — never called directly from the
browser (a prior cockpit build did exactly that with no key, which could
never work and would have exposed a key client-side if "fixed" naively).

Context is built from the same live-state accessors the rest of the cloud
API already trusts (regime, synced positions, recent signals) rather than
a hardcoded fake state, so answers reflect what's actually happening.

Daily message cap (CHAT_DAILY_LIMIT) is a blunt but real cost/abuse guard:
this endpoint is public (a browser can't hold the cloud secret — Vite
inlines VITE_ env vars into the public JS bundle), so nothing yet stops a
caller who finds the URL from spamming it. The cap bounds worst-case spend
regardless of what auth layer eventually sits in front of it.
"""

import logging
import os
import time
from datetime import datetime, timezone

import anthropic

from cloud.api.metrics import record_claude
from core import prompts

logger = logging.getLogger(__name__)

_claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""), timeout=30.0)
MODEL = "claude-sonnet-4-6"

CHAT_DAILY_LIMIT = int(os.getenv("ANALYST_CHAT_DAILY_LIMIT", "60"))
MAX_MESSAGE_CHARS = 500

# date (ISO) -> count of chat calls that day. Separate from cloud/api/metrics'
# combined Claude spend tracking so this cap is easy to reason about on its own.
_chat_calls_today: dict[str, int] = {}


class ChatLimitExceeded(Exception):
    """Raised when the daily chat message cap has been hit."""


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _check_and_increment_daily_cap() -> None:
    day = _today()
    count = _chat_calls_today.get(day, 0)
    if count >= CHAT_DAILY_LIMIT:
        raise ChatLimitExceeded(f"Daily analyst chat limit ({CHAT_DAILY_LIMIT}) reached.")
    _chat_calls_today[day] = count + 1


async def ask_analyst(message: str) -> str:
    """
    Answer one cockpit chat message using live regime/positions/signals
    context. Raises ChatLimitExceeded if the daily cap is hit (caller
    returns this to the user as a friendly rejection, not a 500).
    """
    _check_and_increment_daily_cap()

    context = await _build_context()
    system = prompts.render("analyst_chat_system", context=context)

    started = time.perf_counter()
    response = None
    try:
        response = await _claude.messages.create(
            model=MODEL,
            max_tokens=400,
            system=system,
            messages=[{"role": "user", "content": message[:MAX_MESSAGE_CHARS]}],
        )
    finally:
        usage = getattr(response, "usage", None) if response is not None else None
        record_claude(
            (time.perf_counter() - started) * 1000.0,
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
        )

    text_blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    return "\n".join(text_blocks) if text_blocks else "No response generated."


async def _build_context() -> str:
    from cloud.api.db import get_db
    from cloud.api.positions_routes import get_synced_positions
    from cloud.api.regime_routes import get_synced_regime

    lines = []

    regime = get_synced_regime()
    if regime is None:
        lines.append("Regime: unknown (agent has not synced, or sync is stale)")
    else:
        lines.append(
            f"Regime: {regime.regime.value} (confidence {regime.confidence:.0f}%, "
            f"trend={regime.trend_signal}, vix={regime.vix_signal}, "
            f"allowed strategies={', '.join(regime.allowed_strategies) or 'none'})"
        )

    positions = get_synced_positions()
    if not positions:
        lines.append("Open positions: none")
    else:
        pos_lines = [
            f"{p['symbol']} qty={p['qty']} entry={p['entry']} ltp={p['ltp']} "
            f"pnl={p['pnl']:+.0f} ({p['pnl_pct']:+.2f}%) strategy={p['strategy']}"
            for p in positions
        ]
        lines.append("Open positions:\n  " + "\n  ".join(pos_lines))

    try:
        db = await get_db()
        recent = await db.fetch_recent_signals(limit=5)
    except Exception as e:
        logger.error("Failed to fetch recent signals for chat context: %s", e)
        recent = []
    if not recent:
        lines.append("Recent signals: none today")
    else:
        sig_lines = [
            f"{s['symbol']} {s['action']} @ {s['price']} status={s['status']} "
            f"confluence={s.get('confluence_score')}"
            for s in recent
        ]
        lines.append("Recent signals:\n  " + "\n  ".join(sig_lines))

    return "\n\n".join(lines)
