"""
QuantOS — Claude Screener Ranker
───────────────────────────────────
US-03: Ranks pre-filtered screener candidates using Claude.

Criteria:
  1. Darvas setup quality — proximity to a clean consolidation breakout
  2. Relative strength vs Nifty — outperformance over recent period
  3. Liquidity — volume profile, ease of entry/exit at size

ADR-04: Single batched Claude call for the whole list, not one per symbol.
"""

import json
import logging
import os

import anthropic

from core.screener.ingest import ScreenerCandidate

logger = logging.getLogger(__name__)

_claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
MODEL = "claude-sonnet-4-6"

MAX_CANDIDATES_TO_CLAUDE = 40   # cap to keep prompt size + cost reasonable


async def rank_candidates(
    candidates: list[ScreenerCandidate],
    nifty_change_pct: float = 0.0,
    top_n: int = 10,
) -> list[dict]:
    """
    Send pre-filtered candidates to Claude for ranking.

    Args:
        candidates: pre-filtered ScreenerCandidate list (already passed
                    apply_pre_filters — keep this list small)
        nifty_change_pct: Nifty's % change over the same lookback period,
                          used to compute relative strength
        top_n: how many ranked results to return

    Returns:
        List of dicts: [{symbol, rank, score, rationale}, ...]
        sorted by score descending, length <= top_n
    """
    if not candidates:
        logger.info("No candidates to rank")
        return []

    # Cap candidates sent to Claude — keeps cost predictable (ADR-04)
    capped = candidates[:MAX_CANDIDATES_TO_CLAUDE]
    if len(candidates) > MAX_CANDIDATES_TO_CLAUDE:
        logger.warning(
            "Capping candidates %d → %d for Claude ranking",
            len(candidates), MAX_CANDIDATES_TO_CLAUDE,
        )

    prompt = _build_ranking_prompt(capped, nifty_change_pct, top_n)

    response = await _claude.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    ranked = _parse_ranking_response(raw)

    logger.info("Ranked %d candidates, returning top %d", len(capped), len(ranked))
    return ranked[:top_n]


def _build_ranking_prompt(
    candidates: list[ScreenerCandidate],
    nifty_change_pct: float,
    top_n: int,
) -> str:
    rows = []
    for c in candidates:
        rs = (c.change_pct - nifty_change_pct) if c.change_pct is not None else None
        rows.append(
            f"- {c.symbol}: price=₹{c.price:,.2f}, change={c.change_pct:+.2f}%, "
            f"rel_strength_vs_nifty={rs:+.2f}%, volume={c.volume:,}, "
            f"rel_vol={c.relative_volume or 'NA'}, "
            f"above_50sma={c.above_50_sma}, above_200sma={c.above_200_sma}, "
            f"rsi={c.rsi or 'NA'}, atr_pct={c.atr_pct or 'NA'}"
        )

    candidates_block = "\n".join(rows)

    return f"""
You are ranking pre-filtered NSE stock candidates for Darvas Box breakout potential.

## Market Context
Nifty 50 change over lookback period: {nifty_change_pct:+.2f}%

## Candidates ({len(candidates)} total)
{candidates_block}

## Ranking Criteria (in priority order)
1. **Darvas setup quality** — stocks near a clean consolidation, holding above
   key moving averages, NOT already extended from a big move
2. **Relative strength vs Nifty** — outperforming the index, not just rising
   with the broad market
3. **Liquidity** — sufficient volume and relative volume surge to suggest
   institutional interest, without being a thin/illiquid mover

## Your Task
Rank the top {top_n} candidates. Penalize stocks that are:
- Already extended >15% from 50-day SMA (chasing risk)
- Showing declining relative volume (interest fading)
- RSI > 75 (overbought, poor risk/reward for new entries)

Return ONLY valid JSON, no preamble:

{{
  "rankings": [
    {{
      "symbol": "<symbol>",
      "rank": <1-{top_n}>,
      "score": <0-100>,
      "rationale": "<one sentence, specific to this stock's data>"
    }}
  ]
}}
""".strip()


_SYSTEM_PROMPT = """
You are QuantOS, an AI screener analyst for NSE Indian equities.
Rank candidates objectively based on the data provided.
Always return valid JSON. Be specific in your rationale — reference
actual numbers from the data, not generic statements.
""".strip()


def _parse_ranking_response(raw: str) -> list[dict]:
    """Parse Claude's JSON ranking response."""
    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        rankings = data.get("rankings", [])
        # Sort by score descending, just in case Claude's order is off
        rankings.sort(key=lambda r: r.get("score", 0), reverse=True)
        return rankings
    except Exception as e:
        logger.error("Failed to parse Claude ranking response: %s | raw: %s",
                     e, raw[:300])
        return []
