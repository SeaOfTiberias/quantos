"""
QuantOS — ORB Scalping Live Position Store (candidate 18, layer 2 state)
──────────────────────────────────────────────────────────────────────
A separate JSON-store sibling of agent/positions.py::OpenPosition, NOT a
reuse of it: ORB genuinely needs fields Darvas has no room for -- both an
index symbol AND a resolved option symbol, TWO stop levels (index-points
from core/orb_scalping/live_state.py's current_stop, plus the
25%-of-premium stop from core/orb_scalping/premium.py's
PREMIUM_STOP_PCT), a dte_floor_rolled flag, and the trailing-stop `armed`
state. Forcing these into OpenPosition would mean dead fields on every
Darvas position, or fields whose meaning silently depends on
strategy==... -- both worse than this small, separate store.

Persists at its own path (~/.quantos/orb_open_positions.json), never
shared with agent/positions.py's file: that loader does
OpenPosition(**data) unconditionally and would crash on these extra
fields. Same load/add/update/remove API shape as agent/positions.py by
design, so callers familiar with that module aren't surprised by this
one -- see docs/ORB_EXECUTION_LAYER_DESIGN.md.

Consolidating this with the other position-JSON stores (Darvas,
rotation) into one generic store is a real future cleanup opportunity --
explicitly not done here.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

ORB_OPEN_POSITIONS_PATH = Path.home() / ".quantos" / "orb_open_positions.json"

# Separate from ORB_OPEN_POSITIONS_PATH deliberately: that store's dedup key
# (underlying:trade_date) stops protecting against re-entry the moment a
# position is removed on exit, which is exactly what let a live-side force-exit
# (index-stop or session-flatten, both faster than compute_live_state()'s
# close-only candle replay) get immediately re-entered as a "fresh" breakout --
# caught live 2026-09-10 (session-flatten) and again 2026-09-11 (index stop).
# core/orb_scalping/signal.py::simulate_day() is explicit: "one trade per day,
# first breakout only" -- a rule with no natural home in a store whose whole
# purpose is tracking what's currently OPEN. This tiny sibling instead persists
# "underlying already had its one trade today", set at entry and never cleared
# intraday, so the entry check has a source of truth independent of whatever
# compute_live_state()'s own (slower) replay currently reports.
ORB_TRADED_TODAY_PATH = Path.home() / ".quantos" / "orb_traded_today.json"

# docs/ORB_ENTRY_FILTER_METHODOLOGY.md's filtered sibling runs alongside
# (never instead of) unfiltered candidate 18 -- separate files so the two
# processes' open positions and one-trade-per-day marks never collide.
ORB_OPEN_POSITIONS_FILTERED_PATH = Path.home() / ".quantos" / "orb_open_positions_filtered.json"
ORB_TRADED_TODAY_FILTERED_PATH = Path.home() / ".quantos" / "orb_traded_today_filtered.json"


@dataclass
class OrbOpenPosition:
    underlying: str            # "NIFTY" | "BANKNIFTY"
    option_symbol: str         # resolved Fyers tradeable symbol
    direction: str             # "CALL" | "PUT"
    option_type: str           # "CE" | "PE"
    quantity: int              # lots * lot_size
    strike: float
    expiry: str                # ISO date
    dte_floor_rolled: bool
    entry_index_level: float
    entry_premium: float
    entry_timestamp: str       # ISO
    current_index_stop: float
    current_premium_stop: float
    armed: bool
    entry_order_id: str
    stop_order_id: str
    trade_date: str            # ISO date -- dedup key, one trade per index per day


def _key(underlying: str, trade_date: str) -> str:
    return f"{underlying}:{trade_date}"


def load_open_positions(path: Optional[Path] = None) -> dict[str, OrbOpenPosition]:
    """`path` (added 2026-09-22 for docs/ORB_ENTRY_FILTER_METHODOLOGY.md's
    filtered sibling, which needs its own store so it can run alongside
    unfiltered candidate 18 without sharing state) resolves
    ORB_OPEN_POSITIONS_PATH at CALL time, not as a bound default -- a
    default of `path: Path = ORB_OPEN_POSITIONS_PATH` would capture the
    module attribute's value at function-definition time, which is exactly
    the value every existing test's `monkeypatch.setattr(mod,
    "ORB_OPEN_POSITIONS_PATH", ...)` would then have no effect on."""
    path = path or ORB_OPEN_POSITIONS_PATH
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {key: OrbOpenPosition(**data) for key, data in raw.items()}


def _save(positions: dict[str, OrbOpenPosition], path: Optional[Path] = None) -> None:
    path = path or ORB_OPEN_POSITIONS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({key: asdict(p) for key, p in positions.items()}, indent=2)
    )


def add_position(positions: dict[str, OrbOpenPosition], position: OrbOpenPosition,
                  path: Optional[Path] = None) -> None:
    positions[_key(position.underlying, position.trade_date)] = position
    _save(positions, path)


def get_position(positions: dict[str, OrbOpenPosition], underlying: str,
                  trade_date: str) -> Optional[OrbOpenPosition]:
    return positions.get(_key(underlying, trade_date))


def update_stops(positions: dict[str, OrbOpenPosition], underlying: str, trade_date: str,
                  *, current_index_stop: Optional[float] = None,
                  current_premium_stop: Optional[float] = None,
                  armed: Optional[bool] = None, path: Optional[Path] = None) -> None:
    key = _key(underlying, trade_date)
    if key not in positions:
        return
    if current_index_stop is not None:
        positions[key].current_index_stop = current_index_stop
    if current_premium_stop is not None:
        positions[key].current_premium_stop = current_premium_stop
    if armed is not None:
        positions[key].armed = armed
    _save(positions, path)


def remove_position(positions: dict[str, OrbOpenPosition], underlying: str, trade_date: str,
                     path: Optional[Path] = None) -> None:
    positions.pop(_key(underlying, trade_date), None)
    _save(positions, path)


def load_traded_today(path: Optional[Path] = None) -> set[str]:
    path = path or ORB_TRADED_TODAY_PATH
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text()))
    except (json.JSONDecodeError, OSError):
        return set()


def has_traded_today(traded: set[str], underlying: str, trade_date: str) -> bool:
    return _key(underlying, trade_date) in traded


def mark_traded_today(traded: set[str], underlying: str, trade_date: str,
                       path: Optional[Path] = None) -> None:
    traded.add(_key(underlying, trade_date))
    path = path or ORB_TRADED_TODAY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(traded)))
