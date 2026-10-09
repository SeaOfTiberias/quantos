"""
QuantOS — Trade Watcher: exit rules for a long option position
───────────────────────────────────────────────────────────────
Pure logic, no I/O. scripts/run_trade_watcher.py feeds it every live
price tick for a position it is managing and turns the returned events
into Telegram messages.

The rules, all on the option's own premium:
  - initial stop at `initial_stop_pct` below the entry price
  - once the premium has been `breakeven_at_pct` above entry, the stop
    moves to entry + `breakeven_lock_pct` (0 = plain breakeven; set it to
    cover brokerage and keep a small profit). breakeven_at_pct 0 = off
  - once it has been `trail_after_pct` above entry, the stop trails at
    `trail_pct` below the highest premium seen since entry
  - the stop only ever moves up -- except rearm(), after the user has held
    through an exit alert, which re-arms it below the current price

Stage 1 (this module's only consumer today) never places orders: an
"exit" event is a message telling the user to exit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

DEFAULT_RULES = dict(initial_stop_pct=15.0, breakeven_at_pct=10.0, breakeven_lock_pct=0.0,
                     trail_after_pct=15.0, trail_pct=10.0)


@dataclass(frozen=True)
class ExitRules:
    initial_stop_pct: float = DEFAULT_RULES["initial_stop_pct"]
    breakeven_at_pct: float = DEFAULT_RULES["breakeven_at_pct"]
    breakeven_lock_pct: float = DEFAULT_RULES["breakeven_lock_pct"]
    trail_after_pct:  float = DEFAULT_RULES["trail_after_pct"]
    trail_pct:        float = DEFAULT_RULES["trail_pct"]

    @classmethod
    def from_config(cls, cfg: Optional[dict]) -> "ExitRules":
        cfg = cfg or {}
        return cls(**{k: float(cfg.get(k, v)) for k, v in DEFAULT_RULES.items()})


@dataclass
class ManagedPosition:
    symbol:       str
    entry:        float          # average buy price of the open quantity
    quantity:     int
    high:         float          # highest premium seen since entry
    stop:         float
    breakeven_on: bool = False
    trail_on:     bool = False
    exit_alerted: bool = False   # an EXIT NOW has gone out; stays set until the position closes
    last_ltp:     Optional[float] = None
    events_seen:  list = field(default_factory=list)   # not persisted; for tests/debugging

    @classmethod
    def open(cls, symbol: str, entry: float, quantity: int, rules: ExitRules) -> "ManagedPosition":
        return cls(symbol=symbol, entry=entry, quantity=quantity, high=entry,
                   stop=round(entry * (1 - rules.initial_stop_pct / 100), 2))

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("events_seen", None)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ManagedPosition":
        d = {k: v for k, v in d.items() if k in cls.__dataclass_fields__ and k != "events_seen"}
        return cls(**d)


@dataclass(frozen=True)
class Event:
    kind:  str     # "exit" | "trail_on" | "breakeven" | "stop_raised"
    price: float   # the tick that triggered it
    stop:  float   # the stop after this tick


def on_tick(pos: ManagedPosition, ltp: float, rules: ExitRules) -> list[Event]:
    """Apply one price tick. Exit is checked against the stop as it stood
    BEFORE this tick; only then does the tick ratchet the stop up."""
    if ltp is None or ltp <= 0:
        return []
    pos.last_ltp = ltp
    if ltp <= pos.stop:
        if pos.exit_alerted:
            return []
        pos.exit_alerted = True
        out = [Event("exit", ltp, pos.stop)]
        pos.events_seen.extend(out)
        return out

    events: list[str] = []

    pos.high = max(pos.high, ltp)
    gain_pct = round((pos.high / pos.entry - 1) * 100, 6)   # 115/100 must read as +15%, not 14.999..
    new_stop = pos.stop
    if rules.breakeven_at_pct > 0 and gain_pct >= rules.breakeven_at_pct and not pos.breakeven_on:
        pos.breakeven_on = True
        lock = round(pos.entry * (1 + rules.breakeven_lock_pct / 100), 2)
        if lock > new_stop:
            new_stop = lock
            events.append("breakeven")
    if gain_pct >= rules.trail_after_pct:
        if not pos.trail_on:
            pos.trail_on = True
            events.append("trail_on")
        new_stop = max(new_stop, pos.high * (1 - rules.trail_pct / 100))
    new_stop = round(new_stop, 2)
    if new_stop > pos.stop:
        pos.stop = new_stop
        if not events:   # a breakeven/trail_on message already announces the new stop
            events.append("stop_raised")
    out = [Event(kind, ltp, pos.stop) for kind in events]
    pos.events_seen.extend(out)
    return out


def rearm(pos: ManagedPosition, rules: ExitRules) -> Optional[float]:
    """The user held through an EXIT NOW and its reminders: arm a fresh stop
    `initial_stop_pct` below the last price, as if the position were opened
    there, so a further fall is still caught. The high resets to that price,
    so a trail already on continues from it instead of firing at once off the
    old high. Returns the new stop, or None with no price to arm from."""
    if not pos.last_ltp or pos.last_ltp <= 0:
        return None
    pos.high = pos.last_ltp
    pos.stop = round(pos.last_ltp * (1 - rules.initial_stop_pct / 100), 2)
    pos.exit_alerted = False
    return pos.stop


def is_option_symbol(symbol: str) -> bool:
    """Fyers option symbols end in CE/PE, e.g. NSE:BANKNIFTY26OCT54900CE."""
    s = symbol.upper()
    return (s.startswith("NSE:") or s.startswith("BSE:")) and (s.endswith("CE") or s.endswith("PE")) \
        and not s.endswith("-EQ")
