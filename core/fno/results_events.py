"""
Results-announcement events from NSE's corporate financial-results filing metadata
(quant desk plan E1). Source: data_cache/pead_nse/metadata_raw/YYYYMM.json, one list of filings
per broadcast month (core/fundamentals/pead/nse_client.py fetched them).

An event = the FIRST broadcast of a company's results for a period (symbol + period end date),
whatever the filing (standalone or consolidated, quarterly or annual): that is when the market
first learns the numbers. Later filings for the same period (the other basis, revisions) are not
events.
"""

from __future__ import annotations

import bisect
import glob
import json
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional

META_DIR = Path("data_cache/pead_nse/metadata_raw")
MARKET_CLOSE = time(15, 30)


@dataclass(frozen=True)
class Event:
    symbol: str
    period_end: date
    broadcast: datetime


def _ts(s: str) -> Optional[datetime]:
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


def events_from_filings(filings: list[dict]) -> list[Event]:
    first: dict[tuple[str, date], datetime] = {}
    for f in filings:
        sym, ts = (f.get("symbol") or "").strip(), _ts(f.get("broadCastDate") or "")
        try:
            pe = datetime.strptime((f.get("toDate") or "").strip(), "%d-%b-%Y").date()
        except ValueError:
            continue
        if not sym or ts is None:
            continue
        k = (sym, pe)
        if k not in first or ts < first[k]:
            first[k] = ts
    return sorted((Event(s, p, t) for (s, p), t in first.items()), key=lambda e: (e.broadcast, e.symbol))


def load_events(meta_dir: Path = META_DIR) -> list[Event]:
    filings: list[dict] = []
    for p in sorted(glob.glob(str(meta_dir / "*.json"))):
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        filings += d if isinstance(d, list) else d.get("data", [])
    return events_from_filings(filings)


def pre_and_reaction(broadcast: datetime, sessions: list[date]) -> Optional[tuple[date, date]]:
    """(P, R): P = the last session whose 15:30 close came before the broadcast, R = the session
    after P (the first close that can reflect the results). None outside the session list."""
    d = broadcast.date()
    i = bisect.bisect_right(sessions, d) - 1             # last session on or before the broadcast day
    if i >= 0 and sessions[i] == d and broadcast.time() < MARKET_CLOSE:
        i -= 1                                           # broadcast before that day's close: P is the day before
    if i < 0 or i + 1 >= len(sessions):
        return None
    return sessions[i], sessions[i + 1]
