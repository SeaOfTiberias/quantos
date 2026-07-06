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
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running as `python agent/main.py` from the repo root — the script's
# own directory (agent/) is on sys.path by default, but the repo root
# (needed for `core.*` imports) is not.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
import yaml

from agent.positions import (
    OpenPosition, load_open_positions, add_position, update_stop, remove_position,
)
from core.darvas.box import next_trailing_stop

# How often (in poll ticks) to re-check open positions for trailing/closure.
# Kept slower than the 5s signal poll to avoid hammering the broker with
# historical-data calls for every open position.
TRAIL_EVERY_N_TICKS = 12  # ~60s at the default 5s poll_interval

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
    broker adapter. Raises BrokerError if it can't be sized or placed.

    Places the entry as a plain MARKET order, then — if a stop_loss is
    known — immediately places a second, separate SL_M (stop-loss market)
    order in the opposite direction as the actual stop-loss leg. (An
    earlier version of this tried to use a single Fyers Cover Order for
    this; Fyers' v3 API rejects "CO" as a productType outright — CNC,
    MARGIN, INTRADAY, MTF are the only valid values — so two plain orders
    it is.) The trailing loop (_manage_open_positions) ratchets that SL_M
    order's trigger price up over the life of the position via
    broker.modify_stop_loss(sl_order_id, ...)."""
    from core.brokers.base import Order, OrderDirection, OrderType, ProductType, BrokerError

    symbol = signal["symbol"]
    action = signal["action"]
    price = float(signal["price"])
    stop_loss = signal.get("stop_loss")

    risk_cfg = config.get("risk", {})
    configured_product_type = ProductType[risk_cfg.get("product_type", "INTRADAY").upper()]
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

    entry_direction = OrderDirection.BUY if action == "BUY" else OrderDirection.SELL
    order = Order(
        symbol=symbol,
        direction=entry_direction,
        quantity=quantity,
        order_type=OrderType.MARKET,
        product_type=configured_product_type,
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

    # Auto-exit (Task 4): place a separate SL_M stop order in the opposite
    # direction as the actual stop-loss leg. Disable via risk.auto_exit:
    # false in config (e.g. for CNC/delivery trades you intend to hold).
    auto_exit = bool(risk_cfg.get("auto_exit", True))
    sl_order_id = None
    if auto_exit:
        exit_direction = OrderDirection.SELL if entry_direction == OrderDirection.BUY else OrderDirection.BUY
        sl_order = Order(
            symbol=symbol,
            direction=exit_direction,
            quantity=quantity,
            order_type=OrderType.SL_M,
            product_type=configured_product_type,
            trigger_price=stop_loss,
            tag=f"{signal['signal_id']}-sl",
        )
        sl_result = broker.place_order(sl_order)
        sl_order_id = sl_result.order_id

    return result.order_id, quantity, fill_price, stop_loss, auto_exit, sl_order_id


def _manage_open_positions(broker, cloud_url, headers, sizer, positions: dict):
    """
    For every locally-tracked open position: check whether the broker still
    shows it open. If closed, record it as a ClosedTrade (this is what
    finally feeds TradeHistoryService.record_closed_trade() — the call site
    that's been missing since Task 2, so Kelly sizing can graduate off its
    fixed-2% fallback). If still open, re-run the Darvas box scan and trail
    the stop-loss up if a tighter one has formed.
    """
    from core.brokers.base import OrderStatus
    from core.risk.kelly import ClosedTrade

    try:
        live_positions = {p.symbol: p for p in broker.get_positions()}
    except Exception as e:
        logger.error("Failed to fetch live positions for trailing/close check: %s", e)
        return

    for signal_id, pos in list(positions.items()):
        live = live_positions.get(pos.symbol)
        still_open = live is not None and live.quantity != 0

        if not still_open:
            exit_price, exit_date = None, None
            try:
                history = broker.get_order_history()
                # The SL_M stop order is a real, separate order now (not a
                # bundled CO leg) — if it filled, that's the exit itself.
                sl_fill = next(
                    (o for o in history
                     if o.order_id == pos.sl_order_id and o.status == OrderStatus.EXECUTED),
                    None,
                )
                if sl_fill:
                    exit_price, exit_date = sl_fill.average_price, sl_fill.timestamp
                else:
                    # Closed some other way (e.g. manual square-off in the
                    # Fyers app) — fall back to the latest executed fill for
                    # this symbol, and cancel the now-orphaned stop order.
                    candidates = [
                        o for o in history
                        if o.symbol == pos.symbol
                        and o.order_id != pos.sl_order_id
                        and o.status == OrderStatus.EXECUTED
                    ]
                    if candidates:
                        latest = max(candidates, key=lambda o: o.timestamp)
                        exit_price, exit_date = latest.average_price, latest.timestamp
                    try:
                        broker.cancel_order(pos.sl_order_id)
                    except Exception:
                        pass
            except Exception as e:
                logger.error("[%s] Failed to read order history for exit fill: %s", signal_id, e)

            if exit_price is None:
                try:
                    exit_price = broker.get_ltp([pos.symbol]).get(pos.symbol, pos.current_stop)
                except Exception:
                    exit_price = pos.current_stop
            if exit_date is None:
                exit_date = datetime.now(timezone.utc)

            trade = ClosedTrade(
                trade_id=pos.signal_id,
                symbol=pos.symbol,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                quantity=pos.quantity,
                direction=pos.direction,
                entry_date=datetime.fromisoformat(pos.entry_date),
                exit_date=exit_date,
                strategy=pos.strategy,
            )
            sizer.record_closed_trade(trade)
            _report_outcome(cloud_url, headers, signal_id, "closed", {
                "exit_price": exit_price, "pnl": trade.pnl, "reason": "stop_hit",
            })
            logger.info("[%s] Position closed: %s pnl=%.2f", signal_id, pos.symbol, trade.pnl)
            remove_position(positions, signal_id)
            continue

        if pos.direction != "BUY":
            continue  # trailing only supported for long Darvas breakouts today

        try:
            to_date = datetime.now(timezone.utc)
            from_date = to_date - timedelta(days=5)
            candles = broker.get_historical_data(pos.symbol, pos.timeframe, from_date, to_date)
            new_stop = next_trailing_stop(candles, pos.current_stop)
        except Exception as e:
            logger.error("[%s] Failed to recompute trailing stop for %s: %s",
                         signal_id, pos.symbol, e)
            continue

        if new_stop:
            if broker.modify_stop_loss(pos.sl_order_id, new_stop):
                logger.info("[%s] Trailed stop for %s: %.2f -> %.2f",
                            signal_id, pos.symbol, pos.current_stop, new_stop)
                update_stop(positions, signal_id, new_stop)
            else:
                logger.error("[%s] Broker rejected stop trail for %s", signal_id, pos.symbol)


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
    open_positions = load_open_positions()
    tick = 0

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
                    order_id, quantity, fill_price, stop_loss, auto_exit, sl_order_id = _size_and_place_order(
                        broker, sizer, signal, config
                    )
                    _report_outcome(cloud_url, headers, signal_id, "executed", {
                        "order_id": order_id, "quantity": quantity,
                        "execution_price": fill_price,
                    })
                    logger.info("[%s] Executed: qty=%d @ %.2f (order %s)",
                                signal_id, quantity, fill_price, order_id)

                    if auto_exit:
                        add_position(open_positions, OpenPosition(
                            signal_id=signal_id,
                            symbol=signal["symbol"],
                            direction=signal["action"],
                            quantity=quantity,
                            entry_price=fill_price,
                            entry_date=datetime.now(timezone.utc).isoformat(),
                            timeframe=signal.get("timeframe", "15m"),
                            current_stop=stop_loss,
                            sl_order_id=sl_order_id,
                            strategy=signal.get("strategy", "darvas_breakout"),
                        ))
                except Exception as e:
                    logger.error("[%s] Execution failed: %s", signal_id, e)
                    _report_outcome(cloud_url, headers, signal_id, "failed",
                                    {"reason": str(e)})

            tick += 1
            if tick % TRAIL_EVERY_N_TICKS == 0 and open_positions:
                _manage_open_positions(broker, cloud_url, headers, sizer, open_positions)

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
