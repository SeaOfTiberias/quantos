"""
QuantOS — Alpha Attribution vs Nifty 50
──────────────────────────────────────────
US-19: Answers the most important question: "Is QuantOS actually beating
buy-and-hold Nifty?"

Tracks:
  - QuantOS actual P&L from Fyers execution logs (via TradeHistoryService)
  - Nifty 50 total return over the same period
  - Alpha = QuantOS return - Nifty return
  - Sharpe ratio, max drawdown, win rate, avg R:R
  - Weekly Claude narrative: which signals added alpha, which didn't

Equity curve data suitable for charting in the cockpit (US-13).
"""

import logging
import math
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import anthropic

from core import prompts

logger = logging.getLogger(__name__)

_claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
MODEL = "claude-sonnet-4-6"


# ─── Data models ─────────────────────────────────────────────────────────────

@dataclass
class DailyReturn:
    """Single day's return for QuantOS or the benchmark."""
    date:   date
    return_pct: float       # % return
    cumulative: float       # cumulative % return from inception


@dataclass
class AttributionMetrics:
    """Full attribution comparison between QuantOS and Nifty."""
    start_date:        date
    end_date:          date
    trading_days:      int

    # QuantOS performance
    quantos_total_return:   float       # %
    quantos_sharpe:         float
    quantos_max_drawdown:   float       # %
    quantos_win_rate:       float
    quantos_avg_rr:         float       # avg risk/reward ratio

    # Nifty benchmark
    nifty_total_return:     float       # %
    nifty_max_drawdown:     float       # %

    # Alpha
    alpha:                  float       # quantos_total - nifty_total
    alpha_annualised:       float
    information_ratio:      float       # alpha / tracking error

    # Equity curve data
    quantos_curve:          list[DailyReturn] = field(default_factory=list)
    nifty_curve:            list[DailyReturn] = field(default_factory=list)

    @property
    def is_beating_nifty(self) -> bool:
        return self.alpha > 0

    def summary(self) -> str:
        sign = "+" if self.alpha > 0 else ""
        return (
            f"Alpha: {sign}{self.alpha:.2f}% | "
            f"QuantOS: {self.quantos_total_return:+.2f}% | "
            f"Nifty: {self.nifty_total_return:+.2f}% | "
            f"Sharpe: {self.quantos_sharpe:.2f}"
        )


# ─── Core computation ─────────────────────────────────────────────────────────

def compute_attribution(
    trade_pnls: list[dict],             # [{date, pnl_pct, signal_id, strategy}, ...]
    nifty_daily_closes: list[dict],     # [{date, close}, ...]
    initial_capital: float = 500_000,
) -> AttributionMetrics:
    """
    Compute alpha attribution from trade P&L and Nifty benchmark data.

    Args:
        trade_pnls: per-trade P&L records with date and pnl_pct
        nifty_daily_closes: daily Nifty close prices
        initial_capital: starting capital in INR

    Returns:
        AttributionMetrics with full equity curves and alpha stats
    """
    if not trade_pnls or not nifty_daily_closes:
        return _empty_attribution()

    # Build QuantOS daily return curve from trades
    quantos_curve = _build_quantos_curve(trade_pnls)
    nifty_curve   = _build_nifty_curve(nifty_daily_closes)

    if not quantos_curve or not nifty_curve:
        return _empty_attribution()

    # Align dates
    quantos_start = quantos_curve[0].date
    quantos_end   = quantos_curve[-1].date
    nifty_start_close = next(
        (n["close"] for n in nifty_daily_closes if date.fromisoformat(n["date"]) <= quantos_start),
        nifty_daily_closes[0]["close"]
    )
    nifty_end_close = next(
        (n["close"] for n in reversed(nifty_daily_closes) if date.fromisoformat(n["date"]) <= quantos_end),
        nifty_daily_closes[-1]["close"]
    )

    quantos_total = quantos_curve[-1].cumulative
    nifty_total   = (nifty_end_close - nifty_start_close) / nifty_start_close * 100

    alpha = quantos_total - nifty_total
    days  = (quantos_end - quantos_start).days
    alpha_ann = alpha * 365 / max(1, days)

    returns       = [r.return_pct for r in quantos_curve if r.return_pct != 0]
    sharpe        = _sharpe(returns)
    max_dd        = _max_drawdown([r.cumulative for r in quantos_curve])
    win_rate      = sum(1 for t in trade_pnls if t.get("pnl_pct", 0) > 0) / max(1, len(trade_pnls))
    wins          = [t["pnl_pct"] for t in trade_pnls if t.get("pnl_pct", 0) > 0]
    losses        = [abs(t["pnl_pct"]) for t in trade_pnls if t.get("pnl_pct", 0) < 0]
    avg_rr        = (sum(wins) / len(wins)) / (sum(losses) / len(losses)) if wins and losses else 0

    nifty_returns = [r.return_pct for r in nifty_curve if r.return_pct != 0]
    nifty_max_dd  = _max_drawdown([r.cumulative for r in nifty_curve])

    # Information ratio (alpha / tracking error)
    q_returns_aligned = [r.return_pct for r in quantos_curve]
    n_returns_aligned = [r.return_pct for r in nifty_curve[:len(q_returns_aligned)]]
    active_returns = [q - n for q, n in zip(q_returns_aligned, n_returns_aligned)]
    tracking_error = _std(active_returns)
    avg_active = sum(active_returns) / len(active_returns) if active_returns else 0
    info_ratio = avg_active / tracking_error if tracking_error > 0 else 0

    return AttributionMetrics(
        start_date=quantos_start, end_date=quantos_end,
        trading_days=len(quantos_curve),
        quantos_total_return=round(quantos_total, 2),
        quantos_sharpe=round(sharpe, 3),
        quantos_max_drawdown=round(max_dd, 2),
        quantos_win_rate=round(win_rate, 4),
        quantos_avg_rr=round(avg_rr, 3),
        nifty_total_return=round(nifty_total, 2),
        nifty_max_drawdown=round(nifty_max_dd, 2),
        alpha=round(alpha, 2),
        alpha_annualised=round(alpha_ann, 2),
        information_ratio=round(info_ratio, 3),
        quantos_curve=quantos_curve,
        nifty_curve=nifty_curve,
    )


