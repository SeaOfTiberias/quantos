"""QuantOS — PEAD (post-earnings-announcement drift) data pipeline, Phase 1.

Phase 1: core.fundamentals.pead.nse_client -- NSE session/fetch client.
          core.fundamentals.pead.xbrl -- per-filing quarterly-PAT extraction.
          core.fundamentals.pead.pipeline -- discovery/dedupe/YoY orchestration.

No signal generation, entry/exit rules, or backtest here -- see memory:
quantos-pead-earnings-feasibility for the Phase 2+ scope (out of bounds
for this build).
"""
from core.fundamentals.pead.nse_client import (
    NseSession,
    NseSessionError,
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

__all__ = [
    "NseSession",
    "NseSessionError",
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
]
