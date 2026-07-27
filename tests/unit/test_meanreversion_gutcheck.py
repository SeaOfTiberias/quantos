"""
Mean-Reversion (Nifty Alpha 50) Gut-Check — Unit Tests

Covers the pure (I/O-free) indicator/signal/forward-return logic in
core/meanreversion/gutcheck.py.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brokers.base import OHLCV  # noqa: E402
from core.meanreversion.gutcheck import (  # noqa: E402
    EMA_FAST,
    EMA_SLOW,
    ObservedDay,
    RSI_OVERSOLD,
    RSI_PERIOD,
    compute_hourly_signals,
    compute_signals,
    forward_returns,
    hourly_forward_returns,
    hourly_rsi_crossings,
    rsi14,
    summarize,
    walk_forward_emas,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────

def make_candle(day_offset: int, close: float, open_: float = None,
                 base=datetime(2024, 1, 1, tzinfo=timezone.utc)) -> OHLCV:
    ts = base + timedelta(days=day_offset)
    o = open_ if open_ is not None else close
    return OHLCV(timestamp=ts, open=o, high=max(o, close), low=min(o, close), close=close, volume=1000)


def make_series(closes: list[float], base=datetime(2024, 1, 1, tzinfo=timezone.utc)) -> list[OHLCV]:
    return [make_candle(i, c, base=base) for i, c in enumerate(closes)]


def make_hourly_series(closes: list[float], base: datetime) -> list[OHLCV]:
    return [
        OHLCV(timestamp=base + timedelta(hours=i), open=c, high=c, low=c, close=c, volume=1000)
        for i, c in enumerate(closes)
    ]


# ─── rsi14 ────────────────────────────────────────────────────────────────

def test_rsi14_none_before_period():
    closes = [100.0 + i for i in range(RSI_PERIOD)]  # exactly period closes, period+1 needed
    result = rsi14(closes)
    assert all(v is None for v in result)


def test_rsi14_strictly_rising_series_approaches_100():
    closes = [100.0 + i for i in range(40)]  # monotonic up, no losses at all
    result = rsi14(closes)
    assert result[-1] == pytest.approx(100.0)


def test_rsi14_strictly_falling_series_approaches_0():
    closes = [140.0 - i for i in range(40)]  # monotonic down, no gains at all
    result = rsi14(closes)
    assert result[-1] == pytest.approx(0.0)


def test_rsi14_flat_series_is_neutral_50():
    closes = [100.0] * 30
    result = rsi14(closes)
    assert result[RSI_PERIOD] == pytest.approx(50.0)


# ─── walk_forward_emas ────────────────────────────────────────────────────

def test_walk_forward_emas_none_before_warmup():
    closes = [100.0 + i for i in range(EMA_SLOW - 1)]  # one short of EMA_SLOW
    fast, slow = walk_forward_emas(closes)
    assert fast[EMA_FAST - 2] is None
    assert fast[EMA_FAST - 1] is not None  # exactly EMA_FAST closes available
    assert all(v is None for v in slow)  # never reaches EMA_SLOW closes


def test_walk_forward_emas_no_lookahead():
    """Appending future closes must not change any earlier day's EMA."""
    closes = [100.0 + (i % 5) * 2 for i in range(80)]
    fast_short, slow_short = walk_forward_emas(closes[:60])
    fast_long, slow_long = walk_forward_emas(closes)
    assert fast_long[:60] == fast_short
    assert slow_long[:60] == slow_short


# ─── compute_signals ───────────────────────────────────────────────────────

def _uptrend_sector_flat_pullback_oversold_own():
    """Builds an own-symbol series and a sector series engineered so every
    condition (sector trend up, own price in value zone, own RSI<35) is
    satisfiable somewhere in the tail, for isolating each condition."""
    # Sector: steadily rising -> EMA20 > EMA50 once warmed up.
    sector = make_series([100.0 + i * 0.5 for i in range(80)])
    # Own symbol: rises then pulls back hard right at the end so RSI drops
    # and the close sits between its own (still-elevated) EMA20/EMA50.
    own_closes = [100.0 + i for i in range(60)] + [160.0 - i * 3 for i in range(1, 11)]
    own = make_series(own_closes)
    return own, sector


