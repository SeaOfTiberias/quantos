"""
QuantOS — F&O Screener: stock futures / stock options from NSE's F&O bhavcopy
──────────────────────────────────────────────────────────────────────────────
Pure parsing of one day's raw F&O bhavcopy zip (new UDiFF format, fetched
and cached by core/options/vrp/bhavcopy.py's fetch_raw) into the two things
the screener needs:

  - STF rows -> per-symbol futures OI by expiry + the underlying's close
    (UndrlygPric). The STF symbol set IS the stock F&O universe.
  - STO rows -> every stock option contract's close, OI and volume, for
    picking and liquidity-checking the recommended contract.

Units, confirmed against the 2026-10-09 file: OpnIntrst is in SHARES
(divide by NewBrdLotQty for lots); TtlTradgVol is in CONTRACTS (RELIANCE
26OCT 1520PE: 13 traded, TtlTrfVal = (strike + premium) x 500 x 13).
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from core.options.models import OptionType


@dataclass(frozen=True)
class OptionQuote:
    symbol:      str
    expiry:      date
    strike:      float
    option_type: OptionType
    close:       float
    oi_lots:     int
    volume:      int          # contracts traded that day
    lot_size:    int


@dataclass
class FnoDay:
    trade_date:   date
    spot:         dict[str, float] = field(default_factory=dict)                 # symbol -> underlying close
    futures_oi:   dict[str, dict[date, int]] = field(default_factory=dict)      # symbol -> {expiry: OI shares}
    options:      dict[str, list[OptionQuote]] = field(default_factory=dict)    # symbol -> contracts

    @property
    def symbols(self) -> list[str]:
        return sorted(self.futures_oi)


def _csv_text(raw_zip: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        return zf.read(zf.namelist()[0]).decode("utf-8")


def parse_fno_day(raw_zip: bytes, trade_date: date) -> FnoDay:
    day = FnoDay(trade_date=trade_date)
    futures_oi: dict[str, dict[date, int]] = defaultdict(dict)
    options: dict[str, list[OptionQuote]] = defaultdict(list)
    for r in csv.DictReader(io.StringIO(_csv_text(raw_zip))):
        kind = r["FinInstrmTp"]
        if kind not in ("STF", "STO"):
            continue
        symbol = r["TckrSymb"].strip().upper()
        expiry = date.fromisoformat(r["XpryDt"])
        if kind == "STF":
            futures_oi[symbol][expiry] = int(float(r["OpnIntrst"] or 0))
            if r.get("UndrlygPric"):
                day.spot[symbol] = float(r["UndrlygPric"])
            continue
        lot = int(float(r["NewBrdLotQty"] or 0)) or 1
        options[symbol].append(OptionQuote(
            symbol=symbol, expiry=expiry, strike=float(r["StrkPric"]),
            option_type=OptionType(r["OptnTp"]), close=float(r["ClsPric"] or 0),
            oi_lots=int(float(r["OpnIntrst"] or 0)) // lot,
            volume=int(float(r["TtlTradgVol"] or 0)), lot_size=lot,
        ))
    day.futures_oi = dict(futures_oi)
    day.options = dict(options)
    return day
