#!/usr/bin/env python3
"""
QuantOS — Candidate 18 Real Option Bid-Ask Spread Feasibility Check
──────────────────────────────────────────────────────────────────────
Read-only, no orders. Fetches a LIVE (or last-close, outside market hours)
option chain for NIFTY and BankNifty and logs the REAL bid-ask spread at
the near-the-money strike to a persistent CSV — the same follow-up check
candidate 15's methodology doc named and never got to exercise (it failed
the backtest first). Every premium in the backtest is Black-Scholes-
theoretical; this is the first time this candidate's numbers are compared
against a real, currently-quoted market price.

The first run (2026-07-28, one post-close snapshot) found NIFTY FAILS its
own bar under this cost and BankNifty barely survives -- but that was ONE
sample. This script is meant to be run repeatedly (ideally at a few times
of day, across several real trading days) to build up a real distribution
instead of trusting a single point. Each run APPENDS a row per leg to
`data_cache/orb_scalping_spread_samples.csv` (gitignored, like every other
data_cache/ path in this repo) rather than overwriting it.

Skips a near-expiry contract for NIFTY (entries happen at 09:15-09:30, with
the DTE floor already excluding <2-day contracts) — uses the same DTE
floor the live strategy actually applies.

**BankNifty does NOT get this floor** (fixed 2026-09-02, after Fable's
adversarial review of the Stratified cost variant found it had been applied
here unconditionally to both underlyings since this script was written).
core/orb_scalping/backtest.py's resolve_banknifty_expiry() has no DTE floor
— BankNifty entries on/adjacent to its own monthly expiry genuinely trade
the current month's contract at DTE 0-1, same as any real trader would see.
Applying NIFTY's floor to BankNifty here meant every BankNifty sample taken
near its own monthly expiry measured the WRONG contract (next month, DTE
~30) instead of the one the backtest actually holds — invalidating the
n=3 "expiry-day" BankNifty rate that fed core/orb_scalping/costs.py's
STRATIFIED_SPREAD_SLIPPAGE_BPS. See that module's docstring for the
disclosed consequence and current status.

Usage:
    python scripts/probe_orb_scalping_real_spreads.py
    python scripts/probe_orb_scalping_real_spreads.py --summarize   # just print stats from the log so far
"""

import argparse
import csv
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers import get_broker  # noqa: E402
from core.options import fyers_symbol_master as sm  # noqa: E402
from core.orb_scalping.contract_selection import select_expiry  # noqa: E402,F401
from core.orb_scalping.costs import (  # noqa: E402
    HARSH_FRONT_WEEK_SLIPPAGE_BPS,
    HARSH_NEXT_WEEK_SLIPPAGE_BPS,
    STRESSED_SLIPPAGE_BPS,
)

DTE_FLOOR_DAYS = 2  # same floor core/orb_scalping/backtest.py applies to NIFTY
LOG_PATH = Path("data_cache/orb_scalping_spread_samples.csv")
LOG_FIELDS = ["sampled_at_utc", "underlying", "option_type", "strike", "dte",
              "spot", "bid", "ask", "ltp", "spread_pct_of_mid"]


def _atm_rows(raw_chain: dict, spot: float):
    rows = raw_chain.get("optionsChain", [])
    strikes = sorted({r["strike_price"] for r in rows if r.get("strike_price", -1) > 0})
    if not strikes:
        return None, None
    atm_strike = min(strikes, key=lambda s: abs(s - spot))
    ce = next((r for r in rows if r.get("strike_price") == atm_strike and r.get("option_type") == "CE"), None)
    pe = next((r for r in rows if r.get("strike_price") == atm_strike and r.get("option_type") == "PE"), None)
    return ce, pe


def _leg_record(underlying: str, spot: float, dte: int, row: dict) -> dict:
    bid, ask, ltp = row.get("bid", 0), row.get("ask", 0), row.get("ltp", 0)
    mid = (bid + ask) / 2 if (bid and ask) else None
    spread_pct = (ask - bid) / mid * 100 if mid else None
    return {
        "sampled_at_utc": datetime.now(timezone.utc).isoformat(),
        "underlying": underlying, "option_type": row.get("option_type"),
        "strike": row.get("strike_price"), "dte": dte, "spot": spot,
        "bid": bid, "ask": ask, "ltp": ltp,
        "spread_pct_of_mid": round(spread_pct, 3) if spread_pct is not None else "",
    }