def test_compute_signals_false_before_warmup():
    own, sector = _uptrend_sector_flat_pullback_oversold_own()
    signals = compute_signals(own, sector)
    assert len(signals) == len(own)
    assert not any(signals[:EMA_SLOW])  # can't have a real signal before EMA_SLOW warmup


def test_compute_signals_requires_matching_sector_date():
    own, _ = _uptrend_sector_flat_pullback_oversold_own()
    # Sector series with a completely disjoint calendar -> no date ever matches.
    sector_disjoint = make_series(
        [100.0 + i * 0.5 for i in range(80)],
        base=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    signals = compute_signals(own, sector_disjoint)
    assert not any(signals)


def test_compute_signals_false_when_sector_trend_down():
    own, _ = _uptrend_sector_flat_pullback_oversold_own()
    # Sector falling -> EMA20 < EMA50 -> trend_ok always False.
    sector_down = make_series([200.0 - i * 0.5 for i in range(80)])
    signals = compute_signals(own, sector_down)
    assert not any(signals)


def test_compute_signals_fires_true_when_all_three_conditions_hold():
    """Positive-path check: the engineered uptrend-sector / pullback fixture
    must actually produce a real signal somewhere, confirmed at index 66
    (own RSI14=33.75<35, own close=139.0 sits between EMA20=148.14/
    EMA50=137.68, sector EMA20>EMA50 throughout) — not just correctly
    silent in every negative-path test above."""
    own, sector = _uptrend_sector_flat_pullback_oversold_own()
    signals = compute_signals(own, sector)
    assert any(signals)
    assert signals[66] is True


# ─── hourly_rsi_crossings ────────────────────────────────────────────────────

def test_hourly_rsi_crossings_detects_fresh_cross_only():
    """A dip that pushes RSI below 35 and STAYS there for several bars
    should register only the first crossing index, not every subsequent
    below-35 bar — a transition event, not a persistent state."""
    closes = [100.0 + i for i in range(20)] + [119.0 - i * 3.0 for i in range(1, 10)]
    crossings = hourly_rsi_crossings(closes)
    rsi = rsi14(closes)
    below = [i for i in range(len(rsi)) if rsi[i] is not None and rsi[i] < RSI_OVERSOLD]
    assert len(below) > 1  # RSI stays under 35 for multiple bars in this fixture
    assert len(crossings) == 1
    assert crossings[0] == below[0]  # the crossing is the FIRST below-35 bar


def test_hourly_rsi_crossings_empty_when_never_oversold():
    closes = [100.0 + i for i in range(30)]  # monotonic up, RSI never drops
    assert hourly_rsi_crossings(closes) == []


# ─── compute_hourly_signals (mixed daily/hourly, no-lookahead) ─────────────

def _daily_and_hourly_fixture():
    """Sector: steady uptrend. Own daily: rises then pulls back, landing
    in its own EMA20/50 value zone by day 70 (index 70; own_ema20=151.85,
    own_ema50=141.3, close=149.0 -- confirmed directly). Own hourly: a
    real intraday RSI-oversold crossing at hour 22 on day 71 (2026-07-24
    verified: RSI drops from ~100 to ~16 over the tail, crossing below 35
    at index 22, close=147.1), which should key off day 70's (not day
    71's) daily EMAs."""
    sector_daily = make_series([100.0 + i * 0.5 for i in range(80)])
    own_daily_closes = [100.0 + i for i in range(60)] + [160.0 - i * 1.0 for i in range(1, 21)]
    own_daily = make_series(own_daily_closes)
    day71_base = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=71)
    hourly_closes = [148.0 + i * 0.2 for i in range(20)] + [151.6 - i * 1.5 for i in range(1, 8)]
    own_hourly = make_hourly_series(hourly_closes, day71_base)
    return own_daily, sector_daily, own_hourly


