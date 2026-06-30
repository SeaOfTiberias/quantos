"""
QuantOS — Correlation API Routes
─────────────────────────────────────
US-08: Endpoints for checking correlation between a candidate symbol
and the current open portfolio. Used by the cockpit and the local agent.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from core.risk.correlation import CORRELATION_THRESHOLD

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/correlation", tags=["correlation"])


class CorrelationCheckRequest(BaseModel):
    candidate_symbol:       str
    open_position_symbols:  list[str]
    threshold:              float = CORRELATION_THRESHOLD
    manual_override:        bool = False


@router.post("/check")
async def check_correlation(request: CorrelationCheckRequest):
    """
    Check a candidate symbol's correlation against open positions.

    NOTE: requires a connected broker adapter to fetch price history.
    In the FastAPI app this is wired via the shared CorrelationPortfolioService
    instance configured at startup with the active broker.
    """
    from cloud.api.main import _correlation_service

    if _correlation_service is None:
        return {
            "error": "Correlation service not initialized — no broker connected",
            "candidate_symbol": request.candidate_symbol,
            "is_blocked": False,
        }

    result = await _correlation_service.check_candidate(
        candidate_symbol=request.candidate_symbol,
        open_position_symbols=request.open_position_symbols,
        threshold=request.threshold,
        manual_override=request.manual_override,
    )

    return {
        "candidate_symbol": result.candidate_symbol,
        "is_blocked":        result.is_blocked,
        "max_correlation":   result.max_correlation,
        "correlated_with": [
            {
                "symbol":      c.symbol_b,
                "correlation": c.correlation,
                "data_points": c.data_points,
            }
            for c in result.correlated_with
        ],
        "all_correlations": [
            {
                "symbol":      c.symbol_b,
                "correlation": c.correlation,
                "is_reliable": c.is_reliable,
            }
            for c in result.all_correlations
        ],
        "notes": result.notes,
    }
