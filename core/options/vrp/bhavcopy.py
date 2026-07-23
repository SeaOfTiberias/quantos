"""
QuantOS — VRP Phase 1: NSE Bhavcopy Fetch/Parse/Cache Pipeline
──────────────────────────────────────────────────────────────
Fetches NSE's daily F&O bhavcopy archive and parses it down to NIFTY
index-option rows in one unified schema, across NSE's two archive
generations (see memory: quantos-vrp-data-feasibility for the original
feasibility check):

  - New format: https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_...
  - Legacy format: https://archives.nseindia.com/content/historical/DERIVATIVES/...

CUTOVER_DATE below was binary-searched live (2026-07-23), not guessed: the
new-format URL 404s for every date before 2024-01-01 and resolves from
2024-01-01 onward; the legacy-format URL keeps resolving through 2024-07-05
and 404s from 2024-07-08 onward. The two formats overlap for just over six
months (2024-01-01 through 2024-07-05); this module always prefers the new
format once CUTOVER_DATE is reached, so there is never any ambiguity about
which schema a given date resolves to.

No hardcoded NSE trading-holiday calendar: a non-trading weekday 404s
identically under both formats (a small ~3.4KB S3 error body), so callers
(see scripts/fetch_vrp_bhavcopy.py) detect holidays by attempting the fetch
and treating a 404 as "not a trading day," rather than maintaining a
separate calendar that would silently drift from NSE's actual schedule.

Two independent local caches, both keyed by trade date (see fetch_and_parse):
  - raw/{YYYYMMDD}.zip    — the untouched bhavcopy zip, ALL underlyings.
                            Kept so re-parsing (or ever widening the filter
                            past NIFTY) never needs a re-download.
  - parsed/{YYYYMMDD}.csv — this module's unified schema, NIFTY index
                            options only. What every later phase reads.
Both caches are local-only (gitignored, see data_cache/) -- the raw cache in
particular is whole-market F&O data and far too large to commit.
"""

from __future__ import annotations

import csv
import io
import logging
import time
import zipfile
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator, Optional

import requests

from core.options.models import OptionType

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# See module docstring -- confirmed live 2026-07-23 by direct probing in both
# directions, not assumed.
CUTOVER_DATE = date(2024, 1, 1)

DEFAULT_RAW_CACHE_DIR = Path("data_cache/nse_bhavcopy/raw")
DEFAULT_PARSED_CACHE_DIR = Path("data_cache/nse_bhavcopy/parsed")


class BhavcopyNotAvailable(Exception):
    """Raised when NSE has no bhavcopy for a date (holiday/weekend/future)."""


# ─── URL selection ──────────────────────────────────────────────────────────

def new_format_url(d: date) -> str:
    return (
        "https://nsearchives.nseindia.com/content/fo/"
        f"BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
    )


def legacy_format_url(d: date) -> str:
    mon = d.strftime("%b").upper()
    return (
        "https://archives.nseindia.com/content/historical/DERIVATIVES/"
        f"{d.year}/{mon}/fo{d:%d}{mon}{d.year}bhav.csv.zip"
    )


def url_for(d: date) -> str:
    return new_format_url(d) if d >= CUTOVER_DATE else legacy_format_url(d)


# ─── Unified row schema ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class BhavcopyOptionRow:
    """One NIFTY index-option contract's OHLC/OI for one trading day, in a
    schema unified across both NSE bhavcopy generations."""
    trade_date:        date
    underlying:        str             # always "NIFTY" -- this pipeline filters to it
    expiry:            date
    strike:            float
    option_type:       OptionType
    open:              float
    high:              float
    low:               float
    close:             float
    settle_price:      float
    open_interest:     int
    volume:            int              # contracts traded
    underlying_close:  Optional[float]  # only populated by the new-format schema


_CACHE_FIELDNAMES = [f.name for f in fields(BhavcopyOptionRow)]


# ─── Parsing ─────────────────────────────────────────────────────────────────

def _parse_new_format(raw_csv: bytes, trade_date: date) -> list[BhavcopyOptionRow]:
    text = raw_csv.decode("utf-8")
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        # IDO = index option; other FinInstrmTp values (STO/IDF/STF) cover
        # stock options and index/stock futures, out of scope for VRP.
        if r["FinInstrmTp"] != "IDO" or r["TckrSymb"] != "NIFTY":
            continue
        rows.append(BhavcopyOptionRow(
            trade_date=trade_date,
            underlying="NIFTY",
            expiry=date.fromisoformat(r["XpryDt"]),
            strike=float(r["StrkPric"]),
            option_type=OptionType.CALL if r["OptnTp"] == "CE" else OptionType.PUT,
            open=float(r["OpnPric"]), high=float(r["HghPric"]),
            low=float(r["LwPric"]), close=float(r["ClsPric"]),
            settle_price=float(r["SttlmPric"]),
            open_interest=int(float(r["OpnIntrst"])),
            volume=int(float(r["TtlTradgVol"])),
            underlying_close=float(r["UndrlygPric"]) if r.get("UndrlygPric") else None,
        ))
    return rows


