#!/usr/bin/env python3
"""
QuantOS — Candidate 18 Real Option Bid-Ask Spread Feasibility Check
──────────────────────────────────────────────────────────────────────
Read-only, no orders. Fetches a LIVE (or last-close, outside market hours)
option chain for NIFTY and BankNifty and compares the REAL bid-ask spread
at the near-the-money strike against what this candidate's Harsh cost
model (core/orb_scalping/costs.py) assumes via slippage_bps — the same
follow-up check candidate 15's methodology doc named and never got to
exercise (it failed the backtest first). Every premium in the backtest is
Black-Scholes-theoretical; this is the first time this candidate's numbers
are compared against a real, currently-quoted market price.

Skips the expiry expiring TODAY (if any) for NIFTY, since a same-day
expiry is nearly worthless/illiquid by definition and not representative
of what the strategy actually trades (entries happen at 09:15-09:30, with
the DTE floor already excluding <2-day contracts) — uses the same DTE
floor the live strategy would apply.

Usage:
    python scripts/probe_orb_scalping_real_spreads.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers import get_broker  # noqa: E402
from core.options import fyers_symbol_master as sm  # noqa: E402
from core.orb_scalping.costs import (  # noqa: E402
    HARSH_FRONT_WEEK_SLIPPAGE_BPS,
    HARSH_NEXT_WEEK_SLIPPAGE_BPS,
    STRESSED_SLIPPAGE_BPS,
)

DTE_FLOOR_DAYS = 2  # same floor core/orb_scalping/backtest.py applies to NIFTY


def _atm_rows(raw_chain: dict, spot: float):
    rows = raw_chain.get("optionsChain", [])
    strikes = sorted({r["strike_price"] for r in rows if r.get("strike_price", -1) > 0})
    if not strikes:
        return None, None
    atm_strike = min(strikes, key=lambda s: abs(s - spot))
    ce = next((r for r in rows if r.get("strike_price") == atm_strike and r.get("option_type") == "CE"), None)
    pe = next((r for r in rows if r.get("strike_price") == atm_strike and r.get("option_type") == "PE"), None)
    return ce, pe


def _report_leg(label: str, row: dict):
    if not row:
        print(f"  {label}: not found in chain")
        return
    bid, ask, ltp = row.get("bid", 0), row.get("ask", 0), row.get("ltp", 0)
    mid = (bid + ask) / 2 if (bid and ask) else None
    spread = (ask - bid) if (bid and ask) else None
    print(f"  {label}: strike={row.get('strike_price')} bid={bid} ask={ask} ltp={ltp}")
    if mid and spread is not None:
        print(f"    mid={mid:.2f} spread={spread:.2f} spread_pct_of_mid={spread / mid * 100:.1f}%")
    elif ask and not bid:
        print(f"    bid is 0 (no real buyer quoted) -- spread is effectively the whole ask "
              f"({ask:.2f}, i.e. undefined/very wide in %% terms)")
    else:
        print("    bid/ask both 0 -- no live two-sided quote available right now")


def probe(broker, underlying: str, spot_symbol: str, skip_today: bool):
    print(f"\n=== {underlying} ===")
    spot = broker.get_ltp([spot_symbol]).get(spot_symbol)
    print(f"Spot LTP: {spot}")

    expiries = sm.list_expiries(underlying)
    today = date.today()
    chosen = None
    for e in expiries:
        if skip_today and (e - today).days < DTE_FLOOR_DAYS:
            continue
        chosen = e
        break
    if chosen is None:
        print("No suitable expiry found.")
        return
    print(f"Using expiry: {chosen} (DTE={(chosen - today).days})")

    expiry_epoch = sm.get_expiry_epoch(underlying, chosen)
    raw_chain = broker.get_option_chain(underlying, expiry_epoch)
    ce, pe = _atm_rows(raw_chain, spot)
    _report_leg("ATM CALL", ce)
    _report_leg("ATM PUT", pe)


def main() -> int:
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

    probe(broker, "NIFTY", "NIFTY 50", skip_today=True)
    probe(broker, "BANKNIFTY", "NIFTY BANK", skip_today=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
