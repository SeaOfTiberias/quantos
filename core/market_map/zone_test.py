"""
QuantOS — Market Map: the zone test's event and outcome rules (pure)
────────────────────────────────────────────────────────────────────
docs/PRICE_MAP_ZONES_PREREG_2026-10-28.md and its amendment 1 B, as code.
scripts/run_zone_test.py feeds it bars and point-in-time maps; nothing here
reads a file, a clock or a broker.

  candidate   a band with the previous close more than 0.1 ATR outside it
  entry       the first 5-minute bar of D whose range overlaps the band
  outcome     first passage from the entry bar to the end of D+4:
              rejected = 0.5 ATR back past the near edge (from the bar AFTER entry),
              broken   = 0.5 ATR past the far edge (from the entry bar; a bar
                         doing both counts as broken), else timeout
  placebo     a strong-zone candidate mirrored through the previous close,
              valid if more than 0.3 ATR from every zone of the day's map
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

SUPPORT, RESISTANCE = "support", "resistance"
ENTRY_GAP_ATR = 0.1
MOVE_ATR = 0.5
PLACEBO_CLEAR_ATR = 0.3
SKIP_SESSIONS = 5
REJECTED, BROKEN, TIMEOUT = "rejected", "broken", "timeout"


@dataclass(frozen=True)
class Band:
    low: float
    high: float


def side(band: Band, prev_close: float, atr: float) -> Optional[str]:
    """The test side fixed by the previous close, or None when it is not clearly outside."""
    if prev_close > band.high + ENTRY_GAP_ATR * atr:
        return SUPPORT
    if prev_close < band.low - ENTRY_GAP_ATR * atr:
        return RESISTANCE
    return None


def entry(bars: Sequence, band: Band) -> Optional[int]:
    """Index of the first bar whose range overlaps the band."""
    return next((i for i, b in enumerate(bars) if b.low <= band.high and b.high >= band.low), None)


def outcome(bars: Sequence, band: Band, sd: str, atr: float, complete: bool) -> str:
    """First passage over `bars` (entry bar first). `complete` = the window holds all of D..D+4;
    an incomplete window that resolves nothing is a timeout either way."""
    if sd == SUPPORT:
        rej, brk = band.high + MOVE_ATR * atr, band.low - MOVE_ATR * atr
        for i, b in enumerate(bars):
            if b.low <= brk:
                return BROKEN
            if i > 0 and b.high >= rej:
                return REJECTED
    else:
        rej, brk = band.low - MOVE_ATR * atr, band.high + MOVE_ATR * atr
        for i, b in enumerate(bars):
            if b.high >= brk:
                return BROKEN
            if i > 0 and b.low <= rej:
                return REJECTED
    return TIMEOUT


def placebo(band: Band, prev_close: float, zones: Sequence[dict], atr: float) -> Optional[Band]:
    """The band mirrored through the previous close, if it is clear of every zone by 0.3 ATR."""
    p = Band(round(2 * prev_close - band.high, 4), round(2 * prev_close - band.low, 4))
    pad = PLACEBO_CLEAR_ATR * atr
    if p.low <= 0:
        return None
    for z in zones:
        if z["low"] - pad <= p.high and z["high"] + pad >= p.low:
            return None
    return p


class Seen:
    """Events already counted, per kind, for the 5-session skip across rebuilt maps."""

    def __init__(self):
        self._ev: dict[str, list[tuple[int, Band]]] = {}

    def recent(self, kind: str, session: int, band: Band) -> bool:
        return any(0 < session - s <= SKIP_SESSIONS and b.low <= band.high and b.high >= band.low
                   for s, b in self._ev.get(kind, []))

    def add(self, kind: str, session: int, band: Band) -> None:
        lst = self._ev.setdefault(kind, [])
        lst.append((session, band))
        self._ev[kind] = [(s, b) for s, b in lst if session - s <= SKIP_SESSIONS]


def htf_label(stage: Optional[int], sd: str) -> str:
    """Amendment 1 A: support in stage 2 / resistance in stage 4 = with the HTF trend."""
    if stage == 2:
        return "with" if sd == SUPPORT else "against"
    if stage == 4:
        return "with" if sd == RESISTANCE else "against"
    return "none" if stage in (1, 3) else "unclassified"


def day_events(session: int, zones: Sequence[dict], prev_close: float, atr: float, today_bars: Sequence,
               window: Sequence, complete: bool, seen: Seen) -> list[dict]:
    """Every strong, weak and placebo event of one stock on one session.
    `today_bars` = D's 5-minute bars; `window` = D..D+4's bars (D's first)."""
    out = []

    def test(kind: str, band: Band, sd: str, extra: dict) -> None:
        if seen.recent(kind, session, band):
            return
        i = entry(today_bars, band)
        if i is None:
            return
        seen.add(kind, session, band)
        out.append({"kind": kind, "side": sd, "low": band.low, "high": band.high,
                    "outcome": outcome(window[i:], band, sd, atr, complete), **extra})

    for z in zones:
        band = Band(z["low"], z["high"])
        sd = side(band, prev_close, atr)
        if sd is None:
            continue
        kind = "strong" if z["strong"] else "weak"
        test(kind, band, sd, {"families": "+".join(z.get("families", []))})
        if kind == "strong":
            p = placebo(band, prev_close, zones, atr)
            if p is not None:
                test("placebo", p, RESISTANCE if sd == SUPPORT else SUPPORT, {"families": ""})
    return out
