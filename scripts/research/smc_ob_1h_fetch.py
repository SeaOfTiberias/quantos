#!/usr/bin/env python3
"""Fetch and freeze the data for docs/NIFTY_SMC_OB_1H_PREREG_2026-11-22.md (step 1). Run ON THE VM
(Fyers whitelists its IP), with a fresh Fyers token:

    cd ~/quantos && .venv/bin/python scripts/research/smc_ob_1h_fetch.py

Writes ~/.quantos/research/smc_ob_1h/ :
  NIFTY_60.csv, NIFTY_5.csv, INDIAVIX_60.csv, INDIAVIX_5.csv   ts_ist,o,h,l,c (Fyers; 2017-11-22..END)
  NIFTY_daily.csv                                               a snapshot of ~/.quantos/index_bars/NIFTY.csv
  SHA256SUMS
Fyers keeps a rolling 9-year intraday window (probed 2026-11-22: first bar 2017-11-22 09:15 IST), so the
files are fetched once and never re-fetched for this test.
"""
from __future__ import annotations

import csv
import hashlib
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

IST = timezone(timedelta(hours=5, minutes=30))
START = datetime(2017, 11, 22, tzinfo=IST)
END = datetime(2026, 11, 20, 23, 59, tzinfo=IST)
CHUNK_DAYS = 90                 # Fyers caps minute-resolution requests at 100 days
OUT = Path.home() / ".quantos" / "research" / "smc_ob_1h"
SERIES = [("NIFTY 50", "NIFTY"), ("INDIA VIX", "INDIAVIX")]
TFS = [("1h", "60"), ("5m", "5")]


def fetch(broker, sym: str, tf: str) -> list[tuple]:
    rows, t = {}, START
    while t <= END:
        u = min(t + timedelta(days=CHUNK_DAYS), END)
        for attempt in range(4):
            try:
                for c in broker.get_historical_data(sym, tf, t.astimezone(timezone.utc), u.astimezone(timezone.utc)):
                    ts = c.timestamp.astimezone(IST)
                    rows[ts] = (ts.strftime("%Y-%m-%d %H:%M"), c.open, c.high, c.low, c.close)
                break
            except Exception as e:                                   # noqa: BLE001
                if attempt == 3:
                    raise SystemExit(f"{sym} {tf} {t.date()}..{u.date()} failed: {e}")
                time.sleep(6)
        time.sleep(0.4)
        t = u + timedelta(minutes=1)
    return [rows[k] for k in sorted(rows)]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    from agent.main import load_config
    from core.brokers import get_broker
    b = get_broker(load_config("agent/config.yaml"))
    if not b.connect():
        print("Fyers connect failed: refresh the token")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    if any(OUT.glob("*.csv")):
        print(f"{OUT} already holds files: frozen data is never re-fetched")
        return 1
    for sym, name in SERIES:
        for tf, label in TFS:
            rows = fetch(b, sym, tf)
            p = OUT / f"{name}_{label}.csv"
            with p.open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["ts_ist", "o", "h", "l", "c"])
                w.writerows(rows)
            print(f"{p.name}: {len(rows)} bars, {rows[0][0]} .. {rows[-1][0]}")
    shutil.copy(Path.home() / ".quantos" / "index_bars" / "NIFTY.csv", OUT / "NIFTY_daily.csv")
    sums = "\n".join(f"{sha(p)}  {p.name}" for p in sorted(OUT.glob("*.csv"))) + "\n"
    (OUT / "SHA256SUMS").write_text(sums)
    print(sums)
    return 0


if __name__ == "__main__":
    sys.exit(main())
