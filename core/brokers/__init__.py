"""
Broker factory — resolves broker name from config to adapter instance.
Add new brokers here as they are implemented.
"""

from core.brokers.base import BrokerAdapter, BrokerError
from core.brokers.fyers import FyersBroker
from core.brokers.zerodha import ZerodhaBroker

_BROKER_MAP = {
    "fyers": FyersBroker,
    "zerodha": ZerodhaBroker,
    # "angel_one": AngelOneBroker,  # v2
    # "upstox": UpstoxBroker,       # v2
}


def get_broker(config: dict) -> BrokerAdapter:
    """
    Instantiate the correct broker adapter from config.

    Usage:
        config = load_config()          # reads agent/config.yaml
        broker = get_broker(config)
        broker.connect()
    """
    broker_name = config.get("broker", "").lower()
    if broker_name not in _BROKER_MAP:
        raise BrokerError(
            f"Unknown broker '{broker_name}'. "
            f"Supported: {list(_BROKER_MAP.keys())}"
        )
    return _BROKER_MAP[broker_name](config)


__all__ = ["get_broker", "BrokerAdapter", "BrokerError",
           "FyersBroker", "ZerodhaBroker"]
