"""
QuantOS — Options Intelligence API Routes (US-17, US-18, US-19)
─────────────────────────────────────────────────────────────────────
"""

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/options", tags=["options"])


# ─── US-17: Greeks Live Panel ─────────────────────────────────────────────────

class PositionInput(BaseModel):
    symbol:          str
    strike:          float
    option_type:     str     # "CE" or "PE"
    expiry:          date
    quantity:        int
    entry_premium:   float
    current_premium: float
    implied_vol:     float = 0.18


class GreeksPanelRequest(BaseModel):
    positions:            list[PositionInput]
    spot_prices:          dict[str, float]
    days_to_expiry_map:   dict[str, int]


@router.post("/greeks/panel")
async def get_greeks_panel(request: GreeksPanelRequest):
    """Compute live portfolio Greeks for open options positions."""
    from core.options.live.greeks_panel import compute_live_greeks, format_greeks_panel_whatsapp

    pos_dicts = [
        {
            "symbol":          p.symbol,
            "strike":          p.strike,
            "option_type":     p.option_type,
            "expiry":          p.expiry.isoformat(),
            "quantity":        p.quantity,
            "entry_premium":   p.entry_premium,
            "current_premium": p.current_premium,
            "implied_vol":     p.implied_vol,
        }
        for p in request.positions
    ]

    pg = compute_live_greeks(pos_dicts, request.spot_prices, request.days_to_expiry_map)

    return {
        "net_delta":   pg.net_delta,
        "net_gamma":   pg.net_gamma,
        "net_theta":   pg.net_theta,
        "net_vega":    pg.net_vega,
        "total_pnl":   pg.total_unrealised_pnl,
        "is_theta_positive": pg.is_theta_positive,
        "summary":     pg.summary_line(),
        "positions": [
            {
                "label":     p.position_label,
                "quantity":  p.quantity,
                "delta":     p.delta,
                "gamma":     p.gamma,
                "theta":     p.theta,
                "vega":      p.vega,
                "pnl":       p.unrealised_pnl,
            }
            for p in pg.positions
        ],
        "whatsapp_preview": format_greeks_panel_whatsapp(pg),
    }


# ─── US-18: Options Strategy Backtester ──────────────────────────────────────

class BacktestPeriodInput(BaseModel):
    entry_date:    str
    expiry_date:   str
    underlying:    str = "NIFTY"
    spot_at_entry: float
    spot_at_expiry: float
    iv_rank:       float
    iv:            float = 0.18
    regime:        str


class OptionsBacktestRequest(BaseModel):
    strategy:      str = "iron_condor"
    regime_filter: str = "RANGING"
    iv_rank_min:   float = 60.0
    periods:       list[BacktestPeriodInput]


@router.post("/backtest")
async def run_options_backtest(request: OptionsBacktestRequest):
    """Run a regime-conditioned options strategy backtest."""
    from core.options.backtester import run_regime_conditioned_backtest
    from core.options.models import StrategyTemplate

    try:
        template = StrategyTemplate(request.strategy)
    except ValueError:
        template = StrategyTemplate.IRON_CONDOR

    periods = [p.model_dump() for p in request.periods]
    result = run_regime_conditioned_backtest(
        periods, template, request.regime_filter, request.iv_rank_min,
    )

    return {
        "strategy":          result.strategy.value,
        "regime_filter":     result.regime_filter,
        "iv_rank_min":       result.iv_rank_min,
        "total_periods":     result.total_periods,
        "win_rate":          result.win_rate,
        "avg_pnl_pct":       result.avg_pnl_pct,
        "sharpe":            result.sharpe,
        "max_drawdown_pct":  result.max_drawdown_pct,
        "is_viable":         result.is_viable,
        "overfitting_flag":  result.overfitting_flag,
        "notes":             result.notes,
        "periods": [
            {
                "entry_date":  p.entry_date.isoformat(),
                "regime":      p.regime,
                "iv_rank":     p.iv_rank,
                "pnl":         p.pnl,
                "pnl_pct":     p.pnl_pct,
            }
            for p in result.periods
        ],
    }


# ─── US-19: Alpha Attribution ─────────────────────────────────────────────────

class TradePnlInput(BaseModel):
    date:       str
    pnl_pct:    float
    signal_id:  str = ""
    strategy:   str = ""


class NiftyCloseInput(BaseModel):
    date:  str
    close: float


class AlphaAttributionRequest(BaseModel):
    trade_pnls:          list[TradePnlInput]
    nifty_daily_closes:  list[NiftyCloseInput]
    initial_capital:     float = 500_000
    include_narrative:   bool = True


@router.post("/alpha")
async def compute_alpha(request: AlphaAttributionRequest):
    """
    Compute alpha attribution vs Nifty 50 benchmark.
    Returns equity curves, Sharpe, drawdown, and optional Claude narrative.
    """
    from core.options.alpha_attribution import (
        compute_attribution, generate_alpha_narrative, format_alpha_whatsapp,
    )

    trade_dicts = [t.model_dump() for t in request.trade_pnls]
    nifty_dicts = [{"date": n.date, "close": n.close} for n in request.nifty_daily_closes]

    metrics = compute_attribution(trade_dicts, nifty_dicts, request.initial_capital)

    narrative = ""
    if request.include_narrative:
        narrative = await generate_alpha_narrative(metrics, trade_dicts)

    return {
        "alpha":                  metrics.alpha,
        "alpha_annualised":       metrics.alpha_annualised,
        "quantos_total_return":   metrics.quantos_total_return,
        "nifty_total_return":     metrics.nifty_total_return,
        "sharpe":                 metrics.quantos_sharpe,
        "win_rate":               metrics.quantos_win_rate,
        "max_drawdown_pct":       metrics.quantos_max_drawdown,
        "information_ratio":      metrics.information_ratio,
        "is_beating_nifty":       metrics.is_beating_nifty,
        "narrative":              narrative,
        "summary":                metrics.summary(),
        "equity_curve": {
            "quantos": [{"date": r.date.isoformat(), "cumulative": r.cumulative}
                        for r in metrics.quantos_curve],
            "nifty":   [{"date": r.date.isoformat(), "cumulative": r.cumulative}
                        for r in metrics.nifty_curve],
        },
        "whatsapp_preview": format_alpha_whatsapp(metrics, narrative) if narrative else "",
    }
