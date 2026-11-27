"""
Stock options from NSE's daily F&O bhavcopy (quant desk plan E1, docs/QUANT_DESK_PLAN_2026-11-27.md).

Reads the cached raw zips (both NSE file generations, told by the header) and keeps stock options
(legacy OPTSTK, newer STO) for the requested symbols. `close` is the last traded price; on a day a
contract didn't trade, NSE prints a carried-over close, so callers should use contracts with
volume > 0 only. `underlying` (the stock's price) is in the newer files only.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional


@dataclass(frozen=True)
class OptRow:
    trade_date: date
    symbol: str
    expiry: date
    strike: float
    opt: str              # "CE" or "PE"
    close: float          # last traded price
    settle: float
    volume: int           # contracts
    oi: int
    underlying: Optional[float]


def _f(x: str) -> Optional[float]:
    x = (x or "").strip()
    return float(x) if x else None


def parse_csv(text: str, trade_date: date, symbols: Optional[Iterable[str]] = None) -> list[OptRow]:
    want = set(symbols) if symbols is not None else None
    lines = text.splitlines()
    if not lines:
        return []
    few = want is not None and len(want) < 50          # speed: text pre-filter only for a short symbol list
    keep = [lines[0]]
    for ln in lines[1:]:
        if not (ln.startswith("OPTSTK,") or ",STO," in ln):
            continue
        if few and not any(f",{s}," in ln for s in want):
            continue
        keep.append(ln)
    rows: list[OptRow] = []
    rd = csv.DictReader(io.StringIO("\n".join(keep)))
    new = "TradDt" in (rd.fieldnames or [])
    for r in rd:
        if new:
            if r.get("FinInstrmTp") != "STO":
                continue
            sym = r["TckrSymb"]
            if want is not None and sym not in want:
                continue
            rows.append(OptRow(trade_date, sym, date.fromisoformat(r["XpryDt"]), float(r["StrkPric"]), r["OptnTp"],
                               float(r["ClsPric"]), float(r["SttlmPric"]), int(float(r["TtlTradgVol"] or 0)),
                               int(float(r["OpnIntrst"] or 0)), _f(r.get("UndrlygPric", ""))))
        else:
            if (r.get("INSTRUMENT") or "").strip() != "OPTSTK":
                continue
            sym = r["SYMBOL"].strip()
            if want is not None and sym not in want:
                continue
            rows.append(OptRow(trade_date, sym, datetime.strptime(r["EXPIRY_DT"].strip(), "%d-%b-%Y").date(),
                               float(r["STRIKE_PR"]), r["OPTION_TYP"].strip(), float(r["CLOSE"]), float(r["SETTLE_PR"]),
                               int(float(r["CONTRACTS"] or 0)), int(float(r["OPEN_INT"] or 0)), None))
    return rows


def read_zip_text(raw: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = zf.namelist()
        if len(names) != 1:
            raise ValueError(f"expected one file in the bhavcopy zip, got {names}")
        return zf.read(names[0]).decode("utf-8", errors="replace")


def atm_straddle(rows: list[OptRow], symbol: str, expiry: date, spot: float) -> Optional[tuple[float, OptRow, OptRow]]:
    """(strike, call, put) at the strike nearest `spot` where BOTH legs traded (volume > 0) on that
    expiry; ties go to the lower strike. None if no strike has both legs traded."""
    legs: dict[float, dict[str, OptRow]] = {}
    for r in rows:
        if r.symbol == symbol and r.expiry == expiry and r.volume > 0 and r.close > 0:
            legs.setdefault(r.strike, {})[r.opt] = r
    both = [k for k, v in legs.items() if "CE" in v and "PE" in v]
    if not both:
        return None
    k = min(both, key=lambda s: (abs(s - spot), s))
    return k, legs[k]["CE"], legs[k]["PE"]
