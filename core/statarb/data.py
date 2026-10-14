"""
QuantOS — StatArb (BankNifty test bed): Data Loading
─────────────────────────────────────────────────────
docs/STATARB_BANKNIFTY_METHODOLOGY.md "Data". Two inputs:

  1. Near-month stock-futures closes per symbol from the cached NSE F&O
     bhavcopy raw zips -- both schemas (legacy FUTSTK before
     core/options/vrp/bhavcopy.py's CUTOVER_DATE, new STF from it), unlike
     core/pairs/universe.py which only parses the new one. Parsed rows for
     the requested symbols are cached to a CSV so a re-run doesn't re-read
     ~1,900 zips; only days newer than the parsed cache are re-parsed.
  2. Quarterly-results broadcast dates per symbol from NSE's filing
     metadata API, cached to JSON.
"""

from __future__ import annotations

import csv
import io
import json
import time
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

from core.options.vrp.bhavcopy import (
    BhavcopyNotAvailable, CUTOVER_DATE, DEFAULT_RAW_CACHE_DIR, fetch_raw,
)
from core.pairs.backtest import FuturesDay
from core.pairs.roll_adjust import build_adjusted_series
from core.pairs.universe import NearMonthRow, parse_stf_near_month

DEFAULT_CACHE_DIR = Path("data_cache/statarb")
FIRST_CACHED_DAY = date(2019, 2, 11)
RESULTS_CUTOFF_TIME = (15, 30)  # broadcast at/after this IST time -> reaction is next trading day


# ─── Bhavcopy parsing ───────────────────────────────────────────────────────

def parse_legacy_near_month(raw_zip: bytes, trade_date: date) -> dict[str, NearMonthRow]:
    """Legacy-schema (pre-2024) twin of core/pairs/universe.py's
    parse_stf_near_month: FUTSTK rows, same "smallest unexpired expiry"
    near-month rule, same next-month close for roll adjustment. The legacy
    schema carries no lot size, so lot_size is 0 -- this module never sizes
    by lots (see the methodology doc's notional-based P&L)."""
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        raw_csv = zf.read(zf.namelist()[0]).decode("utf-8")

    by_symbol: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for r in csv.DictReader(io.StringIO(raw_csv)):
        if r.get("INSTRUMENT", "").strip() != "FUTSTK":
            continue
        expiry = datetime.strptime(r["EXPIRY_DT"].strip(), "%d-%b-%Y").date()
        by_symbol[r["SYMBOL"].strip().upper()].append((expiry, float(r["CLOSE"])))

    out: dict[str, NearMonthRow] = {}
    for symbol, rows in by_symbol.items():
        live = sorted((row for row in rows if row[0] >= trade_date), key=lambda row: row[0])
        if not live:
            continue
        expiry, close = live[0]
        out[symbol] = NearMonthRow(close=close, lot_size=0, expiry=expiry,
                                   next_month_close=live[1][1] if len(live) > 1 else None)
    return out


def parse_near_month(raw_zip: bytes, trade_date: date) -> dict[str, NearMonthRow]:
    if trade_date >= CUTOVER_DATE:
        return parse_stf_near_month(raw_zip, trade_date)
    return parse_legacy_near_month(raw_zip, trade_date)


