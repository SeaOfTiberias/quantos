"""
QuantOS — PEAD Phase 1: Point-in-Time Quarterly-PAT Pipeline
────────────────────────────────────────────────────────────────
Orchestrates core.fundamentals.pead.nse_client (fetch) and
core.fundamentals.pead.xbrl (parse) into a point-in-time table of
(symbol, disclosure date, quarter, PAT, YoY surprise) for the Nifty 500,
mirroring core/options/vrp/bhavcopy.py's fetch/cache/dedupe shape.

Two independent local caches, both gitignored under data_cache/ like VRP's:
  - metadata_raw/{YYYYMM}.json  -- one NSE bulk `corporates-financial-results`
                                    response per calendar month, ALL
                                    NSE-listed companies (filtered to Nifty
                                    500 downstream, not at fetch time, so
                                    widening the universe later never needs
                                    a re-fetch).
  - xbrl_raw/{seqNumber}.xml    -- each retained filing's raw XBRL, keyed by
                                    NSE's own `seqNumber` (stable per filing).

**Real gotcha found and worked around**: `format == "New"` does NOT
guarantee a usable `xbrl` link -- confirmed live on a real RELIANCE filing
(broadcast 2018-06-13, `format: "New"`, `xbrl` still the dead placeholder).
`is_xbrl_available()` in xbrl.py checks the URL string itself, never the
`format` field, for exactly this reason.

**No same-file YoY comparative** (see xbrl.py's docstring) -- YoY surprise
is computed here by joining two independently-fetched filings for the same
symbol, same quarter-of-year, one calendar year apart.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, Optional

from core.fundamentals.pead.nse_client import (
    NseSession,
    fetch_financial_results_metadata,
    fetch_xbrl,
)
from core.fundamentals.pead.xbrl import (
    XbrlParseError,
    extract_quarterly_pat,
    is_xbrl_available,
)

logger = logging.getLogger(__name__)

DEFAULT_METADATA_CACHE_DIR = Path("data_cache/pead_nse/metadata_raw")
DEFAULT_XBRL_CACHE_DIR = Path("data_cache/pead_nse/xbrl_raw")

# Confirmed live 2026-07-23: format flips to "New"/parseable XBRL at Q4
# FY2017-18 (broadcast May-Jun 2018) uniformly across large/mid/small caps
# tested. Nothing before this is usable for PAT extraction.
EARLIEST_USABLE_QUARTER_END = date(2018, 3, 31)

_NSE_DATE_FMT = "%d-%b-%Y"
_NSE_BROADCAST_FMT = "%d-%b-%Y %H:%M:%S"


# ─── Metadata discovery (bulk, date-windowed, ALL companies) ────────────────

def _month_chunks(start: date, end: date) -> Iterator[tuple[date, date]]:
    """[start, end] split into calendar-month windows. Confirmed live that
    a 2-month bulk pull returns ~3,700 rows with no truncation; chunking by
    month keeps every request comfortably under whatever NSE's real cap
    turns out to be, at the cost of more requests -- not worth verifying
    the exact ceiling just to shave request count."""
    cur = date(start.year, start.month, 1)
    while cur <= end:
        if cur.month == 12:
            nxt = date(cur.year + 1, 1, 1)
        else:
            nxt = date(cur.year, cur.month + 1, 1)
        chunk_end = min(nxt - timedelta(days=1), end)
        chunk_start = max(cur, start)
        yield chunk_start, chunk_end
        cur = nxt


def fetch_metadata_month(
    nse: NseSession, chunk_start: date, chunk_end: date,
    cache_dir: Path = DEFAULT_METADATA_CACHE_DIR,
) -> list[dict[str, Any]]:
    """One calendar month's bulk filing metadata (every NSE-listed
    company), cached to disk keyed by month. Re-running for an
    already-cached month is a disk read, no network hit."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{chunk_start:%Y%m}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    rows = fetch_financial_results_metadata(nse, chunk_start, chunk_end)
    cache_path.write_text(json.dumps(rows), encoding="utf-8")
    return rows


def discover_filings(
    nse: NseSession, start: date, end: date,
    cache_dir: Path = DEFAULT_METADATA_CACHE_DIR,
) -> Iterator[dict[str, Any]]:
    """Every quarterly-results filing (any company, any format) broadcast
    in [start, end], across however many monthly chunks that spans."""
    for chunk_start, chunk_end in _month_chunks(start, end):
        yield from fetch_metadata_month(nse, chunk_start, chunk_end, cache_dir)


# ─── Filtering + dedup ───────────────────────────────────────────────────────

def _parse_broadcast(raw: str) -> datetime:
    return datetime.strptime(raw, _NSE_BROADCAST_FMT)


def _parse_nse_date(raw: str) -> date:
    return datetime.strptime(raw, _NSE_DATE_FMT).date()


