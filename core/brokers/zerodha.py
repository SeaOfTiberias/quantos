"""
QuantOS — Zerodha / Kite Broker Adapter
────────────────────────────────────────
Implements BrokerAdapter for the Zerodha Kite Connect API.
Install: pip install kiteconnect
"""

from datetime import datetime
import logging

from core.brokers.base import (
    BrokerAdapter, BrokerError,
    Order, OrderResult, OrderStatus, OrderDirection,
    OrderType, Position, OHLCV, ProductType
)

logger = logging.getLogger(__name__)

_TF_MAP = {
    "1m": "minute",
    "5m": "5minute",
    "15m": "15minute",
    "1h": "60minute",
    "1d": "day",
}

_PRODUCT_MAP = {
    ProductType.INTRADAY: "MIS",
    ProductType.CNC: "CNC",
    ProductType.MARGIN: "NRML",
}


class ZerodhaBroker(BrokerAdapter):
    """
    Zerodha Kite Connect broker adapter.

    Config keys expected:
        credentials.api_key
        credentials.api_secret
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self._kite = None

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        try:
            from kiteconnect import KiteConnect

            creds = self.config["credentials"]
            self._kite = KiteConnect(api_key=creds["api_key"])

            request_token = creds.get("request_token") or \
                self._load_token_from_store("zerodha_request_token")

            if not request_token:
                login_url = self._kite.login_url()
                raise BrokerError(
                    f"Zerodha request token not found.\n"
                    f"1. Open this URL: {login_url}\n"
                    f"2. After login, copy the request_token from the redirect URL.\n"
                    f"3. Run: python agent/auth/zerodha_auth.py --token YOUR_TOKEN"
                )

            session = self._kite.generate_session(
                request_token, api_secret=creds["api_secret"]
            )
            self._kite.set_access_token(session["access_token"])
            self._save_token(session["access_token"], "zerodha_access_token")

            self._connected = True
            profile = self._kite.profile()
            logger.info("Zerodha connected: %s", profile.get("user_name"))
            return True

        except ImportError:
            raise BrokerError(
                "kiteconnect not installed. Run: pip install kiteconnect"
            )
        except BrokerError:
            raise
        except Exception as e:
            self._connected = False
            raise BrokerError(f"Zerodha connect error: {e}") from e

    def disconnect(self) -> None:
        if self._kite:
            try:
                self._kite.invalidate_access_token()
            except Exception:
                pass
        self._kite = None
        self._connected = False
        logger.info("Zerodha disconnected.")

    # ── Orders ────────────────────────────────────────────────────────────────

    def place_order(self, order: Order) -> OrderResult:
        self._assert_connected()
        try:
            order_id = self._kite.place_order(
                variety=self._kite.VARIETY_REGULAR,
                exchange=self._kite.EXCHANGE_NSE,
                tradingsymbol=order.symbol,
                transaction_type=(self._kite.TRANSACTION_TYPE_BUY
                                  if order.direction == OrderDirection.BUY
                                  else self._kite.TRANSACTION_TYPE_SELL),
                quantity=order.quantity,
                product=_PRODUCT_MAP[order.product_type],
                order_type=self._map_order_type(order.order_type),
                price=order.price,
                trigger_price=order.trigger_price,
                tag=order.tag or "quantos",
            )
            logger.info("Order placed: %s %s %s qty=%d",
                        order_id, order.direction, order.symbol, order.quantity)
            return OrderResult(
                order_id=str(order_id),
                status=OrderStatus.PENDING,
                symbol=order.symbol,
                direction=order.direction,
                quantity=order.quantity,
                filled_quantity=0,
                average_price=None,
                timestamp=datetime.now(),
            )
        except Exception as e:
            raise BrokerError(f"place_order failed: {e}") from e

    def cancel_order(self, order_id: str) -> bool:
        self._assert_connected()
        try:
            self._kite.cancel_order(
                variety=self._kite.VARIETY_REGULAR,
                order_id=order_id
            )
            return True
        except Exception as e:
            logger.error("cancel_order failed: %s", e)
            return False

    def get_order_status(self, order_id: str) -> OrderResult:
        self._assert_connected()
        orders = self._kite.orders()
        for o in orders:
            if str(o["order_id"]) == str(order_id):
                return self._parse_order(o)
        raise BrokerError(f"Order {order_id} not found.")

    def get_order_history(self) -> list[OrderResult]:
        self._assert_connected()
        return [self._parse_order(o) for o in self._kite.orders()]

    # ── Portfolio ─────────────────────────────────────────────────────────────

    def get_positions(self) -> list[Position]:
        self._assert_connected()
        data = self._kite.positions()
        positions = []
        for p in data.get("net", []):
            if p["quantity"] == 0:
                continue
            positions.append(Position(
                symbol=p["tradingsymbol"],
                quantity=p["quantity"],
                average_price=p["average_price"],
                current_price=p["last_price"],
                pnl=p["pnl"],
                pnl_percent=(p["pnl"] / (p["average_price"] * abs(p["quantity"])) * 100)
                             if p["average_price"] and p["quantity"] else 0,
                product_type=ProductType.INTRADAY if p["product"] == "MIS" else ProductType.CNC,
            ))
        return positions

    def get_funds(self) -> dict:
        self._assert_connected()
        margins = self._kite.margins(segment="equity")
        return {
            "available": margins["available"]["cash"],
            "used": margins["utilised"]["debits"],
            "total": margins["available"]["cash"] + margins["utilised"]["debits"],
        }

    # ── Market Data ───────────────────────────────────────────────────────────

    def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        from_date: datetime,
        to_date: datetime,
    ) -> list[OHLCV]:
        self._assert_connected()
        tf = _TF_MAP.get(timeframe)
        if not tf:
            raise BrokerError(f"Unsupported timeframe: {timeframe}")

        instrument_token = self._get_instrument_token(symbol)
        candles = self._kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_date,
            to_date=to_date,
            interval=tf,
        )
        return [
            OHLCV(
                timestamp=c["date"],
                open=c["open"], high=c["high"],
                low=c["low"], close=c["close"], volume=c["volume"]
            )
            for c in candles
        ]

    def get_ltp(self, symbols: list[str]) -> dict[str, float]:
        self._assert_connected()
        nse_symbols = [f"NSE:{s}" for s in symbols]
        quotes = self._kite.ltp(nse_symbols)
        return {
            k.replace("NSE:", ""): v["last_price"]
            for k, v in quotes.items()
        }

    def get_option_chain(self, underlying: str, expiry: str) -> dict:
        # Zerodha doesn't have a native option chain endpoint;
        # use instrument dump filtered by underlying + expiry
        raise NotImplementedError(
            "Option chain via Zerodha requires instrument dump filtering. "
            "Implement in v2 using kite.instruments('NFO')."
        )

    # ── Internals ─────────────────────────────────────────────────────────────

    def _assert_connected(self):
        if not self._connected or not self._kite:
            raise BrokerError("Zerodha broker not connected. Call connect() first.")

    def _get_instrument_token(self, symbol: str) -> int:
        instruments = self._kite.instruments("NSE")
        for inst in instruments:
            if inst["tradingsymbol"] == symbol:
                return inst["instrument_token"]
        raise BrokerError(f"Instrument token not found for symbol: {symbol}")

    def _load_token_from_store(self, name: str):
        import os
        token_path = os.path.expanduser(f"~/.quantos/{name}")
        if os.path.exists(token_path):
            with open(token_path) as f:
                return f.read().strip()
        return None

    def _save_token(self, token: str, name: str):
        import os
        store_dir = os.path.expanduser("~/.quantos")
        os.makedirs(store_dir, exist_ok=True)
        with open(os.path.join(store_dir, name), "w") as f:
            f.write(token)

    def _map_order_type(self, order_type: OrderType) -> str:
        return {
            OrderType.MARKET: "MARKET",
            OrderType.LIMIT: "LIMIT",
            OrderType.SL: "SL",
            OrderType.SL_M: "SL-M",
        }[order_type]

    def _parse_order(self, o: dict) -> OrderResult:
        status_map = {
            "COMPLETE": OrderStatus.EXECUTED,
            "REJECTED": OrderStatus.REJECTED,
            "CANCELLED": OrderStatus.CANCELLED,
            "OPEN": OrderStatus.OPEN,
            "PENDING": OrderStatus.PENDING,
        }
        return OrderResult(
            order_id=str(o["order_id"]),
            status=status_map.get(o["status"], OrderStatus.PENDING),
            symbol=o["tradingsymbol"],
            direction=OrderDirection.BUY if o["transaction_type"] == "BUY" else OrderDirection.SELL,
            quantity=o["quantity"],
            filled_quantity=o.get("filled_quantity", 0),
            average_price=o.get("average_price"),
            timestamp=o.get("order_timestamp", datetime.now()),
            message=o.get("status_message"),
        )
