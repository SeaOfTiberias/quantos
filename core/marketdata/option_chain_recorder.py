"""
QuantOS — NIFTY / BANKNIFTY option-chain recorder (pure part)
─────────────────────────────────────────────────────────────
Built 2026-09-30 at the user's suggestion: record the real option market every
minute instead of learning option pricing from strategy trades. Candidate 18's
backtest verdict turned on an ASSUMED time-decay model (the backtest has to
rebuild 4.5 years of expired option prices from the index and VIX). A month of
real minute-by-minute chains replaces that assumption with data: how premiums
actually decay intraday and over weekends, near-expiry behaviour, spreads, OI
build-up. It also lets any strategy be replayed on real option prices.

One Fyers optionchain call per (index, expiry) returns every strike near the
money (bid / ask / LTP / volume / OI / OI change) plus the index LTP, the
near-month FUTURES price, India VIX, and total call / put OI. This module only
flattens that response into rows; scripts/record_option_chains.py does the
fetching and writing. Read-only: no orders, ever.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

COLUMNS = [
    "sampled_at_utc", "underlying", "expiry", "expiry_flag", "days_to_expiry",
    "spot", "future", "vix", "total_call_oi", "total_put_oi",
    "strike", "option_type", "symbol", "bid", "ask", "ltp", "volume", "oi", "oi_change", "prev_oi",
]


def recorder_dir() -> Path:
    return Path.home() / ".quantos" / "option_chains"


def parse_expiries(data: dict) -> list[tuple[date, str, str]]:
    """(expiry date, epoch string, flag W/M) for each listed expiry, soonest first."""
    out = []
    for e in data.get("expiryData", []) or []:
        try:
            d = datetime.strptime(e["date"], "%d-%m-%Y").date()
        except (KeyError, ValueError):
            continue
        out.append((d, str(e.get("expiry", "")), e.get("expiry_flag", "")))
    return sorted(out)


def flatten(data: dict, underlying: str, expiry: date, expiry_flag: str,
            sampled_at: datetime) -> list[dict]:
    """One row per option contract in the chain response, each carrying the
    index / futures / VIX / total-OI context sampled in the same call."""
    rows = data.get("optionsChain", []) or []
    index_row = next((r for r in rows if not r.get("option_type")), {})
    vix = (data.get("indiavixData") or {}).get("ltp")
    base = {
        "sampled_at_utc": sampled_at.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "underlying": underlying, "expiry": expiry.isoformat(), "expiry_flag": expiry_flag,
        "days_to_expiry": (expiry - sampled_at.date()).days,
        "spot": index_row.get("ltp"), "future": index_row.get("fp"), "vix": vix,
        "total_call_oi": data.get("callOi"), "total_put_oi": data.get("putOi"),
    }
    out = []
    for r in rows:
        if r.get("option_type") not in ("CE", "PE"):
            continue
        out.append(base | {
            "strike": r.get("strike_price"), "option_type": r.get("option_type"), "symbol": r.get("symbol"),
            "bid": r.get("bid"), "ask": r.get("ask"), "ltp": r.get("ltp"), "volume": r.get("volume"),
            "oi": r.get("oi"), "oi_change": r.get("oich"), "prev_oi": r.get("prev_oi"),
        })
    return out


def append_rows(rows: list[dict], underlying: str, day: date, base: Optional[Path] = None) -> Path:
    """Append to <base>/<YYYY-MM-DD>/<UNDERLYING>.csv, writing the header once."""
    path = (base or recorder_dir()) / day.isoformat() / f"{underlying}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerows(rows)
    return path
