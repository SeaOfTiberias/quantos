"""
QuantOS — Fyers Broker Adapter
──────────────────────────────
Implements BrokerAdapter for the Fyers API v3.
Install: pip install fyers-apiv3
"""

import re
from datetime import datetime
from typing import Optional
import logging

from core.brokers.base import (
    BrokerAdapter, BrokerError, InsufficientFundsError,
    Order, OrderResult, OrderStatus, OrderDirection,
    OrderType, Position, OHLCV, ProductType
)

logger = logging.getLogger(__name__)


# Fyers timeframe string mapping
_TF_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "1h": "60",
    "1d": "D",
}

# Fyers product type mapping — note "CO"/"BO" are NOT valid values here;
# Fyers v3's place_order rejects productType outright unless it's one of
# these four (confirmed live: "productType must be one of the following:
# \"CNC\", \"MARGIN\", \"INTRADAY\", \"MTF\""). Cover/Bracket orders are not
# available through this endpoint — stop-loss is implemented as a second,
# separate SL_M order instead (see agent/main.py _size_and_place_order).
_PRODUCT_MAP = {
    ProductType.INTRADAY: "INTRADAY",
    ProductType.CNC: "CNC",
    ProductType.MARGIN: "MARGIN",
}


def _sanitize_tag(tag: Optional[str]) -> str:
    """Fyers rejects orderTag values containing anything but alphanumerics
    (confirmed live: signal_ids like "SIG-DARV-ABC123" get rejected with
    "orderTag: Only alphanumeric characters allowed") — strip everything
    else rather than push this quirk onto every caller."""
    return re.sub(r"[^A-Za-z0-9]", "", tag or "")