def test_compute_hourly_signals_fires_on_real_crossing_with_prior_day_filters():
    own_daily, sector_daily, own_hourly = _daily_and_hourly_fixture()
    signals = compute_hourly_signals(own_daily, sector_daily, own_hourly)
    assert len(signals) == 1
    assert signals[0].hourly_idx == 22
    assert signals[0].entry_price == pytest.approx(147.1)


def test_compute_hourly_signals_ignores_todays_own_daily_bar():
    """No-lookahead: mutating TODAY's (the crossing's own calendar day)
    daily bar must not change the outcome at all — an intraday decision
    can only see the last COMPLETED daily bar."""
    own_daily, sector_daily, own_hourly = _daily_and_hourly_fixture()
    baseline = compute_hourly_signals(own_daily, sector_daily, own_hourly)

    mutated = list(own_daily)
    mutated[71] = make_candle(71, close=9999.0)  # day 71 = the crossing's own day
    result = compute_hourly_signals(mutated, sector_daily, own_hourly)
    assert result == baseline


def test_compute_hourly_signals_uses_yesterdays_own_daily_bar():
    """Mutating YESTERDAY's (the last completed) daily bar DOES change the
    outcome — confirms the join actually reads that bar, not skipping it
    entirely by accident."""
    own_daily, sector_daily, own_hourly = _daily_and_hourly_fixture()
    baseline = compute_hourly_signals(own_daily, sector_daily, own_hourly)
    assert baseline  # sanity: the unmutated fixture does fire

    mutated = list(own_daily)
    mutated[70] = make_candle(70, close=9999.0)  # day 70 = the last completed bar
    result = compute_hourly_signals(mutated, sector_daily, own_hourly)
    assert result == []


def test_compute_hourly_signals_false_when_sector_trend_down():
    own_daily, _, own_hourly = _daily_and_hourly_fixture()
    sector_down = make_series([200.0 - i * 0.5 for i in range(80)])
    signals = compute_hourly_signals(own_daily, sector_down, own_hourly)
    assert signals == []


# ─── hourly_forward_returns ─────────────────────────────────────────────────

def test_hourly_forward_returns_entry_day_counts_as_day_one():
    """Entry day counts as day 1 of the h-day hold -- same day-counting
    convention as forward_returns() (there, entry_i is day 1, exit is
    entry_i + h - 1) -- so a signal and a baseline "5-day" return cover
    the same length of exposure. Confirmed against forward_returns'
    own test (test_forward_returns_uses_next_day_open_as_entry: entry_i=11,
    horizon 5 -> exit_i=15, a +4 step) -- here entry day=20, horizon 5 ->
    exit day=24, the same +4 step from the entry day."""
    daily_closes = [100.0 + i for i in range(40)]
    own_daily = make_series(daily_closes)
    entry_date = own_daily[20].timestamp  # entry happens intraday on day 20
    result = hourly_forward_returns(own_daily, entry_date, entry_price=105.0, horizons=(5,))
    expected_exit_close = own_daily[24].close  # day 20 + 5 - 1
    expected = (expected_exit_close - 105.0) / 105.0 * 100
    assert result[5] == pytest.approx(expected)


def test_hourly_forward_returns_none_past_end():
    own_daily = make_series([100.0 + i for i in range(10)])
    entry_date = own_daily[8].timestamp
    result = hourly_forward_returns(own_daily, entry_date, entry_price=100.0, horizons=(5,))
    assert result[5] is None


def test_hourly_forward_returns_none_when_entry_date_not_in_daily_series():
    own_daily = make_series([100.0 + i for i in range(10)])
    missing_date = datetime(2030, 1, 1, tzinfo=timezone.utc)
    result = hourly_forward_returns(own_daily, missing_date, entry_price=100.0, horizons=(5,))
    assert result[5] is None


# ─── forward_returns ────────────────────────────────────────────────────────

