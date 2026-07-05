"""
QuantOS Local Agent
────────────────────
Runs on the customer's machine. Holds broker credentials locally.
Polls QuantOS cloud for CONFIRMED signals and executes orders via the
configured broker adapter. The Telegram "execute"/"skip" reply itself is
handled entirely on the cloud side (see cloud/api/main.py /webhook/telegram)
— this agent only ever talks REST to the cloud API (ADR-01: keys never
leave this machine).

ADR-01: Keys never leave this machine.
ADR-05: confirm_before_execute = True by default (human-in-loop on the
cloud side gates a signal from PENDING_CONFIRMATION to CONFIRMED before
this agent will ever see it).

Usage:
    python agent/main.py
    python agent/main.py --config path/to/config.yaml
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Allow running as `python agent/main.py` from the repo root — the script's
# own directory (agent/) is on sys.path by default, but the repo root
# (needed for `core.*` imports) is not.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("quantos.agent")

# Tracks signal_ids this machine has already attempted to execute, so a
# crash/restart between "order placed" and "reported to cloud" can never
# result in the same signal being placed twice.
PROCESSED_SIGNALS_PATH = Path.home() / ".quantos" / "processed_signals.json"


def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        logger.error(
            "Config not found at %s\n"
            "Copy agent/config.yaml.example to agent/config.yaml and fill in your values.",
            config_path
        )
        sys.exit(1)
    with open(path) as f:
        return yaml.safe_load(f)


def _load_processed_ids() -> set:
    if PROCESSED_SIGNALS_PATH.exists():
        try:
            return set(json.loads(PROCESSED_SIGNALS_PATH.read_text()))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def _mark_processed(signal_id: str, processed: set) -> None:
    processed.add(signal_id)
    PROCESSED_SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_SIGNALS_PATH.write_text(json.dumps(sorted(processed)))


def _report_outcome(cloud_url: str, headers: dict, signal_id: str,
                     endpoint: str, payload: dict) -> None:
    try:
        r = requests.post(f"{cloud_url}/signals/{signal_id}/{endpoint}",
                           json=payload, headers=headers, timeout=10)
        r.raise_for_status()
    except Exception as e:
        logger.error("[%s] Failed to report '%s' to cloud: %s", signal_id, endpoint, e)


def _size_and_place_order(broker, sizer, signal: dict, config: dict):
    """Kelly-size the position (core/risk/kelly.py) and place it via the
    broker adapter. Raises BrokerError if it can't be sized or placed."""
    from core.brokers.base import Order, OrderDirection, OrderType, ProductType, BrokerError

    symbol = signal["symbol"]
    action = signal["action"]
    price = float(signal["price"])
    stop_loss = signal.get("stop_loss")

    risk_cfg = config.get("risk", {})
    product_type = ProductType[risk_cfg.get("product_type", "INTRADAY").upper()]
    assumed_stop_pct = float(risk_cfg.get("assumed_stop_pct", 0.015))

    funds = broker.get_funds()
    capital = funds.get("available") or 0

    # get_current_sizing falls back to a fixed 2% until 20+ closed trades
    # are on record (core/risk/kelly.py MIN_TRADES_FOR_KELLY) — this agent
    # doesn't yet persist closed-trade history across runs, so it will use
    # that fixed fallback until trade-history persistence is wired up.
    sizing = sizer.get_current_sizing(symbol, capital=capital)

    if not stop_loss:
        stop_loss = price * (1 - assumed_stop_pct if action == "BUY" else 1 + assumed_stop_pct)
        logger.warning(
            "[%s] Signal has no stop_loss — assuming %.2f%% (%.2f). "
            "Wire stop_loss into the TradingView alert for real Darvas-box stops.",
            signal["signal_id"], assumed_stop_pct * 100, stop_loss,
        )

    quantity = sizing.position_quantity(entry_price=price, stop_loss_price=stop_loss)
    if quantity <= 0:
        raise BrokerError(
            f"Computed quantity {quantity} (capital={capital:.2f}, "
            f"size_pct={sizing.size_pct:.2%}, method={sizing.method}) — "
            f"insufficient funds or stop-loss too tight"
        )

    order = Order(
        symbol=symbol,
        direction=OrderDirection.BUY if action == "BUY" else OrderDirection.SELL,
        quantity=quantity,
        order_type=OrderType.MARKET,
        product_type=product_type,
        tag=signal["signal_id"],
    )
    result = broker.place_order(order)

    # MARKET orders usually fill within seconds — poll briefly for the fill
    # price, but don't block the agent loop indefinitely if it's slow.
    fill_price = result.average_price
    for _ in range(5):
        if fill_price:
            break
        time.sleep(1)
        try:
            fill_price = broker.get_order_status(result.order_id).average_price
        except Exception:
            break
    if not fill_price:
        fill_price = price

    return result.order_id, quantity, fill_price


def run_agent(config: dict):
    from core.brokers import get_broker
    from core.risk import TradeHistoryService

    broker = get_broker(config)
    logger.info("Connecting to broker: %s", config.get("broker"))
    broker.connect()
    logger.info("Broker connected: %s", broker)

    cloud_url = config["cloud"]["api_url"].rstrip("/")
    cloud_secret = config["cloud"].get("api_secret", "")
    headers = {"X-Cloud-Secret": cloud_secret} if cloud_secret else {}
    poll_interval = 5  # seconds

    sizer = TradeHistoryService()
    processed = _load_processed_ids()

    logger.info("Agent running. Cloud: %s | Polling every %ds for CONFIRMED signals.",
                cloud_url, poll_interval)
    logger.info("Press Ctrl+C to stop.")

    try:
        while True:
            try:
                resp = requests.get(
                    f"{cloud_url}/signals",
                    params={"status": "CONFIRMED", "limit": 20},
                    headers=headers, timeout=10,
                )
                resp.raise_for_status()
                signals = resp.json().get("signals", [])
            except Exception as e:
                logger.error("Failed to poll /signals: %s", e)
                signals = []

            for signal in signals:
                signal_id = signal["signal_id"]
                if signal_id in processed:
                    continue
                # Mark BEFORE placing the order — a crash after this point
                # but before place_order() simply drops the trade (safe);
                # a crash after place_order() but before reporting back
                # will not cause a duplicate order on restart.
                _mark_processed(signal_id, processed)

                logger.info("[%s] Executing %s %s @ %.2f",
                            signal_id, signal["action"], signal["symbol"], signal["price"])
                try:
                    order_id, quantity, fill_price = _size_and_place_order(
                        broker, sizer, signal, config
                    )
                    _report_outcome(cloud_url, headers, signal_id, "executed", {
                        "order_id": order_id, "quantity": quantity,
                        "execution_price": fill_price,
                    })
                    logger.info("[%s] Executed: qty=%d @ %.2f (order %s)",
                                signal_id, quantity, fill_price, order_id)
                except Exception as e:
                    logger.error("[%s] Execution failed: %s", signal_id, e)
                    _report_outcome(cloud_url, headers, signal_id, "failed",
                                    {"reason": str(e)})

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        logger.info("Agent stopped.")
        broker.disconnect()


def main():
    parser = argparse.ArgumentParser(description="QuantOS Local Agent")
    parser.add_argument(
        "--config",
        default="agent/config.yaml",
        help="Path to agent config file (default: agent/config.yaml)"
    )
    args = parser.parse_args()
    config = load_config(args.config)
    run_agent(config)


if __name__ == "__main__":
    main()
