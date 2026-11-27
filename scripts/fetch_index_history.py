#!/usr/bin/env python3
"""
QuantOS — daily index history from Fyers, for the Alpha 50 rebuild (2026-11-27)
────────────────────────────────────────────────────────────────────────────────
Read-only. Pulls daily OHLC for NIFTY Alpha 50, NIFTY 50 and NIFTY 500 in 360-day
chunks and writes one CSV per index (date, open, high, low, close) to data_cache/indices/.
Public market data, no account fields.

    .venv/bin/python scripts/fetch_index_history.py --from 2015-01-01 --to 2026-11-26
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

INDICES = {"NIFTYALPHA50": "NSE:NIFTYALPHA50-INDEX", "NIFTY50": "NSE:NIFTY50-INDEX",
           "NIFTY500": "NSE:NIFTY500-INDEX"}
OUT = Path("data_cache/indices")
IST = timezone(timedelta(hours=5, minutes=30))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2015-01-01")
    ap.add_argument("--to", dest="end", default=date.today().isoformat())
    a = ap.parse_args(argv)
    import yaml
    from core.brokers import FyersBroker
    b = FyersBroker(yaml.safe_load(Path("agent/config.yaml").read_text()))
    b.connect()
    OUT.mkdir(parents=True, exist_ok=True)
    start, end = date.fromisoformat(a.start), date.fromisoformat(a.end)
    for name, sym in INDICES.items():
        rows, d = {}, start
        while d <= end:
            e = min(end, d + timedelta(days=359))
            r = b._client.history(data={"symbol": sym, "resolution": "D", "date_format": "1",
                                        "range_from": d.isoformat(), "range_to": e.isoformat(), "cont_flag": "1"})
            if r.get("code") != 200 and r.get("s") != "no_data":
                raise SystemExit(f"{name} {d}..{e}: code {r.get('code')} {r.get('message')}")
            for c in r.get("candles", []):
                day = datetime.fromtimestamp(c[0], tz=IST).date().isoformat()
                rows[day] = (c[1], c[2], c[3], c[4])
            d = e + timedelta(days=1)
            time.sleep(0.4)
        path = OUT / f"{name}.csv"
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "open", "high", "low", "close"])
            for day in sorted(rows):
                w.writerow([day, *rows[day]])
        days = sorted(rows)
        print(f"{name}: {len(days)} days, {days[0] if days else '-'} .. {days[-1] if days else '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
