"""
QuantOS Local Agent — Momentum Turnover Real-Capital Pilot: position store
────────────────────────────────────────────────────────────────────────────
Tracks the real-money pilot's own holdings, cumulative realized P&L, and
quarter-boundary bookkeeping. Entirely separate from:
  - agent/rotation_positions.py (S8-3's weekly rotation — stays dry_run)
  - agent/paper_rotation_positions.py (the paper walk-forward ledger — the
    pilot runs ALONGSIDE this, not instead of it)

`realized_pnl` is the pilot's OWN cumulative net P&L (not the whole broker
account's) — the input to core/rotation/pilot_executor.py's stop-loss check.
Deliberately no `cash` field (unlike the paper ledger): real buy sizing
always reads live broker.get_funds(), never a locally-tracked cash number.

Same on-disk JSON pattern as agent/rotation_positions.py and
agent/paper_rotation_positions.py, one file, atomic full-file rewrite on save.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

PILOT_STATE_PATH = Path.home() / ".quantos" / "rotation_pilot_state.json"


@dataclass
class PilotPosition:
    symbol:       str
    quantity:     int
    entry_price:  float
    entry_date:   str      # ISO timestamp


@dataclass
class PilotState:
    positions:                    dict[str, PilotPosition] = field(default_factory=dict)
    realized_pnl:                 float = 0.0
    last_rebalanced_quarter_end:  Optional[str] = None   # ISO date, idempotency guard


def load_state() -> PilotState:
    if not PILOT_STATE_PATH.exists():
        return PilotState()
    try:
        raw = json.loads(PILOT_STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return PilotState()

    return PilotState(
        positions={s: PilotPosition(**p) for s, p in raw.get("positions", {}).items()},
        realized_pnl=raw.get("realized_pnl", 0.0),
        last_rebalanced_quarter_end=raw.get("last_rebalanced_quarter_end"),
    )


def save_state(state: PilotState) -> None:
    PILOT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "positions": {s: asdict(p) for s, p in state.positions.items()},
        "realized_pnl": state.realized_pnl,
        "last_rebalanced_quarter_end": state.last_rebalanced_quarter_end,
    }
    PILOT_STATE_PATH.write_text(json.dumps(payload, indent=2))
