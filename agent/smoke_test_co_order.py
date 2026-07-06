"""
QuantOS — Stop-Loss / Trailing-Stop Smoke Test
─────────────────────────────────────────────────
Task 4 flagged the Fyers order mechanics for auto-exit as unverified. A
live test proved the first assumption wrong: Fyers v3's place_order
rejects productType="CO" outright ("productType must be one of the
following: CNC, MARGIN, INTRADAY, MTF") — Cover/Bracket orders aren't
available through this endpoint. The corrected design places the entry as
a plain MARKET order, then a second, separate SL_M (stop-loss market)
order as the actual stop-loss leg — see agent/main.py _size_and_place_order.

This script exercises both calls directly against a real Fyers account —
bypassing the webhook/Telegram/Kelly pipeline entirely — so you can watch
the Fyers orderbook and confirm the SL_M placement + trailing-modify calls
work before trusting a real signal to them.

This places REAL orders for REAL money (small size, but real). It will
NOT exit the position for you — square it off manually in the Fyers app
once you're done testing (which also means cancelling the leftover SL_M
stop order, since it won't be triggered by your manual exit).

Usage:
    python agent/smoke_test_co_order.py --symbol SBIN
    python agent/smoke_test_co_order.py --symbol SBIN --qty 2 --stop-pct 0.02
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml


def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        print(f"Config not found at {config_path}")
        sys.exit(1)
    with open(path) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="QuantOS entry + SL_M stop / trailing-stop smoke test")
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--symbol", required=True, help="NSE symbol, e.g. SBIN")
    parser.add_argument("--qty", type=int, default=1)
    parser.add_argument("--stop-pct", type=float, default=0.02,
                         help="Initial stop distance below LTP, as a fraction (default 0.02 = 2%%)")
    parser.add_argument("--trail-pct", type=float, default=0.005,
                         help="How far to trail the stop up on the second call, as a fraction of LTP (default 0.005 = 0.5%%)")
    args = parser.parse_args()

    config = load_config(args.config)

    from core.brokers import get_broker
    from core.brokers.base import Order, OrderDirection, OrderType, ProductType, BrokerError

    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')}")
    broker.connect()
    print(f"Broker connected: {broker}")

    ltp = broker.get_ltp([args.symbol]).get(args.symbol)
    if not ltp:
        print(f"Could not fetch LTP for {args.symbol}")
        sys.exit(1)

    stop_price = round(ltp * (1 - args.stop_pct), 2)
    print(
        f"\n{args.symbol} LTP: {ltp:.2f}\n"
        f"About to place TWO LIVE orders:\n"
        f"  1) BUY {args.qty} share(s) MARKET, product_type=INTRADAY (the entry)\n"
        f"  2) SELL {args.qty} share(s) SL_M @ trigger {stop_price:.2f} "
        f"({args.stop_pct:.1%} below LTP) (the stop-loss leg)\n"
    )
    confirm = input("Type YES to place these real orders: ")
    if confirm.strip() != "YES":
        print("Aborted.")
        return

    entry_order = Order(
        symbol=args.symbol,
        direction=OrderDirection.BUY,
        quantity=args.qty,
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        tag="quantos-smoke-test",
    )
    try:
        entry_result = broker.place_order(entry_order)
    except BrokerError as e:
        print(f"Entry place_order failed: {e}")
        sys.exit(1)
    print(f"\nEntry order placed: {entry_result}")

    sl_order = Order(
        symbol=args.symbol,
        direction=OrderDirection.SELL,
        quantity=args.qty,
        order_type=OrderType.SL_M,
        product_type=ProductType.INTRADAY,
        trigger_price=stop_price,
        tag="quantos-smoke-test-sl",
    )
    try:
        sl_result = broker.place_order(sl_order)
    except BrokerError as e:
        print(f"SL_M place_order failed: {e}")
        print(
            "Entry order already filled — you have a naked position. "
            "Close it manually in the Fyers app."
        )
        sys.exit(1)
    print(f"SL_M stop order placed: {sl_result}")

    print(
        "\nNow check the Fyers orderbook: you should see the filled entry "
        "and a pending SL_M order with the trigger price printed above."
    )
    input("\nPress Enter once you've confirmed the orderbook looks right, to test trailing the stop...")

    new_stop = round(stop_price * (1 + args.trail_pct), 2)
    print(f"Calling modify_stop_loss({sl_result.order_id}, {new_stop}) ...")
    success = broker.modify_stop_loss(sl_result.order_id, new_stop)
    print(f"modify_stop_loss returned: {success}")
    print(
        "Check the Fyers orderbook again — the SL_M order's trigger price "
        f"should now show ~{new_stop:.2f} instead of ~{stop_price:.2f}.\n"
    )

    print(
        "This script does not exit the position. Square off the entry AND "
        "cancel the SL_M order manually in the Fyers app when you're done testing."
    )


if __name__ == "__main__":
    main()