def test_forward_returns_uses_next_day_open_as_entry():
    closes = [100.0 + i for i in range(40)]
    candles = make_series(closes)
    # Give the entry day (signal_idx + 1) a distinct open so entry pricing
    # is unambiguously verifiable.
    candles[11] = make_candle(11, close=candles[11].close, open_=111.0)
    result = forward_returns(candles, signal_idx=10, horizons=(5,))
    expected_exit_close = candles[10 + 1 + 5 - 1].close  # entry_i=11, exit_i=15
    expected = (expected_exit_close - 111.0) / 111.0 * 100
    assert result[5] == pytest.approx(expected)


def test_forward_returns_none_when_window_runs_past_end():
    candles = make_series([100.0 + i for i in range(10)])
    result = forward_returns(candles, signal_idx=8, horizons=(5, 10))
    assert result[5] is None
    assert result[10] is None


def test_forward_returns_none_when_no_next_day_at_all():
    candles = make_series([100.0 + i for i in range(10)])
    result = forward_returns(candles, signal_idx=9, horizons=(5,))
    assert result[5] is None


# ─── summarize ───────────────────────────────────────────────────────────────

def _obs(symbol, offset, is_signal, fwd):
    return ObservedDay(
        symbol=symbol,
        date=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=offset),
        is_signal=is_signal,
        fwd_return=fwd,
    )


def test_summarize_reports_signal_vs_baseline_gap():
    obs = []
    for i in range(10):
        obs.append(_obs("X", i, True, {5: 2.0, 10: 3.0, 20: 4.0}))
    for i in range(10, 20):
        obs.append(_obs("X", i, False, {5: -1.0, 10: -1.0, 20: -1.0}))

    report = summarize(obs)
    assert "10 signal days" in report
    assert "10 baseline days" in report
    assert "+2.00" in report  # signal mean at horizon 5
    assert "-1.00" in report  # baseline mean at horizon 5
    assert "+3.00" in report  # gap at horizon 5 (2.0 - (-1.0))


def test_summarize_handles_empty_observations():
    report = summarize([])
    assert "0 total observed days" in report


def test_summarize_reports_signal_clustering():
    """3 signal days all fall on the SAME calendar date (different
    symbols) -- clustering section should report 1 distinct date, not 3,
    and flag the >1 stocks/date average."""
    obs = [
        _obs("A", 0, True, {5: 1.0, 10: 1.0, 20: 1.0}),
        _obs("B", 0, True, {5: 1.0, 10: 1.0, 20: 1.0}),
        _obs("C", 0, True, {5: 1.0, 10: 1.0, 20: 1.0}),
        _obs("D", 1, False, {5: -1.0, 10: -1.0, 20: -1.0}),
    ]
    report = summarize(obs)
    assert "3 signal-day observations fall on only 1 distinct calendar dates" in report
    assert "largest single-date cluster: 3 stocks" in report


def test_summarize_splits_by_sector_mapped():
    obs = []
    for i in range(5):
        o = _obs("MAPPED", i, True, {5: 10.0, 10: 10.0, 20: 10.0})
        o.sector_mapped = True
        obs.append(o)
    for i in range(5):
        o = _obs("MAPPED_B", i, False, {5: 0.0, 10: 0.0, 20: 0.0})
        o.sector_mapped = True
        obs.append(o)
    for i in range(5):
        o = _obs("FALLBACK", i, True, {5: -10.0, 10: -10.0, 20: -10.0})
        o.sector_mapped = False
        obs.append(o)
    for i in range(5):
        o = _obs("FALLBACK_B", i, False, {5: 0.0, 10: 0.0, 20: 0.0})
        o.sector_mapped = False
        obs.append(o)

    report = summarize(obs)
    assert "Sector-mapped stocks only" in report
    assert "NIFTY-50-fallback stocks only" in report
    # Sector-mapped group's signal mean (+10.00) should appear near that section.
    assert "+10.00" in report
    assert "-10.00" in report
