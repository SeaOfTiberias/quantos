"""QuantOS — Risk Management (Kelly Sizing, Correlation)"""
from core.risk.kelly import (
    ClosedTrade, KellyStats, SizingResult,
    MIN_TRADES_FOR_KELLY, LOOKBACK_TRADES, KELLY_FRACTION,
    MIN_SIZE_PCT, MAX_SIZE_PCT, FALLBACK_SIZE_PCT,
)
from core.risk.kelly_calculator import compute_kelly_stats, calculate_position_size
from core.risk.trade_history import TradeHistoryService, format_sizing_whatsapp
from core.risk.correlation import (
    CorrelationResult, PortfolioCheckResult,
    CORRELATION_THRESHOLD, MIN_DATA_POINTS, LOOKBACK_DAYS,
    daily_returns, pearson_correlation, compute_correlation, check_portfolio_correlation,
)
from core.risk.correlation_service import (
    CorrelationPortfolioService,
    format_correlation_block_whatsapp, format_portfolio_correlation_matrix,
)

__all__ = [
    "ClosedTrade", "KellyStats", "SizingResult",
    "MIN_TRADES_FOR_KELLY", "LOOKBACK_TRADES", "KELLY_FRACTION",
    "MIN_SIZE_PCT", "MAX_SIZE_PCT", "FALLBACK_SIZE_PCT",
    "compute_kelly_stats", "calculate_position_size",
    "TradeHistoryService", "format_sizing_whatsapp",
    "CorrelationResult", "PortfolioCheckResult",
    "CORRELATION_THRESHOLD", "MIN_DATA_POINTS", "LOOKBACK_DAYS",
    "daily_returns", "pearson_correlation", "compute_correlation", "check_portfolio_correlation",
    "CorrelationPortfolioService",
    "format_correlation_block_whatsapp", "format_portfolio_correlation_matrix",
]
