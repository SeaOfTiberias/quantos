"""
scripts/simulate_darvas_atr_stop_equity_curve.py -- Darvas ATR-stop
(Bucket B) real-capital equity curve and Kelly-based position sizing. No
network/broker calls, no dependency on the real ~/.quantos cache: exercises
bucket filtering, mining/holdout split, and the event-driven multi-symbol
simulation engine against synthetic trade dicts shaped exactly like
scripts/backtest_darvas_atr_stop.py's own committed cache format.
"""

from datetime import date, datetime, timezone

import pytest

from scripts.simulate_darvas_atr_stop_equity_curve import (
    BUCKET_B_LABEL, bucket_b_trades, build_trading_days, capital_floor_threshold,
    mining_holdout_split, simulate, trade_fractional_return,
)


def _trade(symbol: str, width_pct: float, entry_date: str, exit_date: str,
           entry_price: float, exit_price: float, breakout_date: str = None,
           reason: str = "stop") -> dict:
    return {
        "symbol": symbol, "breakout_date": breakout_date or entry_date,
        "width_pct": width_pct, "entry_date": entry_date, "entry_price": entry_price,
        "exit_date": exit_date, "exit_price": exit_price, "reason": reason,
    }


def _dt(iso_date: str) -> str:
    return f"{iso_date}T00:00:00+00:00"


class TestBucketBTrades:
    def test_filters_to_the_35_50_pct_band_only(self):
        results = {
            "A": {"trades": [_trade("A", 20.0, _dt("2024-01-01"), _dt("2024-01-05"), 100, 110)]},
            "B": {"trades": [_trade("B", 40.0, _dt("2024-01-01"), _dt("2024-01-05"), 100, 110)]},
            "C": {"trades": [_trade("C", 75.0, _dt("2024-01-01"), _dt("2024-01-05"), 100, 110)]},
        }
        trades = bucket_b_trades(results)
        assert len(trades) == 1
        assert trades[0]["symbol"] == "B"

    def test_boundary_is_exclusive_low_inclusive_high(self):
        results = {
            "X": {"trades": [_trade("X", 35.0, _dt("2024-01-01"), _dt("2024-01-05"), 100, 110)]},
            "Y": {"trades": [_trade("Y", 50.0, _dt("2024-01-01"), _dt("2024-01-05"), 100, 110)]},
        }
        trades = bucket_b_trades(results)
        symbols = {t["symbol"] for t in trades}
        assert "X" not in symbols   # exactly 35% belongs to the <=35% control bucket
        assert "Y" in symbols       # exactly 50% belongs to 35-50%


class TestMiningHoldoutSplit:
    def test_splits_on_breakout_date_not_entry_date(self):
        before = _trade("A", 40.0, _dt("2024-01-02"), _dt("2024-01-10"),
                         100, 110, breakout_date=_dt("2026-02-14"))
        after = _trade("B", 40.0, _dt("2024-01-02"), _dt("2024-01-10"),
                        100, 110, breakout_date=_dt("2026-02-15"))
        mining, holdout = mining_holdout_split([before, after])
        assert before in mining
        assert after in holdout


class TestFractionalReturn:
    def test_positive_return_net_of_costs(self):
        r = trade_fractional_return(entry_price=100.0, exit_price=120.0, qty=100)
        # Gross is exactly +20%; net-of-cost must be slightly less.
        assert 0 < r < 0.20

    def test_zero_qty_or_entry_price_is_zero(self):
        assert trade_fractional_return(100.0, 120.0, 0) == 0.0
        assert trade_fractional_return(0.0, 120.0, 100) == 0.0


class TestBuildTradingDays:
    def test_includes_every_trade_entry_and_exit_date_even_past_calendar_coverage(self):
        far_future_trade = _trade("A", 40.0, _dt("2030-01-02"), _dt("2030-01-10"), 100, 110)
        days = build_trading_days([far_future_trade], date(2030, 1, 10))
        assert date(2030, 1, 2) in days
        assert date(2030, 1, 10) in days


