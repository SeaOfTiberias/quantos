"""
QuantOS — ML Multi-Factor Stock Ranking: Feature Extraction (candidate 16)
────────────────────────────────────────────────────────────────────────────
Per docs/ML_FACTOR_COMBINATION_METHODOLOGY.md's "Features" section. Every
function here is point-in-time-safe: given an `as_of` date, it uses only
data at or before that date. Two factors (momentum, dual-momentum) reuse
already-point-in-time-safe machinery unchanged; two (mean-reversion,
reconstitution recency) wrap existing building blocks with a bisectable
`*_as_of(..., as_of)` interface, since neither module exposed one.

RECONSTITUTION_DATA_FLOOR / sector-fallback are exposed as their own
explicit boolean feature columns rather than silently imputed — the
project's established principle (see mean-reversion gutcheck's own
docstring) for any factor with a real, disclosed data-quality gap.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from core.brokers.base import OHLCV
from core.meanreversion.gutcheck import EMA_FAST, EMA_SLOW, rsi14, walk_forward_emas
from core.rotation.dual_momentum import SymbolIndicators, _index_at_or_before
from core.rotation.nifty500_reconstitution import ReconstitutionEvent
from core.rotation.ranker import SymbolSeries, value_as_of

# Real reconstitution event coverage starts 2023-09-29 (confirmed live
# 2026-07-27 against core/rotation/nifty500_reconstitution.py's real EVENTS
# — 11 events, earliest that date). Any as_of before this has no reliable
# "days since event" answer, exposed via reconstitution_data_known rather
# than silently defaulting to "no event nearby."
RECONSTITUTION_DATA_FLOOR = datetime(2023, 9, 29, tzinfo=timezone.utc)
DAYS_SINCE_EVENT_SENTINEL = 3650.0   # ~10yr cap for "never observed an event" / unknown


# ─── Feature 1: 52-week RS momentum ─────────────────────────────────────────

def momentum_feature(series: SymbolSeries, as_of: datetime) -> Optional[float]:
    """Nearness to 52-week high (close / rolling_52w_high), the exact score
    core/rotation/ranker.py's rank_universe sorts on — None if not warmed
    up yet as of this date."""
    v = value_as_of(series, as_of)
    if v is None:
        return None
    close, high = v
    if high <= 0:
        return None
    return close / high


# ─── Feature 2: dual-momentum composite ─────────────────────────────────────

@dataclass(frozen=True)
class DualMomentumFeature:
    score: Optional[float]       # 0.5*ret90d + 0.5*ret180d, None if not warmed up
    trend_up: Optional[bool]     # EMA50 > EMA200, None if not warmed up


def dual_momentum_feature(ind: SymbolIndicators, as_of: datetime) -> DualMomentumFeature:
    idx = _index_at_or_before(ind.dates, as_of)
    if idx is None:
        return DualMomentumFeature(score=None, trend_up=None)
    e50, e200 = ind.ema50[idx], ind.ema200[idx]
    trend_up = None if (e50 is None or e200 is None) else e50 > e200
    return DualMomentumFeature(score=ind.score[idx], trend_up=trend_up)


# ─── Feature 3: mean-reversion (own RSI/EMA-band + sector trend) ───────────

@dataclass
class MeanReversionIndicators:
    dates:          list[datetime]
    own_closes:     list[float]
    own_rsi:        list[Optional[float]]
    own_ema_fast:   list[Optional[float]]
    own_ema_slow:   list[Optional[float]]
    sector_by_date: dict          # date -> index into sector arrays
    sector_ema_fast: list[Optional[float]]
    sector_ema_slow: list[Optional[float]]
    sector_mapped:  bool          # False if this symbol fell back to NIFTY 50 (see gutcheck.py)


def build_mean_reversion_indicators(
    own_candles: list[OHLCV], sector_candles: list[OHLCV], sector_mapped: bool,
) -> MeanReversionIndicators:
    own_closes = [c.close for c in own_candles]
    own_ema_fast, own_ema_slow = walk_forward_emas(own_closes, EMA_FAST, EMA_SLOW)
    own_rsi = rsi14(own_closes)
    sector_closes = [c.close for c in sector_candles]
    sec_ema_fast, sec_ema_slow = walk_forward_emas(sector_closes, EMA_FAST, EMA_SLOW)
    sector_by_date = {c.timestamp.date(): i for i, c in enumerate(sector_candles)}
    return MeanReversionIndicators(
        dates=[c.timestamp for c in own_candles], own_closes=own_closes, own_rsi=own_rsi,
        own_ema_fast=own_ema_fast, own_ema_slow=own_ema_slow, sector_by_date=sector_by_date,
        sector_ema_fast=sec_ema_fast, sector_ema_slow=sec_ema_slow, sector_mapped=sector_mapped,
    )


@dataclass(frozen=True)
class MeanReversionFeature:
    rsi:              Optional[float]
    band_position:    Optional[float]   # (close - ema_slow) / (ema_fast - ema_slow); ~0=at slow EMA, ~1=at fast EMA
    sector_trend_up:  Optional[bool]
    sector_mapped:    bool


def mean_reversion_feature(ind: MeanReversionIndicators, as_of: datetime) -> MeanReversionFeature:
    idx = bisect.bisect_right(ind.dates, as_of) - 1
    if idx < 0:
        return MeanReversionFeature(None, None, None, ind.sector_mapped)

    rsi = ind.own_rsi[idx]
    e_fast, e_slow = ind.own_ema_fast[idx], ind.own_ema_slow[idx]
    band_position = None
    if e_fast is not None and e_slow is not None and e_fast != e_slow:
        band_position = (ind.own_closes[idx] - e_slow) / (e_fast - e_slow)

    sec_i = ind.sector_by_date.get(as_of.date())
    if sec_i is None:
        # fall back to the most recent sector bar at/before as_of
        sec_dates = sorted(ind.sector_by_date)
        pos = bisect.bisect_right(sec_dates, as_of.date()) - 1
        sec_i = ind.sector_by_date[sec_dates[pos]] if pos >= 0 else None

    sector_trend_up = None
    if sec_i is not None:
        sf, ss = ind.sector_ema_fast[sec_i], ind.sector_ema_slow[sec_i]
        if sf is not None and ss is not None:
            sector_trend_up = sf > ss

    return MeanReversionFeature(rsi=rsi, band_position=band_position,
                                 sector_trend_up=sector_trend_up, sector_mapped=ind.sector_mapped)


# ─── Feature 4: days since last reconstitution event ────────────────────────

@dataclass(frozen=True)
class ReconstitutionFeature:
    days_since_added:   float   # DAYS_SINCE_EVENT_SENTINEL if never added within coverage (long-standing constituent) or unknown
    recently_added:     bool    # True if added within coverage and closer than the sentinel
    data_known:         bool    # False if as_of predates RECONSTITUTION_DATA_FLOOR


def reconstitution_feature(
    symbol: str, as_of: datetime, events: list[ReconstitutionEvent],
) -> ReconstitutionFeature:
    if as_of < RECONSTITUTION_DATA_FLOOR:
        return ReconstitutionFeature(days_since_added=DAYS_SINCE_EVENT_SENTINEL,
                                      recently_added=False, data_known=False)

    last_added: Optional[datetime] = None
    for event in events:
        if event.effective_date <= as_of and symbol in event.added:
            if last_added is None or event.effective_date > last_added:
                last_added = event.effective_date

    if last_added is None:
        return ReconstitutionFeature(days_since_added=DAYS_SINCE_EVENT_SENTINEL,
                                      recently_added=False, data_known=True)

    days = (as_of - last_added).days
    return ReconstitutionFeature(days_since_added=float(days),
                                  recently_added=days < DAYS_SINCE_EVENT_SENTINEL, data_known=True)
