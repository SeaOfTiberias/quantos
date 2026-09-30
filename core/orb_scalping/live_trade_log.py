"""
QuantOS — ORB live trade event log (real orders only)
──────────────────────────────────────────────────────
The live counterpart of core/orb_scalping/dry_run_log.py. A live close is
recorded as a ClosedTrade in trade_history.json, but ClosedTrade carries no
exit reason, no pre-trade quote and no order ids. Those are exactly what the
1-lot live pilot (2026-09-30) exists to measure: how real fills differ from the
chain quote paper trades at, and which exit paths actually fire at the broker.

One append-only JSON-lines file per strategy_name
(~/.quantos/<strategy_name>_live_trades.jsonl), one "entry" event when a
real position opens and one "exit" event when it closes. Two events, not one
row, so a crash between entry and exit still leaves the entry on record.
Same append-only / skip-malformed-lines conventions as dry_run_log.py.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


def live_trade_log_path(strategy_name: str) -> Path:
    return Path.home() / ".quantos" / f"{strategy_name}_live_trades.jsonl"


@dataclass(frozen=True)
class LiveTradeEvent:
    event:          str                      # "entry" | "exit"
    underlying:     str                      # "NIFTY" | "BANKNIFTY"
    option_symbol:  str
    direction:      str                      # "CALL" | "PUT"
    timestamp:      str                      # ISO
    quantity:       int
    # entry: the option-chain LTP the decision was made on (what paper would
    # record). exit: None.
    quoted_premium: Optional[float] = None
    # Real average fill from the broker; None when it could not be read.
    fill_price:     Optional[float] = None
    reason:         Optional[str] = None     # exit only: premium_stop | stop | trailing_stop | session_flatten | manual | unknown
    order_id:       Optional[str] = None
    stop_order_id:  Optional[str] = None     # entry only; None means no stop was left resting
    note:           str = ""


def append_live_event(event: LiveTradeEvent, strategy_name: str, path: Optional[Path] = None) -> None:
    path = path or live_trade_log_path(strategy_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(event)) + "\n")


def load_live_events(strategy_name: str, path: Optional[Path] = None) -> list[LiveTradeEvent]:
    path = path or live_trade_log_path(strategy_name)
    if not path.exists():
        return []
    out: list[LiveTradeEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(LiveTradeEvent(**json.loads(line)))
        except (json.JSONDecodeError, TypeError):
            continue
    return out
