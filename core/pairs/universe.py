"""
QuantOS — Pairs Trading: Sector-Tagged Futures Universe
─────────────────────────────────────────────────────────
See docs/PAIRS_TRADING_METHODOLOGY.md "Universe" section for the full
rationale. Two independent sources, intersected:

  1. Single-stock-futures (STF) symbols from the already-cached NSE F&O
     bhavcopy raw zips (core/options/vrp/bhavcopy.py's fetch_raw/cache,
     reused as-is -- this module never re-downloads what VRP already has).
  2. NSE's own sectoral index constituent CSVs, fetched live from
     nsearchives.nseindia.com (confirmed fetchable 2026-07-25 -- same host
     the bhavcopy pipeline already uses, unlike the nseindia.com/
     niftyindices.com hosts this project's other universe files needed a
     manual download for).

A symbol qualifies for the pairs universe only if it appears in BOTH
sources. Pairs are only ever formed within the same sector tag (see
core/pairs/cointegration.py) -- this module's job is just to produce that
sector -> [symbols] mapping, nothing else.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import requests

from core.options.vrp.bhavcopy import BhavcopyNotAvailable, DEFAULT_RAW_CACHE_DIR, fetch_raw

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Confirmed live (HTTP 200) 2026-07-25 -- see docs/PAIRS_TRADING_METHODOLOGY.md.
# "niftyfinservice" and "niftyprivatebank" 404'd under this URL pattern and are
# deliberately not included (a wrong guessed name would silently no-op below).
SECTOR_INDEX_NAMES = [
    "niftybank", "niftyit", "niftypharma", "niftyrealty", "niftymetal",
    "niftyfmcg", "niftyauto", "niftyenergy", "niftymedia",
    "niftyconsumerdurables", "niftyoilgas", "niftypsubank", "niftyhealthcare",
]

DEFAULT_SECTOR_CACHE_DIR = Path("data_cache/nse_sector_lists")


def _sector_index_url(name: str) -> str:
    return f"https://nsearchives.nseindia.com/content/indices/ind_{name}list.csv"


def fetch_sector_constituents(
    name: str,
    cache_dir: Path = DEFAULT_SECTOR_CACHE_DIR,
    *,
    session: Optional[requests.Session] = None,
) -> list[str]:
    """Symbols in one NSE sectoral index, cached locally (these lists change
    rarely -- semi-annual reviews like the broad indices -- so a same-day
    cache hit is always safe, no TTL logic needed for a single research run)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{name}.csv"
    if cache_path.exists():
        text = cache_path.read_text(encoding="utf-8-sig")
    else:
        sess = session or requests
        resp = sess.get(_sector_index_url(name), headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        text = resp.content.decode("utf-8-sig")
        cache_path.write_text(text, encoding="utf-8")

    symbols = []
    for row in csv.DictReader(io.StringIO(text)):
        sym = (row.get("Symbol") or "").strip().upper()
        if sym:
            symbols.append(sym)
    return symbols


def build_sector_map(
    sector_names: list[str] = SECTOR_INDEX_NAMES,
    cache_dir: Path = DEFAULT_SECTOR_CACHE_DIR,
    *,
    session: Optional[requests.Session] = None,
) -> dict[str, list[str]]:
    """{sector_name: [symbols]}. A symbol may appear under more than one
    sector -- deliberately not deduped, see module docstring / methodology
    doc's Step 3."""
    return {name: fetch_sector_constituents(name, cache_dir, session=session) for name in sector_names}


# ─── STF symbol extraction from the cached bhavcopy raw zip ────────────────

def parse_stf_symbols(raw_zip: bytes) -> set[str]:
    """Every distinct single-stock-futures underlying present in one day's
    raw bhavcopy zip. New-format schema only (FinInstrmTp == 'STF' does not
    exist in the legacy pre-2024 schema -- see bhavcopy.py's CUTOVER_DATE)."""
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        raw_csv = zf.read(zf.namelist()[0]).decode("utf-8")
    return {
        r["TckrSymb"].strip().upper()
        for r in csv.DictReader(io.StringIO(raw_csv))
        if r["FinInstrmTp"] == "STF"
    }


@dataclass(frozen=True)
class NearMonthRow:
    close:              float
    lot_size:           int
    expiry:             date
    next_month_close:   Optional[float] = None
    # ^ Same day's close for the NEXT-nearest listed expiry (the contract
    # that becomes near-month once this one expires) -- None if a second
    # expiry isn't listed that day. Added for docs/PAIRS_TRADING_V2_METHODOLOGY.md's
    # roll-adjustment (core/pairs/roll_adjust.py): the ratio between a
    # contract's own last near-month price and its successor's SAME-DAY
    # price is what lets a roll seam be spliced out without ever needing a
    # future day's data.


def parse_stf_near_month(raw_zip: bytes, trade_date: date) -> dict[str, NearMonthRow]:
    """One NEAR-MONTH row per STF symbol present in the day's raw bhavcopy
    -- the contract with the smallest expiry that has not yet passed as of
    `trade_date` (there are normally 3 listed expiries per symbol; this
    always resolves to the current front month, never a synthetic/rolled
    series -- see docs/PAIRS_TRADING_METHODOLOGY.md's "no-continuous-contract
    rule", superseded for signal/formation purposes by
    docs/PAIRS_TRADING_V2_METHODOLOGY.md's roll-adjustment, which is built
    from the near_month/next_month pair returned here, not a third parse).
    A symbol with every listed expiry already <= trade_date (should not
    happen in a same-day bhavcopy, but not assumed) is skipped."""
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        raw_csv = zf.read(zf.namelist()[0]).decode("utf-8")

    by_symbol: dict[str, list[tuple[date, float, int]]] = defaultdict(list)
    for r in csv.DictReader(io.StringIO(raw_csv)):
        if r["FinInstrmTp"] != "STF":
            continue
        symbol = r["TckrSymb"].strip().upper()
        expiry = date.fromisoformat(r["XpryDt"])
        by_symbol[symbol].append((expiry, float(r["ClsPric"]), int(float(r["NewBrdLotQty"]))))

    out: dict[str, NearMonthRow] = {}
    for symbol, rows in by_symbol.items():
        future_rows = sorted((row for row in rows if row[0] >= trade_date), key=lambda row: row[0])
        if not future_rows:
            continue
        expiry, close, lot_size = future_rows[0]
        next_month_close = future_rows[1][1] if len(future_rows) > 1 else None
        out[symbol] = NearMonthRow(close=close, lot_size=lot_size, expiry=expiry,
                                    next_month_close=next_month_close)
    return out


def latest_stf_symbols(
    asof: date,
    raw_cache_dir: Path = DEFAULT_RAW_CACHE_DIR,
    *,
    session: Optional[requests.Session] = None,
    max_lookback_days: int = 10,
) -> set[str]:
    """STF symbols from the most recent trading day at or before `asof` that
    has a fetchable/cached bhavcopy. Walks backward day by day (not just
    `asof` itself) so a holiday/weekend `asof` still resolves -- same
    "attempt the fetch, treat 404 as not-a-trading-day" pattern bhavcopy.py
    itself uses, rather than a separate holiday calendar."""
    from datetime import timedelta

    d = asof
    for _ in range(max_lookback_days):
        try:
            raw = fetch_raw(d, raw_cache_dir, session=session)
        except BhavcopyNotAvailable:
            d -= timedelta(days=1)
            continue
        symbols = parse_stf_symbols(raw)
        if symbols:
            return symbols
        d -= timedelta(days=1)
    raise RuntimeError(f"no STF rows found in any bhavcopy within {max_lookback_days} days of {asof}")


# ─── Intersection: sector -> futures-listed symbols only ───────────────────

def build_pairs_universe(
    sector_map: dict[str, list[str]],
    stf_symbols: set[str],
) -> dict[str, list[str]]:
    """{sector_name: [symbols]}, restricted to symbols that also have listed
    single-stock futures. Sectors with fewer than 2 qualifying symbols
    contribute no pairs and are dropped -- not an error, just uninformative."""
    out: dict[str, list[str]] = {}
    for sector, symbols in sector_map.items():
        qualifying = sorted(set(symbols) & stf_symbols)
        if len(qualifying) >= 2:
            out[sector] = qualifying
    return out


def candidate_pairs(universe: dict[str, list[str]]) -> list[tuple[str, str, str]]:
    """(symbol_a, symbol_b, sector) for every unordered same-sector pair. A
    symbol tagged under multiple sectors contributes a separate pair entry
    per sector it shares with its counterpart (see methodology doc Step 3) --
    achieved naturally here since each sector's symbol list is processed
    independently, not merged into one global dedup set."""
    pairs = []
    for sector, symbols in universe.items():
        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                pairs.append((symbols[i], symbols[j], sector))
    return pairs


def symbol_sector_counts(universe: dict[str, list[str]]) -> dict[str, int]:
    """How many sectors each symbol qualifies under -- diagnostic only, for
    reporting the multi-sector-tag rate mentioned in the methodology doc."""
    counts: dict[str, int] = defaultdict(int)
    for symbols in universe.values():
        for s in symbols:
            counts[s] += 1
    return dict(counts)
