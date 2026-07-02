"""
QuantOS — Backtest Interpreter API Routes
──────────────────────────────────────────
US-11: POST /backtest/analyse — upload TradingView trade list CSV,
get back structured Claude analysis with overfitting assessment.
"""

import logging

from fastapi import APIRouter, UploadFile, HTTPException

from core.backtest.parser import parse_tradingview_csv
from core.backtest.analyst import analyse_backtest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("/analyse")
async def analyse_backtest_csv(
    file: UploadFile,
    strategy_name: str = "Unknown Strategy",
):
    """
    Upload a TradingView strategy tester trade list CSV.
    Returns a Claude-powered analysis with verdict, strengths,
    weaknesses, overfitting assessment, and improvement suggestions.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    content = (await file.read()).decode("utf-8")

    try:
        report = parse_tradingview_csv(content, strategy_name=strategy_name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    analysis = await analyse_backtest(report)

    return {
        "strategy_name": strategy_name,
        "total_trades":  report.overall.total_trades,
        "analysis":      analysis,
        "year_by_year":  {
            str(yr): {
                "trades":         m.total_trades,
                "sharpe":         m.sharpe_ratio,
                "win_rate":       m.win_rate,
                "profit_factor":  m.profit_factor,
            }
            for yr, m in report.by_year.items()
        },
    }