def _parse_legacy_format(raw_csv: bytes, trade_date: date) -> list[BhavcopyOptionRow]:
    text = raw_csv.decode("utf-8")
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        if r["INSTRUMENT"] != "OPTIDX" or r["SYMBOL"] != "NIFTY":
            continue
        rows.append(BhavcopyOptionRow(
            trade_date=trade_date,
            underlying="NIFTY",
            expiry=datetime.strptime(r["EXPIRY_DT"], "%d-%b-%Y").date(),
            strike=float(r["STRIKE_PR"]),
            option_type=OptionType.CALL if r["OPTION_TYP"] == "CE" else OptionType.PUT,
            open=float(r["OPEN"]), high=float(r["HIGH"]),
            low=float(r["LOW"]), close=float(r["CLOSE"]),
            settle_price=float(r["SETTLE_PR"]),
            open_interest=int(float(r["OPEN_INT"])),
            volume=int(float(r["CONTRACTS"])),
            underlying_close=None,  # not present in the legacy schema
        ))
    return rows


def parse_bhavcopy_zip(raw_zip: bytes, trade_date: date) -> list[BhavcopyOptionRow]:
    """Unzip a single-file bhavcopy archive and parse it with whichever
    schema applies to `trade_date`."""
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        names = zf.namelist()
        if len(names) != 1:
            raise ValueError(f"expected exactly one file in {trade_date} bhavcopy zip, got {names}")
        raw_csv = zf.read(names[0])
    if trade_date >= CUTOVER_DATE:
        return _parse_new_format(raw_csv, trade_date)
    return _parse_legacy_format(raw_csv, trade_date)


# ─── Fetch + cache ───────────────────────────────────────────────────────────

def fetch_raw(
    d: date,
    raw_cache_dir: Path = DEFAULT_RAW_CACHE_DIR,
    *,
    session: Optional[requests.Session] = None,
    max_retries: int = 3,
) -> bytes:
    """Download the raw bhavcopy zip for `d`, or serve it from raw_cache_dir
    if already cached. Raises BhavcopyNotAvailable on 404 (holiday/weekend/
    future) -- callers should treat that as "skip this date," not an error."""
    raw_cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = raw_cache_dir / f"{d:%Y%m%d}.zip"
    if cache_path.exists():
        return cache_path.read_bytes()

    sess = session or requests
    url = url_for(d)
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            resp = sess.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        except requests.RequestException as e:
            last_exc = e
            time.sleep(1.5 * (attempt + 1))
            continue
        if resp.status_code == 404:
            raise BhavcopyNotAvailable(f"no bhavcopy for {d} (holiday/weekend/future)")
        if resp.status_code != 200:
            last_exc = RuntimeError(f"{url} -> HTTP {resp.status_code}")
            time.sleep(1.5 * (attempt + 1))
            continue
        cache_path.write_bytes(resp.content)
        return resp.content
    raise RuntimeError(f"failed to fetch {url} after {max_retries} attempts: {last_exc}")


def _write_parsed_cache(path: Path, rows: list[BhavcopyOptionRow]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(_CACHE_FIELDNAMES)
        for row in rows:
            d = asdict(row)
            writer.writerow([
                d["trade_date"].isoformat(), d["underlying"], d["expiry"].isoformat(),
                d["strike"], d["option_type"].value, d["open"], d["high"], d["low"],
                d["close"], d["settle_price"], d["open_interest"], d["volume"],
                "" if d["underlying_close"] is None else d["underlying_close"],
            ])


def _read_parsed_cache(path: Path) -> list[BhavcopyOptionRow]:
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(BhavcopyOptionRow(
                trade_date=date.fromisoformat(r["trade_date"]),
                underlying=r["underlying"],
                expiry=date.fromisoformat(r["expiry"]),
                strike=float(r["strike"]),
                option_type=OptionType(r["option_type"]),
                open=float(r["open"]), high=float(r["high"]),
                low=float(r["low"]), close=float(r["close"]),
                settle_price=float(r["settle_price"]),
                open_interest=int(r["open_interest"]),
                volume=int(r["volume"]),
                underlying_close=float(r["underlying_close"]) if r["underlying_close"] else None,
            ))
    return rows


def fetch_and_parse(
    d: date,
    raw_cache_dir: Path = DEFAULT_RAW_CACHE_DIR,
    parsed_cache_dir: Path = DEFAULT_PARSED_CACHE_DIR,
    *,
    session: Optional[requests.Session] = None,
) -> list[BhavcopyOptionRow]:
    """Cached fetch + parse for one trading day, filtered to NIFTY index
    options. Parsed results are cached separately from raw downloads so a
    re-run of this function never re-downloads OR re-parses a date it's
    already seen. Raises BhavcopyNotAvailable for holidays/weekends/future
    dates, same as fetch_raw."""
    parsed_cache_dir.mkdir(parents=True, exist_ok=True)
    parsed_path = parsed_cache_dir / f"{d:%Y%m%d}.csv"
    if parsed_path.exists():
        return _read_parsed_cache(parsed_path)

    raw = fetch_raw(d, raw_cache_dir, session=session)
    rows = parse_bhavcopy_zip(raw, d)
    _write_parsed_cache(parsed_path, rows)
    return rows


def load_cached_range(
    start: date, end: date, parsed_cache_dir: Path = DEFAULT_PARSED_CACHE_DIR,
) -> Iterator[BhavcopyOptionRow]:
    """Read every already-parsed trading day in [start, end] from the parsed
    cache, in date order. Dates with no cached file (holidays, or dates never
    fetched) are silently skipped -- this is a read-only view over whatever
    scripts/fetch_vrp_bhavcopy.py has already populated, not a fetcher."""
    d = start
    while d <= end:
        parsed_path = parsed_cache_dir / f"{d:%Y%m%d}.csv"
        if parsed_path.exists():
            yield from _read_parsed_cache(parsed_path)
        d += timedelta(days=1)
