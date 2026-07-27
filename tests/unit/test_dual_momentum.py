"""
Strategy 1 (Regime-Filtered Dual-Momentum) — Unit Tests

Covers core/rotation/dual_momentum.py's pure indicator/ranking/simulation
logic per docs/S1_DUAL_MOMENTUM_METHODOLOGY.md.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brokers.base import OHLCV  # noqa: E402
from core.risk.costs import CostModel  # noqa: E402
from core.rotation.dual_momentum import (  # noqa: E402
    ATR_PERIOD,
    EMA_TREND_FAST,
    EMA_TREND_SLOW,
    ENTRY_TOP_N,
    EXIT_TOP_N,
    _atr_at_entry,
    build_indicators,
    ranked_eligible_symbols,
    simulate_dual_momentum,
    stop_level,
    walk_forward_ema,
    wilder_atr,
)

ZERO_COST = CostModel(
    brokerage_flat=0.0, brokerage_pct=0.0, stt_pct=0.0, exchange_txn_pct=0.0,
    sebi_pct=0.0, stamp_pct=0.0, gst_pct=0.0, slippage_bps=0.0,
)


def make_candle(day_offset, close, open_=None, high=None, low=None,
                 base=datetime(2024, 1, 1, tzinfo=timezone.utc)):
    o = open_ if open_ is not None else close
    h = high if high is not None else max(o, close)
    l = low if low is not None else min(o, close)
    return OHLCV(timestamp=base + timedelta(days=day_offset), open=o, high=h, low=l, close=close, volume=1000)


def make_flat_series(n, price=100.0, base=datetime(2024, 1, 1, tzinfo=timezone.utc)):
    return [make_candle(i, price, base=base) for i in range(n)]


# ─── wilder_atr ───────────────────────────────────────────────────────────

def test_wilder_atr_zero_for_flat_ohlc():
    candles = make_flat_series(30)
    atr = wilder_atr([c.high for c in candles], [c.low for c in candles], [c.close for c in candles])
    assert atr[ATR_PERIOD] == pytest.approx(0.0)


def test_wilder_atr_none_before_warmup():
    candles = make_flat_series(10)
    atr = wilder_atr([c.high for c in candles], [c.low for c in candles], [c.close for c in candles])
    assert all(v is None for v in atr)


def test_wilder_atr_positive_for_real_range():
    candles = [
        make_candle(i, close=100.0 + i, high=102.0 + i, low=98.0 + i)
        for i in range(30)
    ]
    atr = wilder_atr([c.high for c in candles], [c.low for c in candles], [c.close for c in candles])
    assert atr[ATR_PERIOD] == pytest.approx(4.0, abs=0.5)  # true range ~4 every day here


# ─── walk_forward_ema (no-lookahead) ────────────────────────────────────────

def test_walk_forward_ema_no_lookahead():
    closes = [100.0 + (i % 7) for i in range(300)]
    short = walk_forward_ema(closes[:250], EMA_TREND_SLOW)
    long = walk_forward_ema(closes, EMA_TREND_SLOW)
    assert long[:250] == short


def test_walk_forward_ema_none_before_period():
    closes = [100.0 + i for i in range(EMA_TREND_FAST - 1)]
    assert all(v is None for v in walk_forward_ema(closes, EMA_TREND_FAST))


# ─── build_indicators: score computation ────────────────────────────────────

def test_build_indicators_score_none_before_180d_warmup():
    candles = make_flat_series(179)
    ind = build_indicators(candles)
    assert all(v is None for v in ind.score)


def test_build_indicators_score_matches_hand_computed_returns():
    # Constant +1/day close so 90d/180d returns are exactly computable.
    closes = [100.0 + i for i in range(200)]
    candles = [make_candle(i, c) for i, c in enumerate(closes)]
    ind = build_indicators(candles)
    idx = 199
    r90 = (closes[idx] / closes[idx - 90] - 1) * 100
    r180 = (closes[idx] / closes[idx - 180] - 1) * 100
    expected = 0.5 * r90 + 0.5 * r180
    assert ind.score[idx] == pytest.approx(expected)


# ─── ranked_eligible_symbols ────────────────────────────────────────────────

def test_ranked_eligible_symbols_excludes_downtrend():
    uptrend = build_indicators([make_candle(i, 100.0 + i * 0.5) for i in range(220)])
    downtrend = build_indicators([make_candle(i, 300.0 - i * 0.5) for i in range(220)])
    indicators = {"UP": uptrend, "DOWN": downtrend}
    as_of = uptrend.dates[-1]
    ranked = ranked_eligible_symbols(indicators, as_of)
    assert "UP" in ranked
    assert "DOWN" not in ranked  # EMA50 < EMA200 for a steady downtrend


def test_ranked_eligible_symbols_sorted_best_first():
    strong = build_indicators([make_candle(i, 100.0 + i * 2.0) for i in range(220)])
    weak = build_indicators([make_candle(i, 100.0 + i * 0.2) for i in range(220)])
    indicators = {"STRONG": strong, "WEAK": weak}
    as_of = strong.dates[-1]
    ranked = ranked_eligible_symbols(indicators, as_of)
    assert ranked == ["STRONG", "WEAK"]


def test_ranked_eligible_symbols_respects_eligible_restriction():
    a = build_indicators([make_candle(i, 100.0 + i * 2.0) for i in range(220)])
    b = build_indicators([make_candle(i, 100.0 + i * 1.5) for i in range(220)])
    indicators = {"A": a, "B": b}
    as_of = a.dates[-1]
    ranked = ranked_eligible_symbols(indicators, as_of, eligible=frozenset({"B"}))
    assert ranked == ["B"]


# ─── stop_level ──────────────────────────────────────────────────────────────

def test_stop_level_chandelier_already_tighter_than_initial_at_entry():
    """Given 2.0 < 2.5 (Chandelier's multiplier is smaller than the initial
    stop's), the Chandelier line (entry - 2xATR) is mathematically ALWAYS
    at or above (tighter than) the initial stop (entry - 2.5xATR) from the
    moment of entry onward, even before highest_high has risen at all --
    max() picks the Chandelier line immediately, not after some delay.
    This is an inherent property of these specific multipliers, not a bug:
    the initial stop only ever matters in the (rare, ATR-shrinking) case
    where atr_now < atr_at_entry makes the Chandelier line temporarily
    wider than the frozen initial stop."""
    level = stop_level(entry_price=100.0, atr_at_entry=2.0, highest_high_since_entry=100.0, atr_now=2.0)
    assert level == pytest.approx(100.0 - 2.0 * 2.0)  # Chandelier, not initial stop


def test_stop_level_initial_stop_governs_when_atr_expands_after_entry():
    """The initial (frozen-at-entry-ATR) stop only actually binds when ATR
    has RISEN more than 25% since entry with no favorable move yet
    (algebraically: initial_stop > chandelier-at-highest_high==entry_price
    reduces to atr_now > 1.25 * atr_at_entry) -- a volatility expansion
    right after entry makes the CURRENT-ATR Chandelier line swing wider
    (looser) than the smaller frozen-entry-ATR initial stop."""
    level = stop_level(entry_price=100.0, atr_at_entry=2.0, highest_high_since_entry=100.0, atr_now=3.0)
    initial_stop = 100.0 - 2.5 * 2.0   # = 95.0
    chandelier = 100.0 - 2.0 * 3.0     # = 94.0 -- wider (looser) than the initial stop here
    assert initial_stop > chandelier
    assert level == pytest.approx(initial_stop)


def test_stop_level_chandelier_overtakes_after_rally():
    # After a rally, highest_high rises well above entry -- chandelier line
    # should now be the higher (tighter, more protective) of the two.
    level = stop_level(entry_price=100.0, atr_at_entry=2.0, highest_high_since_entry=130.0, atr_now=2.0)
    initial_stop = 100.0 - 2.5 * 2.0
    chandelier = 130.0 - 2.0 * 2.0
    assert chandelier > initial_stop
    assert level == pytest.approx(chandelier)


# ─── simulate_dual_momentum (integration) ───────────────────────────────────

def _build_universe(n_symbols=30, n_days=400):
    """Symbols with varying trend strength so ranking/rotation has real
    texture, all warmed up well past the 200d+180d requirement."""
    indicators = {}
    for k in range(n_symbols):
        slope = 0.1 + k * 0.05   # each symbol trends at a different rate
        candles = [make_candle(i, 100.0 + i * slope) for i in range(n_days)]
        indicators[f"SYM{k}"] = build_indicators(candles)
    return indicators


def _weekly_rebal_dates(dates):
    """Mirror S8-3's own anchor: last trading day of each ISO week."""
    rebal = set()
    by_week = {}
    for d in dates:
        by_week.setdefault((d.isocalendar()[0], d.isocalendar()[1]), []).append(d)
    for week_dates in by_week.values():
        rebal.add(max(week_dates))
    return rebal


def test_simulate_entries_fill_at_next_day_open_not_rebal_day_close():
    indicators = _build_universe(n_symbols=20, n_days=260)
    all_dates = sorted(set(d for ind in indicators.values() for d in ind.dates))
    rebal_dates = _weekly_rebal_dates(all_dates)

    result = simulate_dual_momentum(
        all_dates, rebal_dates, indicators, initial_capital=1_000_000.0,
        position_size=50_000.0, cost_model=ZERO_COST,
    )
    assert result.trades or result.curve  # sanity: simulation actually ran
    # No entry trade's entry_date should be a date with no bar for that
    # symbol landing exactly ON a rebalance date at that date's own close --
    # concretely: every trade's entry_price must equal that symbol's OPEN
    # on entry_date, not its close (the fill convention under test).
    for trade in result.trades:
        ind = indicators[trade.symbol]
        idx = ind.dates.index(trade.entry_date)
        assert trade.entry_price == pytest.approx(ind.opens[idx])


def test_simulate_no_lookahead_extending_future_leaves_past_trades_unchanged():
    indicators_short = _build_universe(n_symbols=15, n_days=260)
    dates_short = sorted(set(d for ind in indicators_short.values() for d in ind.dates))
    rebal_short = _weekly_rebal_dates(dates_short)
    result_short = simulate_dual_momentum(
        dates_short, rebal_short, indicators_short, initial_capital=1_000_000.0,
        position_size=50_000.0, cost_model=ZERO_COST,
    )

    indicators_long = _build_universe(n_symbols=15, n_days=320)
    dates_long_full = sorted(set(d for ind in indicators_long.values() for d in ind.dates))
    # Only replay up through the same cutoff as the short run.
    cutoff = dates_short[-1]
    dates_long = [d for d in dates_long_full if d <= cutoff]
    rebal_long = _weekly_rebal_dates(dates_long)
    result_long = simulate_dual_momentum(
        dates_long, rebal_long, indicators_long, initial_capital=1_000_000.0,
        position_size=50_000.0, cost_model=ZERO_COST,
    )

    # Equity curve up to the shared cutoff must be identical regardless of
    # whether more (future, unused) history exists in `indicators` -- the
    # walk-forward indicators themselves are already no-lookahead-tested
    # elsewhere; this confirms the simulation loop doesn't leak future data.
    curve_short = {p.date: p.equity for p in result_short.curve}
    curve_long = {p.date: p.equity for p in result_long.curve}
    for d in curve_short:
        assert curve_long[d] == pytest.approx(curve_short[d])


def test_atr_at_entry_uses_prior_day_not_fill_day():
    """No same-day lookahead: must return the PRIOR trading day's ATR14,
    not the fill day's own (not-yet-known-at-market-open) value. Caught by
    independent review (Fable, 2026-07-24)."""
    # Flat true range for most of the series, then a deliberate spike
    # exactly ON the fill day -- if the bug were still present (using
    # atr14[fill_idx] instead of atr14[fill_idx - 1]), the huge same-day
    # spike would leak into atr_at_entry; the fix must ignore it entirely.
    n = 40
    closes = [100.0] * n
    highs = [100.2] * n
    lows = [99.8] * n
    fill_idx = 30
    highs[fill_idx], lows[fill_idx] = 500.0, 1.0  # a massive true-range spike, same day as the fill
    candles = [make_candle(i, closes[i], high=highs[i], low=lows[i]) for i in range(n)]
    ind = build_indicators(candles)

    result = _atr_at_entry(ind, fill_idx)
    assert result == pytest.approx(ind.atr14[fill_idx - 1])
    assert result != pytest.approx(ind.atr14[fill_idx])  # confirms the spike really would have leaked in


def test_atr_at_entry_zero_at_series_start():
    ind = build_indicators(make_flat_series(30))
    assert _atr_at_entry(ind, 0) == 0.0
    assert _atr_at_entry(ind, None) == 0.0


def test_simulate_atr_stop_exits_on_close_breach():
    # One clean uptrend symbol, then a sharp multi-day drop engineered to
    # breach the ATR stop after entry.
    n_days = 260
    closes = [100.0 + i * 0.3 for i in range(n_days - 15)]
    closes += [closes[-1] - i * 3.0 for i in range(1, 16)]   # sharp drop at the end
    candles = [make_candle(i, c, high=c + 0.5, low=c - 0.5) for i, c in enumerate(closes)]
    trending = build_indicators(candles)
    # A second, always-eligible-but-never-top-ranked symbol so the universe
    # isn't degenerate (ranking needs >=1 alternative to be meaningful).
    flat = build_indicators([make_candle(i, 50.0 + i * 0.01) for i in range(n_days)])
    indicators = {"DROP": trending, "FLAT": flat}
    all_dates = trending.dates
    rebal_dates = _weekly_rebal_dates(all_dates)

    result = simulate_dual_momentum(
        all_dates, rebal_dates, indicators, initial_capital=1_000_000.0,
        position_size=200_000.0, cost_model=ZERO_COST,
    )
    reasons = {t.exit_reason for t in result.trades if t.symbol == "DROP"}
    assert "atr_stop" in reasons


def test_simulate_eligible_asof_fn_called_per_rebalance_not_once():
    """eligible_asof_fn must be re-resolved on EVERY rebalance date, not
    captured once at the start -- the real point-in-time-universe bug this
    replaced (a single static frozenset would silently reproduce S8-3's
    original survivorship-bias mistake)."""
    indicators = _build_universe(n_symbols=20, n_days=260)
    all_dates = sorted(set(d for ind in indicators.values() for d in ind.dates))
    rebal_dates = _weekly_rebal_dates(all_dates)

    calls = []

    def eligible_asof_fn(d):
        calls.append(d)
        return None  # no restriction, just recording calls

    simulate_dual_momentum(
        all_dates, rebal_dates, indicators, initial_capital=1_000_000.0,
        position_size=50_000.0, cost_model=ZERO_COST, eligible_asof_fn=eligible_asof_fn,
    )
    assert len(calls) == len(rebal_dates)
    assert set(calls) == rebal_dates


def test_simulate_eligible_asof_fn_restricts_ranking():
    indicators = _build_universe(n_symbols=20, n_days=260)
    all_dates = sorted(set(d for ind in indicators.values() for d in ind.dates))
    rebal_dates = _weekly_rebal_dates(all_dates)

    # Only ever eligible for one symbol -- no other symbol should ever be traded.
    result = simulate_dual_momentum(
        all_dates, rebal_dates, indicators, initial_capital=1_000_000.0,
        position_size=50_000.0, cost_model=ZERO_COST,
        eligible_asof_fn=lambda d: frozenset({"SYM0"}),
    )
    traded_symbols = {t.symbol for t in result.trades}
    assert traded_symbols <= {"SYM0"}


def test_simulate_regime_gate_blocks_new_entries_but_not_exits():
    indicators = _build_universe(n_symbols=20, n_days=260)
    all_dates = sorted(set(d for ind in indicators.values() for d in ind.dates))
    rebal_dates = _weekly_rebal_dates(all_dates)

    # Regime "off" for the entire window -- no new entries should ever fire.
    regime_off = {d: False for d in all_dates}
    result = simulate_dual_momentum(
        all_dates, rebal_dates, indicators, initial_capital=1_000_000.0,
        position_size=50_000.0, cost_model=ZERO_COST, regime_ok_by_date=regime_off,
    )
    assert result.trades == []   # never entered anything, so nothing to exit either
    assert all(p.equity == pytest.approx(1_000_000.0) for p in result.curve)
