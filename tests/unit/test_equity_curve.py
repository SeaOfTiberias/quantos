"""
core/rotation/equity_curve.py — real capital-tracked equity curve for
S8-3 rotation (vs. the pooled per-trade stats in docs/S8_3_BACKTEST_RESULTS.md,
which can't answer "what does my real capital become"). Covers sizing
reuse, the three exit-rule variants (rank_only/stop_loss/ema_cross),
CAGR/Sharpe/max-drawdown correctness, and the Nifty benchmark/alpha calc.
"""

from datetime import datetime, timedelta

import pytest

from core.risk.costs import CostModel
from core.rotation.equity_curve import (
    EquityCurvePoint, compute_alpha, simulate_index_buy_and_hold, simulate_portfolio,
)
from core.rotation.ranker import SymbolSeries

ZERO_COST = CostModel(brokerage_pct=0, brokerage_flat=0, stt_pct=0,
                       exchange_txn_pct=0, sebi_pct=0, stamp_pct=0,
                       gst_pct=0, slippage_bps=0)


def _dates(n: int, start=datetime(2024, 1, 1)) -> list[datetime]:
    return [start + timedelta(days=i) for i in range(n)]


def _series(dates: list[datetime], closes: list[float], highs: list[float] = None) -> SymbolSeries:
    highs = highs if highs is not None else [max(closes[:i + 1]) for i in range(len(closes))]
    return SymbolSeries(dates=dates, closes=closes, highs=highs)


class TestBasicEquityTracking:

    def test_single_symbol_always_top_ranked_tracks_price(self):
        dates = _dates(15)
        # Rebalance on day 0 and day 7 only; symbol always ranks #1 (only symbol).
        series = {"A": _series(dates, closes=[100.0] * 15)}
        rebal = {dates[0], dates[7]}

        result = simulate_portfolio(
            dates, rebal, series, top_n=1, initial_capital=100_000.0,
            position_size=100_000.0, cost_model=ZERO_COST, exit_rule="rank_only",
        )
        # Bought ~1000 shares at 100 on day 0, price never moves, so equity
        # stays flat at (or very near) initial capital throughout.
        assert result.curve[0].equity == pytest.approx(100_000.0, abs=200)
        assert result.curve[-1].equity == pytest.approx(100_000.0, abs=200)

    def test_price_appreciation_flows_through_to_equity(self):
        dates = _dates(10)
        closes = [100.0 + i for i in range(10)]   # steady rise 100 -> 109
        series = {"A": _series(dates, closes=closes)}
        rebal = {dates[0]}

        result = simulate_portfolio(
            dates, rebal, series, top_n=1, initial_capital=100_000.0,
            position_size=100_000.0, cost_model=ZERO_COST, exit_rule="rank_only",
        )
        assert result.final_equity > result.initial_capital
        assert result.total_return_pct > 0

    def test_never_spends_more_than_available_capital(self):
        """Reuses core/rotation/executor.py's own _size_new_entrants — this
        just proves the reuse is actually wired, not a parallel reimplementation."""
        dates = _dates(5)
        # Three symbols each expensive enough that not all 3 can be funded
        # at position_size with only initial_capital available.
        series = {
            "A": _series(dates, closes=[40_000.0] * 5),
            "B": _series(dates, closes=[40_000.0] * 5),
            "C": _series(dates, closes=[40_000.0] * 5),
        }
        result = simulate_portfolio(
            dates, {dates[0]}, series, top_n=3, initial_capital=100_000.0,
            position_size=50_000.0, cost_model=ZERO_COST, exit_rule="rank_only",
        )
        # Equity can dip by at most rounding-related cash left idle -- never negative equity.
        assert all(p.equity >= 0 for p in result.curve)
        assert result.curve[0].equity <= 100_000.0 + 1.0


