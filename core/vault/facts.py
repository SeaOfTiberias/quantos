"""
QuantOS — Obsidian Vault: market facts
───────────────────────────────────────
The numeric side of a rule audit. `MarketFacts` wraps one symbol's daily bars
and exposes exactly the vocabulary the rule DSL is allowed to reference —
`close`, `sma(n)`, `high(n)`, `volume_sma(n)` and friends — each addressable
at a bar offset so a note can write `sma(200)[20]` for "the 200-day average
twenty sessions ago".

Two rules govern this module:

1. **Reuse, never re-implement.** `sma_series`/`ema_series` come from
   core/discovery/momentum_shortlist.py and `rolling_high_series` from
   core/rotation/ranker.py. Both are already tested and already drive live
   output. A second, private moving-average implementation here would be a
   silent fork of the definitions the rest of the system trades on — the same
   hazard core/rotation/ranker.py's docstring warns about for the ranking
   formula.

2. **Never fabricate a fact.** Every accessor returns None rather than a
   guess when it cannot be computed — not enough bars to warm up the window,
   or a value that was simply never supplied. The rule engine turns that None
   into INSUFFICIENT_DATA, which blocks. `rs_rating` is the sharp case: it is
   a *cross-sectional* measure that cannot be derived from one symbol's bars,
   so it must be injected by a caller that actually has the universe. If it
   isn't, any rule mentioning it is unevaluable and says so.
"""

from __future__ import annotations

from typing import Optional

from core.brokers.base import OHLCV
from core.discovery.momentum_shortlist import ema_series, sma_series


class MarketFacts:
    """Read-only view of one symbol's daily history, addressed by bar offset.

    Offset 0 is the most recent bar; offset 1 is the session before it. All
    windows are measured backwards from the offset, so `sma(50)[10]` is the
    50-day mean of the fifty sessions ending ten sessions ago.
    """

    def __init__(
        self,
        symbol: str,
        daily: list[OHLCV],
        *,
        rs_rating: Optional[float] = None,
    ) -> None:
        """
        `rs_rating` is a 0-100 cross-sectional percentile (higher = stronger),
        supplied by whoever holds the universe. Left None, rules referencing
        it become unevaluable rather than silently passing. See
        core/vault/gates.py for how the momentum shortlist derives one from
        its own 52-week-high ranking, and what that proxy does and does not
        mean.
        """
        self.symbol = symbol
        self._bars = daily
        self._rs_rating = rs_rating
        self._closes = [b.close for b in daily]
        self._volumes = [float(b.volume) for b in daily]
        # Series are computed once per window size and reused across every
        # rule in every note — a Minervini audit alone touches SMA 50/150/200
        # at two offsets each.
        self._sma_cache: dict[int, list[Optional[float]]] = {}
        self._ema_cache: dict[int, list[Optional[float]]] = {}
        self._vol_sma_cache: dict[int, list[Optional[float]]] = {}

    # ── bar-level scalars ─────────────────────────────────────────────────

    def _bar(self, offset: int) -> Optional[OHLCV]:
        if offset < 0 or offset >= len(self._bars):
            return None
        return self._bars[-1 - offset]

    def close(self, offset: int = 0) -> Optional[float]:
        bar = self._bar(offset)
        return bar.close if bar else None

    def bar_open(self, offset: int = 0) -> Optional[float]:
        bar = self._bar(offset)
        return bar.open if bar else None

    def bar_high(self, offset: int = 0) -> Optional[float]:
        bar = self._bar(offset)
        return bar.high if bar else None

    def bar_low(self, offset: int = 0) -> Optional[float]:
        bar = self._bar(offset)
        return bar.low if bar else None

    def volume(self, offset: int = 0) -> Optional[float]:
        bar = self._bar(offset)
        return float(bar.volume) if bar else None

    def rs_rating(self, offset: int = 0) -> Optional[float]:
        """Cross-sectional relative strength percentile, 0-100.

        Only defined at offset 0 — it is a snapshot supplied by the caller,
        not a series this class can walk backwards through. A note asking for
        `rs_rating[20]` gets None (and therefore INSUFFICIENT_DATA) rather
        than today's value quietly standing in for a historical one.
        """
        if offset != 0:
            return None
        return self._rs_rating

    # ── window functions ──────────────────────────────────────────────────

    def _at(self, series: list[Optional[float]], offset: int) -> Optional[float]:
        if offset < 0 or offset >= len(series):
            return None
        return series[-1 - offset]

    def sma(self, period: int, offset: int = 0) -> Optional[float]:
        if period <= 0:
            return None
        if period not in self._sma_cache:
            self._sma_cache[period] = sma_series(self._closes, period)
        return self._at(self._sma_cache[period], offset)

    def ema(self, period: int, offset: int = 0) -> Optional[float]:
        if period <= 0:
            return None
        if period not in self._ema_cache:
            self._ema_cache[period] = ema_series(self._closes, period)
        return self._at(self._ema_cache[period], offset)

    def volume_sma(self, period: int, offset: int = 0) -> Optional[float]:
        if period <= 0:
            return None
        if period not in self._vol_sma_cache:
            self._vol_sma_cache[period] = sma_series(self._volumes, period)
        return self._at(self._vol_sma_cache[period], offset)

    def high(self, period: int, offset: int = 0) -> Optional[float]:
        """Highest HIGH over `period` bars ending at `offset`.

        Deliberately the bar high, not the close: Minervini's "within 25% of
        the 52-week high" and Weinstein's stage boundaries are both drawn
        against the actual extreme the market printed.
        """
        return self._window_extreme(offset, period, want_max=True)

    def low(self, period: int, offset: int = 0) -> Optional[float]:
        """Lowest LOW over `period` bars ending at `offset`."""
        return self._window_extreme(offset, period, want_max=False)

    def _window_extreme(self, offset: int, period: int,
                        *, want_max: bool) -> Optional[float]:
        if period <= 0 or offset < 0:
            return None
        end = len(self._bars) - offset          # exclusive
        start = end - period
        # Refuse a partial window. A "52-week high" computed from 30 bars is
        # not a 52-week high, and reporting one would understate the level
        # every downstream comparison is made against.
        if start < 0 or end <= 0:
            return None
        window = self._bars[start:end]
        return max(b.high for b in window) if want_max else min(b.low for b in window)

    # ── introspection ─────────────────────────────────────────────────────

    @property
    def bar_count(self) -> int:
        return len(self._bars)

    def __repr__(self) -> str:
        return f"<MarketFacts {self.symbol} bars={len(self._bars)} rs={self._rs_rating}>"
