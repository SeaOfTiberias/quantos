#!/usr/bin/env python3
"""
Desk E1 spread calibration (docs/E1_RESULTS_VOL_PREREG_2026-11-27.md): live bid/ask of at-the-money
stock options, read-only Fyers quotes, no orders. Run on the VM (Fyers token + static IP) at 10:30,
12:30 and 14:30 IST on 2026-11-30; each run appends to one CSV.

    python scripts/calibrate_option_spreads.py --out ~/.quantos/e1_spreads_20261130.csv
    python scripts/calibrate_option_spreads.py --summary ~/.quantos/e1_spreads_20261130.csv

Sample: every 5th stock of the F&O stock-option list (Fyers symbol master, alphabetical, starting
with the first). Per stock: spot = last traded price of the equity; expiry = the nearest option
expiry; strike = the listed strike nearest spot (ties to the lower); both the call and the put are
quoted. A leg with no bid or no ask is recorded and excluded from h.

h = mean over all quoted legs of (ask - bid) / 2 / mid.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

IST = timezone(timedelta(hours=5, minutes=30))
STEP = 5
FIELDS = ["ts_ist", "symbol", "spot", "expiry", "strike", "right", "bid", "ask", "mid", "half_spread_frac", "status"]


def sample(underlyings: list[str], step: int = STEP) -> list[str]:
    return sorted(set(underlyings))[::step]


def atm_strike(strikes: list[float], spot: float) -> float:
    return min(strikes, key=lambda k: (abs(k - spot), k))


def leg_row(ts, sym, spot, exp, k, right, v: dict) -> dict:
    bid, ask = float(v.get("bid") or 0), float(v.get("ask") or 0)
    if bid <= 0 or ask <= 0 or ask < bid:
        return dict(ts_ist=ts, symbol=sym, spot=spot, expiry=exp, strike=k, right=right, bid=bid, ask=ask,
                    mid="", half_spread_frac="", status="no two-sided quote")
    mid = (bid + ask) / 2
    return dict(ts_ist=ts, symbol=sym, spot=spot, expiry=exp, strike=k, right=right, bid=bid, ask=ask,
                mid=round(mid, 4), half_spread_frac=round((ask - bid) / 2 / mid, 6), status="ok")


def summarize(rows: list[dict]) -> dict:
    ok = [float(r["half_spread_frac"]) for r in rows if r["status"] == "ok"]
    return dict(legs=len(rows), quoted=len(ok), excluded=len(rows) - len(ok),
                h_mean=statistics.mean(ok) if ok else float("nan"),
                h_median=statistics.median(ok) if ok else float("nan"),
                h_p75=statistics.quantiles(ok, n=4)[2] if len(ok) > 3 else float("nan"))


def run(out: Path) -> int:
    from core.mcp_tools.live import LiveMarket
    from core.options import fyers_symbol_master as fsm
    m = LiveMarket()
    text = fsm._load_master_text("NSE_FO")
    rows_all = list(csv.reader(text.splitlines()))
    unders = [r[fsm._COL_UNDERLYING] for r in rows_all if len(r) > fsm._COL_OPTION_TYPE and r[fsm._COL_INSTRUMENT_TYPE] == "15"]
    picks = sample(unders)
    ts = datetime.now(IST).strftime("%Y-%m-%d %H:%M")
    today = datetime.now(IST).date()
    out_rows = []
    for sym in picks:
        try:
            eq = m.client.quotes({"symbols": f"NSE:{sym}-EQ"})["d"][0]["v"]
            spot = float(eq["lp"])
            rs = [r for r in fsm._parse_rows(text, sym) if fsm._row_expiry(r) >= today]
            exp = min(fsm._row_expiry(r) for r in rs)
            rs = [r for r in rs if fsm._row_expiry(r) == exp]
            k = atm_strike(sorted({float(r[fsm._COL_STRIKE]) for r in rs}), spot)
            legs = {r[fsm._COL_OPTION_TYPE]: r[fsm._COL_FYERS_SYMBOL] for r in rs if float(r[fsm._COL_STRIKE]) == k}
            q = m.quotes([legs["CE"], legs["PE"]])
            for right in ("CE", "PE"):
                out_rows.append(leg_row(ts, sym, spot, exp.isoformat(), k, right, q.get(legs[right], {})))
        except Exception as e:                       # one bad symbol never stops the sample
            out_rows.append(dict(ts_ist=ts, symbol=sym, spot="", expiry="", strike="", right="", bid="", ask="",
                                 mid="", half_spread_frac="", status=f"error: {str(e)[:80]}"))
    new = not out.exists()
    with out.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerows(out_rows)
    print(f"{ts}: {len(picks)} stocks, {summarize(out_rows)}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--summary", type=Path)
    a = ap.parse_args(argv)
    if a.summary:
        with a.summary.expanduser().open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for t in sorted({r["ts_ist"] for r in rows}):
            print(t, summarize([r for r in rows if r["ts_ist"] == t]))
        print("ALL", summarize(rows))
        return 0
    return run(a.out.expanduser())


if __name__ == "__main__":
    raise SystemExit(main())
