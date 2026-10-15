"""
QuantOS — Candidate 23 Stage 2: stock-option call rows from cached bhavcopy
───────────────────────────────────────────────────────────────────────────
docs/SURGE_SPREAD_STAGE2_METHODOLOGY.md "Option data". One pass over the
cached F&O bhavcopy zips, keeping only CE rows for the symbols that have an
open event window on each date, in both schemas (legacy OPTSTK before
core/options/vrp/bhavcopy.py's CUTOVER_DATE, STO from it). The result is
cached as one gzipped CSV, so later runs read it in seconds.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd

from core.options.vrp.bhavcopy import CUTOVER_DATE, DEFAULT_RAW_CACHE_DIR
from core.statarb.data import SYMBOL_RENAMES

DEFAULT_CACHE = Path("data_cache/surge/option_rows.csv.gz")
COLUMNS = ["trade_date", "symbol", "expiry", "strike", "close", "settle", "contracts", "lot"]
_OLD_NAME = {new: old for old, new in SYMBOL_RENAMES.items()}


def parse_ce_rows(raw_zip: bytes, trade_date: date, symbols: set[str]) -> pd.DataFrame:
    """CE rows for `symbols` from one day's bhavcopy zip, in COLUMNS order.
    Renamed tickers are read under their old name and reported under the
    new one (ZOMATO rows -> ETERNAL)."""
    lookup = set(symbols) | {_OLD_NAME[s] for s in symbols if s in _OLD_NAME}
    df = pd.read_csv(io.BytesIO(raw_zip), compression="zip", dtype=str, keep_default_na=False)
    if trade_date >= CUTOVER_DATE:
        df = df[(df["FinInstrmTp"] == "STO") & (df["OptnTp"] == "CE") & df["TckrSymb"].isin(lookup)]
        out = pd.DataFrame({
            "symbol": df["TckrSymb"].str.strip(),
            "expiry": pd.to_datetime(df["XpryDt"]).dt.date,
            "strike": df["StrkPric"].astype(float),
            "close": df["ClsPric"].astype(float),
            "settle": df["SttlmPric"].astype(float),
            "contracts": pd.to_numeric(df["TtlTradgVol"], errors="coerce").fillna(0),
            "lot": pd.to_numeric(df["NewBrdLotQty"], errors="coerce").fillna(0).astype(int),
        })
    else:
        df = df[(df["INSTRUMENT"].str.strip() == "OPTSTK") & (df["OPTION_TYP"] == "CE")
                & df["SYMBOL"].str.strip().isin(lookup)]
        out = pd.DataFrame({
            "symbol": df["SYMBOL"].str.strip(),
            "expiry": pd.to_datetime(df["EXPIRY_DT"], format="%d-%b-%Y").dt.date,
            "strike": df["STRIKE_PR"].astype(float),
            "close": df["CLOSE"].astype(float),
            "settle": df["SETTLE_PR"].astype(float),
            "contracts": pd.to_numeric(df["CONTRACTS"], errors="coerce").fillna(0),
            "lot": 0,
        })
    out["symbol"] = out["symbol"].map(lambda s: SYMBOL_RENAMES.get(s, s))
    out.insert(0, "trade_date", trade_date)
    return out[COLUMNS]


def load_option_rows(
    needs: dict[date, set[str]],
    *,
    raw_cache_dir: Path = DEFAULT_RAW_CACHE_DIR,
    cache_path: Path = DEFAULT_CACHE,
    progress: bool = True,
) -> pd.DataFrame:
    """CE rows for every (date, symbol) in `needs`. Cache-first: a cache
    that already covers every needed (date, symbol) pair is returned as is;
    otherwise only the missing dates are parsed and appended."""
    cached = pd.DataFrame(columns=COLUMNS)
    if cache_path.exists():
        cached = pd.read_csv(cache_path, parse_dates=["trade_date", "expiry"])
        cached["trade_date"] = cached["trade_date"].dt.date
        cached["expiry"] = cached["expiry"].dt.date
    have = set(zip(cached["trade_date"], cached["symbol"])) if len(cached) else set()
    have_dates = set(cached["trade_date"]) if len(cached) else set()

    todo = sorted(d for d, syms in needs.items()
                  if d not in have_dates or any((d, s) not in have for s in syms))
    frames = [cached] if len(cached) else []
    for n, d in enumerate(todo, 1):
        path = raw_cache_dir / f"{d:%Y%m%d}.zip"
        if not path.exists():
            continue
        frames.append(parse_ce_rows(path.read_bytes(), d, needs[d]))
        if progress and n % 100 == 0:
            print(f"  option rows: {n}/{len(todo)} dates")
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    rows = pd.concat(frames, ignore_index=True).drop_duplicates(
        ["trade_date", "symbol", "expiry", "strike"], keep="last")
    if todo:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        rows.to_csv(cache_path, index=False, compression="gzip")
    return rows


def needs_for_events(events: Iterable, dates: list[date], window: int = 8) -> dict[date, set[str]]:
    """{date: symbols} covering each event's entry day and the following
    `window` trading days (a superset of any exit day)."""
    out: dict[date, set[str]] = {}
    for e in events:
        for i in range(e.t, min(e.t + window + 1, len(dates))):
            out.setdefault(dates[i], set()).add(e.symbol)
    return out