def _weekdays(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def _last_cached_raw_day(raw_cache_dir: Path) -> Optional[date]:
    days = [datetime.strptime(p.stem, "%Y%m%d").date()
            for p in raw_cache_dir.glob("*.zip") if p.stem.isdigit()]
    return max(days) if days else None


# ─── Parsed-row cache ───────────────────────────────────────────────────────

_PANEL_FIELDS = ["trade_date", "symbol", "close", "lot_size", "expiry", "next_month_close"]


def _read_panel_cache(path: Path) -> dict[str, list[FuturesDay]]:
    out: dict[str, list[FuturesDay]] = defaultdict(list)
    if not path.exists():
        return out
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            out[r["symbol"]].append(FuturesDay(
                trade_date=date.fromisoformat(r["trade_date"]),
                close=float(r["close"]),
                lot_size=int(r["lot_size"]),
                expiry=date.fromisoformat(r["expiry"]),
                next_month_close=float(r["next_month_close"]) if r["next_month_close"] else None,
            ))
    return out


def _write_panel_cache(path: Path, panel: dict[str, list[FuturesDay]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(_PANEL_FIELDS)
        for symbol in sorted(panel):
            for d in panel[symbol]:
                w.writerow([d.trade_date.isoformat(), symbol, d.close, d.lot_size,
                            d.expiry.isoformat(),
                            "" if d.next_month_close is None else d.next_month_close])


# Pure ticker renames, old -> new, spliced into one series. Demergers
# (e.g. TATAMOTORS -> TMPV) are NOT renames and must never go here.
SYMBOL_RENAMES = {"ZOMATO": "ETERNAL", "TATAGLOBAL": "TATACONSUM"}


def load_futures_panel(
    symbols: list[str],
    end: date,
    *,
    raw_cache_dir: Path = DEFAULT_RAW_CACHE_DIR,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    allow_network: bool = True,
) -> dict[str, list[FuturesDay]]:
    """{symbol: roll-adjusted near-month FuturesDay series, ascending} for
    FIRST_CACHED_DAY..end.

    The parsed cache holds EVERY stock-futures symbol, so switching universe
    (BankNifty -> Nifty 50) never re-reads the zips; only days newer than
    the cache are parsed. A weekday missing from the raw cache on or before
    the newest cached zip is treated as a holiday without asking NSE --
    fetch_raw caches only successes, so asking would re-hit the network for
    every holiday on every run."""
    cache_path = cache_dir / "futures_panel_all.csv"
    panel: dict[str, list[FuturesDay]] = _read_panel_cache(cache_path)
    last_parsed = max((d.trade_date for v in panel.values() for d in v), default=None)

    last_raw = _last_cached_raw_day(raw_cache_dir)
    start = (last_parsed + timedelta(days=1)) if last_parsed else FIRST_CACHED_DAY
    n_new = 0
    for d in _weekdays(start, end):
        cache_file = raw_cache_dir / f"{d:%Y%m%d}.zip"
        if not cache_file.exists() and (not allow_network or (last_raw and d <= last_raw)):
            continue
        try:
            raw = fetch_raw(d, raw_cache_dir)
        except BhavcopyNotAvailable:
            continue
        rows = parse_near_month(raw, d)
        if not rows:
            continue
        n_new += 1
        for symbol, r in rows.items():
            panel[symbol].append(FuturesDay(d, r.close, r.lot_size, r.expiry,
                                            next_month_close=r.next_month_close))
    if n_new:
        _write_panel_cache(cache_path, panel)

    merged: dict[str, list[FuturesDay]] = defaultdict(list)
    for symbol, series in panel.items():
        merged[SYMBOL_RENAMES.get(symbol, symbol)].extend(series)

    out: dict[str, list[FuturesDay]] = {}
    for symbol in {s.upper() for s in symbols} & set(merged):
        by_day = {d.trade_date: d for d in merged[symbol]}  # rename overlap day: keep one
        adjusted, _ = build_adjusted_series([by_day[k] for k in sorted(by_day)])
        out[symbol] = adjusted
    return out


# ─── Results dates ──────────────────────────────────────────────────────────

def _broadcast_to_datetime(s: str) -> Optional[datetime]:
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def fetch_results_broadcasts(
    symbols: list[str],
    first_year: int,
    last_year: int,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    delay: float = 1.0,
) -> dict[str, list[datetime]]:
    """{symbol: sorted distinct results broadcast datetimes}. One request
    per (symbol, calendar year): a single multi-year request came back
    truncated in testing (2026-10-13, SBIN 2019-2026 stopped at 2025-02).
    Completed past years are served from cache; the current year is always
    re-fetched so new filings appear."""
    from core.fundamentals.pead.nse_client import (
        NseSession, NseSessionError, fetch_financial_results_metadata,
    )

    cache_path = cache_dir / "results_dates.json"
    cache: dict[str, dict[str, list[str]]] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text())

    this_year = date.today().year
    nse: Optional[NseSession] = None
    dirty = False
    for symbol in symbols:
        per_year = cache.setdefault(symbol, {})
        for year in range(first_year, last_year + 1):
            if str(year) in per_year and year < this_year:
                continue
            nse = nse or NseSession()
            try:
                rows = fetch_financial_results_metadata(
                    nse, date(year, 1, 1), min(date(year, 12, 31), date.today()), symbol=symbol)
            except NseSessionError as e:
                print(f"  results fetch failed {symbol} {year}: {e}")
                continue
            per_year[str(year)] = sorted({r["broadCastDate"] for r in rows if r.get("broadCastDate")})
            dirty = True
            time.sleep(delay)

    if dirty:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=1))

    out: dict[str, list[datetime]] = {}
    for symbol in symbols:
        stamps = {_broadcast_to_datetime(s) for year in cache.get(symbol, {}).values() for s in year}
        out[symbol] = sorted(s for s in stamps if s is not None)
    return out


