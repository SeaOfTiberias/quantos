"""
QuantOS Local Agent — Momentum Turnover Walk-Forward: paper position store
────────────────────────────────────────────────────────────────────────────
docs/MOMENTUM_TURNOVER_WALKFORWARD_METHODOLOGY.md (candidate 11's
out-of-sample walk-forward). Tracks a virtual cash ledger, virtual
holdings, closed trades, and a mark-to-market equity curve for the
quarterly-cadence momentum walk-forward — entirely separate from
agent/rotation_positions.py (S8-3's REAL weekly rotation holdings). No
code path here ever touches real capital or the real position file.

Same on-disk JSON pattern as agent/positions.py and
agent/rotation_positions.py, one file, atomic full-file rewrite on save.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

PAPER_WALKFORWARD_STATE_PATH = Path.home() / ".quantos" / "paper_rotation_walkforward.json"


@dataclass
class PaperPosition:
    symbol:       str
    quantity:     int
    entry_price:  float
    entry_date:   str      # ISO date


@dataclass
class PaperTrade:
    symbol:       str
    entry_date:   str
    entry_price:  float
    exit_date:    str
    exit_price:   float
    quantity:     int
    exit_reason:  str      # "rank_dropout" (the only reason this walk-forward's
                            # exit_rule="rank_only" can ever produce, matching
                            # the pre-registered ablation exactly)
    cost:         float    # round-trip CostModel.cost_of() charged on this trade


@dataclass
class EquityPoint:
    date:   str    # ISO date
    equity: float  # cash + mark-to-market value of open paper holdings


@dataclass
class PaperWalkforwardState:
    initial_capital:            float
    cash:                        float
    positions:                   dict[str, PaperPosition] = field(default_factory=dict)
    closed_trades:                list[PaperTrade] = field(default_factory=list)
    equity_curve:                 list[EquityPoint] = field(default_factory=list)
    last_rebalanced_quarter_end:  Optional[str] = None   # ISO date, idempotency guard


def load_state(initial_capital: float) -> PaperWalkforwardState:
    """First call ever (no file yet) starts a fresh ledger at
    initial_capital — every later call must pass the SAME initial_capital
    (docs/MOMENTUM_TURNOVER_WALKFORWARD_METHODOLOGY.md pre-commits
    ₹1,000,000, do not change it mid-flight); the stored value always wins
    once a file exists, since only the file's own capital reflects
    what's actually happened to the ledger since day one."""
    if not PAPER_WALKFORWARD_STATE_PATH.exists():
        return PaperWalkforwardState(initial_capital=initial_capital, cash=initial_capital)
    try:
        raw = json.loads(PAPER_WALKFORWARD_STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return PaperWalkforwardState(initial_capital=initial_capital, cash=initial_capital)

    return PaperWalkforwardState(
        initial_capital=raw["initial_capital"],
        cash=raw["cash"],
        positions={s: PaperPosition(**p) for s, p in raw.get("positions", {}).items()},
        closed_trades=[PaperTrade(**t) for t in raw.get("closed_trades", [])],
        equity_curve=[EquityPoint(**e) for e in raw.get("equity_curve", [])],
        last_rebalanced_quarter_end=raw.get("last_rebalanced_quarter_end"),
    )


def save_state(state: PaperWalkforwardState) -> None:
    PAPER_WALKFORWARD_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "initial_capital": state.initial_capital,
        "cash": state.cash,
        "positions": {s: asdict(p) for s, p in state.positions.items()},
        "closed_trades": [asdict(t) for t in state.closed_trades],
        "equity_curve": [asdict(e) for e in state.equity_curve],
        "last_rebalanced_quarter_end": state.last_rebalanced_quarter_end,
    }
    PAPER_WALKFORWARD_STATE_PATH.write_text(json.dumps(payload, indent=2))
