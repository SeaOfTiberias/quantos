#!/usr/bin/env python3
"""
QuantOS — fetch the bars for the price-map zone test (on the VM)
────────────────────────────────────────────────────────────────
docs/PRICE_MAP_ZONES_PREREG_2026-10-28.md, amendment 1 B: every F&O stock's
Fyers daily bars from 2024-06-01 and 5-minute bars from 2025-07-20, both to
2026-11-03, cached once as ~/.quantos/zone_test_bars/<SYMBOL>.json.gz
([epoch, o, h, l, c, v] rows). scripts/run_zone_test.py slices them per day.

    python scripts/fetch_zone_test_bars.py [--pause 0.35] [SYMBOL ...]

Resumable: a symbol already cached is skipped. Stops at a Fyers rate-limit
refusal. Places no orders. Public market data only.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

IST = timezone(timedelta(hours=5, minutes=30))
OUT = Path.home() / ".quantos" / "zone_test_bars"
DAILY_FROM = datetime(2024, 6, 1, tzinfo=IST)
INTRADAY_FROM = datetime(2025, 7, 20, tzinfo=IST)
TO = datetime(2026, 11, 3, 23, 59, tzinfo=IST)
DAILY_CHUNK, INTRADAY_CHUNK = 365, 99          # Fyers: 366 days of daily, 100 of 5-minute per call


def chunks(start: datetime, end: datetime, days: int):
    while start < end:
        stop = min(start + timedelta(days=days), end)
        yield start, stop
        start = stop + timedelta(seconds=1)


def fetch(broker, fyers_symbol: str, tf: str, start: datetime, days: int, pause: float) -> list[list]:
    rows: dict[int, list] = {}
    for a, b in chunks(start, TO, days):
        try:
            got = broker.get_historical_data(fyers_symbol, tf, a, b) or []
        except Exception as e:                # a window before listing is empty, not a failure
            if "no_data" not in str(e):
                raise
            got = []
        for bar in got:
            t = int(bar.timestamp.timestamp())
            rows[t] = [t, bar.open, bar.high, bar.low, bar.close, bar.volume]
        time.sleep(pause)
    return [rows[t] for t in sorted(rows)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbols", nargs="*", help="default: every F&O stock in the Fyers master")
    ap.add_argument("--pause", type=float, default=0.35, help="seconds between Fyers calls")
    a = ap.parse_args(argv)
    from core.mcp_tools.live import LiveMarket
    from scripts.price_map import fno_symbols
    symbols = [s.upper() for s in a.symbols] or fno_symbols()
    broker = LiveMarket("agent/config.yaml").broker
    OUT.mkdir(parents=True, exist_ok=True)
    done = skipped = failed = 0
    t0 = time.time()
    for s in symbols:
        path = OUT / f"{s}.json.gz"
        if path.exists():
            skipped += 1
            continue
        try:
            daily = fetch(broker, f"NSE:{s}-EQ", "1d", DAILY_FROM, DAILY_CHUNK, a.pause)
            intraday = fetch(broker, f"NSE:{s}-EQ", "5m", INTRADAY_FROM, INTRADAY_CHUNK, a.pause)
        except Exception as e:
            if "-360" in str(e) or "request limit" in str(e).lower():
                print(f"{s}: Fyers rate limit -- stopping after {done}")
                break
            print(f"{s}: failed ({str(e)[:120]})")
            failed += 1
            continue
        tmp = path.with_suffix(".tmp")
        with gzip.open(tmp, "wt") as f:
            json.dump({"symbol": s, "daily": daily, "intraday": intraday}, f)
        tmp.replace(path)
        done += 1
        print(f"{s}: {len(daily)} daily, {len(intraday)} 5-min ({time.time() - t0:.0f}s)", flush=True)
    print(f"done {done}, already cached {skipped}, failed {failed} -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
