"""
QuantOS Local Agent — Open Position Store
──────────────────────────────────────────
Tracks positions the agent has entered (CO order + trailing stop) so the
trailing state survives an agent restart. Same on-disk pattern as the
processed-signals cache in agent/main.py.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

OPEN_POSITIONS_PATH = Path.home() / ".quantos" / "open_positions.json"


@dataclass
class OpenPosition:
    signal_id:    str
    symbol:       str
    direction:    str      # "BUY" or "SELL"
    quantity:     int
    entry_price:  float
    entry_date:   str      # ISO timestamp
    timeframe:    str      # entry timeframe used for re-evaluating the trailing stop
    current_stop: float
    sl_order_id:  str
    strategy:     str = "darvas_breakout"


def load_open_positions() -> dict[str, OpenPosition]:
    if not OPEN_POSITIONS_PATH.exists():
        return {}
    try:
        raw = json.loads(OPEN_POSITIONS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {sid: OpenPosition(**data) for sid, data in raw.items()}


def _save(positions: dict[str, OpenPosition]) -> None:
    OPEN_POSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPEN_POSITIONS_PATH.write_text(
        json.dumps({sid: asdict(p) for sid, p in positions.items()}, indent=2)
    )


def add_position(positions: dict[str, OpenPosition], position: OpenPosition) -> None:
    positions[position.signal_id] = position
    _save(positions)


def update_stop(positions: dict[str, OpenPosition], signal_id: str, new_stop: float) -> None:
    if signal_id in positions:
        positions[signal_id].current_stop = new_stop
        _save(positions)


def remove_position(positions: dict[str, OpenPosition], signal_id: str) -> None:
    positions.pop(signal_id, None)
    _save(positions)
