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

import anthropic

logger = logging.getLogger(__name__)

_claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
MODEL   = "claude-sonnet-4-6"


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
    Get current market regime, synced from the local agent's live
    RegimeService (core/regime/service.py, run by agent/main.py since it's
    the one process with a connected broker — ADR-01) via
    POST /regime/sync -> cloud/api/regime_routes.py. That module owns the
    real caching/staleness logic (ADR-04: 15-min TTL); this function is
    just an adapter to the dict shape _build_prompt() expects.

    Falls back to an explicitly UNKNOWN regime — rather than the old
    hardcoded "TRENDING/UPTREND" stub — if the agent has never synced or
    its last sync is stale, so Claude is told plainly when regime data
    can't be trusted instead of being fed confident-looking fake data.
    """
    from cloud.api.regime_routes import get_synced_regime

    result = get_synced_regime()
    if result is None:
        return {
            "classification":     "UNKNOWN",
            "nifty_trend":        "UNKNOWN",
            "vix_signal":         "UNKNOWN",
            "breadth_signal":     "UNKNOWN",
            "confidence":         0,
            "allowed_strategies": [],
            "note": "No regime synced from the local agent yet — treat regime "
                    "alignment as unknown, don't penalize or reward based on it.",
        }

    return {
        "classification":     result.regime.value,
        "nifty_trend":        result.trend_signal,
        "vix_signal":         result.vix_signal,
        "breadth_signal":     result.breadth_signal,
        "confidence":         result.confidence,
        "allowed_strategies": result.allowed_strategies,
    }


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
- Classification:      {regime['classification']}
- Nifty trend signal:  {regime['nifty_trend']}
- VIX signal:          {regime['vix_signal']}
- Breadth signal:      {regime['breadth_signal']}
- Regime confidence:   {regime['confidence']}
- Strategies allowed in this regime: {', '.join(regime['allowed_strategies']) or 'none'}
{f"- Note: {regime['note']}" if regime.get('note') else ""}

## Your Task
Evaluate this signal across these dimensions:
1. **Regime alignment** — Does the signal direction match the current regime? If the regime
   is UNKNOWN, treat this dimension as neutral — don't penalize or reward for it.
2. **Extension risk** — Is the stock likely overextended after a big move?
3. **Strategy fit** — Is {signal['strategy']} appropriate given the regime's allowed strategies above?
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
