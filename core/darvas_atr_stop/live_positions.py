"""
QuantOS — Darvas ATR-Stop (Bucket B) Live Position Store
──────────────────────────────────────────────────────────────────────
Separate JSON store, sibling of core/orb_scalping/live_positions.py and
NOT a reuse of agent/positions.py::OpenPosition -- that store belongs to
the OLD scanner.py/Telegram-confirm pipeline this candidate deliberately
does not build on (see scripts/run_darvas_atr_stop_live.py's module
docstring for why). Keyed by symbol alone, not symbol+date: unlike
candidate 18's one-trade-per-day options positions, a Darvas equity
position is held for days-to-weeks, so "is SYMBOL currently held" is the
whole dedup question -- there is never more than one open position per
symbol at a time (a fresh breakout in an already-held symbol cannot
re-fire; see analyse_symbol's own prev_close <= box_ceil gate).

Persists at its own path (~/.quantos/darvas_atr_stop_open_positions.json).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

DARVAS_ATR_STOP_OPEN_POSITIONS_PATH = Path.home() / ".quantos" / "darvas_atr_stop_open_positions.json"


@dataclass
class DarvasOpenPosition:
    symbol:            str
    quantity:           int
    entry_price:        float
    entry_date:         str      # ISO date -- also the trade_id/dedup source
    box_width_pct:      float
    seen_ceiling:        float    # box ceiling the current stop/target were derived from
    current_stop:        float
    current_target:      float
    entry_order_id:      str
    stop_order_id:        str


def load_open_positions(path: Optional[Path] = None) -> dict[str, DarvasOpenPosition]:
    """`path` resolves DARVAS_ATR_STOP_OPEN_POSITIONS_PATH at CALL time, not
    as a bound default -- same reasoning as core/orb_scalping/live_positions.py's
    own loader: a bound default would ignore a test's
    monkeypatch.setattr(mod, "DARVAS_ATR_STOP_OPEN_POSITIONS_PATH", ...)."""
    path = path or DARVAS_ATR_STOP_OPEN_POSITIONS_PATH
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {symbol: DarvasOpenPosition(**data) for symbol, data in raw.items()}


def _save(positions: dict[str, DarvasOpenPosition], path: Optional[Path] = None) -> None:
    path = path or DARVAS_ATR_STOP_OPEN_POSITIONS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({symbol: asdict(p) for symbol, p in positions.items()}, indent=2)
    )


def add_position(positions: dict[str, DarvasOpenPosition], position: DarvasOpenPosition,
                  path: Optional[Path] = None) -> None:
    positions[position.symbol] = position
    _save(positions, path)


def get_position(positions: dict[str, DarvasOpenPosition], symbol: str) -> Optional[DarvasOpenPosition]:
    return positions.get(symbol)


def update_trail(positions: dict[str, DarvasOpenPosition], symbol: str, *,
                  current_stop: Optional[float] = None, current_target: Optional[float] = None,
                  seen_ceiling: Optional[float] = None, path: Optional[Path] = None) -> None:
    if symbol not in positions:
        return
    if current_stop is not None:
        positions[symbol].current_stop = current_stop
    if current_target is not None:
        positions[symbol].current_target = current_target
    if seen_ceiling is not None:
        positions[symbol].seen_ceiling = seen_ceiling
    _save(positions, path)


def remove_position(positions: dict[str, DarvasOpenPosition], symbol: str,
                     path: Optional[Path] = None) -> None:
    positions.pop(symbol, None)
    _save(positions, path)
