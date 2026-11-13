"""Daily bars for NIFTY and BANKNIFTY from NSE's public index close file (no broker login).

    https://nsearchives.nseindia.com/content/indices/ind_close_all_DDMMYYYY.csv

One file per session, with every NSE index's OHLC, volume and turnover. The bars are kept as
<root>/<SYM>.csv in the column layout structure.l1_read expects (date, o, h, l, c, vol, val), so
the index is read by the same map engine as stocks (docs/TRADE_REASONING.md, step 1).
"""
from __future__ import annotations

import csv
import io
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

URL = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{d:%d%m%Y}.csv"
INDICES = {"Nifty 50": "NIFTY", "Nifty Bank": "BANKNIFTY"}
# Older files name them differently (before about 2016): the same indices.
ALIASES = {"S&P CNX Nifty": "NIFTY", "CNX Nifty": "NIFTY", "CNX Bank": "BANKNIFTY"}
COLS = ["date", "o", "h", "l", "c", "vol", "val"]
DEFAULT_ROOT = Path.home() / ".quantos" / "index_bars"


def _num(x: str) -> Optional[float]:
    x = (x or "").strip()
    if x in ("", "-"):
        return None
    try:
        return float(x)
    except ValueError:
        return None


def _date(x: str) -> Optional[date]:
    for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(x, fmt).date()
        except ValueError:
            pass
    return None


def parse_day(body: bytes | str, d: date) -> dict[str, dict]:
    """One index close file -> {SYM: bar} for INDICES. Rows dated other than `d` are ignored
    (a stale file must not be stored under the wrong day)."""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        name = (row.get("Index Name") or "").strip()
        sym = INDICES.get(name) or ALIASES.get(name)
        if not sym:
            continue
        rd = _date((row.get("Index Date") or "").strip())
        if rd != d:
            continue
        o, h, l, c = (_num(row.get(k)) for k in ("Open Index Value", "High Index Value",
                                                  "Low Index Value", "Closing Index Value"))
        if None in (h, l, c):
            continue
        o = o if o else c        # very old files carry no open for some indices
        vol = _num(row.get("Volume")) or 0.0
        val = (_num(row.get("Turnover (Rs. Cr.)")) or 0.0) * 1e7
        out[sym] = dict(date=d.isoformat(), o=o, h=max(h, o, c), l=min(l, o, c), c=c, vol=vol, val=val)
    return out


class IndexBars:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else DEFAULT_ROOT

    def path(self, sym: str) -> Path:
        return self.root / f"{sym}.csv"

    def load(self, sym: str) -> pd.DataFrame:
        p = self.path(sym)
        if not p.exists():
            df = pd.DataFrame(columns=COLS)
            df["date"] = pd.to_datetime(df["date"])
            return df
        df = pd.read_csv(p)
        df["date"] = pd.to_datetime(df["date"])
        return df.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)

    def last_session(self) -> Optional[date]:
        ds = [self.load(s)["date"].max() for s in INDICES.values() if self.path(s).exists()]
        ds = [d for d in ds if pd.notna(d)]
        return min(ds).date() if ds else None

    def append(self, bars: dict[str, dict]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for sym, bar in bars.items():
            p = self.path(sym)
            new = not p.exists()
            with p.open("a", newline="") as f:
                w = csv.DictWriter(f, fieldnames=COLS)
                if new:
                    w.writeheader()
                w.writerow(bar)

    def refresh(self, start: date, end: date, fetch=None, pause: float = 0.3, log=print) -> dict:
        """Fetch every weekday from `start` to `end` not already stored. A missing file (holiday,
        not yet published) is skipped; a later run picks a late file up."""
        if fetch is None:
            from core.market_map import nse_daily as nd
            fetch = nd.fetch
        have = {s: set(self.load(s)["date"].dt.date) for s in INDICES.values()}
        added, missing = [], []
        d = start
        while d <= end:
            if d.weekday() < 5 and not all(d in have[s] for s in have):
                body = None
                try:
                    body = fetch(URL.format(d=d))
                except Exception as e:  # network trouble: report, keep going
                    log(f"{d}: fetch failed ({e})")
                bars = parse_day(body, d) if body else {}
                bars = {s: b for s, b in bars.items() if d not in have[s]}
                if bars:
                    self.append(bars)
                    added.append(d.isoformat())
                elif not body:
                    missing.append(d.isoformat())
                if pause:
                    time.sleep(pause)
            d += timedelta(days=1)
        return dict(added=len(added), first=added[0] if added else None, last=added[-1] if added else None,
                    missing=len(missing))
