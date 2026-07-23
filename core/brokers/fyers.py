"""
QuantOS — Fyers Broker Adapter
──────────────────────────────
Implements BrokerAdapter for the Fyers API v3.
Install: pip install fyers-apiv3
"""

import re
from datetime import datetime, timezone
from typing import Optional
import logging

from core.brokers.base import (
    BrokerAdapter, BrokerError, InsufficientFundsError,
    Order, OrderResult, OrderStatus, OrderDirection,
    OrderType, Position, OHLCV, Quote, ProductType
)

logger = logging.getLogger(__name__)

# Fyers' /quotes endpoint rejects a request carrying more than 50 symbols,
# so get_quotes() batches a larger (breadth-sized) universe into chunks.
_QUOTES_CHUNK = 50


# Fyers timeframe string mapping
_TF_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "1h": "60",
    "1d": "D",
}

# Fyers formats index symbols differently from equities: "-INDEX" suffix
# instead of "-EQ", and no spaces in the name. core/regime/fetcher.py is
# the first caller to ever request an index symbol here (NIFTY_SYMBOL,
# VIX_SYMBOL) — every existing caller (core/darvas/*.py) only ever deals
# in individual equities, so this gap was never exercised before.
#
# Two naming conventions for the same instruments coexist in this codebase
# and both need to resolve to the same Fyers symbol: the quote/historical-
# data layer uses "NIFTY 50"/"NIFTY BANK" (core/regime/fetcher.py's
# NIFTY_SYMBOL/BANK_NIFTY conventions), while the options domain
# (core/options/fyers_symbol_master.py, keyed off Fyers' own F&O symbol
# master's underlying_symbol column) uses the bare "NIFTY"/"BANKNIFTY" —
# confirmed live 2026-07-21 when get_option_chain("NIFTY", ...) hit this
# gap and Fyers rejected "NSE:NIFTY" outright ("Please provide a valid
# symbol") before this alias existed.
_INDEX_SYMBOL_MAP = {
    "NIFTY 50":        "NIFTY50",
    "NIFTY":           "NIFTY50",
    "NIFTY BANK":      "NIFTYBANK",
    "BANKNIFTY":       "NIFTYBANK",
    "INDIA VIX":       "INDIAVIX",
    "NIFTY ALPHA 50":  "NIFTYALPHA50",
}


def _fyers_symbol(symbol: str) -> str:
    if symbol in _INDEX_SYMBOL_MAP:
        return f"NSE:{_INDEX_SYMBOL_MAP[symbol]}-INDEX"
    return f"NSE:{symbol}-EQ"


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
            # fyers_apiv3 unconditionally writes every API call to
            # fyersApi.log/fyersRequests.log via its own FileHandlers
            # (request_logger is hardcoded to DEBUG regardless of what we
            # pass here) — unbounded disk growth over the agent's lifetime.
            # Capping each handler's own level (independent of the SDK's
            # internal logger level) stops the writes without depending on
            # the vendored aws_lambda_powertools logger's internals.
            for sdk_logger in (getattr(self._client, "api_logger", None),
                               getattr(self._client, "request_logger", None)):
                for handler in getattr(sdk_logger, "handlers", []):
                    handler.setLevel(logging.CRITICAL)

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
                "symbol": _fyers_symbol(order.symbol),
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
            "symbol": _fyers_symbol(symbol),
            "resolution": tf,
            # date_format=0 means range_from/range_to are Unix epoch seconds
            # (date_format=1 would mean "yyyy-mm-dd" strings instead) —
            # confirmed live via agent/debug_discovery_scan.py: this was
            # "1" while range_from/range_to were already epoch integers,
            # so every single history call failed with Fyers error code -50
            # until the two-stage Darvas pipeline was the first caller to
            # actually exercise this method against live daily candles.
            "date_format": "0",
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
                # tz-aware UTC — a naive timestamp here broke Stage A's
                # discovery scanner, which subtracts these from
                # datetime.now(timezone.utc) to compute days_in_box
                # ("can't subtract offset-naive and offset-aware
                # datetimes"). Fyers candle epochs are UTC seconds.
                timestamp=datetime.fromtimestamp(c[0], tz=timezone.utc),
                open=c[1], high=c[2], low=c[3], close=c[4], volume=int(c[5])
            )
            for c in candles
        ]

    def get_ltp(self, symbols: list[str]) -> dict[str, float]:
        self._assert_connected()
        # Map back to whatever the caller originally asked for, keyed by the
        # exact Fyers symbol requested, rather than heuristically stripping
        # "-EQ" — confirmed live 2026-07-21 that heuristic silently dropped
        # every index request (e.g. requesting "NIFTY 50" builds
        # "NSE:NIFTY50-INDEX"; stripping only "-EQ" left "NIFTY50-INDEX",
        # which never matches the caller's original "NIFTY 50" key).
        fyers_to_original = {_fyers_symbol(s): s for s in symbols}
        response = self._client.quotes(data={"symbols": ",".join(fyers_to_original.keys())})
        if response.get("code") != 200:
            raise BrokerError(f"LTP fetch failed: {response}")
        result = {}
        for q in response.get("d", []):
            original = fyers_to_original.get(q["n"], q["n"].replace("NSE:", "").replace("-EQ", ""))
            result[original] = q["v"]["lp"]
        return result

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """
        Fetch full quote snapshots (LTP + previous close) for a symbol list.

        Fyers' /quotes endpoint caps a request at 50 symbols, so a
        breadth-sized universe (hundreds of names) is split into chunks and
        merged. Each quote's `v` block carries `lp` (last), `prev_close_price`,
        `ch` (change) and `chp` (change %) — everything advance/decline needs.
        """
        self._assert_connected()
        out: dict[str, Quote] = {}
        for i in range(0, len(symbols), _QUOTES_CHUNK):
            chunk = symbols[i:i + _QUOTES_CHUNK]
            # Map back to the caller's original symbol rather than
            # heuristically stripping "-EQ" — see get_ltp()'s identical fix
            # (confirmed live 2026-07-21) for why that silently drops indices.
            fyers_to_original = {_fyers_symbol(s): s for s in chunk}
            response = self._client.quotes(data={"symbols": ",".join(fyers_to_original.keys())})
            if response.get("code") != 200:
                raise BrokerError(f"Quotes fetch failed: {response}")
            for q in response.get("d", []):
                v = q.get("v", {}) or {}
                original = fyers_to_original.get(
                    q["n"], q["n"].replace("NSE:", "").replace("-EQ", ""))
                out[original] = Quote(
                    symbol=original,
                    ltp=v.get("lp", 0.0) or 0.0,
                    prev_close=v.get("prev_close_price", 0.0) or 0.0,
                    change=v.get("ch", 0.0) or 0.0,
                    change_pct=v.get("chp", 0.0) or 0.0,
                )
        return out

    def get_option_chain(self, underlying: str, expiry: str) -> dict:
        self._assert_connected()
        # Confirmed live 2026-07-21: this previously hardcoded f"NSE:{underlying}"
        # (e.g. "NSE:NIFTY"), which Fyers rejected outright — the option chain
        # endpoint wants the same "-INDEX" convention as quotes/historical data
        # (_fyers_symbol handles equities and both index-naming conventions).
        data = {"symbol": _fyers_symbol(underlying), "strikecount": 10,
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
