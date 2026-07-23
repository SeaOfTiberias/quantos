"""QuantOS — Options VRP (variance risk premium) backtest build.

Phase 1: core.options.vrp.bhavcopy — NSE bhavcopy fetch/parse/cache pipeline.
Phase 2: core.options.vrp.strikes — entry-cycle + strike reconstruction.
Phase 3: core.options.vrp.simulator — pooled per-trade P&L (gross, no costs).
"""
from core.options.vrp.bhavcopy import (
    BhavcopyNotAvailable,
    BhavcopyOptionRow,
    CUTOVER_DATE,
    fetch_and_parse,
    fetch_raw,
    load_cached_range,
    parse_bhavcopy_zip,
    url_for,
)
from core.options.vrp.simulator import (
    BacktestStats,
    StrangleTrade,
    compute_stats,
    simulate,
)
from core.options.vrp.strikes import (
    EntryCycle,
    StrangleSelection,
    StrikeSelection,
    build_entry_cycles,
    select_strangle,
    synthetic_forward,
)

__all__ = [
    "BhavcopyNotAvailable",
    "BhavcopyOptionRow",
    "CUTOVER_DATE",
    "fetch_and_parse",
    "fetch_raw",
    "load_cached_range",
    "parse_bhavcopy_zip",
    "url_for",
    "EntryCycle",
    "StrangleSelection",
    "StrikeSelection",
    "build_entry_cycles",
    "select_strangle",
    "synthetic_forward",
    "BacktestStats",
    "StrangleTrade",
    "compute_stats",
    "simulate",
]
