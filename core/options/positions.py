"""
QuantOS — Options Execution Position Store
─────────────────────────────────────────────
Tracks open multi-leg options spreads placed via the regime/strategy
advisor, entirely separate from agent/positions.py's Darvas OpenPosition
store and agent/rotation_positions.py's rotation store — same reasoning
as rotation's own module docstring: none of these three position counts
or caps are related to each other.

Exit rule is "hold to expiry" (no active management, no stop-loss field —
see the quantos-dashboard-polish-next-session design decision), so this
store exists for three reasons only: (1) cockpit visibility, (2) letting
core/options/regime_trigger.py refuse to fire a second suggestion for an
underlying that already has one open, (3) an audit trail of what was
actually placed. It does NOT track post-expiry settlement P&L — that
would need an end-of-day settlement-price capture, a separate feature
this doesn't build.

Keyed by underlying (not signal_id) — at most one open options position
per underlying at a time is the whole point of the dedup this store exists
to support. Same on-disk JSON pattern as agent/rotation_positions.py.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

OPTIONS_POSITIONS_PATH = Path.home() / ".quantos" / "options_positions.json"


@dataclass
class OptionsPosition:
    signal_id:   str
    underlying:  str
    strategy:    str
    expiry:      str              # ISO date
    legs:        list[dict] = field(default_factory=list)  # resolved legs incl. fills
    entry_date:  str = ""         # ISO timestamp


def load_positions() -> dict[str, OptionsPosition]:
    if not OPTIONS_POSITIONS_PATH.exists():
        return {}
    try:
        raw = json.loads(OPTIONS_POSITIONS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {underlying: OptionsPosition(**data) for underlying, data in raw.items()}


def _save(positions: dict[str, OptionsPosition]) -> None:
    OPTIONS_POSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPTIONS_POSITIONS_PATH.write_text(
        json.dumps({u: asdict(p) for u, p in positions.items()}, indent=2)
    )


def add_position(positions: dict[str, OptionsPosition], position: OptionsPosition) -> None:
    positions[position.underlying] = position
    _save(positions)


def remove_position(positions: dict[str, OptionsPosition], underlying: str) -> None:
    positions.pop(underlying, None)
    _save(positions)


def has_open_position(positions: dict[str, OptionsPosition], underlying: str,
                       today: Optional[date] = None) -> bool:
    """True if `underlying` has a tracked position whose expiry hasn't
    passed yet. A position past its own expiry no longer blocks a new
    suggestion — the contract has already settled at the broker."""
    position = positions.get(underlying)
    if position is None:
        return False
    today = today or date.today()
    return date.fromisoformat(position.expiry) >= today
