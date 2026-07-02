"""
QuantOS — Strategy Versioning API Routes
──────────────────────────────────────────
US-09: Endpoints to record parameter changes and query strategy history.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from core.versioning.models import BacktestDelta
from core.versioning.service import StrategyVersioningService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategies", tags=["versioning"])

_versioning_service = StrategyVersioningService()


class BacktestDeltaInput(BaseModel):
    sharpe_before:       Optional[float] = None
    sharpe_after:        Optional[float] = None
    win_rate_before:     Optional[float] = None
    win_rate_after:      Optional[float] = None
    max_dd_before:       Optional[float] = None
    max_dd_after:        Optional[float] = None
    total_trades_before: Optional[int]   = None
    total_trades_after:  Optional[int]   = None


class UpdateStrategyRequest(BaseModel):
    strategy_name: str
    parameters:    dict[str, Any]
    rationale:     str = ""
    author:        str = "system"
    backtest_delta: Optional[BacktestDeltaInput] = None
    push_to_github: bool = True


@router.post("/update")
async def update_strategy(request: UpdateStrategyRequest):
    """
    Record a strategy parameter change.
    Auto-versions, generates Claude commit message, pushes to GitHub.
    """
    delta = None
    if request.backtest_delta:
        d = request.backtest_delta
        delta = BacktestDelta(
            sharpe_before=d.sharpe_before, sharpe_after=d.sharpe_after,
            win_rate_before=d.win_rate_before, win_rate_after=d.win_rate_after,
            max_dd_before=d.max_dd_before, max_dd_after=d.max_dd_after,
            total_trades_before=d.total_trades_before,
            total_trades_after=d.total_trades_after,
        )

    version = await _versioning_service.update_strategy(
        strategy_name=request.strategy_name,
        new_params=request.parameters,
        rationale=request.rationale,
        backtest_delta=delta,
        author=request.author,
        push_to_github=request.push_to_github,
    )

    return {
        "strategy_name":  version.strategy_name,
        "version":        version.version,
        "changed_params": version.changed_params,
        "commit_message": version.commit_message,
        "commit_sha":     version.commit_sha,
        "timestamp":      version.timestamp.isoformat(),
    }


@router.get("/{strategy_name}/history")
async def get_history(strategy_name: str):
    """Get full version history for a strategy."""
    versions = _versioning_service.get_history(strategy_name)
    return {
        "strategy_name": strategy_name,
        "version_count": len(versions),
        "versions": [
            {
                "version":        v.version,
                "commit_message": v.commit_message,
                "changed_params": v.changed_params,
                "author":         v.author,
                "timestamp":      v.timestamp.isoformat(),
                "commit_sha":     v.commit_sha,
                "backtest_delta": v.backtest_delta.to_dict() if v.backtest_delta else None,
            }
            for v in versions
        ],
    }


@router.get("/{strategy_name}/current")
async def get_current(strategy_name: str):
    """Get current parameters for a strategy."""
    params = _versioning_service.get_current_params(strategy_name)
    if params is None:
        return {"strategy_name": strategy_name, "parameters": None,
                "message": "Strategy not registered"}
    return {"strategy_name": strategy_name, "parameters": params}


@router.get("/changelog/weekly")
async def weekly_changelog():
    """Get a weekly summary of all strategy changes."""
    return {"changelog": _versioning_service.weekly_changelog()}
