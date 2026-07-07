"""
QuantOS — Strategy Recommendation API Routes
─────────────────────────────────────────────────
US-05b: Endpoint to request an AI strategy recommendation for an underlying.
Pulls the current regime (cached, ADR-04) and a supplied option chain,
then asks Claude to pick and explain the optimal strategy.
"""

import logging
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.options.models import OptionChainSnapshot, OptionLeg, OptionType
from core.options.recommender import recommend_strategy
from core.options.alerts import format_strategy_whatsapp
from core.options.strategy_builder import StrategyBuildError
from cloud.api.regime_routes import get_synced_regime

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


@router.post("/recommend")
async def recommend(request: StrategyRequest):
    """
    Get an AI strategy recommendation for an underlying given its
    current option chain and market context.

    Uses the cached regime (US-05) to determine which strategies are
    allowed, then asks Claude to pick the best fit and explain why.
    """
    regime = get_synced_regime()
    if regime is None:
        raise HTTPException(
            status_code=503,
            detail="Regime not available yet — waiting for the local agent's next sync "
                   "(agent/main.py runs RegimeService and POSTs to /regime/sync)",
        )

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
        rec = await recommend_strategy(chain, regime)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
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
        "rationale":   rec.rationale,
        "regime_context": rec.regime_context,
        "confidence_score": rec.confidence_score,
        "whatsapp_preview": format_strategy_whatsapp(rec),
    }