def _report_leg(label: str, record: dict):
    print(f"  {label}: strike={record['strike']} bid={record['bid']} ask={record['ask']} ltp={record['ltp']}")
    if record["spread_pct_of_mid"] != "":
        print(f"    spread_pct_of_mid={record['spread_pct_of_mid']}%")
    elif record["ask"] and not record["bid"]:
        print(f"    bid is 0 (no real buyer quoted) -- spread is effectively the whole ask "
              f"({record['ask']}, i.e. undefined/very wide in %% terms)")
    else:
        print("    bid/ask both 0 -- no live two-sided quote available right now")


def probe(broker, underlying: str, spot_symbol: str, writer, *, dte_floor_days: int) -> list:
    """`dte_floor_days`: minimum days-to-expiry the chosen contract must
    clear, matching whatever the real backtest applies for this underlying
    — 2 for NIFTY (core/orb_scalping/backtest.py's resolve_nifty_expiry),
    0 for BankNifty (resolve_banknifty_expiry has no floor at all). Passing
    the same value for both was the 2026-09-02 bug: it silently measured
    BankNifty's spread on a different, longer-dated contract than the one
    the backtest actually holds near BankNifty's own monthly expiry."""
    print(f"\n=== {underlying} ===")
    spot = broker.get_ltp([spot_symbol]).get(spot_symbol)
    print(f"Spot LTP: {spot}")

    expiries = sm.list_expiries(underlying)
    today = date.today()
    chosen = select_expiry(expiries, today, dte_floor_days)
    if chosen is None:
        print("No suitable expiry found.")
        return []
    dte = (chosen - today).days
    print(f"Using expiry: {chosen} (DTE={dte}, floor={dte_floor_days})")

    expiry_epoch = sm.get_expiry_epoch(underlying, chosen)
    raw_chain = broker.get_option_chain(underlying, expiry_epoch)
    ce, pe = _atm_rows(raw_chain, spot)
    records = []
    for label, row in (("ATM CALL", ce), ("ATM PUT", pe)):
        if not row:
            print(f"  {label}: not found in chain")
            continue
        record = _leg_record(underlying, spot, dte, row)
        _report_leg(label, record)
        records.append(record)
        writer.writerow(record)
    return records


def summarize_log() -> int:
    if not LOG_PATH.exists():
        print(f"No log yet at {LOG_PATH} -- run without --summarize first.")
        return 1
    rows = list(csv.DictReader(LOG_PATH.open(newline="", encoding="utf-8")))
    by_key: dict[tuple, list] = {}
    for r in rows:
        pct = r["spread_pct_of_mid"]
        if pct == "":
            continue
        by_key.setdefault((r["underlying"], r["option_type"]), []).append(float(pct))
    print(f"{len(rows)} total logged rows ({len({r['sampled_at_utc'][:10] for r in rows})} distinct days) from {LOG_PATH}\n")
    for (underlying, opt), pcts in sorted(by_key.items()):
        avg = sum(pcts) / len(pcts)
        print(f"{underlying} {opt}: n={len(pcts)}  mean spread_pct_of_mid={avg:.2f}%  "
              f"min={min(pcts):.2f}%  max={max(pcts):.2f}%")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--summarize", action="store_true", help="Print stats from the log so far, no live fetch.")
    args = parser.parse_args()

    if args.summarize:
        return summarize_log()

    config = load_config("agent/config.yaml")
    broker = get_broker(config)
    if not broker.connect():
        print("ERROR: broker connect() failed -- check the Fyers token.")
        return 1

    print(f"Backtest cost-model assumptions for reference: Stressed slippage = "
          f"{STRESSED_SLIPPAGE_BPS}bps/leg ({STRESSED_SLIPPAGE_BPS / 100:.2f}% one-way, "
          f"~{STRESSED_SLIPPAGE_BPS / 100 * 2:.2f}% round-trip). Harsh = "
          f"{HARSH_FRONT_WEEK_SLIPPAGE_BPS}bps/leg front-week, "
          f"{HARSH_NEXT_WEEK_SLIPPAGE_BPS}bps/leg next-week "
          f"(~{HARSH_FRONT_WEEK_SLIPPAGE_BPS / 100 * 2:.2f}% / "
          f"~{HARSH_NEXT_WEEK_SLIPPAGE_BPS / 100 * 2:.2f}% round-trip).")

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new = not LOG_PATH.exists()
    with LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if is_new:
            writer.writeheader()
        probe(broker, "NIFTY", "NIFTY 50", writer, dte_floor_days=DTE_FLOOR_DAYS)
        probe(broker, "BANKNIFTY", "NIFTY BANK", writer, dte_floor_days=0)
    print(f"\nAppended to {LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
