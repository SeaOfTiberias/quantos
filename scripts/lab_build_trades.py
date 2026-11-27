#!/usr/bin/env python3
"""
Build the Strategy Lab's trade files (cockpit #/lab, research/lab/strategies.json) in one schema:

    trade_id, symbol, side, entry_time, entry_price, exit_time, exit_price, qty, gross, cost, net, chart_symbol, note

`gross/cost/net` are in the strategy's `pnl_unit` (registry): rupees or bps of notional. `chart_symbol`
is the daily-bar symbol the page draws candles for (an index or stock), blank if none.

    python scripts/lab_build_trades.py            # every converter whose source exists
    python scripts/lab_build_trades.py e3_overnight

Converters read results already on disk; nothing is re-tuned. E3 re-reads the cached bhavcopy
(about 2-3 minutes) through the pre-registered script's own functions.
"""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = Path("research/lab/trades")
FIELDS = ["trade_id", "symbol", "side", "entry_time", "entry_price", "exit_time", "exit_price", "qty",
          "gross", "cost", "net", "chart_symbol", "note"]


def _r(x, n=2):
    return "" if x is None else round(float(x), n)


def write(name: str, rows: list[dict]) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for i, r in enumerate(rows, 1):
            w.writerow({"trade_id": i, **{k: r.get(k, "") for k in FIELDS if k != "trade_id"}})
    print(f"{p}: {len(rows)} trades")
    return p


def breakout_1010() -> list[dict]:
    """docs/BREAKOUT_1010_RESULTS.csv: BANKNIFTY option premiums (Black-Scholes, not traded prices)."""
    out = []
    with open("docs/BREAKOUT_1010_RESULTS.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append(dict(symbol="BANKNIFTY option (modelled)", side="long", entry_time=r["entry_date"],
                            entry_price=_r(r["entry_premium"]), exit_time=r["exit_date"], exit_price=_r(r["exit_premium"]),
                            qty="", gross=_r(r["profit_inr"]), cost=_r(r["costs_inr"]), net=_r(r["net_profit_inr"]),
                            chart_symbol="BANKNIFTY", note=f"net {r['net_profit_pct']}% · {r['bars_held']} bars"))
    return out


def ml_factor() -> list[dict]:
    """docs/ML_FACTOR_COMBINATION_RESULTS.trades.csv, the ML run only (the baseline is the comparator).
    Per-trade costs aren't in the file: net = gross here; the run's total cost is in its results doc."""
    out = []
    with open("docs/ML_FACTOR_COMBINATION_RESULTS.trades.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["run"] != "ml_net":
                continue
            g = (float(r["exit_price"]) - float(r["entry_price"])) * float(r["qty"])
            out.append(dict(symbol=r["symbol"], side="long", entry_time=r["entry_date"][:10],
                            entry_price=_r(r["entry_price"]), exit_time=r["exit_date"][:10], exit_price=_r(r["exit_price"]),
                            qty=r["qty"], gross=_r(g), cost="", net=_r(g), chart_symbol=r["symbol"],
                            note=f"{r['exit_reason']} · per-trade cost not recorded"))
    return out


def e3_overnight() -> list[dict]:
    """Every pre-registered night (scripts/measure_overnight_futures.py): bps of notional, verdict costs."""
    from core.fno import bhavcopy_futures as bf
    from core.reference.calendar import next_trading_day
    from scripts import measure_overnight_futures as mo
    data = bf.load(mo.START, date.today())
    out = []
    for sym in mo.SYMBOLS:
        for n in mo.nights(data, sym, next_trading_day):
            g, c = n.overnight * 1e4, mo.cost_2026(n)
            out.append(dict(symbol=f"{sym} FUT {n.expiry:%b%y}".upper(), side="long",
                            entry_time=f"{n.d} 15:30", entry_price=_r(n.close_d), exit_time=f"{n.nxt} 09:15",
                            exit_price=_r(n.open_next), qty="1 lot", gross=_r(g), cost=_r(c), net=_r(g - c),
                            chart_symbol=sym, note="close = last-30-min VWAP"))
    out.sort(key=lambda r: (r["entry_time"], r["symbol"]))
    return out


CONVERTERS = {"breakout_1010": breakout_1010, "ml_factor": ml_factor, "e3_overnight": e3_overnight}


def main(argv=None) -> int:
    names = (argv if argv is not None else sys.argv[1:]) or list(CONVERTERS)
    for n in names:
        write(n, CONVERTERS[n]())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
