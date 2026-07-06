"""
QuantOS Broker Adapter Interface (ADR-02)
─────────────────────────────────────────
Abstract base class for all broker integrations.
Core logic (Darvas scanner, Claude analyst, Kelly sizer)
only ever interacts with this interface — never with a
specific broker's SDK directly.

To add a new broker: subclass BrokerAdapter and implement
all abstract methods. Register in brokers/__init__.py.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class OrderDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"           # Stop-loss
    SL_M = "SL_M"       # Stop-loss market


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ProductType(str, Enum):
    INTRADAY = "INTRADAY"
    CNC = "CNC"         # Cash and Carry (delivery)
    MARGIN = "MARGIN"


@dataclass
class Order:
    symbol: str
    direction: OrderDirection
    quantity: int
    order_type: OrderType
    product_type: ProductType
    price: Optional[float] = None       # Required for LIMIT orders
    trigger_price: Optional[float] = None  # Required for SL orders
    tag: Optional[str] = None           # e.g. "US-01-darvas-breakout"


@dataclass
class OrderResult:
    order_id: str
    status: OrderStatus
    symbol: str
    direction: OrderDirection
    quantity: int
    filled_quantity: int
    average_price: Optional[float]
    timestamp: datetime
    message: Optional[str] = None


@dataclass
class Position:
    symbol: str
    quantity: int                       # Positive = long, negative = short
    average_price: float
    current_price: float
    pnl: float
    pnl_percent: float
    product_type: ProductType


@dataclass
class OHLCV:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class BrokerAdapter(ABC):
    """
    Abstract broker adapter. All broker implementations must
    subclass this and implement every abstract method.

    Usage:
        config = load_config()
        broker = FyersBroker(config)   # or ZerodhaBroker, etc.
        broker.connect()
        result = broker.place_order(order)
    """

    def __init__(self, config: dict):
        self.config = config
        self._connected = False

    # ── Connection ────────────────────────────────────────────────────────────

    @abstractmethod
    def connect(self) -> bool:
        """Authenticate and establish session. Returns True on success."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Clean up session."""
        ...

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Orders ────────────────────────────────────────────────────────────────

    @abstractmethod
    def place_order(self, order: Order) -> OrderResult:
        """Place an order. Raises BrokerError on failure."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order. Returns True on success."""
        ...

    @abstractmethod
    def modify_stop_loss(self, order_id: str, new_trigger_price: float) -> bool:
        """Trail an open order's stop-loss leg to a new absolute trigger
        price (e.g. a Cover Order's SL child order). Returns True on success."""
        ...

    @abstractmethod
    def get_order_status(self, order_id: str) -> OrderResult:
        """Get current status of an order."""
        ...

    @abstractmethod
    def get_order_history(self) -> list[OrderResult]:
        """Get all orders for the current trading day."""
        ...

    # ── Portfolio ─────────────────────────────────────────────────────────────

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """Get all open positions."""
        ...

    @abstractmethod
    def get_funds(self) -> dict:
        """Get available margin/funds. Returns dict with 'available', 'used', 'total'."""
        ...

    # ── Market Data ───────────────────────────────────────────────────────────

    @abstractmethod
    def get_historical_data(
        self,
        symbol: str,
        timeframe: str,       # "1m" | "5m" | "15m" | "1h" | "1d"
        from_date: datetime,
        to_date: datetime,
    ) -> list[OHLCV]:
        """Fetch OHLCV historical data for a symbol."""
        ...

    @abstractmethod
    def get_ltp(self, symbols: list[str]) -> dict[str, float]:
        """Get last traded price for one or more symbols."""
        ...

    # ── Options (used by Epic 7) ──────────────────────────────────────────────

    def get_option_chain(self, underlying: str, expiry: str) -> dict:
        """
        Get full option chain for an underlying.
        Default raises NotImplementedError — brokers that support
        options should override this.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support option chain data."
        )

    # ── Utilities ─────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return f"{self.__class__.__name__}({status})"


class BrokerError(Exception):
    """Raised when a broker operation fails."""
    pass


class InsufficientFundsError(BrokerError):
    """Raised when there are insufficient funds for an order."""
    pass


class MarketClosedError(BrokerError):
    """Raised when attempting to trade outside market hours."""
    pass