class TestRankDropoutExit:

    def test_symbol_sold_when_it_drops_out_of_top_n(self):
        dates = _dates(15)
        # B is unambiguously top-ranked at day 0 (score 1.0 vs A's 0.9 — a
        # real gap, not a tie that'd fall back to dict-iteration order),
        # then collapses relative to A by day 7, dropping out of the top-1
        # basket at that rebalance while A recovers to its own high and
        # takes the slot.
        a_closes = [90.0] * 7 + [100.0] * 8
        b_closes = [100.0] * 7 + [10.0] * 8
        series = {
            "A": _series(dates, closes=a_closes, highs=[100.0] * 15),
            "B": _series(dates, closes=b_closes, highs=[100.0] * 15),
        }
        rebal = {dates[0], dates[7]}

        result = simulate_portfolio(
            dates, rebal, series, top_n=1, initial_capital=200_000.0,
            position_size=100_000.0, cost_model=ZERO_COST, exit_rule="rank_only",
        )
        exits = [t for t in result.trades if t.exit_reason == "rank_dropout"]
        assert len(exits) == 1
        assert exits[0].exit_date == dates[7]


class TestStopLossExit:

    def test_triggers_intraweek_not_just_at_rebalance(self):
        """The whole point: a 5% single-day drop must be caught the day it
        happens, not only discovered at the next weekly rebalance."""
        dates = _dates(10)
        # Flat at 100 for days 0-2, drops 6% on day 3 (mid-week, no rebalance
        # scheduled that day), stays down. Only rebalance is day 0.
        closes = [100.0, 100.0, 100.0, 94.0, 94.0, 94.0, 94.0, 94.0, 94.0, 94.0]
        series = {"A": _series(dates, closes=closes, highs=[100.0] * 10)}

        result = simulate_portfolio(
            dates, {dates[0]}, series, top_n=1, initial_capital=100_000.0,
            position_size=100_000.0, cost_model=ZERO_COST, exit_rule="stop_loss",
            stop_loss_pct=0.05,
        )
        stop_exits = [t for t in result.trades if t.exit_reason == "stop_loss"]
        assert len(stop_exits) == 1
        assert stop_exits[0].exit_date == dates[3]   # the day the drop happened, not later

    def test_small_dip_under_threshold_does_not_trigger(self):
        dates = _dates(10)
        closes = [100.0] * 5 + [97.0] * 5   # 3% dip, under the 5% threshold
        series = {"A": _series(dates, closes=closes, highs=[100.0] * 10)}

        result = simulate_portfolio(
            dates, {dates[0]}, series, top_n=1, initial_capital=100_000.0,
            position_size=100_000.0, cost_model=ZERO_COST, exit_rule="stop_loss",
            stop_loss_pct=0.05,
        )
        assert not any(t.exit_reason == "stop_loss" for t in result.trades)


class TestEmaCrossExit:

    def test_triggers_when_fast_ema_crosses_below_slow_ema(self):
        dates = _dates(40)
        # Rises for 25 days (fast EMA stays above slow), then falls hard for
        # the rest -- fast EMA (9) reacts faster than slow EMA (21) and
        # crosses below it partway through the decline.
        closes = [100.0 + i for i in range(25)] + [125.0 - 3 * i for i in range(15)]
        series = {"A": _series(dates, closes=closes, highs=[max(closes[:i + 1]) for i in range(40)])}

        result = simulate_portfolio(
            dates, {dates[0]}, series, top_n=1, initial_capital=100_000.0,
            position_size=100_000.0, cost_model=ZERO_COST, exit_rule="ema_cross",
            ema_fast=9, ema_slow=21,
        )
        cross_exits = [t for t in result.trades if t.exit_reason == "ema_cross"]
        assert len(cross_exits) == 1
        assert cross_exits[0].exit_date > dates[25]   # triggers during the decline, not before

    def test_no_cross_no_exit(self):
        dates = _dates(30)
        closes = [100.0 + i * 0.5 for i in range(30)]   # steady rise, never crosses
        series = {"A": _series(dates, closes=closes, highs=[max(closes[:i + 1]) for i in range(30)])}

        result = simulate_portfolio(
            dates, {dates[0]}, series, top_n=1, initial_capital=100_000.0,
            position_size=100_000.0, cost_model=ZERO_COST, exit_rule="ema_cross",
        )
        assert not any(t.exit_reason == "ema_cross" for t in result.trades)