class FyersBroker(BrokerAdapter):
    """
    Fyers API v3 broker adapter.

    Config keys expected:
        credentials.api_key
        credentials.api_secret
        credentials.redirect_uri
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self._client = None
        self._access_token: Optional[str] = None

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        try:
            from fyers_apiv3 import fyersModel

            creds = self.config["credentials"]
            app_id = creds["api_key"]

            # In production the access token is obtained via OAuth flow
            # and stored securely. For now we load from config/env.
            self._access_token = creds.get("access_token") or \
                self._load_token_from_store()

            if not self._access_token:
                raise BrokerError(
                    "Fyers access token not found. "
                    "Run `python agent/auth/fyers_auth.py` to authenticate."
                )

            self._client = fyersModel.FyersModel(
                client_id=app_id,
                token=self._access_token,
                is_async=False,
                log_path=""
            )

            # Validate connection
            profile = self._client.get_profile()
            if profile.get("code") != 200:
                raise BrokerError(f"Fyers connection failed: {profile}")

            self._connected = True
            logger.info("Fyers connected: %s", profile["data"]["name"])
            return True

        except ImportError:
            raise BrokerError(
                "fyers-apiv3 not installed. Run: pip install fyers-apiv3"
            )
        except Exception as e:
            self._connected = False
            raise BrokerError(f"Fyers connect error: {e}") from e

    def disconnect(self) -> None:
        self._client = None
        self._connected = False
        logger.info("Fyers disconnected.")

    # ── Orders ────────────────────────────────────────────────────────────────

    def place_order(self, order: Order) -> OrderResult:
        self._assert_connected()
        try:
            data = {
                "symbol": f"NSE:{order.symbol}-EQ",
                "qty": order.quantity,
                "type": self._map_order_type(order.order_type),
                "side": 1 if order.direction == OrderDirection.BUY else -1,
                "productType": _PRODUCT_MAP[order.product_type],
                "limitPrice": order.price or 0,
                "stopPrice": order.trigger_price or 0,
                "validity": "DAY",
                "disclosedQty": 0,
                "offlineOrder": False,
                "orderTag": _sanitize_tag(order.tag) or "quantos",
            }

            response = self._client.place_order(data=data)
            if response.get("code") != 200:
                raise BrokerError(f"Order rejected: {response.get('message')}")

            order_id = response["id"]
            logger.info("Order placed: %s %s %s qty=%d",
                        order_id, order.direction, order.symbol, order.quantity)

            return OrderResult(
                order_id=order_id,
                status=OrderStatus.PENDING,
                symbol=order.symbol,
                direction=order.direction,
                quantity=order.quantity,
                filled_quantity=0,
                average_price=None,
                timestamp=datetime.now(),
                message=response.get("message"),
            )
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(f"place_order failed: {e}") from e

    def cancel_order(self, order_id: str) -> bool:
        self._assert_connected()
        response = self._client.cancel_order(data={"id": order_id})
        return response.get("code") == 200

    def modify_stop_loss(self, order_id: str, new_trigger_price: float) -> bool:
        """Trail a standalone SL_M stop order (placed separately from the
        entry — see agent/main.py _size_and_place_order) to a new absolute
        trigger price. NOT yet verified against a live Fyers account/order —
        confirm the modify_order payload shape with a real pending SL_M
        order before trusting this live."""
        self._assert_connected()
        try:
            response = self._client.modify_order(data={
                "id": order_id,
                "type": self._map_order_type(OrderType.SL_M),
                "stopPrice": new_trigger_price,
            })
            if response.get("code") != 200:
                logger.error("modify_stop_loss rejected for order %s: %s",
                             order_id, response.get("message"))
                return False
            return True
        except Exception as e:
            logger.error("modify_stop_loss failed for order %s: %s", order_id, e)
            return False

    def get_order_status(self, order_id: str) -> OrderResult:
        self._assert_connected()
        response = self._client.orderbook()
        if response.get("code") != 200:
            raise BrokerError(f"Failed to fetch orderbook: {response}")
        for o in response.get("orderBook", []):
            if o["id"] == order_id:
                return self._parse_order(o)
        raise BrokerError(f"Order {order_id} not found in orderbook.")

    def get_order_history(self) -> list[OrderResult]:
        self._assert_connected()
        response = self._client.orderbook()
        if response.get("code") != 200:
            return []
        return [self._parse_order(o) for o in response.get("orderBook", [])]

    # ── Portfolio ─────────────────────────────────────────────────────────────

    def get_positions(self) -> list[Position]:
        self._assert_connected()
        response = self._client.positions()
        if response.get("code") != 200:
            return []
        positions = []
        for p in response.get("netPositions", []):
            positions.append(Position(
                symbol=p["symbol"].replace("NSE:", "").replace("-EQ", ""),
                quantity=p["netQty"],
                average_price=p["netAvg"],
                current_price=p["ltp"],
                pnl=p["pl"],
                pnl_percent=(p["pl"] / (p["netAvg"] * abs(p["netQty"])) * 100)
                             if p["netAvg"] and p["netQty"] else 0,
                product_type=ProductType.INTRADAY,
            ))
        return positions

    def get_funds(self) -> dict:
        self._assert_connected()
        response = self._client.funds()
        if response.get("code") != 200:
            raise BrokerError(f"Failed to fetch funds: {response}")
        fund_data = {f["title"]: f["equityAmount"]
                     for f in response.get("fund_limit", [])}
        return {
            "available": fund_data.get("Available Balance", 0),
            "used": fund_data.get("Utilized Amount", 0),
            "total": fund_data.get("Total Balance", 0),
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
            raise BrokerError(f"Unsupported timeframe: {timeframe}. "
                              f"Use one of: {list(_TF_MAP.keys())}")
        data = {
            "symbol": f"NSE:{symbol}-EQ",
            "resolution": tf,
            "date_format": "1",
            "range_from": str(int(from_date.timestamp())),
            "range_to": str(int(to_date.timestamp())),
            "cont_flag": "1",
        }
        response = self._client.history(data=data)
        if response.get("code") != 200:
            raise BrokerError(f"History fetch failed: {response}")

        candles = response.get("candles", [])
        return [
            OHLCV(
                timestamp=datetime.fromtimestamp(c[0]),
                open=c[1], high=c[2], low=c[3], close=c[4], volume=int(c[5])
            )
            for c in candles
        ]

    def get_ltp(self, symbols: list[str]) -> dict[str, float]:
        self._assert_connected()
        fyers_symbols = [f"NSE:{s}-EQ" for s in symbols]
        response = self._client.quotes(data={"symbols": ",".join(fyers_symbols)})
        if response.get("code") != 200:
            raise BrokerError(f"LTP fetch failed: {response}")
        result = {}
        for q in response.get("d", []):
            clean = q["n"].replace("NSE:", "").replace("-EQ", "")
            result[clean] = q["v"]["lp"]
        return result

    def get_option_chain(self, underlying: str, expiry: str) -> dict:
        self._assert_connected()
        data = {"symbol": f"NSE:{underlying}", "strikecount": 10,
                "timestamp": expiry}
        response = self._client.optionchain(data=data)
        if response.get("code") != 200:
            raise BrokerError(f"Option chain fetch failed: {response}")
        return response.get("data", {})

    # ── Internals ────────────────────────────────────────────────────────────

    def _assert_connected(self):
        if not self._connected or not self._client:
            raise BrokerError("Fyers broker not connected. Call connect() first.")

    def _load_token_from_store(self) -> Optional[str]:
        """Load persisted access token from local file."""
        import os
        token_path = os.path.expanduser("~/.quantos/fyers_token")
        if os.path.exists(token_path):
            with open(token_path) as f:
                return f.read().strip()
        return None

    def _map_order_type(self, order_type: OrderType) -> int:
        return {
            OrderType.LIMIT: 1,
            OrderType.MARKET: 2,
            OrderType.SL: 3,
            OrderType.SL_M: 4,
        }[order_type]

    def _parse_order(self, o: dict) -> OrderResult:
        status_map = {
            1: OrderStatus.PENDING,
            2: OrderStatus.EXECUTED,
            4: OrderStatus.CANCELLED,
            5: OrderStatus.REJECTED,
            6: OrderStatus.OPEN,
        }
        return OrderResult(
            order_id=o["id"],
            status=status_map.get(o["status"], OrderStatus.PENDING),
            symbol=o["symbol"].replace("NSE:", "").replace("-EQ", ""),
            direction=OrderDirection.BUY if o["side"] == 1 else OrderDirection.SELL,
            quantity=o["qty"],
            filled_quantity=o.get("filledQty", 0),
            average_price=o.get("tradedPrice"),
            timestamp=datetime.fromtimestamp(o.get("orderDateTime", 0)),
            message=o.get("message"),
        )
