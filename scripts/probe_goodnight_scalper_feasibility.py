#!/usr/bin/env python3
"""
QuantOS — "Good Night" Open-Price Stock-Options Scalper: Feasibility Probe (candidate 20, pre-methodology)
────────────────────────────────────────────────────────────────────────────
Read-only, no orders. Before committing to a pre-registered methodology
doc for this candidate (an Open==Low/Open==High/cross-back-through-open
09:15-09:18 IST signal on individual Nifty200 Momentum 30 stock options,
+10%/-15% premium exit by 09:30 IST), this checks the concrete feasibility
risks flagged before any code was written:

1. 1-minute historical depth per stock -- candidate 18 found Fyers retains
   only ~28-29 days of 1m history for NIFTY/BankNifty/VIX, and unlike that
   candidate, THIS strategy cannot fall back to 5-minute bars (the signal
   is only meaningful at 1m resolution inside a 15-minute window). If the
   same wall applies here, it directly caps how much backtest history is
   possible.
2. How often "Open==Low" / "Open==High" (exact tick match) actually occurs
   on real 1-minute data, over whatever window is available -- the spec's
   own condition is fragile enough that its real hit-rate needs checking
   before assuming it's a usable signal at all. Reports a small-tolerance
   near-miss rate alongside the exact match, since real tick data may
   round differently than a course description assumes.
3. Stock-option expiry cadence/DTE structure (confirms whether stock
   options are monthly-only, unlike NIFTY's weekly cadence -- changes how
   often the spec's ">=2 DTE" floor would ever actually bind).
4. A live ATM CE/PE bid-ask spread read for a handful of names -- not
   specifically the 09:15-09:18 IST window (this probe runs whenever it's
   run), but a first-pass liquidity sanity check, same disclosed
   limitation as scripts/probe_orb_scalping_real_spreads.py's original
   single-snapshot read.

Universe: agent/universe_nifty200momentum30.txt (NSE's own published
NIFTY200 Momentum 30 index, current constituents -- the survivorship
caveat of using today's list for a historical backtest is a separate,
already-flagged methodology decision, not what this probe checks).

Usage:
    python scripts/probe_goodnight_scalper_feasibility.py
    python scripts/probe_goodnight_scalper_feasibility.py --liquidity-sample 8
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import _load_universe, load_config  # noqa: E402
from core.brokers import get_broker  # noqa: E402
from core.options import fyers_symbol_master as sm  # noqa: E402

UNIVERSE_PATH = "agent/universe_nifty200momentum30.txt"

# Same ladder/window shape as scripts/probe_1min_depth.py, for direct
# comparability with candidate 18's own finding.
PROBE_DAYS_AGO = [7, 10, 13, 16, 19, 22, 25, 28, 30, 35, 45, 60, 90]
WINDOW_DAYS = 3

OPEN_TIME_UTC = time(3, 45)   # 09:15 IST
RECENT_DAYS_FOR_OPEN_CHECK = 10   # comfortably inside even a ~28-day wall
NEAR_MISS_TOLERANCE_PCT = 0.05    # within 0.05% of open counts as a "near miss"


def probe_1min_depth(broker, symbol: str) -> int | None:
    now = datetime.now(timezone.utc)
    last_good = None
    for days_ago in PROBE_DAYS_AGO:
        to_dt = now - timedelta(days=days_ago)
        from_dt = to_dt - timedelta(days=WINDOW_DAYS)
        try:
            candles = broker.get_historical_data(symbol, "1m", from_dt, to_dt)
        except Exception as e:
            print(f"    {days_ago:>3}d ago: ERROR {e}")
            break
        if not candles:
            break
        last_good = days_ago
    return last_good


def probe_open_price_pattern(broker, symbol: str) -> dict:
    now = datetime.now(timezone.utc)
    from_dt = now - timedelta(days=RECENT_DAYS_FOR_OPEN_CHECK)
    try:
        candles = broker.get_historical_data(symbol, "1m", from_dt, now)
    except Exception as e:
        return {"error": str(e)}
    by_day: dict[date, list] = {}
    for c in candles:
        if c.timestamp.time() == OPEN_TIME_UTC:
            by_day.setdefault(c.timestamp.date(), []).append(c)
    exact_low = exact_high = near_low = near_high = 0
    days_checked = 0
    for day_candles in by_day.values():
        c = day_candles[0]
        days_checked += 1
        if c.open == c.low:
            exact_low += 1
        elif abs(c.open - c.low) / c.open * 100 <= NEAR_MISS_TOLERANCE_PCT:
            near_low += 1
        if c.open == c.high:
            exact_high += 1
        elif abs(c.high - c.open) / c.open * 100 <= NEAR_MISS_TOLERANCE_PCT:
            near_high += 1
    return {"days_checked": days_checked, "exact_low": exact_low, "exact_high": exact_high,
            "near_low": near_low, "near_high": near_high}


def probe_expiry_structure(underlying: str) -> dict:
    try:
        expiries = sm.list_expiries(underlying)
    except Exception as e:
        return {"error": str(e)}
    today = date.today()
    gaps = [(expiries[i + 1] - expiries[i]).days for i in range(len(expiries) - 1)]
    return {"count": len(expiries), "nearest_dte": (expiries[0] - today).days if expiries else None,
            "gaps_days": gaps}


def probe_liquidity(broker, underlying: str) -> dict:
    try:
        expiries = sm.list_expiries(underlying)
        if not expiries:
            return {"error": "no expiries listed"}
        expiry = expiries[0]
        expiry_epoch = sm.get_expiry_epoch(underlying, expiry)
        spot = broker.get_ltp([underlying]).get(underlying)
        raw_chain = broker.get_option_chain(underlying, expiry_epoch)
    except Exception as e:
        return {"error": str(e)}
    rows = raw_chain.get("optionsChain", [])
    strikes = sorted({r["strike_price"] for r in rows if r.get("strike_price", -1) > 0})
    if not strikes or spot is None:
        return {"error": "no strikes/spot available"}
    atm = min(strikes, key=lambda s: abs(s - spot))
    result = {"expiry": expiry.isoformat(), "spot": spot, "atm_strike": atm}
    for opt_type in ("CE", "PE"):
        row = next((r for r in rows if r.get("strike_price") == atm and r.get("option_type") == opt_type), None)
        if not row:
            result[opt_type] = "not found"
            continue
        bid, ask = row.get("bid", 0), row.get("ask", 0)
        mid = (bid + ask) / 2 if (bid and ask) else None
        spread_pct = (ask - bid) / mid * 100 if mid else None
        result[opt_type] = {"bid": bid, "ask": ask, "ltp": row.get("ltp"),
                             "spread_pct_of_mid": round(spread_pct, 3) if spread_pct is not None else "n/a"}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--liquidity-sample", type=int, default=6,
                         help="How many universe symbols to check live option-chain liquidity for (default 6).")
    args = parser.parse_args()

    universe = _load_universe(UNIVERSE_PATH)
    print(f"Universe: {len(universe)} symbols from {UNIVERSE_PATH}\n")

    config = load_config("agent/config.yaml")
    broker = get_broker(config)
    if not broker.connect():
        print("ERROR: broker connect() failed -- check the Fyers token.")
        return 1

    print("=== 1. 1-minute historical depth per symbol ===")
    depths = {}
    for symbol in universe:
        depth = probe_1min_depth(broker, symbol)
        depths[symbol] = depth
        print(f"  {symbol:<14} confirmed depth: {depth if depth is not None else 'NONE'} days")
    good = {s: d for s, d in depths.items() if d}
    if good:
        print(f"\n  Shallowest confirmed depth across the universe: {min(good.values())} days "
              f"({min(good, key=good.get)})")

    print("\n=== 2. Open==Low / Open==High real hit-rate (last "
          f"{RECENT_DAYS_FOR_OPEN_CHECK} days) ===")
    for symbol in universe:
        r = probe_open_price_pattern(broker, symbol)
        if "error" in r:
            print(f"  {symbol:<14} ERROR {r['error']}")
            continue
        print(f"  {symbol:<14} days={r['days_checked']:>2}  "
              f"exact_low={r['exact_low']} near_low={r['near_low']}  "
              f"exact_high={r['exact_high']} near_high={r['near_high']}")

    print("\n=== 3. Stock-option expiry structure ===")
    for symbol in universe:
        r = probe_expiry_structure(symbol)
        if "error" in r:
            print(f"  {symbol:<14} ERROR {r['error']}")
            continue
        print(f"  {symbol:<14} {r['count']} expiries listed, nearest DTE={r['nearest_dte']}, "
              f"gaps(days)={r['gaps_days'][:4]}")

    print(f"\n=== 4. Live ATM CE/PE spread sample (first {args.liquidity_sample} symbols) ===")
    for symbol in universe[:args.liquidity_sample]:
        r = probe_liquidity(broker, symbol)
        print(f"  {symbol}: {r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