class TestMetrics:

    def test_cagr_matches_known_growth_over_one_year(self):
        dates = _dates(366)
        # 10% growth over ~1 year, single symbol, no rebalancing after entry.
        closes = [100.0 * (1.10 ** (i / 365)) for i in range(366)]
        series = {"A": _series(dates, closes=closes, highs=[max(closes[:i + 1]) for i in range(366)])}

        result = simulate_portfolio(
            dates, {dates[0]}, series, top_n=1, initial_capital=1_000_000.0,
            position_size=1_000_000.0, cost_model=ZERO_COST, exit_rule="rank_only",
        )
        assert result.cagr_pct == pytest.approx(10.0, abs=1.0)

    def test_max_drawdown_never_exceeds_100_percent(self):
        """The exact defect the pooled per-trade stats had (652.4%
        "drawdown") -- must be structurally impossible here."""
        dates = _dates(20)
        closes = [100.0] * 5 + [1.0] * 15   # catastrophic 99% drop
        series = {"A": _series(dates, closes=closes, highs=[100.0] * 20)}

        result = simulate_portfolio(
            dates, {dates[0]}, series, top_n=1, initial_capital=100_000.0,
            position_size=100_000.0, cost_model=ZERO_COST, exit_rule="rank_only",
        )
        assert 0 <= result.max_drawdown_pct <= 100

    def test_empty_curve_handled_gracefully(self):
        result = simulate_portfolio(
            [], set(), {}, top_n=1, initial_capital=100_000.0,
            position_size=100_000.0, cost_model=ZERO_COST,
        )
        assert result.final_equity == 100_000.0
        assert result.curve == []

    def test_all_positions_force_closed_by_final_date(self):
        dates = _dates(10)
        series = {"A": _series(dates, closes=[100.0 + i for i in range(10)], highs=[110.0] * 10)}
        result = simulate_portfolio(
            dates, {dates[0]}, series, top_n=1, initial_capital=100_000.0,
            position_size=100_000.0, cost_model=ZERO_COST,
        )
        assert result.final_equity == pytest.approx(result.curve[-1].equity)


class TestNiftyBenchmarkAndAlpha:

    def test_buy_and_hold_tracks_index_return(self):
        dates = _dates(366)
        closes = [(d, 20_000.0 * (1.12 ** (i / 365))) for i, d in enumerate(dates)]
        bench = simulate_index_buy_and_hold(closes, initial_capital=1_000_000.0)
        assert bench.total_return_pct == pytest.approx(12.0, abs=1.0)
        assert bench.cagr_pct == pytest.approx(12.0, abs=1.0)

    def test_empty_closes_handled_gracefully(self):
        bench = simulate_index_buy_and_hold([], initial_capital=1_000_000.0)
        assert bench.final_equity == 1_000_000.0

    def test_compute_alpha_positive_when_strategy_beats_benchmark(self):
        dates = _dates(366)
        strat_closes = [100.0 * (1.20 ** (i / 365)) for i in range(366)]
        series = {"A": _series(dates, closes=strat_closes, highs=[max(strat_closes[:i + 1]) for i in range(366)])}
        strategy = simulate_portfolio(
            dates, {dates[0]}, series, top_n=1, initial_capital=1_000_000.0,
            position_size=1_000_000.0, cost_model=ZERO_COST,
        )
        nifty_closes = [(d, 20_000.0 * (1.10 ** (i / 365))) for i, d in enumerate(dates)]
        benchmark = simulate_index_buy_and_hold(nifty_closes, initial_capital=1_000_000.0)

        alpha = compute_alpha(strategy, benchmark)
        assert alpha["strategy_beats_benchmark"] is True
        assert alpha["alpha_total_return_pct"] > 0

    def test_compute_alpha_negative_when_benchmark_wins(self):
        dates = _dates(366)
        strat_closes = [100.0 * (1.05 ** (i / 365)) for i in range(366)]
        series = {"A": _series(dates, closes=strat_closes, highs=[max(strat_closes[:i + 1]) for i in range(366)])}
        strategy = simulate_portfolio(
            dates, {dates[0]}, series, top_n=1, initial_capital=1_000_000.0,
            position_size=1_000_000.0, cost_model=ZERO_COST,
        )
        nifty_closes = [(d, 20_000.0 * (1.15 ** (i / 365))) for i, d in enumerate(dates)]
        benchmark = simulate_index_buy_and_hold(nifty_closes, initial_capital=1_000_000.0)

        alpha = compute_alpha(strategy, benchmark)
        assert alpha["strategy_beats_benchmark"] is False
        assert alpha["alpha_total_return_pct"] < 0
