"""
QuantOS — Momentum + Base Quality Shortlist (discretionary swing-trading aid)
──────────────────────────────────────────────────────────────────────────────
NOT a signal, NOT a strategy, no execution path. Every attempt to *automate*
trading on a Darvas breakout has failed on turnover/cost grounds (S7-3's
"no demonstrated edge" verdict, candidate 18's live-spread stress test). The
S8-3/candidate-11 momentum family is the one ranking formula that survived
Fable's unanchored re-evaluation against VCP and Stage Analysis (memory:
quantos-fable-anchoring-vcp-stage-review) — but even that is still awaiting
its own out-of-sample verdict (quantos-momentum-turnover-walkforward-status).
So it's used here only to RANK names for a human to look at, never to size
or place an order.

Combines two independently-built, already-tested primitives:
  - core/rotation/ranker.py's 52-week-high-proximity score (close / rolling
    252-day high) — the best-evidenced relative-strength signal this project
    has found.
  - core/darvas/weekly_discovery.py's weekly box state machine — never shown
    to misidentify a genuine consolidation, only shown to have no edge when
    automated as an entry/exit trigger. Used here purely to label whether a
    name is currently basing tightly (worth a human's attention for a
    lower-risk entry) or already extended (worth watching for a pullback).
  - a daily EMA9/EMA21 trend gate (added 2026-07-29 after GLENMARK showed
    up labeled "building a base" while actively rolling over — the box
    state machine only detects sideways-ness, never direction, so a tight
    range mid-downtrend and a genuine bullish pause looked identical to it).
    A "tight" base only counts toward a bucket if the name is also in a
    short-term uptrend by this measure.

Output is a mechanical, reproducible label — not a recommendation. A human
still decides whether/when/how much to buy.
"""

import bisect
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.brokers.base import OHLCV
from core.darvas.weekly_discovery import DiscoveryResult, analyse_symbol
from core.rotation.ranker import LOOKBACK_DAYS, SymbolSeries, rolling_high_series, value_as_of

# Daily EMA9/EMA21 trend gate. Confirmed live 2026-07-29: GLENMARK had a
# "tight" weekly Darvas box (width in the narrowest tercile) while its
# daily EMA9 had already crossed under EMA21 four sessions earlier -- an
# active short-term downtrend the box detector's own logic can't see, since
# it only tracks whether price has stopped making new highs/lows, never
# which direction it's actually headed. A range that's merely "not making
# new highs or lows" is satisfied just as easily by a stock rolling over as
# by one genuinely pausing mid-uptrend, so "tight" alone isn't enough to
# call something a constructive base worth a human's attention. This is
# the same EMA9/EMA21 check a discretionary trader would eyeball on a daily
# chart, chosen over a slower filter (e.g. price vs. 50/200 SMA) precisely
# because it reacts fast enough to catch a fresh rollover like GLENMARK's.
EMA_FAST = 9
EMA_SLOW = 21

# Top third of the scanned universe by 52-week-high proximity = "LEADER"
# tier. Middle/bottom thirds are still returned (nothing here hides a name),
# just ranked and labeled lower-priority for a momentum-focused review.
LEADER_TERCILE = 1 / 3

# "Tight base" is the narrowest third of box widths AMONG names that
# currently have a live weekly box, not a fixed percentage cutoff. A fixed
# 4% threshold (core/darvas/box.py's DarvasBox.is_tight, borrowed here in an
# earlier version) was calibrated for that module's short-window intraday
# boxes and never matched this weekly engine's own natural scale — a live
# run against Nifty Alpha 50 (2026-07-29) came back with confirmed-box
# widths of 8.6%-34.1% and zero names under 4%, so every name silently
# landed in WATCH/LEADER_EXTENDED regardless of how narrow its base
# actually was relative to its peers. Ranking widths against each other,
# same as the momentum tercile above, self-calibrates to whatever this
# engine's real distribution is instead of guessing a magic number.
TIGHT_BASE_TERCILE = 1 / 3

# Darvas statuses that represent an actual, currently-live box (as opposed
# to "BOX FORMING", which has no confirmed ceiling/floor yet to be tight).
_LIVE_BASE_STATUSES = ("FRESH BREAKOUT", "APPROACHING", "WATCHING")

BUCKET_PRIORITY = {
    "LEADER_TIGHT_BASE": 0,
    "LEADER_EXTENDED": 1,
    "BUILDING_BASE": 2,
    "WATCH": 3,
}


@dataclass
class ShortlistEntry:
    symbol:         str
    close:          float
    momentum_pct:   float              # close / rolling_52w_high * 100
    momentum_rank:  int                # 1 = closest to its 52-week high
    momentum_tier:  str                # LEADER | MIDPACK | LAGGARD
    bucket:         str                # LEADER_TIGHT_BASE | LEADER_EXTENDED | BUILDING_BASE | WATCH
    base_status:    str                # weekly_discovery status, or "NO BASE" if analyse_symbol returned None
    trend_up:       bool               # daily EMA9 > EMA21 -- see EMA_FAST/EMA_SLOW's comment
    box_width_pct:  Optional[float] = None
    dist_to_ceil:   Optional[float] = None
    rr_ratio:       Optional[float] = None
    vol_ratio:      float = 0.0


def _ema_series(closes: list[float], period: int) -> list[Optional[float]]:
    """Standard EMA, SMA-seeded: None for the first `period`-1 bars (not
    warmed up), then the seed SMA, then the usual recursive smoothing."""
    if len(closes) < period:
        return [None] * len(closes)
    k = 2 / (period + 1)
    result: list[Optional[float]] = [None] * (period - 1)
    prev = sum(closes[:period]) / period
    result.append(prev)
    for c in closes[period:]:
        prev = c * k + prev * (1 - k)
        result.append(prev)
    return result


