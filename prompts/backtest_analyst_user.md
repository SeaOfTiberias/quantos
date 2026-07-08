Analyse this TradingView backtest for the "{strategy_name}" strategy.

## Overall Performance
- Total trades:     {total_trades}
- Win rate:         {win_rate:.1%}
- Avg win / loss:   {avg_win_pct:.2f}% / {avg_loss_pct:.2f}%
- Win/loss ratio:   {win_loss_ratio:.2f}
- Profit factor:    {profit_factor:.2f}
- Sharpe ratio:     {sharpe_ratio:.2f}
- Max drawdown:     {max_drawdown_pct:.1f}%
- Net profit:       {net_profit_pct:.1f}%
- Trades/month:     {trades_per_month:.1f}
- Avg bars held:    {avg_bars_held:.0f}

## Year-by-Year
{year_block}

## Walk-Forward Split (first half vs second half)
{wf_block}

## Pre-detected Flags
{flags}

## Your Analysis Task
Return ONLY valid JSON, no preamble:

{{
  "verdict": "<PROMISING|MARGINAL|OVERFIT_RISK|AVOID>",
  "confidence": <0-100>,
  "strengths": ["<strength 1>", "<strength 2>"],
  "weaknesses": ["<weakness 1>", "<weakness 2>"],
  "overfitting_assessment": "<2-3 sentences on whether this looks overfit>",
  "walk_forward_recommendation": "<recommended walk-forward test approach>",
  "suggested_improvements": ["<specific, actionable suggestion 1>", "<suggestion 2>"],
  "narrative": "<3-4 sentence overall summary a practitioner would find useful>"
}}
