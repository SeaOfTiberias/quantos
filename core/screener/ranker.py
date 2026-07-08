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
from core import prompts

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
        system=prompts.load("screener_ranker_system"),
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

    return prompts.render(
        "screener_ranker_user",
        nifty_change_pct=nifty_change_pct,
        n_candidates=len(candidates),
        candidates_block=candidates_block,
        top_n=top_n,
    )


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
