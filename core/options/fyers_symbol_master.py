"""
QuantOS — Fyers Options Symbol Master
──────────────────────────────────────
Resolves (underlying, expiry, strike, CE/PE) to Fyers' real tradeable
symbol + lot size by looking them up in Fyers' own published symbol
master file, instead of reconstructing the symbol string by hand.

Why not hand-build the symbol string: Fyers' options symbol format
differs between weekly index expiries (compact numeric month+day, e.g.
"NIFTY2672129450CE" for 21-Jul-2026) and monthly expiries used by every
stock and an index's month-end contract (3-letter month, e.g.
"SBIN26JUL600CE") — confirmed against the live file 2026-07-21. Getting
this wrong risks placing an order against a nonexistent or wrong symbol.
The master file also carries the authoritative lot size per instrument,
which SEBI revises periodically (NIFTY changed 75->65 in Jan 2026) —
looking it up beats hardcoding a table that goes stale.

The master file is a public, unauthenticated download (no Fyers session
or access token needed) — safe to fetch/test independent of a live
broker connection.
"""

import csv
import io
import logging
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

import requests

from core.options.models import OptionType

logger = logging.getLogger(__name__)

_MASTER_URL = "https://public.fyers.in/sym_details/{segment}.csv"
_CACHE_DIR = os.path.expanduser("~/.quantos")
_CACHE_MAX_AGE_SECONDS = 24 * 60 * 60  # refresh daily — expiries/lots do change

# Column indices in the master CSV, confirmed against a live download
# 2026-07-21 (the file ships with no header row; Fyers' own published
# header docs are disputed/stale per community reports, so these were
# derived directly from real rows rather than trusted from docs):
#   0 fytoken, 1 description, 2 instrument_type, 3 lot_size, 4 tick_size,
#   7 last_updated, 8 expiry_epoch, 9 fyers_symbol, 10 exchange_code,
#   11 segment_code, 12 scrip_code, 13 underlying_symbol,
#   14 underlying_scrip_code, 15 strike, 16 option_type ("CE"/"PE"/"XX")
_COL_INSTRUMENT_TYPE = 2
_COL_LOT_SIZE = 3
_COL_EXPIRY_EPOCH = 8
_COL_FYERS_SYMBOL = 9
_COL_UNDERLYING = 13
_COL_STRIKE = 15
_COL_OPTION_TYPE = 16

# instrument_type codes seen in NSE_FO.csv: 11=index future, 13=stock
# future, 14=index option, 15=stock option. Futures rows carry
# strike=-1.0 / option_type="XX" so they'd never match an option lookup
# anyway, but filtering by type is a cheap extra guard.
_OPTION_INSTRUMENT_TYPES = {"14", "15"}


class SymbolMasterError(Exception):
    """Raised when the symbol master can't be fetched or a lookup fails."""
    pass


@dataclass(frozen=True)
class ResolvedOption:
    symbol: str              # real Fyers tradeable symbol, e.g. "NSE:NIFTY2672129450CE"
    lot_size: int
    expiry: date
    strike: float
    option_type: OptionType


def _cache_path(segment: str) -> str:
    return os.path.join(_CACHE_DIR, f"fyers_symbol_master_{segment}.csv")


def _download_master(segment: str) -> str:
    url = _MASTER_URL.format(segment=segment)
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def _load_master_text(segment: str, force_refresh: bool = False) -> str:
    path = _cache_path(segment)
    if not force_refresh and os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if age < _CACHE_MAX_AGE_SECONDS:
            with open(path, encoding="utf-8") as f:
                return f.read()

    text = _download_master(segment)
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return text


def _parse_rows(text: str, underlying: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text))
    underlying = underlying.upper()
    return [
        row for row in reader
        if len(row) > _COL_OPTION_TYPE
        and row[_COL_INSTRUMENT_TYPE] in _OPTION_INSTRUMENT_TYPES
        and row[_COL_UNDERLYING].upper() == underlying
    ]


def _row_expiry(row: list[str]) -> date:
    epoch = int(float(row[_COL_EXPIRY_EPOCH]))
    return datetime.fromtimestamp(epoch, tz=timezone.utc).date()


def list_expiries(underlying: str, segment: str = "NSE_FO",
                   force_refresh: bool = False) -> list[date]:
    """All distinct future-or-today expiry dates available for `underlying`,
    sorted ascending."""
    text = _load_master_text(segment, force_refresh=force_refresh)
    rows = _parse_rows(text, underlying)
    if not rows:
        raise SymbolMasterError(f"No option rows found for underlying {underlying!r}")

    today = datetime.now(tz=timezone.utc).date()
    expiries = {_row_expiry(r) for r in rows}
    return sorted(e for e in expiries if e >= today)


def get_expiry_epoch(underlying: str, expiry: date, segment: str = "NSE_FO",
                      force_refresh: bool = False) -> str:
    """
    The epoch-seconds string Fyers' optionchain endpoint's "timestamp"
    parameter actually wants — confirmed live 2026-07-21 that passing an
    ISO date string there ("2026-07-21") gets rejected ("Please provide
    valid expiry"); Fyers' own error response included the exact
    epoch-per-expiry mapping this reads from, sourced from the same master
    file rather than a second round-trip through the error path.
    """
    text = _load_master_text(segment, force_refresh=force_refresh)
    rows = _parse_rows(text, underlying)
    for row in rows:
        if _row_expiry(row) == expiry:
            return str(int(float(row[_COL_EXPIRY_EPOCH])))
    raise SymbolMasterError(
        f"No contract found for {underlying} {expiry.isoformat()} — can't "
        f"resolve its expiry epoch from the {segment} symbol master"
    )


def get_lot_size(underlying: str, segment: str = "NSE_FO",
                  force_refresh: bool = False) -> int:
    """Lot size for `underlying`. Constant across strikes/expiries for a
    given underlying in practice — takes the first matching row."""
    text = _load_master_text(segment, force_refresh=force_refresh)
    rows = _parse_rows(text, underlying)
    if not rows:
        raise SymbolMasterError(f"No option rows found for underlying {underlying!r}")
    return int(rows[0][_COL_LOT_SIZE])


def resolve_option_symbol(
    underlying: str,
    expiry: date,
    strike: float,
    option_type: OptionType,
    segment: str = "NSE_FO",
    force_refresh: bool = False,
) -> ResolvedOption:
    """
    Look up the real Fyers tradeable symbol + lot size for an exact
    (underlying, expiry, strike, option_type) combination.

    Raises SymbolMasterError if no matching contract exists — e.g. the
    strike isn't listed or the expiry has passed/doesn't exist — rather
    than guessing a symbol string that might not be tradeable.
    """
    text = _load_master_text(segment, force_refresh=force_refresh)
    rows = _parse_rows(text, underlying)

    for row in rows:
        if (_row_expiry(row) == expiry
                and float(row[_COL_STRIKE]) == float(strike)
                and row[_COL_OPTION_TYPE] == option_type.value):
            return ResolvedOption(
                symbol=row[_COL_FYERS_SYMBOL],
                lot_size=int(row[_COL_LOT_SIZE]),
                expiry=expiry,
                strike=float(strike),
                option_type=option_type,
            )

    raise SymbolMasterError(
        f"No contract found for {underlying} {expiry.isoformat()} "
        f"{strike} {option_type.value} — not listed in the {segment} symbol master"
    )
