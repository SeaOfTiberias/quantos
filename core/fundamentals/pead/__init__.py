"""QuantOS — PEAD (post-earnings-announcement drift) data pipeline.

Phase 1: core.fundamentals.pead.nse_client -- NSE session/fetch client.
          core.fundamentals.pead.xbrl -- per-filing quarterly-PAT extraction.
          core.fundamentals.pead.pipeline -- discovery/dedupe/YoY orchestration.
Gut-check (pre-Phase-2, per a Fable review): core.fundamentals.pead.eq_bhavcopy
          -- NSE equity daily-close fetch/cache.
          core.fundamentals.pead.gutcheck -- forward-return vs surprise
          correlation, NOT a backtest (no costs/sizing/threshold).

No signal generation, entry/exit rules, or full backtest here -- see
memory: quantos-pead-earnings-feasibility for the Phase 2+ scope (out of
bounds for this build).
"""
from core.fundamentals.pead.nse_client import (
    NseNotFoundError,
    NseSession,
    NseSessionError,
    fetch_bytes,
    fetch_financial_results_metadata,
    fetch_xbrl,
)
from core.fundamentals.pead.xbrl import (
    QuarterlyPat,
    XbrlParseError,
    extract_pat_by_context,
    extract_quarterly_pat,
    is_xbrl_available,
)
from core.fundamentals.pead.pipeline import (
    EARLIEST_RELIABLE_START,
    EARLIEST_USABLE_QUARTER_END,
    RECONSTITUTION_COVERAGE_START,
    PeadSignalRow,
    PointInTimeFiling,
    compute_yoy_surprise,
    dedupe_consolidated_preferred,
    discover_filings,
    fetch_and_extract_pat,
    fetch_metadata_month,
    filter_usable,
    restrict_to_universe,
)
from core.fundamentals.pead.eq_bhavcopy import (
    CUTOVER_DATE as EQ_BHAVCOPY_CUTOVER_DATE,
    EqBhavcopyNotAvailable,
    EqCloseRow,
    fetch_and_parse as fetch_and_parse_eq_bhavcopy,
)
from core.fundamentals.pead.gutcheck import (
    ForwardReturn,
    HorizonSummary,
    build_price_index,
    compute_forward_return,
    summarize as summarize_gutcheck,
)

__all__ = [
    "NseNotFoundError",
    "NseSession",
    "NseSessionError",
    "fetch_bytes",
    "fetch_financial_results_metadata",
    "fetch_xbrl",
    "QuarterlyPat",
    "XbrlParseError",
    "extract_pat_by_context",
    "extract_quarterly_pat",
    "is_xbrl_available",
    "EARLIEST_RELIABLE_START",
    "EARLIEST_USABLE_QUARTER_END",
    "RECONSTITUTION_COVERAGE_START",
    "PeadSignalRow",
    "PointInTimeFiling",
    "compute_yoy_surprise",
    "dedupe_consolidated_preferred",
    "discover_filings",
    "fetch_and_extract_pat",
    "fetch_metadata_month",
    "filter_usable",
    "restrict_to_universe",
    "EQ_BHAVCOPY_CUTOVER_DATE",
    "EqBhavcopyNotAvailable",
    "EqCloseRow",
    "fetch_and_parse_eq_bhavcopy",
    "ForwardReturn",
    "HorizonSummary",
    "build_price_index",
    "compute_forward_return",
    "summarize_gutcheck",
]
