"""
QuantOS — Options Intelligence API Routes (US-17, US-18, US-19)
─────────────────────────────────────────────────────────────────────
"""

import json
import logging
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cloud.api.auth import require_cloud_secret
from cloud.api.db import Signal, get_db
from cloud.api.notifier import (
    deliver_confirmation, format_options_confirmation_message,
    send_options_execution_report, send_options_partial_failure_alert,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/options", tags=["options"])

STRATEGY_SOURCE_TAG_PREFIX = "OPT"


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


# ─── Options Execution (regime/strategy advisor -> real orders) ──────────────
#
# Confirm-before-execute, matching the existing Darvas Telegram flow (NOT
# S8-3 rotation's no-veto carve-out) -- see docs/SPRINT4_BACKLOG.md and the
# quantos-dashboard-polish-next-session design memory. The suggestion is
# generated agent-side (core/options/regime_trigger.py -- only the agent
# holds a connected broker, ADR-01) and POSTed here to persist as a
# PENDING_CONFIRMATION signal + send the Telegram confirm prompt. A human
# "execute"/"skip" reply flows through the EXISTING /webhook/telegram
# handler in main.py unchanged -- it already extracts the signal ID out of
# any replied-to message by regex, regardless of the body. The agent's
# existing GET /signals?status=CONFIRMED poll loop then picks this signal
# up alongside every other kind, branching to multi-leg execution when
# options_detail is present (agent/main.py).
#
# Multi-leg detail is NOT modelled as new typed columns -- it's one JSON
# blob (Signal.options_detail) so every existing consumer of the signals
# table (cockpit, dedup guard, generic confirm/skip/failed routes) keeps
# working unmodified against NULL for every equity signal.


class OptionLegInput(BaseModel):
    action:      str      # "BUY" or "SELL"
    option_type: str      # "CE" or "PE"
    strike:      float
    premium:     float    # premium at suggestion time, for display only
    quantity:    int       # lots
    symbol:      str      # real Fyers tradeable symbol (fyers_symbol_master)
    lot_size:    int


class OptionsSignalRequest(BaseModel):
    underlying:             str
    expiry:                 str    # ISO date
    strategy:               str    # StrategyTemplate value, e.g. "bull_call_spread"
    legs:                   list[OptionLegInput]
    rationale:              str = ""
    regime_context:         str = ""
    max_profit:             float = 0.0
    max_loss:               float = 0.0
    net_premium:            float = 0.0
    probability_of_profit:  float = 50.0


class OptionLegFillInput(BaseModel):
    action:      str
    option_type: str
    strike:      float
    quantity:    int
    symbol:      str
    order_id:    str
    fill_price:  Optional[float] = None


class OptionsExecutedRequest(BaseModel):
    underlying: str
    legs:       list[OptionLegFillInput]


class OptionLegFlattenInput(BaseModel):
    leg:        dict
    flattened:  bool
    order_id:   Optional[str] = None
    error:      Optional[str] = None


class OptionsPartialFailureRequest(BaseModel):
    underlying:      str
    failed_leg:      dict
    error:           str
    flatten_results: list[OptionLegFlattenInput] = []


def _new_options_signal_id() -> str:
    return f"SIG-{STRATEGY_SOURCE_TAG_PREFIX}-{uuid.uuid4().hex[:8].upper()}"


@router.post("/signal")
async def create_options_signal(payload: OptionsSignalRequest,
                                 _auth=Depends(require_cloud_secret)):
    """Called by the local agent when the regime/strategy advisor produces
    a new suggestion (core/options/regime_trigger.py, fired on a regime
    change). Persists PENDING_CONFIRMATION and sends the Telegram confirm
    prompt -- mirrors the TradingView webhook's step 7/8, but for a
    multi-leg options signal instead of a single equity order."""
    signal_id = _new_options_signal_id()
    detail = {
        "expiry":                 payload.expiry,
        "legs":                   [leg.model_dump() for leg in payload.legs],
        "rationale":              payload.rationale,
        "regime_context":         payload.regime_context,
        "max_profit":             payload.max_profit,
        "max_loss":               payload.max_loss,
        "net_premium":            payload.net_premium,
        "probability_of_profit":  payload.probability_of_profit,
    }

    db = await get_db()
    await db.insert_signal(Signal(
        signal_id=signal_id,
        user_id=os.getenv("DEFAULT_USER_ID", "system"),
        symbol=payload.underlying,
        action=payload.strategy,
        price=abs(payload.net_premium),
        timeframe="expiry",
        strategy=payload.strategy,
        confluence_score=100.0,   # not applicable — see rotation_routes.py's identical pattern
        status="PENDING_CONFIRMATION",
        created_at=datetime.now(timezone.utc),
        options_detail=json.dumps(detail),
    ))

    message = format_options_confirmation_message(
        signal_id=signal_id, underlying=payload.underlying, strategy=payload.strategy,
        expiry=payload.expiry, legs=detail["legs"], max_profit=payload.max_profit,
        max_loss=payload.max_loss, net_premium=payload.net_premium,
        probability_of_profit=payload.probability_of_profit,
        rationale=payload.rationale, regime_context=payload.regime_context,
    )
    await deliver_confirmation(signal_id, message)

    logger.info("[%s] Options signal created: %s %s (%d legs)",
                signal_id, payload.underlying, payload.strategy, len(payload.legs))
    return {"signal_id": signal_id, "status": "PENDING_CONFIRMATION"}


@router.post("/signal/{signal_id}/executed")
async def report_options_executed(signal_id: str, payload: OptionsExecutedRequest,
                                   _auth=Depends(require_cloud_secret)):
    """Called by the local agent once every leg of a confirmed spread has
    filled successfully (core/options/executor.py)."""
    db = await get_db()
    await db.mark_executed(signal_id, execution_price=abs(
        sum(leg.fill_price or 0.0 for leg in payload.legs)
    ))
    await send_options_execution_report(
        signal_id=signal_id, underlying=payload.underlying,
        legs=[leg.model_dump() for leg in payload.legs],
    )
    logger.info("[%s] Options spread executed: %d legs filled",
                signal_id, len(payload.legs))
    return {"signal_id": signal_id, "status": "EXECUTED"}


@router.post("/signal/{signal_id}/partial_failure")
async def report_options_partial_failure(signal_id: str, payload: OptionsPartialFailureRequest,
                                          _auth=Depends(require_cloud_secret)):
    """Called by the local agent when a leg was rejected after one or more
    earlier legs of the same spread already filled (core/options/executor.py's
    auto-flatten path). Always sends the loudest alert this project has —
    a naked option position is exactly the unbounded-risk scenario a spread
    exists to prevent, and if the flatten itself also failed there is no
    further automatic recourse."""
    await _set_signal_status(signal_id, "FAILED")
    logger.critical("[%s] Options leg failure (underlying=%s): %s",
                     signal_id, payload.underlying, payload.error)
    await send_options_partial_failure_alert(
        signal_id=signal_id, underlying=payload.underlying,
        failed_leg=payload.failed_leg, error=payload.error,
        flatten_results=[f.model_dump() for f in payload.flatten_results],
    )
    return {"signal_id": signal_id, "status": "FAILED"}


async def _set_signal_status(signal_id: str, new_status: str) -> None:
    db = await get_db()
    await db.update_signal_status(signal_id, new_status)
    logger.info("[%s] Status -> %s", signal_id, new_status)