def _is_uptrend(daily: list[OHLCV], as_of_date: datetime,
                 fast: int = EMA_FAST, slow: int = EMA_SLOW) -> bool:
    """EMA(fast) > EMA(slow) on daily closes, evaluated at the most recent
    bar at or before as_of_date. False (not just "unknown") when there
    isn't enough history to warm up either EMA -- a base can't be called
    constructive on data we don't have."""
    dates = [c.timestamp for c in daily]
    idx = bisect.bisect_right(dates, as_of_date) - 1
    if idx < 0:
        return False
    closes = [c.close for c in daily[:idx + 1]]
    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)
    if ema_fast[-1] is None or ema_slow[-1] is None:
        return False
    return ema_fast[-1] > ema_slow[-1]


def _momentum_tier(rank: int, total: int) -> str:
    tercile_size = max(1, round(total * LEADER_TERCILE))
    if rank <= tercile_size:
        return "LEADER"
    if rank <= total - tercile_size:
        return "MIDPACK"
    return "LAGGARD"


def _tight_base_symbols(base_by_symbol: dict[str, Optional[DiscoveryResult]]) -> set[str]:
    """Symbols in the narrowest TIGHT_BASE_TERCILE of box width, among only
    those with a currently-live base (a symbol with no base, or one still
    BOX FORMING, is never "tight" regardless of any width value)."""
    live = sorted(
        (base.box_width_pct, symbol)
        for symbol, base in base_by_symbol.items()
        if base is not None
        and base.status in _LIVE_BASE_STATUSES
        and base.box_width_pct is not None
    )
    if not live:
        return set()
    tercile_size = max(1, round(len(live) * TIGHT_BASE_TERCILE))
    return {symbol for _, symbol in live[:tercile_size]}


def _bucket(momentum_tier: str, has_tight_base: bool) -> str:
    if momentum_tier == "LEADER":
        return "LEADER_TIGHT_BASE" if has_tight_base else "LEADER_EXTENDED"
    return "BUILDING_BASE" if has_tight_base else "WATCH"


def build_shortlist(
    daily_by_symbol: dict[str, list[OHLCV]],
    as_of_date: datetime,
    momentum_window: int = LOOKBACK_DAYS,
    ema_fast: int = EMA_FAST,
    ema_slow: int = EMA_SLOW,
) -> list[ShortlistEntry]:
    """Pure, no-I/O: given each symbol's daily candles, rank by 52-week-high
    proximity and overlay each symbol's current Darvas base state.

    Symbols without enough warmed-up history for the momentum score (fewer
    than `momentum_window` daily bars) are silently excluded from ranking —
    same rule core/rotation/ranker.py's rank_universe uses. `momentum_window`
    defaults to the real 252-day lookback; tests pass a smaller value to
    warm up on compact fixtures, same pattern as
    tests/unit/test_rotation_ranker.py's own helper. `ema_fast`/`ema_slow`
    default to the real EMA9/EMA21 trend gate; tests pass smaller values for
    the same reason.

    A symbol only counts toward the "tight base" tercile if it's ALSO in an
    uptrend (ema_fast > ema_slow) — a name that's merely range-bound but
    rolling over (see EMA_FAST/EMA_SLOW's module comment) never qualifies
    as a base worth a human's attention, regardless of how narrow its box
    is. It still falls through to LEADER_EXTENDED or WATCH via _bucket()'s
    existing "not tight" path — base_status/box_width_pct etc. stay as
    whatever Darvas actually detected; only bucket eligibility changes.
    """
    momentum_scores: list[tuple[str, float, float]] = []
    base_by_symbol: dict[str, Optional[DiscoveryResult]] = {}
    uptrend_by_symbol: dict[str, bool] = {}

    for symbol, daily in daily_by_symbol.items():
        series = SymbolSeries(
            dates=[c.timestamp for c in daily],
            closes=[c.close for c in daily],
            highs=rolling_high_series(daily, window=momentum_window),
        )
        v = value_as_of(series, as_of_date)
        if v is None:
            continue
        close, high = v
        if high > 0:
            momentum_scores.append((symbol, close, close / high * 100))
            base_by_symbol[symbol] = analyse_symbol(symbol, daily)
            uptrend_by_symbol[symbol] = _is_uptrend(daily, as_of_date, ema_fast, ema_slow)

    momentum_scores.sort(key=lambda x: -x[2])
    total = len(momentum_scores)
    uptrending_bases = {
        symbol: base for symbol, base in base_by_symbol.items()
        if uptrend_by_symbol[symbol]
    }
    tight_symbols = _tight_base_symbols(uptrending_bases)

    entries = []
    for rank, (symbol, close, pct) in enumerate(momentum_scores, start=1):
        tier = _momentum_tier(rank, total)
        base = base_by_symbol[symbol]
        tight = symbol in tight_symbols
        bucket = _bucket(tier, tight)
        entries.append(ShortlistEntry(
            symbol=symbol, close=round(close, 2),
            momentum_pct=round(pct, 2), momentum_rank=rank, momentum_tier=tier,
            bucket=bucket,
            base_status=base.status if base else "NO BASE",
            trend_up=uptrend_by_symbol[symbol],
            box_width_pct=base.box_width_pct if base else None,
            dist_to_ceil=base.dist_to_ceil if base else None,
            rr_ratio=base.rr_ratio if base else None,
            vol_ratio=base.vol_ratio if base else 0.0,
        ))

    entries.sort(key=lambda e: (BUCKET_PRIORITY[e.bucket], -e.momentum_pct))
    return entries
