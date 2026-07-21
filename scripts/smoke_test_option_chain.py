"""
Read-only live smoke test for the options-execution Phase 1 foundations:
symbol master resolution + the get_option_chain() -> OptionChainSnapshot
converter. Places NO orders and prompts for NO input — safe to run
non-interactively, unlike agent/smoke_test_co_order.py.

Prints the raw optionsChain row shape (so chain_builder.py's field-name
assumptions can be corrected against a real response if wrong) and the
built OptionChainSnapshot's summary stats.

Usage:
    python scripts/smoke_test_option_chain.py --underlying NIFTY
    python scripts/smoke_test_option_chain.py --underlying SBIN
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml


def main():
    parser = argparse.ArgumentParser(description="Read-only option chain smoke test")
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--underlying", default="NIFTY")
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    from core.brokers import get_broker
    from core.brokers.base import BrokerError
    from core.options import fyers_symbol_master as sm
    from core.options.chain_builder import build_chain_snapshot, ChainBuildError

    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')}")
    try:
        broker.connect()
    except BrokerError as e:
        print(f"connect() failed: {e}")
        print("If this is an auth/token error, the stored token has likely "
              "expired — run the interactive fyers_auth.py refresh yourself "
              "in your own terminal, then re-run this script.")
        sys.exit(1)
    print(f"Broker connected: {broker}\n")

    spot_symbol = "NIFTY 50" if args.underlying == "NIFTY" else args.underlying
    ltp = broker.get_ltp([spot_symbol]).get(spot_symbol) or broker.get_ltp([spot_symbol]).get(args.underlying)
    print(f"Spot LTP for {args.underlying}: {ltp}")

    print(f"\nResolving available expiries for {args.underlying} from the symbol master...")
    try:
        expiries = sm.list_expiries(args.underlying)
    except sm.SymbolMasterError as e:
        print(f"Symbol master lookup failed: {e}")
        sys.exit(1)
    if not expiries:
        print("No future expiries found — aborting.")
        sys.exit(1)
    nearest_expiry = expiries[0]
    print(f"Nearest expiry: {nearest_expiry} ({len(expiries)} total available)")

    print(f"\nFetching raw option chain from Fyers for {args.underlying} @ {nearest_expiry}...")
    try:
        expiry_epoch = sm.get_expiry_epoch(args.underlying, nearest_expiry)
        raw_chain = broker.get_option_chain(args.underlying, expiry_epoch)
    except BrokerError as e:
        print(f"get_option_chain() failed: {e}")
        sys.exit(1)

    rows = raw_chain.get("optionsChain", [])
    print(f"\nRaw response top-level keys: {list(raw_chain.keys())}")
    print(f"optionsChain row count: {len(rows)}")
    if rows:
        print("First 2 raw rows (inspect field names against chain_builder.py's assumptions):")
        print(json.dumps(rows[:2], indent=2, default=str))
    else:
        print("optionsChain is empty or missing — chain_builder.py's key "
              "assumption ('optionsChain') may be wrong. Full raw response:")
        print(json.dumps(raw_chain, indent=2, default=str))
        sys.exit(1)

    days_to_expiry = max(1, (nearest_expiry - date.today()).days)
    print(f"\nBuilding OptionChainSnapshot (days_to_expiry={days_to_expiry})...")
    try:
        snapshot = build_chain_snapshot(
            underlying=args.underlying, expiry=nearest_expiry,
            spot_price=ltp, raw_chain=raw_chain, days_to_expiry=days_to_expiry,
        )
    except ChainBuildError as e:
        print(f"build_chain_snapshot() failed: {e}")
        print("This means chain_builder.py's field-name assumptions were "
              "wrong against this real response — fix _STRIKE_KEYS/"
              "_OPTION_TYPE_KEYS/_LTP_KEYS/_OI_KEYS to match the raw rows "
              "printed above.")
        sys.exit(1)

    print(
        f"\nSnapshot built OK:\n"
        f"  underlying={snapshot.underlying}  spot={snapshot.spot_price}\n"
        f"  legs={len(snapshot.legs)}  pcr={snapshot.pcr}  max_pain={snapshot.max_pain}\n"
        f"  atm_strike={snapshot.atm_strike()}"
    )
    atm = snapshot.atm_strike()
    atm_call = snapshot.get_leg(atm, __import__("core.options.models", fromlist=["OptionType"]).OptionType.CALL)
    if atm_call:
        print(f"  ATM call: strike={atm_call.strike} premium={atm_call.premium} "
              f"oi={atm_call.open_interest} solved_iv={atm_call.implied_vol:.3f}")

    print(f"\nResolving the ATM call's real tradeable symbol via the symbol master...")
    try:
        resolved = sm.resolve_option_symbol(
            args.underlying, nearest_expiry, atm,
            __import__("core.options.models", fromlist=["OptionType"]).OptionType.CALL,
        )
        print(f"  Resolved: {resolved.symbol}  lot_size={resolved.lot_size}")
    except sm.SymbolMasterError as e:
        print(f"  resolve_option_symbol() failed: {e}")

    print("\nDone. No orders were placed.")


if __name__ == "__main__":
    main()