_BOARD_MEETINGS_URL = "https://www.nseindia.com/api/corporate-board-meetings"


def fetch_results_board_meetings(
    symbols: list[str],
    first_year: int,
    last_year: int,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    delay: float = 1.0,
) -> dict[str, list[date]]:
    """{symbol: sorted board-meeting dates whose purpose includes financial
    results}, past AND scheduled. Needed because NSE's
    corporates-financial-results metadata returns almost nothing after
    ~2025-02 (found 2026-10-13: every bank 2 filings in 2025, 0 in 2026),
    and because it is the only source of UPCOMING results dates. Same
    per-(symbol, year) caching as fetch_results_broadcasts; the current and
    next year are always re-fetched."""
    from core.fundamentals.pead.nse_client import NseSession, NseSessionError, _get_json

    cache_path = cache_dir / "results_board_meetings.json"
    cache: dict[str, dict[str, list[str]]] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text())

    this_year = date.today().year
    nse: Optional[NseSession] = None
    dirty = False
    for symbol in symbols:
        per_year = cache.setdefault(symbol, {})
        for year in range(first_year, max(last_year, this_year + 1) + 1):
            if str(year) in per_year and year < this_year:
                continue
            nse = nse or NseSession()
            params = {"index": "equities", "symbol": symbol,
                      "from_date": f"01-01-{year}", "to_date": f"31-12-{year}"}
            try:
                rows = _get_json(nse, _BOARD_MEETINGS_URL, params)
            except NseSessionError as e:
                print(f"  board-meeting fetch failed {symbol} {year}: {e}")
                continue
            rows = rows if isinstance(rows, list) else []
            per_year[str(year)] = sorted({
                r["bm_date"] for r in rows
                if "financial result" in (r.get("bm_purpose") or "").lower() and r.get("bm_date")
            })
            dirty = True
            time.sleep(delay)

    if dirty:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=1))

    out: dict[str, list[date]] = {}
    for symbol in symbols:
        days = set()
        for year in cache.get(symbol, {}).values():
            for s in year:
                try:
                    days.add(datetime.strptime(s, "%d-%b-%Y").date())
                except ValueError:
                    continue
        out[symbol] = sorted(days)
    return out


def results_reaction_days(
    symbols: list[str], trading_days: list[date], *, use_filings: bool = True,
) -> tuple[dict[str, set[int]], dict[str, list[date]]]:
    """({symbol: reaction-day row indices}, {symbol: meeting dates after the
    last trading day}). Union of filing broadcasts (timestamped) and results
    board meetings (date only -> the meeting day itself is the reaction day,
    so a position is closed the evening before whether results come out
    intraday or after the close)."""
    first, last = trading_days[0].year, trading_days[-1].year
    broadcasts = fetch_results_broadcasts(symbols, first, last) if use_filings else {}
    meetings = fetch_results_board_meetings(symbols, first, last)
    days: dict[str, set[int]] = {}
    upcoming: dict[str, list[date]] = {}
    for sym in symbols:
        idx = {i for b in broadcasts.get(sym, []) if (i := reaction_day_index(b, trading_days)) is not None}
        idx |= {i for m in meetings.get(sym, [])
                if (i := reaction_day_index(datetime.combine(m, datetime.min.time()), trading_days)) is not None}
        days[sym] = idx
        upcoming[sym] = [m for m in meetings.get(sym, []) if m > trading_days[-1]]
    return days, upcoming


def reaction_day_index(broadcast: datetime, trading_days: list[date]) -> Optional[int]:
    """Index into trading_days of the first session that can react to a
    broadcast: the same day if broadcast before 15:30 on a trading day,
    else the next trading day."""
    import bisect

    d = broadcast.date()
    if (broadcast.hour, broadcast.minute) >= RESULTS_CUTOFF_TIME:
        d += timedelta(days=1)
    i = bisect.bisect_left(trading_days, d)
    return i if i < len(trading_days) else None
