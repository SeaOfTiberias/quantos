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

Output is a mechanical, reproducible label — not a recommendation. A human
still decides whether/when/how much to buy.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.brokers.base import OHLCV
from core.darvas.weekly_discovery import DiscoveryResult, analyse_symbol
from core.rotation.ranker import LOOKBACK_DAYS, SymbolSeries, rolling_high_series, value_as_of

# Top third of the scanned universe by 52-week-high proximity = "LEADER"
# tier. Middle/bottom thirds are still returned (nothing here hides a name),
# just ranked and labeled lower-priority for a momentum-focused review.
LEADER_TERCILE = 1 / 3

# Mirrors core/darvas/box.py's DarvasBox.is_tight threshold — same
# definition of "tight base" used everywhere else in this codebase.
TIGHT_BASE_WIDTH_PCT = 4.0

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
    box_width_pct:  Optional[float] = None
    dist_to_ceil:   Optional[float] = None
    rr_ratio:       Optional[float] = None
    vol_ratio:      float = 0.0


def _momentum_tier(rank: int, total: int) -> str:
    tercile_size = max(1, round(total * LEADER_TERCILE))
    if rank <= tercile_size:
        return "LEADER"
    if rank <= total - tercile_size:
        return "MIDPACK"
    return "LAGGARD"


def _has_tight_base(base: Optional[DiscoveryResult]) -> bool:
    return bool(
        base is not None
        and base.status in _LIVE_BASE_STATUSES
        and base.box_width_pct is not None
        and base.box_width_pct < TIGHT_BASE_WIDTH_PCT
    )


def _bucket(momentum_tier: str, has_tight_base: bool) -> str:
    if momentum_tier == "LEADER":
        return "LEADER_TIGHT_BASE" if has_tight_base else "LEADER_EXTENDED"
    return "BUILDING_BASE" if has_tight_base else "WATCH"


def build_shortlist(
    daily_by_symbol: dict[str, list[OHLCV]],
    as_of_date: datetime,
    momentum_window: int = LOOKBACK_DAYS,
) -> list[ShortlistEntry]:
    """Pure, no-I/O: given each symbol's daily candles, rank by 52-week-high
    proximity and overlay each symbol's current Darvas base state.

    Symbols without enough warmed-up history for the momentum score (fewer
    than `momentum_window` daily bars) are silently excluded from ranking —
    same rule core/rotation/ranker.py's rank_universe uses. `momentum_window`
    defaults to the real 252-day lookback; tests pass a smaller value to
    warm up on compact fixtures, same pattern as
    tests/unit/test_rotation_ranker.py's own helper.
    """
    momentum_scores: list[tuple[str, float, float]] = []

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

    momentum_scores.sort(key=lambda x: -x[2])
    total = len(momentum_scores)

    entries = []
    for rank, (symbol, close, pct) in enumerate(momentum_scores, start=1):
        tier = _momentum_tier(rank, total)
        base = analyse_symbol(symbol, daily_by_symbol[symbol])
        tight = _has_tight_base(base)
        bucket = _bucket(tier, tight)
        entries.append(ShortlistEntry(
            symbol=symbol, close=round(close, 2),
            momentum_pct=round(pct, 2), momentum_rank=rank, momentum_tier=tier,
            bucket=bucket,
            base_status=base.status if base else "NO BASE",
            box_width_pct=base.box_width_pct if base else None,
            dist_to_ceil=base.dist_to_ceil if base else None,
            rr_ratio=base.rr_ratio if base else None,
            vol_ratio=base.vol_ratio if base else 0.0,
        ))

    entries.sort(key=lambda e: (BUCKET_PRIORITY[e.bucket], -e.momentum_pct))
    return entries
