"""
ML Multi-Factor Stock Ranking — Dataset Assembly Unit Tests

Covers core/mlfactors/dataset.py: point-in-time label construction (top
20% of forward returns among that week's eligible universe), and that
warmup/eligibility gating actually excludes symbols correctly.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brokers.base import OHLCV  # noqa: E402
from core.mlfactors.dataset import build_dataset, build_symbol_precomputed  # noqa: E402
from core.rotation.nifty500_reconstitution import UniverseSnapshot  # noqa: E402

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
N_DAYS = 420   # enough for 252d momentum warmup + 200d EMA trend warmup


def daily(prices: list) -> list:
    return [
        OHLCV(timestamp=START + timedelta(days=i), open=p, high=p * 1.01, low=p * 0.99,
              close=p, volume=1000)
        for i, p in enumerate(prices)
    ]


def _mildly_trending(base: float, daily_pct: float) -> list:
    """Compounding (not additive) drift -- stays strictly positive and
    never perfectly flat, unlike an additive drift which can go negative
    (a large negative drift) or produce an exactly-flat EMA20==EMA50 edge
    case (a zero drift) that real market data never actually hits."""
    prices = [base]
    for _ in range(N_DAYS - 1):
        prices.append(prices[-1] * (1 + daily_pct))
    return prices


def _weekly_dates(n_weeks: int, start_day: int) -> list:
    return [START + timedelta(days=start_day + 7 * i) for i in range(n_weeks)]


def _full_universe_snapshot(symbols: set) -> list:
    return [UniverseSnapshot(symbols=frozenset(symbols), valid_from=START - timedelta(days=1), valid_until=None)]


def _build_universe(symbols_and_drifts: dict) -> dict:
    sector = daily(_mildly_trending(100.0, 0.001))
    return {
        sym: build_symbol_precomputed(daily(_mildly_trending(100.0, drift)), sector, sector_mapped=True)
        for sym, drift in symbols_and_drifts.items()
    }


def test_last_rebalance_date_produces_no_rows():
    precomputed = _build_universe({"A": 0.006, "B": 0.003, "C": 0.001, "D": -0.001, "E": -0.003})
    rebal_dates = _weekly_dates(2, start_day=400)   # only 2 dates -> 1 gap
    snapshots = _full_universe_snapshot(set(precomputed.keys()))
    rows = build_dataset(precomputed, rebal_dates, snapshots, reconstitution_events=[])
    dates_used = {r.date for r in rows}
    assert rebal_dates[-1] not in dates_used


def test_top_quintile_label_assigned_to_best_forward_performer():
    # 6 symbols, sharply different daily drifts -> unambiguous forward-return ranking
    precomputed = _build_universe({
        "BEST": 0.010, "GOOD": 0.004, "MID1": 0.001, "MID2": 0.0002, "BAD1": -0.004, "BAD2": -0.008,
    })
    rebal_dates = _weekly_dates(2, start_day=400)
    snapshots = _full_universe_snapshot(set(precomputed.keys()))

    rows = build_dataset(precomputed, rebal_dates, snapshots, reconstitution_events=[])

    by_symbol = {r.symbol: r for r in rows}
    assert by_symbol["BEST"].label == 1
    # top 20% of 6 symbols -> top 1 (int(6*0.2)-1 index 0) is the only guaranteed-1 label
    assert by_symbol["BAD2"].label == 0
    assert by_symbol["BAD1"].label == 0


def test_ineligible_symbol_excluded_from_dataset():
    precomputed = _build_universe({"IN": 0.006, "OUT": 0.006, "C": 0.003, "D": 0.0005,
                                    "E": -0.003, "F": -0.001})
    rebal_dates = _weekly_dates(2, start_day=400)
    snapshots = _full_universe_snapshot({"IN", "C", "D", "E", "F"})   # OUT is not a constituent, 5 eligible

    rows = build_dataset(precomputed, rebal_dates, snapshots, reconstitution_events=[])

    assert "OUT" not in {r.symbol for r in rows}
    assert "IN" in {r.symbol for r in rows}


def test_symbol_not_warmed_up_excluded():
    precomputed = _build_universe({"A": 0.006, "B": 0.003, "C": 0.001, "D": -0.001, "E": -0.003})
    # a too-short series for YOUNG -- can't warm up the 252d momentum window
    sector = daily(_mildly_trending(100.0, 0.003))
    precomputed["YOUNG"] = build_symbol_precomputed(daily([100.0] * 50), sector, sector_mapped=True)
    rebal_dates = _weekly_dates(2, start_day=400)
    snapshots = _full_universe_snapshot(set(precomputed.keys()))

    rows = build_dataset(precomputed, rebal_dates, snapshots, reconstitution_events=[])

    assert "YOUNG" not in {r.symbol for r in rows}


def test_too_few_eligible_symbols_skips_the_date():
    precomputed = _build_universe({"A": 0.006, "B": 0.003})   # only 2, below the 5-symbol floor
    rebal_dates = _weekly_dates(2, start_day=400)
    snapshots = _full_universe_snapshot(set(precomputed.keys()))

    rows = build_dataset(precomputed, rebal_dates, snapshots, reconstitution_events=[])

    assert rows == []
