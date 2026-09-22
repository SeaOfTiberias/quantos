"""
QuantOS — ORB dry-run trade log (observability only)
──────────────────────────────────────────────────────
Neither variant of the live ORB script (unfiltered candidate 18 or
docs/ORB_ENTRY_FILTER_METHODOLOGY.md's filtered sibling) places a real
order in dry_run, so a closed dry-run position previously left no
queryable record of what would have happened — only a printed line in
journalctl (this is how every number in this project's live ORB tracking
sessions had to be reconstructed, by hand, from log archaeology). This
module is that missing record: one append-only JSON-lines file per
variant, written on every dry-run close.

It exists specifically so docs/ORB_ENTRY_FILTER_METHODOLOGY.md's
prospective-verdict method (compute Stratified-shaped PF/Sharpe on
genuinely new forward trades, filtered vs. unfiltered, same window) has
something to read once enough trades accumulate — nothing reads this file
yet.

Append-only, one JSON object per line, never rewritten in place — the
failure mode to avoid is a partial rewrite corrupting trades that already
happened; appending a line is atomic enough for this, and a single
malformed line on read is skippable without losing the rest of the log.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

ORB_DRY_RUN_LOG_PATH = Path.home() / ".quantos" / "orb_dry_run_trades.jsonl"
ORB_DRY_RUN_LOG_FILTERED_PATH = Path.home() / ".quantos" / "orb_dry_run_trades_filtered.jsonl"


@dataclass(frozen=True)
class DryRunTrade:
    underlying:      str             # "NIFTY" | "BANKNIFTY"
    direction:        str            # "CALL" | "PUT"
    entry_timestamp:  str            # ISO
    entry_premium:    float
    exit_timestamp:   str            # ISO
    exit_reason:      str            # "stop" | "trailing_stop" | "premium_stop" | "session_flatten"
    quantity:         int
    # None when no live quote could be fetched at the moment of exit —
    # never guessed or backfilled from a later, unrelated price.
    exit_premium:     Optional[float] = None


def append_dry_run_trade(trade: DryRunTrade, path: Optional[Path] = None) -> None:
    path = path or ORB_DRY_RUN_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(trade)) + "\n")


def load_dry_run_trades(path: Optional[Path] = None) -> list[DryRunTrade]:
    """Never raises: a malformed line is skipped, not fatal to the rest of
    the log — same defensive-read convention as every JSON store in this
    package (core/orb_scalping/live_positions.py's load_open_positions)."""
    path = path or ORB_DRY_RUN_LOG_PATH
    if not path.exists():
        return []
    out: list[DryRunTrade] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(DryRunTrade(**json.loads(line)))
        except (json.JSONDecodeError, TypeError):
            continue
    return out
