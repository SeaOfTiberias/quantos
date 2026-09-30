#!/usr/bin/env python3
"""
QuantOS — record NIFTY / BANKNIFTY option chains every minute (read-only)
──────────────────────────────────────────────────────────────────────────
Fired every minute during NSE market hours by quantos-option-chain-recorder.timer
(at :50 past the minute, clear of the ORB units at :00 / :20 / :40). For each
index, the two nearest expiries: one Fyers optionchain call each, +-STRIKE_COUNT
strikes around the money, CE and PE, with the index, futures and VIX context.
Rows append to ~/.quantos/option_chains/<YYYY-MM-DD>/<UNDERLYING>.csv. See
core/marketdata/option_chain_recorder.py for why this exists.

Never places an order. A failed call is logged and skipped; the next minute
simply records again.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers import get_broker  # noqa: E402
from core.marketdata.option_chain_recorder import append_rows, flatten, parse_expiries, recorder_dir  # noqa: E402

INDICES = (("NIFTY", "NSE:NIFTY50-INDEX"), ("BANKNIFTY", "NSE:NIFTYBANK-INDEX"))
EXPIRIES_PER_INDEX = 2
STRIKE_COUNT = 10            # +-10 strikes around ATM, CE and PE
CALL_SPACING_SECONDS = 0.4   # stay well inside Fyers' per-second limit


def _log_coverage(now: datetime, underlying: str, ok: int, failed: int, rows: int,
                  latency_ms: float, note: str = "") -> None:
    """One line per index per minute (Fable P0, 2026-09-30): without it a missing
    minute is indistinguishable from "no data", and a dead broker has hidden behind
    green health signals before. Also flags a response with no futures price or
    VIX, since derived IV depends on both."""
    path = recorder_dir() / now.date().isoformat() / "coverage.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", encoding="utf-8") as fh:
        if new:
            fh.write("sampled_at_utc,underlying,calls_ok,calls_failed,rows,latency_ms,note" + chr(10))
        fh.write(f"{now.isoformat(timespec='seconds')},{underlying},{ok},{failed},{rows},{latency_ms:.0f},{note}"
                 + chr(10))


def record_index(client, underlying: str, fyers_symbol: str, now: datetime) -> int:
    """Nearest expiry first (its response carries the expiry list), then the next."""
    t0, ok, failed, notes = time.monotonic(), 0, 0, []
    first = client.optionchain(data={"symbol": fyers_symbol, "strikecount": STRIKE_COUNT, "timestamp": ""})
    if first.get("code") != 200:
        _log_coverage(now, underlying, 0, 1, 0, (time.monotonic() - t0) * 1000, "first call failed")
        raise RuntimeError(f"optionchain failed: {first}")
    ok += 1
    data = first.get("data", {})
    expiries = parse_expiries(data)[:EXPIRIES_PER_INDEX]
    if not expiries:
        raise RuntimeError("no expiries in the chain response")
    written = 0
    for i, (exp, epoch, flag) in enumerate(expiries):
        if i > 0:
            time.sleep(CALL_SPACING_SECONDS)
            resp = client.optionchain(data={"symbol": fyers_symbol, "strikecount": STRIKE_COUNT, "timestamp": epoch})
            if resp.get("code") != 200:
                failed += 1
                print(f"  {underlying} {exp}: optionchain failed ({resp.get('message')}) -- skipped this minute.")
                continue
            ok += 1
            data = resp.get("data", {})
        rows = flatten(data, underlying, exp, flag, now)
        if rows and (rows[0]["future"] is None or rows[0]["vix"] is None):
            notes.append(f"{exp} missing {'future' if rows[0]['future'] is None else 'vix'}")
        append_rows(rows, underlying, now.date())
        written += len(rows)
    _log_coverage(now, underlying, ok, failed, written, (time.monotonic() - t0) * 1000, "; ".join(notes))
    return written


def main() -> int:
    broker = get_broker(load_config("agent/config.yaml"))
    if not broker.connect():
        print("ERROR: broker connect() failed -- check the Fyers token.")
        return 1
    now = datetime.now(timezone.utc)
    for underlying, symbol in INDICES:
        try:
            n = record_index(broker._client, underlying, symbol, now)
            print(f"  {underlying}: recorded {n} contracts.")
        except Exception as e:
            print(f"  {underlying}: recording failed ({e}) -- next minute retries.")
        time.sleep(CALL_SPACING_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
