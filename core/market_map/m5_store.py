"""
5-minute bars for the weekly profiles (sprint plan S5, slice 5b; definitions v1 §4: the
weekly money zone comes from 30-minute brackets of 5-minute bars, the weekly VPOC from
their volume). Fyers holds 5-minute history from 2017-12-01 (probed 2026-11-07).

Layout under the L1 store root:  m5/<SYM>/<YEAR>.csv.gz   ts,o,h,l,c,vol
  ts = bar start, Unix seconds (UTC); prices raw, as Fyers sends them.
  m5/_state.json  {sym: {"last_ts": int, "backfilled": bool}}

Adjusted on read with the daily store's multiplier for the bar's date (the same split and
bonus factors as the daily bars), so both profiles share one price scale.
"""

from __future__ import annotations

import gzip
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

IST = ZoneInfo("Asia/Kolkata")
COLS = ["ts", "o", "h", "l", "c", "vol"]


class M5Store:
    def __init__(self, root: Path) -> None:
        self.root = Path(root) / "m5"
        self.state_path = self.root / "_state.json"

    def state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    def set_state(self, sym: str, **kw) -> None:
        s = self.state()
        s.setdefault(sym, {}).update(kw)
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, indent=0, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.state_path)

    def _path(self, sym: str, year: int) -> Path:
        return self.root / sym / f"{year}.csv.gz"

    def _read_year(self, sym: str, year: int) -> pd.DataFrame:
        p = self._path(sym, year)
        if not p.exists():
            return pd.DataFrame(columns=COLS)
        return pd.read_csv(p)

    def write(self, sym: str, rows: pd.DataFrame) -> int:
        """Merge rows (columns COLS) into the year files; a repeated ts keeps the new row.
        Returns the number of rows written in total for the touched years."""
        if rows.empty:
            return 0
        rows = rows[COLS].copy()
        years = pd.to_datetime(rows["ts"], unit="s", utc=True).dt.tz_convert(IST).dt.year
        n = 0
        for y, part in rows.groupby(years):
            old = self._read_year(sym, int(y))
            m = pd.concat([old, part]).drop_duplicates("ts", keep="last").sort_values("ts")
            p = self._path(sym, int(y))
            p.parent.mkdir(parents=True, exist_ok=True)
            buf = io.StringIO()
            m.to_csv(buf, index=False, float_format="%.15g", lineterminator="\n")
            tmp = p.with_suffix(".tmp")
            with gzip.open(tmp, "wt", encoding="utf-8", newline="") as f:
                f.write(buf.getvalue())
            os.replace(tmp, p)
            n += len(m)
        return n

    def read_raw(self, sym: str, since: Optional[datetime] = None) -> pd.DataFrame:
        d = self.root / sym
        if not d.exists():
            return pd.DataFrame(columns=COLS + ["dt"])
        y0 = since.astimezone(IST).year if since else 0
        parts = [pd.read_csv(p) for p in sorted(d.glob("*.csv.gz")) if int(p.name[:4]) >= y0]
        if not parts:
            return pd.DataFrame(columns=COLS + ["dt"])
        df = pd.concat(parts).drop_duplicates("ts", keep="last").sort_values("ts").reset_index(drop=True)
        df["dt"] = pd.to_datetime(df["ts"], unit="s", utc=True).dt.tz_convert(IST).dt.tz_localize(None)
        return df

    def adjusted(self, sym: str, daily_adj: pd.DataFrame) -> pd.DataFrame:
        """5-minute bars on the daily store's adjusted scale: prices times the multiplier of
        the bar's date (`mult` from Store.adjusted), volume divided by it. Bars on dates the
        daily store doesn't hold are dropped."""
        df = self.read_raw(sym)
        if df.empty or daily_adj.empty:
            return df
        mult = pd.Series(daily_adj["mult"].to_numpy(float), index=pd.to_datetime(daily_adj["date"]).dt.normalize())
        m = df["dt"].dt.normalize().map(mult)
        df = df[m.notna()].copy()
        m = m[m.notna()].to_numpy(float)
        for c in ("o", "h", "l", "c"):
            df[c] = df[c].to_numpy(float) * m
        df["vol"] = df["vol"].to_numpy(float) / m
        df["date"] = df["dt"].dt.normalize()
        return df.reset_index(drop=True)


def bars_frame(bars) -> pd.DataFrame:
    """Broker OHLCV list -> rows (columns COLS)."""
    return pd.DataFrame([(int(b.timestamp.timestamp()), b.open, b.high, b.low, b.close, b.volume) for b in bars],
                        columns=COLS)
