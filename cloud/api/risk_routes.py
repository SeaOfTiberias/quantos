"""
QuantOS — Risk Sizing API Routes
─────────────────────────────────────
US-07: Endpoints for Kelly-based position sizing.
Called by the local agent before placing an order, and by the
cockpit dashboard to show current sizing stats.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from core.risk.kelly import ClosedTrade
from core.risk.trade_history import TradeHistoryService, format_sizing_whatsapp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/risk", tags=["risk"])

# Shared instance — same pattern as event filter service
_trade_history = TradeHistoryService()


class ClosedTradeInput(BaseModel):
    trade_id:    str
    symbol:      str
    entry_price: float
    exit_price:  float
    quantity:    int
    direction:   str
    entry_date:  datetime
    exit_date:   datetime
    strategy:    str = ""


class SizingRequest(BaseModel):
    symbol:   str
    capital:  float


@router.post("/trades/close")
async def record_trade_close(trade: ClosedTradeInput):
    """
    Record a closed trade. Triggers immediate Kelly recalculation.
    Called by the local agent when a broker order is confirmed filled
    and the position is closed.
    """
    closed = ClosedTrade(
        trade_id=trade.trade_id,
        symbol=trade.symbol.upper(),
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        quantity=trade.quantity,
        direction=trade.direction.upper(),
        entry_date=trade.entry_date,
        exit_date=trade.exit_date,
        strategy=trade.strategy,
    )
    sizing = _trade_history.record_closed_trade(closed)

    return {
        "trade_id":   closed.trade_id,
        "pnl":        round(closed.pnl, 2),
        "pnl_pct":    round(closed.pnl_pct * 100, 2),
        "new_sizing": {
            "size_pct":    sizing.size_pct,
            "risk_amount": sizing.risk_amount,
            "method":      sizing.method,
        },
    }


@router.post("/sizing")
async def get_sizing(request: SizingRequest):
    """
    Get current Kelly-based sizing recommendation for a symbol.
    Called by the local agent before placing each new order.
    """
    result = _trade_history.get_current_sizing(request.symbol, request.capital)

    return {
        "symbol":         result.symbol,
        "size_pct":        result.size_pct,
        "risk_amount":     result.risk_amount,
        "method":          result.method,
        "notes":           result.notes,
        "kelly_stats": (
            {
                "sample_size":    result.kelly_stats.sample_size,
                "win_rate":       result.kelly_stats.win_rate,
                "avg_win_pct":    result.kelly_stats.avg_win_pct,
                "avg_loss_pct":   result.kelly_stats.avg_loss_pct,
                "win_loss_ratio": result.kelly_stats.win_loss_ratio,
                "raw_kelly":      result.kelly_stats.raw_kelly,
            }
            if result.kelly_stats else None
        ),
        "whatsapp_preview": format_sizing_whatsapp(result),
    }


@router.get("/stats")
async def get_trade_stats():
    """Overall trade history stats for the cockpit dashboard."""
    return _trade_history.stats_summary()


@router.get("/trades")
async def list_trades(symbol: str | None = None):
    """List trade history, optionally filtered by symbol."""
    trades = _trade_history.get_trade_history(symbol)
    return {
        "count": len(trades),
        "trades": [
            {
                "trade_id":    t.trade_id,
                "symbol":      t.symbol,
                "direction":   t.direction,
                "entry_price": t.entry_price,
                "exit_price":  t.exit_price,
                "quantity":    t.quantity,
                "pnl":         round(t.pnl, 2),
                "pnl_pct":     round(t.pnl_pct * 100, 2),
                "is_win":      t.is_win,
                "strategy":    t.strategy,
                "exit_date":   t.exit_date.isoformat(),
            }
            for t in trades
        ],
    }
