#!/usr/bin/env python3
"""
QuantOS — 1-Minute Historical Data Depth Probe (candidate 18, Open Item #1)
────────────────────────────────────────────────────────────────────────────
docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md's Open Items list this as the
prerequisite before the backtest window can lock: every prior intraday
candidate (14, 15, expiry-day) used 5-minute-or-coarser data with depth
confirmed live before its methodology doc committed to a window; nobody
has probed 1-minute depth. This script finds where Fyers' 1m history for
NIFTY 50 / NIFTY BANK / India VIX actually stops returning data, by
querying a short window at successively older anchor points.

Read-only (get_historical_data only) — no orders, safe to run anytime,
does not require market hours.

Usage:
    python scripts/probe_1min_depth.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers import get_broker  # noqa: E402

SYMBOLS = ["NIFTY 50", "NIFTY BANK", "INDIA VIX"]

# Anchor points to probe, oldest-relevant-first assumption reversed: we walk
# backward from "recent" to "old" and stop at the first anchor that returns
# no candles for a given symbol. A 3-day window at each anchor is enough to
# clear weekends/holidays while keeping each probe request small.
PROBE_DAYS_AGO = [7, 10, 13, 16, 19, 22, 25, 28, 30, 35, 45, 60, 90, 120, 180, 270, 365]
WINDOW_DAYS = 3


def probe_symbol(broker, symbol: str) -> None:
    print(f"\n=== {symbol} ===")
    now = datetime.now(timezone.utc)
    last_good_days_ago = None
    for days_ago in PROBE_DAYS_AGO:
        to_dt = now - timedelta(days=days_ago)
        from_dt = to_dt - timedelta(days=WINDOW_DAYS)
        try:
            candles = broker.get_historical_data(symbol, "1m", from_dt, to_dt)
        except Exception as e:
            print(f"  {days_ago:>5} days ago ({from_dt.date()}..{to_dt.date()}): ERROR {e}")
            break
        n = len(candles)
        status = "OK" if n > 0 else "EMPTY"
        print(f"  {days_ago:>5} days ago ({from_dt.date()}..{to_dt.date()}): {status} ({n} candles)")
        if n > 0:
            last_good_days_ago = days_ago
        else:
            break
    if last_good_days_ago is not None:
        print(f"  -> confirmed data at least {last_good_days_ago} days back "
              f"(~{now.date() - timedelta(days=last_good_days_ago)})")
    else:
        print("  -> no 1m data found at ANY probed anchor, including 7 days ago")


def main() -> int:
    config = load_config("agent/config.yaml")
    broker = get_broker(config)
    if not broker.connect():
        print("Broker connect() returned False — check agent/config.yaml and "
              "run `python agent/auth/fyers_auth.py` if the token is stale.")
        return 1

    for symbol in SYMBOLS:
        probe_symbol(broker, symbol)

    return 0


if __name__ == "__main__":
    sys.exit(main())