def filter_usable(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only rows with a real, fetchable XBRL link (see module
    docstring: `format == "New"` alone is not sufficient -- some New-format
    rows still carry the dead placeholder link)."""
    return [r for r in rows if is_xbrl_available(r.get("xbrl", ""))]


def dedupe_consolidated_preferred(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per (symbol, fromDate, toDate): prefer "Consolidated" over
    "Non-Consolidated" when both were filed for the same quarter (the
    normal case for companies with subsidiaries -- both variants get
    broadcast, usually minutes apart). Among same-type duplicates (a
    revision/correction re-filing), keep the latest broadCastDate."""
    best: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in rows:
        key = (r["symbol"], r["fromDate"], r["toDate"])
        existing = best.get(key)
        if existing is None:
            best[key] = r
            continue
        r_is_consolidated = r.get("consolidated") == "Consolidated"
        e_is_consolidated = existing.get("consolidated") == "Consolidated"
        if r_is_consolidated and not e_is_consolidated:
            best[key] = r
        elif r_is_consolidated == e_is_consolidated:
            if _parse_broadcast(r["broadCastDate"]) > _parse_broadcast(existing["broadCastDate"]):
                best[key] = r
    return list(best.values())


def restrict_to_universe(
    rows: list[dict[str, Any]], eligible_symbols: frozenset,
) -> list[dict[str, Any]]:
    """Keep only rows whose symbol was in the given universe (e.g. that
    quarter's point-in-time Nifty 500 membership, per
    core.rotation.nifty500_reconstitution). Caller decides how to compute
    membership per-row date -- this is a pure filter."""
    return [r for r in rows if r["symbol"] in eligible_symbols]


# ─── XBRL fetch + PAT extraction ─────────────────────────────────────────────

@dataclass(frozen=True)
class PointInTimeFiling:
    symbol: str
    broadcast_date: datetime  # the real disclosure timestamp
    quarter_start: date
    quarter_end: date
    consolidated: bool
    pat: float                # raw rupees, this filing's own quarter (context OneD)
    seq_number: str


def fetch_and_extract_pat(
    nse: NseSession, row: dict[str, Any],
    cache_dir: Path = DEFAULT_XBRL_CACHE_DIR,
) -> Optional[PointInTimeFiling]:
    """Fetch (or read from cache) one filing's XBRL and extract its
    quarterly PAT. Returns None if the file is fetchable but doesn't parse
    the way this module expects (logged, not raised) -- a single malformed
    filing must not kill a multi-thousand-filing run."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    seq = str(row["seqNumber"])
    cache_path = cache_dir / f"{seq}.xml"
    if cache_path.exists():
        xbrl_bytes = cache_path.read_bytes()
    else:
        xbrl_bytes = fetch_xbrl(nse, row["xbrl"])
        cache_path.write_bytes(xbrl_bytes)

    try:
        pat = extract_quarterly_pat(xbrl_bytes)
    except XbrlParseError as e:
        logger.warning("skipping filing seq=%s (%s): %s", seq, row.get("symbol"), e)
        return None

    return PointInTimeFiling(
        symbol=row["symbol"],
        broadcast_date=_parse_broadcast(row["broadCastDate"]),
        quarter_start=_parse_nse_date(row["fromDate"]),
        quarter_end=_parse_nse_date(row["toDate"]),
        consolidated=row.get("consolidated") == "Consolidated",
        pat=pat,
        seq_number=seq,
    )


# ─── YoY surprise ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PeadSignalRow:
    symbol: str
    broadcast_date: datetime
    quarter_start: date
    quarter_end: date
    pat: float
    pat_prior_year: float
    yoy_surprise_pct: float


def compute_yoy_surprise(filings: list[PointInTimeFiling]) -> list[PeadSignalRow]:
    """Joins each filing to the SAME symbol's filing for the same
    quarter-of-year exactly one year earlier (matched on quarter_start,
    not broadcast_date -- the disclosure date drifts year to year but the
    reporting quarter doesn't). Filings with no prior-year match (the
    first usable year of a symbol's history) are dropped, not zero-filled
    -- there is no real "no surprise" case here, just missing data."""
    by_key = {(f.symbol, f.quarter_start): f for f in filings}
    out: list[PeadSignalRow] = []
    for f in filings:
        try:
            prior_start = f.quarter_start.replace(year=f.quarter_start.year - 1)
        except ValueError:
            continue  # Feb 29 quarter boundary, not a real case for calendar quarters
        prior = by_key.get((f.symbol, prior_start))
        if prior is None or prior.pat == 0:
            continue
        surprise_pct = (f.pat - prior.pat) / abs(prior.pat) * 100
        out.append(PeadSignalRow(
            symbol=f.symbol, broadcast_date=f.broadcast_date,
            quarter_start=f.quarter_start, quarter_end=f.quarter_end,
            pat=f.pat, pat_prior_year=prior.pat, yoy_surprise_pct=surprise_pct,
        ))
    return out
