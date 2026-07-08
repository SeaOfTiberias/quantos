You are recommending an options strategy for {underlying}.

## Market Context
- Regime:          {regime_value} (confidence {confidence:.0f}%)
- Trend signal:     {trend_signal}
- VIX signal:       {vix_signal}
- Spot price:       ₹{spot_price:,.2f}
- Days to expiry:   {days_to_expiry}

## Options Context
- IV Rank:          {iv_rank:.0f}/100
- IV Percentile:     {iv_percentile:.0f}/100
- PCR (OI-based):    {pcr:.2f}
- Max Pain:          ₹{max_pain:,.2f}

## Allowed Strategies (regime-gated)
{allowed_strategies}

## Your Task
Pick the ONE strategy from the allowed list above that best fits this
market context. Consider:
- High IV Rank (>60) favours premium-selling strategies (iron_condor,
  short_strangle, covered_call, cash_secured_put)
- Low IV Rank (<40) favours premium-buying strategies (bull_call_spread,
  bear_put_spread, debit_spread)
- PCR > 1.2 suggests put-heavy positioning (potential support); PCR < 0.8
  suggests call-heavy positioning (potential resistance)
- Max pain proximity to spot suggests pin risk near expiry

Return ONLY valid JSON, no preamble:

{{
  "strategy": "<one of: {allowed_strategies}>",
  "confidence": <0-100>,
  "rationale": "<2-3 sentences explaining the pick, referencing the actual
                 regime, IVR, and PCR numbers above>"
}}
