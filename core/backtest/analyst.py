"""
QuantOS — Claude Backtest Analyst
─────────────────────────────────────
US-11: Takes a BacktestReport (from parser.py) and asks Claude to:
  - Identify which market conditions the strategy underperforms in
  - Flag parameter overfitting risk (Sharpe degradation in second half)
  - Suggest walk-forward test windows
  - Return a structured analysis report
"""

import json
import logging
import os

import anthropic

from core.backtest.parser import BacktestReport, BacktestMetrics
from core import prompts

logger = logging.getLogger(__name__)

_claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
MODEL = "claude-sonnet-4-6"


async def analyse_backtest(report: BacktestReport) -> dict:
    """
    Send a BacktestReport to Claude for analysis.

    Returns a structured analysis dict with:
      - verdict: "PROMISING" | "MARGINAL" | "OVERFIT_RISK" | "AVOID"
      - confidence: 0-100
      - strengths: list of what the strategy does well
      - weaknesses: list of identified issues
      - overfitting_assessment: detailed overfitting analysis
      - walk_forward_recommendation: suggested test windows
      - suggested_improvements: concrete parameter suggestions
      - narrative: full prose summary
    """
    prompt = _build_analysis_prompt(report)

    response = await _claude.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=prompts.load("backtest_analyst_system"),
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    return _parse_analysis(raw, report)


def _build_analysis_prompt(report: BacktestReport) -> str:
    o = report.overall

    # Year-by-year breakdown
    year_lines = []
    for yr, m in sorted(report.by_year.items()):
        year_lines.append(
            f"  {yr}: {m.total_trades} trades | Sharpe {m.sharpe_ratio:.2f} | "
            f"WR {m.win_rate:.0%} | PF {m.profit_factor:.2f}"
        )
    year_block = "\n".join(year_lines) if year_lines else "  Not enough data for yearly split"

    # Walk-forward split
    wf_block = "Not available (< 10 trades total)"
    if report.first_half and report.second_half:
        f, s = report.first_half, report.second_half
        wf_block = (
            f"  First half:  {f.total_trades} trades | Sharpe {f.sharpe_ratio:.2f} | "
            f"WR {f.win_rate:.0%} | PF {f.profit_factor:.2f}\n"
            f"  Second half: {s.total_trades} trades | Sharpe {s.sharpe_ratio:.2f} | "
            f"WR {s.win_rate:.0%} | PF {s.profit_factor:.2f}"
        )

    flags = "\n".join(f"  - {n}" for n in report.notes) or "  None detected"

    return prompts.render(
        "backtest_analyst_user",
        strategy_name=report.strategy_name,
        total_trades=o.total_trades,
        win_rate=o.win_rate,
        avg_win_pct=o.avg_win_pct,
        avg_loss_pct=o.avg_loss_pct,
        win_loss_ratio=o.win_loss_ratio,
        profit_factor=o.profit_factor,
        sharpe_ratio=o.sharpe_ratio,
        max_drawdown_pct=o.max_drawdown_pct,
        net_profit_pct=o.net_profit_pct,
        trades_per_month=o.trades_per_month,
        avg_bars_held=o.avg_bars_held,
        year_block=year_block,
        wf_block=wf_block,
        flags=flags,
    )


def _parse_analysis(raw: str, report: BacktestReport) -> dict:
    """Parse Claude's analysis, with safe fallback."""
    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)

        # Ensure required fields exist
        data.setdefault("verdict", "MARGINAL")
        data.setdefault("confidence", 50)
        data.setdefault("strengths", [])
        data.setdefault("weaknesses", [])
        data.setdefault("overfitting_assessment", "Insufficient data for assessment")
        data.setdefault("walk_forward_recommendation",
                        "Recommend minimum 3-year out-of-sample test")
        data.setdefault("suggested_improvements", [])
        data.setdefault("narrative", "Analysis unavailable")

        # Attach pre-computed stats for reference
        data["computed_stats"] = {
            "total_trades":     report.overall.total_trades,
            "sharpe":           report.overall.sharpe_ratio,
            "win_rate":         report.overall.win_rate,
            "profit_factor":    report.overall.profit_factor,
            "max_drawdown_pct": report.overall.max_drawdown_pct,
            "has_degradation":  report.has_degradation,
            "is_overfit_risk":  report.overall.is_overfit_risk,
        }

        return data

    except Exception as e:
        logger.error("Failed to parse Claude backtest analysis: %s | raw: %s", e, raw[:300])
        return {
            "verdict": "MARGINAL",
            "confidence": 0,
            "strengths": [],
            "weaknesses": ["Analysis parsing failed"],
            "overfitting_assessment": "Unable to assess",
            "walk_forward_recommendation": "Run full walk-forward test manually",
            "suggested_improvements": [],
            "narrative": "Claude analysis could not be parsed. Review raw metrics manually.",
            "computed_stats": {},
        }
