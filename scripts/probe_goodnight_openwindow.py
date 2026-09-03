#!/usr/bin/env python3
"""
QuantOS — "Good Night" Scalper: Real At-Open Window Probe (candidate 20, feasibility)
──────────────────────────────────────────────────────────────────────
Read-only, no orders. docs/GOODNIGHT_SCALPER_FEASIBILITY.md's one open
item: every liquidity number so far was read MID-SESSION, not at the
strategy's actual 09:15:30-09:18:00 IST entry window where liquidity is
thinnest. This is the properly-timed measurement -- designed to fire
2-3 times across that exact window on a real trading morning (see
deploy/systemd/quantos-goodnight-openwindow-probe.timer, one-time fires).

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

Every row is timestamped and appended (not deduped) to
data_cache/goodnight_openwindow_probe.csv -- multiple fires across the
window are intentional here (unlike the stop-out probe's one-event-per-
day design): they show whether spread is stable or moving within the
strategy's own stated entry window.

Depends on the VM's Fyers token already being freshly refreshed before
this fires -- same as every other morning-scheduled job. A stale token
fails this run harmlessly (no orders, self-healing next trading day).

Usage:
    python scripts/probe_goodnight_openwindow.py
"""

from __future__ import annotations

import csv
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


def main() -> int:
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
