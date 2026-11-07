#!/usr/bin/env python3
"""
5-minute bars from Fyers into the L1 store's m5/ folder (sprint plan S5, slice 5b).
Data only: no orders, no alerts, no change to any live job.

  --backfill   every symbol not yet backfilled, from 2017-12-01 (Fyers' first 5-minute
               bar) in 99-day requests. Resumable: a symbol is marked done only when all
               its requests succeeded, so a rerun after a dropped token picks up where it
               stopped (finished symbols are skipped).
  (default)    top-up: each symbol from its last bar to today, for the daily refresh.

Symbols: the store's top-500 list (universe.json) plus --extra (the golden set).
Throttled to stay under Fyers' per-minute limit (about 200 requests a minute).

Usage (VM):
  .venv/bin/python scripts/fetch_m5.py --backfill --extra HDFCBANK,SUPREMEIND
  .venv/bin/python scripts/fetch_m5.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.market_map.l1_store import Store  # noqa: E402
from core.market_map.m5_store import M5Store, bars_frame  # noqa: E402

START = datetime(2017, 12, 1, tzinfo=timezone.utc)
CHUNK_DAYS = 99
PAUSE = 0.15                        # seconds between requests: ~130 a minute measured with the request time


def chunks(start: datetime, end: datetime, days: int = CHUNK_DAYS) -> list[tuple[datetime, datetime]]:
    out, s = [], start
    while s < end:
        e = min(s + timedelta(days=days), end)
        out.append((s, e))
        s = e + timedelta(seconds=1)
    return out


def symbols(store: Store, extra: list[str]) -> list[str]:
    u = json.loads(store.universe_path.read_text(encoding="utf-8"))
    out = [r["sym"] for r in u["rows"]]
    return out + [x for x in extra if x not in out]


def fetch(broker, sym: str, start: datetime, end: datetime, sleep=time.sleep):
    """All bars in [start, end] as one frame; raises if any request fails."""
    frames = []
    for s, e in chunks(start, end):
        try:
            bars = broker.get_historical_data(f"NSE:{sym}-EQ", "5m", s, e) or []
        except Exception as ex:
            if "no_data" not in str(ex):
                raise
            bars = []                        # a window before the listing: Fyers says no_data
        frames.append(bars_frame(bars))
        sleep(PAUSE)
    import pandas as pd
    return pd.concat(frames) if frames else bars_frame([])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--extra", default="")
    ap.add_argument("--limit", type=int, default=None, help="at most this many symbols (a test run)")
    ap.add_argument("--config", default="agent/config.yaml")
    a = ap.parse_args(argv)
    logging.disable(logging.INFO)          # the broker's connect log names the account holder

    store = Store(a.root)
    m5 = M5Store(store.root)
    syms = symbols(store, [x.strip().upper() for x in a.extra.split(",") if x.strip()])
    from agent.main import load_config
    from core.brokers import get_broker
    b = get_broker(load_config(a.config))
    if not b.connect():
        print("ERROR: Fyers connect() failed -- refresh the token")
        return 2
    now = datetime.now(timezone.utc)
    basis = now.date().isoformat()           # Fyers' bars are adjusted up to this day (m5_store)
    state = m5.state()
    todo = [s for s in syms if not (a.backfill and state.get(s, {}).get("backfilled"))]
    if a.limit:
        todo = todo[:a.limit]
    t0, done, failed = time.time(), 0, []
    for i, sym in enumerate(todo, 1):
        st = state.get(sym, {})
        if a.backfill:
            start = START
        elif st.get("last_ts"):
            start = datetime.fromtimestamp(st["last_ts"], timezone.utc) + timedelta(minutes=5)
        else:
            continue                        # never backfilled: the backfill run owns it
        try:
            rows = fetch(b, sym, start, now)
        except Exception as e:
            failed.append((sym, str(e)[:120]))
            print(f"[{i}/{len(todo)}] {sym}: FAILED {str(e)[:120]}", flush=True)
            if "token" in str(e).lower() or "auth" in str(e).lower():
                print("token problem: stopping; rerun after a refresh resumes here")
                break
            continue
        m5.write(sym, rows)
        last = int(rows["ts"].max()) if len(rows) else st.get("last_ts")
        m5.set_state(sym, last_ts=last, **({"backfilled": True, "basis": basis} if a.backfill else {}))
        done += 1
        if a.backfill or i % 50 == 0:
            print(f"[{i}/{len(todo)}] {sym}: {len(rows)} bars, {time.time() - t0:.0f}s", flush=True)
    print(f"m5: {done} symbol(s) {'backfilled' if a.backfill else 'topped up'}, {len(failed)} failed, "
          f"{time.time() - t0:.0f}s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
