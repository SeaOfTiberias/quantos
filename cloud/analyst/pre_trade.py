"""
QuantOS — Claude Pre-Trade Analyst
─────────────────────────────────────
US-04: Before any order executes, route the signal through Claude.
Claude evaluates sector momentum, news sentiment, extension risk,
and returns a confidence score 0–100.

ADR-04: Only called when confluence_score >= MIN_CONFLUENCE (70).
        Regime classification is cached — not recalculated per signal.
"""

import json
import logging
import os
from datetime import datetime, timezone

import anthropic

logger = logging.getLogger(__name__)

_claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
MODEL   = "claude-sonnet-4-6"

# ── Regime cache (ADR-04: 15-min TTL) ────────────────────────────────────────
_regime_cache: dict = {}
REGIME_CACHE_TTL = int(os.getenv("REGIME_CACHE_TTL", "900"))   # 15 min default


async def analyse_signal(signal: dict) -> float:
    """
    Run Claude pre-trade analysis on a signal.

    Args:
        signal: dict with keys symbol, action, price, timeframe,
                strategy, confluence_score, notes, signal_id

    Returns:
        confidence score 0.0–100.0

    Raises:
        Exception if Claude API call fails (caller handles gracefully)
    """
    symbol = signal["symbol"]
    regime = await _get_regime(symbol)

    prompt = _build_prompt(signal, regime)

    response = await _claude.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    logger.debug("[%s] Claude raw response: %s", signal.get("signal_id"), raw[:300])

    score = _parse_confidence_score(raw)
    logger.info("[%s] Pre-trade confidence: %.1f", signal.get("signal_id"), score)
    return score


async def _get_regime(symbol: str) -> dict:
    """
    Get current market regime. Cached for REGIME_CACHE_TTL seconds (ADR-04).
    In production this calls the regime detection engine (US-05).
    """
    now = datetime.now(timezone.utc).timestamp()
    cached = _regime_cache.get("regime")

    if cached and (now - cached["cached_at"]) < REGIME_CACHE_TTL:
        logger.debug("Regime cache hit (age: %.0fs)", now - cached["cached_at"])
        return cached["data"]

    # TODO: call core/regime/classifier.py (US-05) for live regime
    # For now return a structured placeholder that Claude can reason about
    regime = {
        "classification": "TRENDING",      # TRENDING | RANGING | VOLATILE | BEARISH
        "nifty_trend":    "UPTREND",
        "vix_india":      14.2,
        "advance_decline": 1.8,            # ratio — above 1.5 = bullish breadth
        "note":           "Regime from cache placeholder — US-05 will populate this",
    }

    _regime_cache["regime"] = {"data": regime, "cached_at": now}
    logger.info("Regime refreshed: %s (VIX: %.1f)", regime["classification"], regime["vix_india"])
    return regime


def _build_prompt(signal: dict, regime: dict) -> str:
    return f"""
You are the QuantOS pre-trade analyst. Evaluate this trading signal and return a confidence score.

## Signal
- Symbol:          {signal['symbol']}
- Action:          {signal['action']}
- Price:           ₹{signal['price']:,.2f}
- Timeframe:       {signal['timeframe']}
- Strategy:        {signal['strategy']}
- Confluence:      {signal['confluence_score']:.0f}/100
- Notes:           {signal.get('notes', 'None')}

## Market Regime
- Classification:  {regime['classification']}
- Nifty trend:     {regime['nifty_trend']}
- VIX India:       {regime['vix_india']}
- Advance/Decline: {regime['advance_decline']}

## Your Task
Evaluate this signal across these dimensions:
1. **Regime alignment** — Does the signal direction match the current regime?
2. **Extension risk** — Is the stock likely overextended after a big move?
3. **Strategy fit** — Is {signal['strategy']} appropriate for a {regime['classification']} regime?
4. **Risk/reward** — Does this setup offer asymmetric potential?

Return your response as JSON only — no preamble, no explanation outside the JSON:

{{
  "confidence_score": <number 0-100>,
  "regime_alignment": "<STRONG|MODERATE|WEAK|AGAINST>",
  "key_concern": "<single biggest risk in one sentence>",
  "key_strength": "<single biggest edge in one sentence>",
  "recommendation": "<EXECUTE|REDUCE_SIZE|SKIP>"
}}
""".strip()


_SYSTEM_PROMPT = """
You are QuantOS, an AI pre-trade analyst for NSE Indian equities.
Your role is to evaluate trading signals and return structured JSON confidence scores.
Be concise, data-driven, and appropriately conservative on risk.
Never refuse to score — always return valid JSON even if data is incomplete.
""".strip()


def _parse_confidence_score(raw: str) -> float:
    """Extract confidence_score from Claude's JSON response."""
    try:
        # Strip markdown code fences if present
        clean = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        score = float(data["confidence_score"])
        return max(0.0, min(100.0, score))
    except Exception as e:
        logger.warning("Could not parse Claude response as JSON: %s | raw: %s", e, raw[:200])
        # Conservative fallback — don't block pipeline, return mid score
        return 50.0