async def generate_alpha_narrative(metrics: AttributionMetrics, trade_pnls: list[dict]) -> str:
    """Generate a weekly Claude narrative on alpha attribution."""
    top_winners = sorted(
        [t for t in trade_pnls if t.get("pnl_pct", 0) > 0],
        key=lambda t: t.get("pnl_pct", 0), reverse=True
    )[:3]
    top_losers = sorted(
        [t for t in trade_pnls if t.get("pnl_pct", 0) < 0],
        key=lambda t: t.get("pnl_pct", 0)
    )[:3]

    winners_str = ", ".join(
        f"{t.get('signal_id', '?')} (+{t.get('pnl_pct', 0):.1f}%)" for t in top_winners
    ) or "none"
    losers_str = ", ".join(
        f"{t.get('signal_id', '?')} ({t.get('pnl_pct', 0):.1f}%)" for t in top_losers
    ) or "none"

    prompt = prompts.render(
        "alpha_attribution_user",
        start_date=metrics.start_date,
        end_date=metrics.end_date,
        quantos_total_return=metrics.quantos_total_return,
        nifty_total_return=metrics.nifty_total_return,
        alpha=metrics.alpha,
        quantos_sharpe=metrics.quantos_sharpe,
        quantos_win_rate=metrics.quantos_win_rate,
        winners_str=winners_str,
        losers_str=losers_str,
    )

    try:
        response = await _claude.messages.create(
            model=MODEL, max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error("Alpha narrative generation failed: %s", e)
        sign = "outperformed" if metrics.is_beating_nifty else "underperformed"
        return (
            f"QuantOS {sign} Nifty by {abs(metrics.alpha):.2f}% this period. "
            f"Win rate {metrics.quantos_win_rate:.0%}, Sharpe {metrics.quantos_sharpe:.2f}. "
            f"{'Continue current approach.' if metrics.is_beating_nifty else 'Review signal quality.'}"
        )


def format_alpha_whatsapp(metrics: AttributionMetrics, narrative: str) -> str:
    """Format alpha attribution report for WhatsApp."""
    icon = "✅" if metrics.is_beating_nifty else "🔻"
    lines = [
        f"📈 QuantOS Alpha Report",
        f"_{metrics.start_date} → {metrics.end_date}_",
        "--------------------",
        f"{icon} Alpha: {metrics.alpha:+.2f}%",
        f"QuantOS: {metrics.quantos_total_return:+.2f}%",
        f"Nifty:   {metrics.nifty_total_return:+.2f}%",
        "--------------------",
        f"Sharpe:    {metrics.quantos_sharpe:.2f}",
        f"Win rate:  {metrics.quantos_win_rate:.0%}",
        f"Avg R:R:   {metrics.quantos_avg_rr:.2f}",
        f"Max DD:    {metrics.quantos_max_drawdown:.1f}%",
        f"Info ratio: {metrics.information_ratio:.2f}",
        "--------------------",
        f"_{narrative}_",
    ]
    return "\n".join(lines)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _build_quantos_curve(trade_pnls: list[dict]) -> list[DailyReturn]:
    by_date: dict[date, float] = {}
    for t in trade_pnls:
        d = date.fromisoformat(t["date"]) if isinstance(t["date"], str) else t["date"]
        by_date[d] = by_date.get(d, 0.0) + t.get("pnl_pct", 0.0)
    curve, cum = [], 0.0
    for d in sorted(by_date):
        cum += by_date[d]
        curve.append(DailyReturn(date=d, return_pct=by_date[d], cumulative=cum))
    return curve


def _build_nifty_curve(closes: list[dict]) -> list[DailyReturn]:
    sorted_closes = sorted(closes, key=lambda c: c["date"])
    if not sorted_closes:
        return []
    base = sorted_closes[0]["close"]
    curve = []
    prev = base
    for c in sorted_closes:
        ret = (c["close"] - prev) / prev * 100 if prev else 0
        cum = (c["close"] - base) / base * 100
        curve.append(DailyReturn(
            date=date.fromisoformat(c["date"]) if isinstance(c["date"], str) else c["date"],
            return_pct=ret, cumulative=cum,
        ))
        prev = c["close"]
    return curve


def _sharpe(returns: list[float], rf: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    std  = _std(returns)
    return (mean - rf) / std * math.sqrt(252) if std > 0 else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def _max_drawdown(cumulative_returns: list[float]) -> float:
    peak = max_dd = 0.0
    for ret in cumulative_returns:
        peak = max(peak, ret)
        max_dd = max(max_dd, peak - ret)
    return max_dd


def _empty_attribution() -> AttributionMetrics:
    today = date.today()
    return AttributionMetrics(
        start_date=today, end_date=today, trading_days=0,
        quantos_total_return=0, quantos_sharpe=0, quantos_max_drawdown=0,
        quantos_win_rate=0, quantos_avg_rr=0, nifty_total_return=0,
        nifty_max_drawdown=0, alpha=0, alpha_annualised=0, information_ratio=0,
    )
