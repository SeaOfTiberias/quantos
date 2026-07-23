"""
QuantOS — PEAD Gut-Check: NSE Equity (Capital Market) Bhavcopy Fetch/Cache
────────────────────────────────────────────────────────────────────────────
Daily close prices for the forward-return gut-check Fable recommended
before Phase 2 (see memory: quantos-pead-earnings-feasibility) -- does
return sign/magnitude after a filing's `broadcast_date` correlate with its
`yoy_surprise_pct`? Needs a price series per symbol, not just the PAT table
core.fundamentals.pead.pipeline already builds.

Deliberately NOT using a broker (Fyers) for this -- confirmed in a prior
session that Fyers is IP-whitelisted to the deployment VM's static IP, so
broker calls would fail from wherever this actually runs. NSE's own daily
equity (capital-market segment) bhavcopy archive is free, no-auth (same
session-cookie pattern as core.fundamentals.pead.nse_client), and mirrors
core/options/vrp/bhavcopy.py's two-format-generation shape almost exactly:

  - New format (2024+): https://nsearchives.nseindia.com/content/cm/
    BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip
    Confirmed live 2026-07-23 for 2024-01-01 (200) and 2023-10-01/2023-10-15
    (both 404) -- same CUTOVER_DATE as VRP's F&O bhavcopy (2024-01-01), which
    makes sense: both are NSE's unified new-schema rollout, not
    segment-specific.
  - Legacy format (pre-2024): https://archives.nseindia.com/content/
    historical/EQUITIES/{YYYY}/{MON}/cm{DD}{MON}{YYYY}bhav.csv.zip
    Confirmed live for 2023-10-16 (200). Same URL family as VRP's legacy
    F&O archive, "EQUITIES" instead of "DERIVATIVES", "cm" prefix instead
    of "fo".

Filtered to `SERIES`/`SctySrs == "EQ"` (main-board equity) only -- BE/BZ/etc
are trade-for-trade or other special series, not the normal listing most
Nifty 500 constituents trade under, and not needed for this gut-check.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from core.fundamentals.pead.nse_client import NseNotFoundError, NseSession, fetch_bytes

DEFAULT_RAW_CACHE_DIR = Path("data_cache/pead_nse/eq_bhavcopy_raw")
DEFAULT_PARSED_CACHE_DIR = Path("data_cache/pead_nse/eq_bhavcopy_parsed")

# Confirmed live 2026-07-23 -- see module docstring. Same date VRP's F&O
# bhavcopy uses; not a coincidence, both are NSE's unified schema rollout.
CUTOVER_DATE = date(2024, 1, 1)


class EqBhavcopyNotAvailable(Exception):
    """Raised when NSE has no equity bhavcopy for a date (holiday/weekend/future)."""


def new_format_url(d: date) -> str:
    return f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"


def legacy_format_url(d: date) -> str:
    mon = d.strftime("%b").upper()
    return f"https://archives.nseindia.com/content/historical/EQUITIES/{d.year}/{mon}/cm{d:%d}{mon}{d.year}bhav.csv.zip"


def url_for(d: date) -> str:
    return new_format_url(d) if d >= CUTOVER_DATE else legacy_format_url(d)


@dataclass(frozen=True)
class EqCloseRow:
    trade_date: date
    symbol: str
    close: float


def _parse_new_format(raw_csv: bytes, trade_date: date) -> list[EqCloseRow]:
    text = raw_csv.decode("utf-8")
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        if r["FinInstrmTp"] != "STK" or r["SctySrs"] != "EQ":
            continue
        rows.append(EqCloseRow(trade_date=trade_date, symbol=r["TckrSymb"], close=float(r["ClsPric"])))
    return rows


def _parse_legacy_format(raw_csv: bytes, trade_date: date) -> list[EqCloseRow]:
    text = raw_csv.decode("utf-8")
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        if r["SERIES"] != "EQ":
            continue
        rows.append(EqCloseRow(trade_date=trade_date, symbol=r["SYMBOL"], close=float(r["CLOSE"])))
    return rows


def parse_bhavcopy_zip(raw_zip: bytes, trade_date: date) -> list[EqCloseRow]:
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        names = zf.namelist()
        if len(names) != 1:
            raise ValueError(f"expected exactly one file in {trade_date} equity bhavcopy zip, got {names}")
        raw_csv = zf.read(names[0])
    if trade_date >= CUTOVER_DATE:
        return _parse_new_format(raw_csv, trade_date)
    return _parse_legacy_format(raw_csv, trade_date)


def fetch_raw(nse: NseSession, d: date, raw_cache_dir: Path = DEFAULT_RAW_CACHE_DIR) -> bytes:
    """Download the raw equity bhavcopy zip for `d`, or serve from cache.
    Raises EqBhavcopyNotAvailable on 404 (holiday/weekend/future) -- same
    "404 means not a trading day" discipline as VRP's F&O bhavcopy, no
    separate holiday calendar maintained. fetch_bytes() already raises
    NseNotFoundError (not a generic NseSessionError) immediately on a 404,
    with no retry -- caught by TYPE here, not by string-matching an
    exception message."""
    raw_cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = raw_cache_dir / f"{d:%Y%m%d}.zip"
    if cache_path.exists():
        return cache_path.read_bytes()

    try:
        content = fetch_bytes(nse, url_for(d))
    except NseNotFoundError as e:
        raise EqBhavcopyNotAvailable(f"no equity bhavcopy for {d} (holiday/weekend/future)") from e
    cache_path.write_bytes(content)
    return content


def fetch_and_parse(
    nse: NseSession, d: date,
    raw_cache_dir: Path = DEFAULT_RAW_CACHE_DIR, parsed_cache_dir: Path = DEFAULT_PARSED_CACHE_DIR,
) -> list[EqCloseRow]:
    parsed_cache_dir.mkdir(parents=True, exist_ok=True)
    parsed_path = parsed_cache_dir / f"{d:%Y%m%d}.csv"
    if parsed_path.exists():
        rows = []
        with parsed_path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append(EqCloseRow(trade_date=date.fromisoformat(r["trade_date"]), symbol=r["symbol"], close=float(r["close"])))
        return rows

    raw = fetch_raw(nse, d, raw_cache_dir)
    rows = parse_bhavcopy_zip(raw, d)
    with parsed_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["trade_date", "symbol", "close"])
        for row in rows:
            writer.writerow([row.trade_date.isoformat(), row.symbol, row.close])
    return rows
