"""QuantOS — S8-3 weekly RS-momentum rotation module"""
from core.rotation.ranker import (
    SymbolSeries, RebalancePlan,
    rolling_high_series, build_symbol_series, value_as_of,
    rank_universe, diff_target_basket,
    LOOKBACK_DAYS, TOP_N,
)
from core.rotation.executor import RebalanceResult, run_weekly_rebalance

__all__ = [
    "SymbolSeries", "RebalancePlan",
    "rolling_high_series", "build_symbol_series", "value_as_of",
    "rank_universe", "diff_target_basket",
    "LOOKBACK_DAYS", "TOP_N",
    "RebalanceResult", "run_weekly_rebalance",
]
