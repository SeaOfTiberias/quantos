"""
ML Multi-Factor Stock Ranking — Feature Extraction Unit Tests

Covers core/mlfactors/features.py per
docs/ML_FACTOR_COMBINATION_METHODOLOGY.md's "Features" section: each
feature must be point-in-time-safe (uses only data at/before `as_of`) and
disclose data-quality gaps as explicit flags rather than silent imputation.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brokers.base import OHLCV  # noqa: E402
from core.mlfactors.features import (  # noqa: E402
    DAYS_SINCE_EVENT_SENTINEL,
    RECONSTITUTION_DATA_FLOOR,
    build_mean_reversion_indicators,
    dual_momentum_feature,
    mean_reversion_feature,
    momentum_feature,
    reconstitution_feature,
)
from core.rotation.dual_momentum import build_indicators
from core.rotation.nifty500_reconstitution import ReconstitutionEvent
from core.rotation.ranker import build_symbol_series

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def daily(n: int, prices: list) -> list:
    return [
        OHLCV(timestamp=START + timedelta(days=i), open=p, high=p * 1.01, low=p * 0.99,
              close=p, volume=1000)
        for i, p in enumerate(prices)
    ]


# ─── momentum_feature ────────────────────────────────────────────────────

def test_momentum_feature_none_before_warmup():
    candles = daily(100, [100.0] * 100)   # < 252-day lookback
    series = build_symbol_series(candles)
    assert momentum_feature(series, START + timedelta(days=99)) is None


def test_momentum_feature_close_to_high_ratio():
    prices = [100.0] * 251 + [90.0]   # warmed up, closes well off the 52w high
    candles = daily(252, prices)
    series = build_symbol_series(candles)
    result = momentum_feature(series, START + timedelta(days=251))
    assert result is not None
    # rolling 252-day high is 101 (100 * the daily() helper's 1.01 high multiplier),
    # close is 90 -> 90/101, not a round 0.9
    assert abs(result - (90.0 / 101.0)) < 1e-9


# ─── dual_momentum_feature ────────────────────────────────────────────────

def test_dual_momentum_feature_none_before_any_data():
    candles = daily(5, [100.0] * 5)
    ind = build_indicators(candles)
    result = dual_momentum_feature(ind, START - timedelta(days=1))
    assert result.score is None
    assert result.trend_up is None


def test_dual_momentum_feature_warmed_up():
    # a long, mildly-rising series so 90d/180d/EMA200 windows all warm up
    prices = [100.0 + 0.05 * i for i in range(400)]
    candles = daily(400, prices)
    ind = build_indicators(candles)
    result = dual_momentum_feature(ind, START + timedelta(days=399))
    assert result.score is not None
    assert result.trend_up is not None


# ─── mean_reversion_feature ───────────────────────────────────────────────

def test_mean_reversion_feature_flags_unmapped_sector():
    own = daily(60, [100.0] * 60)
    sector = daily(60, [100.0] * 60)
    ind = build_mean_reversion_indicators(own, sector, sector_mapped=False)
    result = mean_reversion_feature(ind, START + timedelta(days=59))
    assert result.sector_mapped is False


def test_mean_reversion_feature_none_before_data_exists():
    own = daily(10, [100.0] * 10)
    sector = daily(10, [100.0] * 10)
    ind = build_mean_reversion_indicators(own, sector, sector_mapped=True)
    result = mean_reversion_feature(ind, START - timedelta(days=1))
    assert result.rsi is None
    assert result.band_position is None


def test_mean_reversion_band_position_computed_once_warmed_up():
    prices = [100.0 + i * 0.3 for i in range(60)]   # trending up, EMA20 > EMA50 eventually
    own = daily(60, prices)
    sector = daily(60, prices)
    ind = build_mean_reversion_indicators(own, sector, sector_mapped=True)
    result = mean_reversion_feature(ind, START + timedelta(days=59))
    assert result.band_position is not None
    assert result.rsi is not None


# ─── reconstitution_feature ────────────────────────────────────────────────

def test_reconstitution_feature_data_known_false_before_floor():
    result = reconstitution_feature("RELIANCE", RECONSTITUTION_DATA_FLOOR - timedelta(days=1), events=[])
    assert result.data_known is False
    assert result.days_since_added == DAYS_SINCE_EVENT_SENTINEL


def test_reconstitution_feature_sentinel_when_never_added():
    events = [ReconstitutionEvent(effective_date=RECONSTITUTION_DATA_FLOOR,
                                   added=frozenset({"OTHERSYM"}), removed=frozenset(),
                                   source="test")]
    result = reconstitution_feature("RELIANCE", RECONSTITUTION_DATA_FLOOR + timedelta(days=10), events)
    assert result.data_known is True
    assert result.days_since_added == DAYS_SINCE_EVENT_SENTINEL
    assert result.recently_added is False


def test_reconstitution_feature_days_since_real_addition():
    added_date = RECONSTITUTION_DATA_FLOOR + timedelta(days=5)
    events = [ReconstitutionEvent(effective_date=added_date, added=frozenset({"NEWCO"}),
                                   removed=frozenset(), source="test")]
    as_of = added_date + timedelta(days=20)
    result = reconstitution_feature("NEWCO", as_of, events)
    assert result.data_known is True
    assert result.days_since_added == 20.0
    assert result.recently_added is True


def test_reconstitution_feature_ignores_future_events():
    future_add = RECONSTITUTION_DATA_FLOOR + timedelta(days=100)
    events = [ReconstitutionEvent(effective_date=future_add, added=frozenset({"NEWCO"}),
                                   removed=frozenset(), source="test")]
    as_of = RECONSTITUTION_DATA_FLOOR + timedelta(days=10)   # before the event
    result = reconstitution_feature("NEWCO", as_of, events)
    assert result.days_since_added == DAYS_SINCE_EVENT_SENTINEL   # not yet added as of this date
