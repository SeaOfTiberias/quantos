"""
QuantOS — Strategy Chain Analysis API Routes
─────────────────────────────────────────────────
Deterministic chain analysis for a strategy template the human has already
chosen: build its legs from the real option chain, compute real Greeks and
risk/reward. No Claude call, no regime dependency, no algorithmic pick —
see core/options/recommender.py's module docstring for why (disabled
2026-07-25 after Fable's review found the regime-gated Claude recommendation
was worse than no signal, not just unvalidated).
"""

import logging
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.options.models import OptionChainSnapshot, OptionLeg, OptionType, StrategyTemplate
from core.options.recommender import analyse_chain
from core.options.alerts import format_strategy_whatsapp
from core.options.strategy_builder import StrategyBuildError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategy", tags=["strategy"])


class OptionLegInput(BaseModel):
    strike:        float
    option_type:   str   # "CE" or "PE"
    premium:       float
    open_interest: int
    volume:        int
    implied_vol:   float


class StrategyRequest(BaseModel):
    underlying:     str
    spot_price:     float
    expiry:         date
    legs:           list[OptionLegInput]
    iv_rank:        float
    iv_percentile:  float
    pcr:            float
    max_pain:       float
    template:       str   # StrategyTemplate value — human-chosen, not gated by regime


@router.post("/recommend")
async def recommend(request: StrategyRequest):
    """
    Analyse a human-chosen strategy template against the current option
    chain: real legs, real Greeks, real max profit/loss/PoP. No regime
    gating, no AI pick — the template is the caller's choice.
    """
    try:
        template = StrategyTemplate(request.template)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown strategy template: {request.template}")

    chain = OptionChainSnapshot(
        underlying=request.underlying,
        spot_price=request.spot_price,
        expiry=request.expiry,
        legs=[
            OptionLeg(
                strike=leg.strike,
                option_type=OptionType.CALL if leg.option_type == "CE" else OptionType.PUT,
                expiry=request.expiry,
                premium=leg.premium,
                open_interest=leg.open_interest,
                volume=leg.volume,
                implied_vol=leg.implied_vol,
            )
            for leg in request.legs
        ],
        iv_rank=request.iv_rank,
        iv_percentile=request.iv_percentile,
        pcr=request.pcr,
        max_pain=request.max_pain,
    )

    try:
        rec = analyse_chain(chain, template)
    except StrategyBuildError as e:
        raise HTTPException(status_code=422, detail=f"Could not build strategy: {e}")

    return {
        "underlying":  rec.underlying,
        "strategy":    rec.strategy.value,
        "legs": [
            {
                "action":      leg.action,
                "option_type": leg.option_type.value,
                "strike":      leg.strike,
                "premium":     leg.premium,
                "quantity":    leg.quantity,
            }
            for leg in rec.legs
        ],
        "greeks": {
            "delta": rec.net_delta,
            "gamma": rec.net_gamma,
            "theta": rec.net_theta,
            "vega":  rec.net_vega,
        },
        "max_profit":  rec.max_profit,
        "max_loss":    rec.max_loss if rec.max_loss != float("-inf") else None,
        "probability_of_profit": rec.probability_of_profit,
        "whatsapp_preview": format_strategy_whatsapp(rec),
    }
