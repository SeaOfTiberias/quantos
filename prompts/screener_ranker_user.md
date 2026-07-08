You are ranking pre-filtered NSE stock candidates for Darvas Box breakout potential.

## Market Context
Nifty 50 change over lookback period: {nifty_change_pct:+.2f}%

## Candidates ({n_candidates} total)
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
