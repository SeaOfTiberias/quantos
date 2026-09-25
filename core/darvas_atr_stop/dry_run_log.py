"""
QuantOS — Darvas ATR-Stop dry-run trade log (observability only)
──────────────────────────────────────────────────────────────────────
Same problem and same fix as core/orb_scalping/dry_run_log.py: dry_run
never places a real order, so a closed dry-run position previously left
no queryable record of what would have happened -- only a printed line
in journalctl. This module is that missing record: one append-only
JSON-lines file, written on every dry-run close, bundling a full
entry+exit round trip in one line.

Why this exists specifically (not just "for completeness"): PF/Sharpe on
the backtest's own cache tells you whether a signal has edge. It cannot
tell you whether LIVE data reproduces the same entries, the same box
widths, the same trailing behaviour, or roughly the same holding period
the backtest assumed -- exactly the gap
docs/DARVAS_ATR_STOP_EQUITY_CURVE_RESULTS.md's own equity-curve work
depends on eventually closing with REAL (not backtest-cache) trades. One
line per completed round trip -- entry/exit price, date, quantity, exit
reason, and the box context the trade was actually sized against -- is
enough to feed a real equity-curve simulator later without re-deriving
any of it from logs by hand, the same reconstruction problem ORB's own
sessions hit before this pattern existed.

Append-only, one JSON object per line, never rewritten in place -- same
atomicity reasoning as core/orb_scalping/dry_run_log.py: appending a
line can't corrupt a trade that already happened, and a single malformed
line on read is skippable without losing the rest of the log.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

DARVAS_ATR_STOP_DRY_RUN_LOG_PATH = Path.home() / ".quantos" / "darvas_atr_stop_dry_run_trades.jsonl"


@dataclass(frozen=True)
class DarvasDryRunTrade:
    symbol:            str
    entry_timestamp:   str      # ISO date -- when the position was opened
    entry_price:       float    # the sizing-time estimate (LTP, or yesterday's close as fallback)
    exit_timestamp:    str      # ISO
    exit_reason:       str      # "stop" | "target"
    quantity:          int
    box_width_pct:     float    # confirms this really was a Bucket B (35-50%) entry, over live data
    seen_ceiling:      float    # box ceiling the stop/target were last derived from at exit
    boundary_price:    float    # the theoretical stop/target level that triggered this exit
    # Best-effort real quote fetched at the moment of exit -- observability
    # only, never fed into sizing or trade_history (same convention as
    # ORB's own exit_premium). None when no live quote could be fetched.
    exit_ltp:          Optional[float] = None


def append_dry_run_trade(trade: DarvasDryRunTrade, path: Optional[Path] = None) -> None:
    path = path or DARVAS_ATR_STOP_DRY_RUN_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(trade)) + "\n")


def load_dry_run_trades(path: Optional[Path] = None) -> list[DarvasDryRunTrade]:
    """Never raises: a malformed line is skipped, not fatal to the rest of
    the log -- same defensive-read convention as every JSON store in this
    package (core/darvas_atr_stop/live_positions.py's load_open_positions)."""
    path = path or DARVAS_ATR_STOP_DRY_RUN_LOG_PATH
    if not path.exists():
        return []
    out: list[DarvasDryRunTrade] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(DarvasDryRunTrade(**json.loads(line)))
        except (json.JSONDecodeError, TypeError):
            continue
    return out
