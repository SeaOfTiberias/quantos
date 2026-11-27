"""
Index futures rows from NSE's daily F&O bhavcopy (quant desk plan, docs/QUANT_DESK_PLAN_2026-11-27.md).

Reads the raw zips that core/options/vrp/bhavcopy.py already caches (every contract, both NSE
file generations) and keeps index futures for the requested underlyings. The format is told
by the file's header, not the date (the two generations overlap in 2024).

Field notes:
- `close` is NSE's closing/settlement price for futures: the volume-weighted average of the
  last half hour, not the last trade. `last` (the actual last trade) exists only in the newer
  format (2024-01-01 on); it is None before.
- `open` is the first trade of the day.
- `lot_size` exists only in the newer format (NewBrdLotQty); None before.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

RAW_DIR = Path("data_cache/nse_bhavcopy/raw")


@dataclass(frozen=True)
class FutRow:
    trade_date: date
    symbol: str
    expiry: date
    open: float
    high: float
    low: float
    close: float          # settlement = last-30-minute VWAP
    last: Optional[float]  # last trade, newer format only
    volume: int           # contracts
    oi: int
    lot_size: Optional[int]


def _f(x: str) -> Optional[float]:
    x = (x or "").strip()
    return float(x) if x else None


_KINDS = {"index": ("FUTIDX", "IDF"), "stock": ("FUTSTK", "STF")}


def parse_csv(text: str, trade_date: date, symbols: Optional[Iterable[str]] = ("NIFTY", "BANKNIFTY"),
              kind: str = "index") -> list[FutRow]:
    """kind 'index' = index futures, 'stock' = stock futures. symbols=None keeps every underlying."""
    want = set(symbols) if symbols is not None else None
    legacy_tp, new_tp = _KINDS[kind]
    rows: list[FutRow] = []
    lines = text.splitlines()
    if lines:                                     # speed: only matching future lines reach the CSV parser
        lines = [lines[0]] + [ln for ln in lines[1:] if legacy_tp in ln or f",{new_tp}," in ln]
    rd = csv.DictReader(io.StringIO("\n".join(lines)))
    new = "TradDt" in (rd.fieldnames or [])
    for r in rd:
        if new:
            if r.get("FinInstrmTp") != new_tp or (want is not None and r.get("TckrSymb") not in want):
                continue
            lot = _f(r.get("NewBrdLotQty", ""))
            rows.append(FutRow(trade_date, r["TckrSymb"], date.fromisoformat(r["XpryDt"]),
                               float(r["OpnPric"]), float(r["HghPric"]), float(r["LwPric"]),
                               float(r["ClsPric"]), _f(r.get("LastPric", "")),
                               int(float(r["TtlTradgVol"] or 0)), int(float(r["OpnIntrst"] or 0)),
                               int(lot) if lot else None))
        else:
            if (r.get("INSTRUMENT") or "").strip() != legacy_tp or (
                    want is not None and (r.get("SYMBOL") or "").strip() not in want):
                continue
            rows.append(FutRow(trade_date, r["SYMBOL"].strip(),
                               datetime.strptime(r["EXPIRY_DT"].strip(), "%d-%b-%Y").date(),
                               float(r["OPEN"]), float(r["HIGH"]), float(r["LOW"]), float(r["CLOSE"]),
                               None, int(float(r["CONTRACTS"] or 0)), int(float(r["OPEN_INT"] or 0)), None))
    return rows


def parse_zip(raw: bytes, trade_date: date, symbols: Iterable[str] = ("NIFTY", "BANKNIFTY")) -> list[FutRow]:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = zf.namelist()
        if len(names) != 1:
            raise ValueError(f"expected one file in the {trade_date} bhavcopy zip, got {names}")
        text = zf.read(names[0]).decode("utf-8", errors="replace")
    return parse_csv(text, trade_date, symbols)


def load(start: date, end: date, raw_dir: Path = RAW_DIR,
         symbols: Iterable[str] = ("NIFTY", "BANKNIFTY")) -> dict[date, list[FutRow]]:
    """trade date -> index futures rows, from the cached zips only (no network)."""
    out: dict[date, list[FutRow]] = {}
    for p in sorted(raw_dir.glob("*.zip")):
        try:
            d = datetime.strptime(p.stem, "%Y%m%d").date()
        except ValueError:
            continue
        if start <= d <= end:
            rows = parse_zip(p.read_bytes(), d, symbols)
            if rows:
                out[d] = rows
    return out


def contract_after(rows: list[FutRow], symbol: str, d: date) -> Optional[FutRow]:
    """The nearest-expiry contract of `symbol` that expires strictly after `d`, so a position
    opened on d can still be closed the next session."""
    c = [r for r in rows if r.symbol == symbol and r.expiry > d]
    return min(c, key=lambda r: r.expiry) if c else None
