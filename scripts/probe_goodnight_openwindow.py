#!/usr/bin/env python3
"""
QuantOS — "Good Night" Scalper: Real At-Open Window Probe (candidate 20, feasibility)
──────────────────────────────────────────────────────────────────────
Read-only, no orders. docs/GOODNIGHT_SCALPER_FEASIBILITY.md's one open
item: every liquidity number before 2026-09-04 was read MID-SESSION, not
at the strategy's actual 09:15:30-09:18:00 IST entry window where
liquidity is thinnest. The first real at-open reading (2026-09-04)
confirmed spread IS wider there -- user's own framing, same day: "gather
a few more at-open sessions" before drawing any conclusion. This now
fires once per trading morning (deploy/systemd/quantos-goodnight-
openwindow-probe.timer, recurring Mon-Fri -- converted 2026-09-04 from a
same-day 3x design that didn't actually work as intended: each run takes
~2.5 minutes, so tightly-spaced same-day fires got skipped/coalesced,
and two same-day snapshots ~3 minutes apart turned out highly
correlated anyway. Days, not intra-window snapshots, is the axis that
actually adds information).

For each Nifty200 Momentum 30 symbol (agent/universe_nifty200momentum30.txt):
1. Fetch TODAY's 09:15 1-minute candle (closed -- Fyers' history endpoint
   has no "still forming" candle access, so this probes the closed
   09:15:00-09:15:59 bar rather than the spec's literal "scan the active
   candle at 09:15:30" -- a disclosed simplification appropriate for a
   feasibility check, not the execution-layer's job to fix).
2. Classifies Setup A (Open==Low -> CALL) / Setup B (Open==High -> PUT).
3. For every symbol that qualifies, AND for a fixed liquidity-sample
   subset regardless of whether it qualifies (so there's always an
   at-open reading even on a day where few stocks show the exact
   pattern), fetches the live ATM CE/PE option chain right now and logs
   the real bid-ask spread.

Every row is timestamped and appended (never deduped or overwritten) to
data_cache/goodnight_openwindow_probe.csv -- the accumulating record
across trading days.

Depends on the VM's Fyers token already being freshly refreshed before
this fires -- same as every other morning-scheduled job. A stale token
fails this run harmlessly (no orders, self-healing: just misses that
day's sample).

Usage:
    python scripts/probe_goodnight_openwindow.py
    python scripts/probe_goodnight_openwindow.py --summarize
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time as time_module
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import _load_universe, load_config  # noqa: E402
from core.brokers import get_broker  # noqa: E402
from core.options import fyers_symbol_master as sm  # noqa: E402

UNIVERSE_PATH = "agent/universe_nifty200momentum30.txt"
OPEN_CANDLE_TIME_UTC = time(3, 45)   # 09:15 IST
LIQUIDITY_SAMPLE_SIZE = 10           # always-checked subset, regardless of setup

LOG_PATH = Path("data_cache/goodnight_openwindow_probe.csv")
LOG_FIELDS = ["sampled_at_utc", "symbol", "setup", "open", "low", "high",
              "reason_checked", "expiry", "atm_strike", "option_type",
              "bid", "ask", "ltp", "spread_pct_of_mid"]

SLEEP_BETWEEN_CALLS_SECS = 2.0
MAX_RETRIES = 4
RETRY_BASE_WAIT_SECS = 6.0


def _call_with_retry(fn, *args, **kwargs):
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            result = fn(*args, **kwargs)
            time_module.sleep(SLEEP_BETWEEN_CALLS_SECS)
            return result
        except Exception as e:
            last_exc = e
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BASE_WAIT_SECS * (attempt + 1)
                print(f"    retrying in {wait:.0f}s after: {e}")
                time_module.sleep(wait)
    raise last_exc


def classify_open_candle(broker, symbol: str) -> dict:
    now = datetime.now(timezone.utc)
    session_start = datetime.combine(now.date(), OPEN_CANDLE_TIME_UTC, tzinfo=timezone.utc)
    try:
        candles = _call_with_retry(broker.get_historical_data, symbol, "1m",
                                    session_start, session_start + timedelta(minutes=2))
    except Exception as e:
        return {"error": str(e)}
    todays_open = [c for c in candles if c.timestamp.time() == OPEN_CANDLE_TIME_UTC]
    if not todays_open:
        return {"error": "no 09:15 candle available yet"}
    c = todays_open[0]
    setup = "CALL" if c.open == c.low else ("PUT" if c.open == c.high else None)
    return {"setup": setup, "open": c.open, "low": c.low, "high": c.high}


def probe_liquidity(broker, symbol: str) -> dict:
    try:
        expiries = sm.list_expiries(symbol)
        if not expiries:
            return {"error": "no expiries listed"}
        expiry = expiries[0]
        expiry_epoch = sm.get_expiry_epoch(symbol, expiry)
        spot = _call_with_retry(broker.get_ltp, [symbol]).get(symbol)
        raw_chain = _call_with_retry(broker.get_option_chain, symbol, expiry_epoch)
    except Exception as e:
        return {"error": str(e)}
    rows = raw_chain.get("optionsChain", [])
    strikes = sorted({r["strike_price"] for r in rows if r.get("strike_price", -1) > 0})
    if not strikes or spot is None:
        return {"error": "no strikes/spot available"}
    atm = min(strikes, key=lambda s: abs(s - spot))
    legs = {}
    for opt_type in ("CE", "PE"):
        row = next((r for r in rows if r.get("strike_price") == atm and r.get("option_type") == opt_type), None)
        if not row:
            continue
        bid, ask, ltp = row.get("bid", 0), row.get("ask", 0), row.get("ltp", 0)
        mid = (bid + ask) / 2 if (bid and ask) else None
        spread_pct = (ask - bid) / mid * 100 if mid else None
        legs[opt_type] = {"bid": bid, "ask": ask, "ltp": ltp,
                           "spread_pct_of_mid": round(spread_pct, 3) if spread_pct is not None else ""}
    return {"expiry": expiry.isoformat(), "atm_strike": atm, "legs": legs}


def summarize_log() -> int:
    """Groups by trading day (the DATE portion of sampled_at_utc), so
    "a few more sessions" has a concrete, checkable count -- accumulating
    across days is the whole point of the 2026-09-04 switch to a
    recurring daily timer, see this module's docstring."""
    if not LOG_PATH.exists():
        print(f"No log yet at {LOG_PATH} -- run without --summarize first.")
        return 1
    rows = list(csv.DictReader(LOG_PATH.open(newline="", encoding="utf-8")))
    days = sorted({r["sampled_at_utc"][:10] for r in rows})
    print(f"{len(rows)} total logged rows across {len(days)} trading day(s): {days}\n")

    liquidity_rows = [r for r in rows if r["reason_checked"] and r["spread_pct_of_mid"]]
    setup_rows = [r for r in rows if not r["reason_checked"] and r["setup"]]

    print(f"Setup hit-rate: {len(setup_rows)} qualifying (symbol, day) observations "
          f"out of {len([r for r in rows if not r['reason_checked']])} checked.\n")

    by_day: dict[str, list[float]] = {}
    for r in liquidity_rows:
        by_day.setdefault(r["sampled_at_utc"][:10], []).append(float(r["spread_pct_of_mid"]))
    print("Liquidity (spread_pct_of_mid) by day:")
    for day, vals in sorted(by_day.items()):
        print(f"  {day}: n={len(vals)}  mean={statistics.mean(vals):.2f}%  median={statistics.median(vals):.2f}%  "
              f"min={min(vals):.2f}%  max={max(vals):.2f}%")

    all_vals = [float(r["spread_pct_of_mid"]) for r in liquidity_rows]
    if all_vals:
        print(f"\nAll days combined: n={len(all_vals)}  mean={statistics.mean(all_vals):.2f}%  "
              f"median={statistics.median(all_vals):.2f}%")

    by_symbol: dict[str, list[float]] = {}
    for r in liquidity_rows:
        by_symbol.setdefault(r["symbol"], []).append(float(r["spread_pct_of_mid"]))
    persistent_illiquid = {s: v for s, v in by_symbol.items() if len(v) >= 2 and min(v) > 20}
    if persistent_illiquid:
        print("\nPersistently wide spread (>20% on every reading, n>=2) -- likely genuinely illiquid, not noise:")
        for s, v in sorted(persistent_illiquid.items()):
            print(f"  {s}: {[round(x, 1) for x in v]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--summarize", action="store_true", help="Print stats from the log so far, no live fetch.")
    args = parser.parse_args()

    if args.summarize:
        return summarize_log()

    universe = _load_universe(UNIVERSE_PATH)
    print(f"Universe: {len(universe)} symbols from {UNIVERSE_PATH}")

    config = load_config("agent/config.yaml")
    broker = get_broker(config)
    if not broker.connect():
        print("ERROR: broker connect() failed -- check the Fyers token (needs today's morning refresh).")
        return 1

    now_utc = datetime.now(timezone.utc)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new = not LOG_PATH.exists()
    with LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if is_new:
            writer.writeheader()

        qualifying = []
        for symbol in universe:
            r = classify_open_candle(broker, symbol)
            if "error" in r:
                print(f"  {symbol:<14} ERROR {r['error']}")
                continue
            print(f"  {symbol:<14} open={r['open']} low={r['low']} high={r['high']} setup={r['setup']}")
            if r["setup"]:
                qualifying.append(symbol)
            writer.writerow({
                "sampled_at_utc": now_utc.isoformat(), "symbol": symbol, "setup": r["setup"] or "",
                "open": r["open"], "low": r["low"], "high": r["high"],
                "reason_checked": "", "expiry": "", "atm_strike": "", "option_type": "",
                "bid": "", "ask": "", "ltp": "", "spread_pct_of_mid": "",
            })

        to_check = sorted(set(qualifying) | set(universe[:LIQUIDITY_SAMPLE_SIZE]))
        print(f"\nQualifying today: {qualifying}")
        print(f"Checking live ATM liquidity for {len(to_check)} symbols "
              f"({len(qualifying)} qualifying + always-sampled subset)...")
        for symbol in to_check:
            reason = "qualifying_setup" if symbol in qualifying else "liquidity_sample"
            r = probe_liquidity(broker, symbol)
            if "error" in r:
                print(f"  {symbol:<14} [{reason}] ERROR {r['error']}")
                continue
            for opt_type, leg in r["legs"].items():
                print(f"  {symbol:<14} [{reason}] {opt_type} spread_pct_of_mid={leg['spread_pct_of_mid']}%")
                writer.writerow({
                    "sampled_at_utc": datetime.now(timezone.utc).isoformat(), "symbol": symbol, "setup": "",
                    "open": "", "low": "", "high": "", "reason_checked": reason,
                    "expiry": r["expiry"], "atm_strike": r["atm_strike"], "option_type": opt_type,
                    "bid": leg["bid"], "ask": leg["ask"], "ltp": leg["ltp"],
                    "spread_pct_of_mid": leg["spread_pct_of_mid"],
                })

    print(f"\nAppended to {LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
