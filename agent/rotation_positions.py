"""
QuantOS Local Agent — S8-3 Rotation Position Store
─────────────────────────────────────────────────────
Tracks the weekly RS-momentum rotation basket's current holdings, entirely
separate from agent/positions.py's Darvas OpenPosition store — the two
strategies must never share a position count or file, since rotation's
20-name cap and Darvas's max_open_positions cap (2-5) are unrelated limits.

No stop-loss field: this strategy's exit rule is rank-based ("sell the week
a symbol first leaves the top N"), not stop-based — see
docs/S8_3_MOMENTUM_METHODOLOGY.md's entry/exit section. Same on-disk JSON
pattern as agent/positions.py.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROTATION_POSITIONS_PATH = Path.home() / ".quantos" / "rotation_positions.json"


@dataclass
class RotationPosition:
    symbol:       str
    quantity:     int
    entry_price:  float
    entry_date:   str      # ISO timestamp


def load_rotation_positions() -> dict[str, RotationPosition]:
    if not ROTATION_POSITIONS_PATH.exists():
        return {}
    try:
        raw = json.loads(ROTATION_POSITIONS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {symbol: RotationPosition(**data) for symbol, data in raw.items()}


def _save(positions: dict[str, RotationPosition]) -> None:
    ROTATION_POSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ROTATION_POSITIONS_PATH.write_text(
        json.dumps({symbol: asdict(p) for symbol, p in positions.items()}, indent=2)
    )


def add_position(positions: dict[str, RotationPosition], position: RotationPosition) -> None:
    positions[position.symbol] = position
    _save(positions)


def remove_position(positions: dict[str, RotationPosition], symbol: str) -> None:
    positions.pop(symbol, None)
    _save(positions)