class TestSimulateFixedNotional:
    def test_single_trade_realizes_correct_pnl(self):
        t = _trade("A", 40.0, _dt("2024-01-02"), _dt("2024-01-10"), entry_price=100.0, exit_price=120.0)
        days = [date(2024, 1, 2), date(2024, 1, 10)]
        result, skipped = simulate([t], days, initial_capital=100_000.0, sizing="fixed_notional")
        assert skipped == []
        assert len(result.closed_positions) == 1
        pos = result.closed_positions[0]
        assert pos.qty == 1000   # floor(100_000 / 100.0) shares, fixed Rs100k notional
        assert result.final_equity > 100_000.0   # a real (net-of-cost) profit

    def test_insufficient_cash_for_even_one_share_is_skipped(self):
        t = _trade("A", 40.0, _dt("2024-01-02"), _dt("2024-01-10"), entry_price=50_000.0, exit_price=55_000.0)
        days = [date(2024, 1, 2), date(2024, 1, 10)]
        result, skipped = simulate([t], days, initial_capital=1_000.0, sizing="fixed_notional")
        assert result.closed_positions == []
        assert len(skipped) == 1

    def test_concurrent_symbols_share_one_cash_pool_and_the_second_sizes_down(self):
        a = _trade("A", 40.0, _dt("2024-01-02"), _dt("2024-01-20"), entry_price=1000.0, exit_price=1000.0)
        b = _trade("B", 40.0, _dt("2024-01-05"), _dt("2024-01-20"), entry_price=1000.0, exit_price=1000.0)
        days = [date(2024, 1, 2), date(2024, 1, 5), date(2024, 1, 20)]
        # 150,000 affords one full Rs100k position (100 shares), leaving only
        # 50,000 free when B opens while A is still held -- unlike options'
        # whole-lot granularity, a share-sized position just sizes DOWN to
        # whatever cash remains rather than being skipped outright.
        result, skipped = simulate([a, b], days, initial_capital=150_000.0, sizing="fixed_notional")
        assert skipped == []
        assert len(result.closed_positions) == 2
        qty_by_symbol = {p.instrument_id: p.qty for p in result.closed_positions}
        assert qty_by_symbol["A"] == 100          # full Rs100k / Rs1000 target
        assert qty_by_symbol["B"] == 50           # capped by the Rs50,000 actually left

    def test_a_truly_unaffordable_single_share_is_skipped(self):
        a = _trade("A", 40.0, _dt("2024-01-02"), _dt("2024-01-20"), entry_price=1000.0, exit_price=1000.0)
        b = _trade("B", 40.0, _dt("2024-01-05"), _dt("2024-01-20"), entry_price=60_000.0, exit_price=60_000.0)
        days = [date(2024, 1, 2), date(2024, 1, 5), date(2024, 1, 20)]
        # After A takes 100,000 of the 150,000, only 50,000 is left -- not
        # even one share of a Rs60,000 stock.
        result, skipped = simulate([a, b], days, initial_capital=150_000.0, sizing="fixed_notional")
        assert len(result.closed_positions) == 1
        assert len(skipped) == 1
        assert skipped[0]["symbol"] == "B"


class TestSimulateEquityFraction:
    def test_position_size_scales_with_compounding_equity(self):
        # B opens strictly AFTER A has fully closed (a gap day between them),
        # so B's sizing sees A's REALIZED gain, not a same-day tie where an
        # open and a close on the identical timestamp would otherwise both
        # value the still-technically-open A position at its entry price.
        days = [date(2024, 1, 1), date(2024, 1, 4), date(2024, 1, 6), date(2024, 1, 9)]
        trades = [
            _trade("A", 40.0, _dt("2024-01-01"), _dt("2024-01-04"), entry_price=100.0, exit_price=150.0),
            _trade("B", 40.0, _dt("2024-01-06"), _dt("2024-01-09"), entry_price=100.0, exit_price=150.0),
        ]
        result, skipped = simulate(trades, days, initial_capital=100_000.0, sizing="fraction", fraction=0.5)
        assert skipped == []
        qtys = [p.qty for p in result.closed_positions]
        assert qtys[0] < qtys[1]   # later trade sized off a larger (compounded) equity

    def test_zero_shares_from_a_tiny_fraction_is_skipped(self):
        t = _trade("A", 40.0, _dt("2024-01-02"), _dt("2024-01-10"), entry_price=100.0, exit_price=110.0)
        result, skipped = simulate([t], [date(2024, 1, 2), date(2024, 1, 10)],
                                    initial_capital=100.0, sizing="fraction", fraction=0.01)
        assert result.closed_positions == []
        assert len(skipped) == 1


class TestCapitalFloorThreshold:
    def test_finds_the_smallest_capital_that_can_afford_even_one_share(self):
        # Rs60,000/share stock -- a truly discrete affordability cliff, unlike
        # a cheap stock that just sizes down smoothly to any small capital.
        t = _trade("A", 40.0, _dt("2024-01-02"), _dt("2024-01-10"), entry_price=60_000.0, exit_price=66_000.0)
        days = [date(2024, 1, 2), date(2024, 1, 10)]
        floor = capital_floor_threshold([t], days, "fixed_notional", 0.0,
                                         candidates=[10_000.0, 50_000.0, 100_000.0, 200_000.0])
        assert floor == 100_000.0   # smallest tested tier that can afford >= 1 share

    def test_returns_none_if_nothing_tested_clears_it(self):
        t = _trade("A", 40.0, _dt("2024-01-02"), _dt("2024-01-10"), entry_price=1_000_000.0, exit_price=1_100_000.0)
        days = [date(2024, 1, 2), date(2024, 1, 10)]
        floor = capital_floor_threshold([t], days, "fixed_notional", 0.0, candidates=[10_000.0, 50_000.0])
        assert floor is None
