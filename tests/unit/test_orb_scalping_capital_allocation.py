"""
scripts/simulate_orb_scalping_capital_allocation.py -- candidate 18's
equity-proportional position-sizing research. No network/broker calls:
exercises the mining/holdout split, lot-sizing arithmetic, and the
event-driven simulation engines against synthetic BacktestTrade objects
and a stub cost function, standing in for the real Stratified cost model
so tests don't depend on the real NSE expiry calendar.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from core.backtest.parser import BacktestTrade
from scripts.simulate_orb_scalping_capital_allocation import (
    mining_holdout_split, simulate_equity_fraction, simulate_fixed_lot, size_lots,
)

ZERO_COST = lambda *args: 0.0  # noqa: E731


def _trade(trade_num: int, day: date, entry_price: float, exit_price: float,
           qty: float = 65, costs: float = 0.0) -> BacktestTrade:
    entry_dt = datetime(day.year, day.month, day.day, 9, 20, tzinfo=timezone.utc)
    exit_dt = datetime(day.year, day.month, day.day, 15, 0, tzinfo=timezone.utc)
    profit = (exit_price - entry_price) * qty
    notional = entry_price * qty
    return BacktestTrade(
        trade_num=trade_num, direction="Long", qty=qty,
        entry_date=entry_dt, entry_price=entry_price,
        exit_date=exit_dt, exit_price=exit_price,
        profit=profit, profit_pct=(profit / notional * 100) if notional else 0.0,
        cum_profit=0.0, bars_held=10, costs=costs,
    )


class TestMiningHoldoutSplit:
    def test_80_20_boundary_matches_window_length(self):
        window = (date(2024, 1, 1), date(2024, 1, 1) + timedelta(days=100))   # 100-day window
        _mining, _holdout, boundary = mining_holdout_split([], window)
        expected_offset_days = round((window[1] - window[0]).days * 0.8)
        assert boundary == window[0] + timedelta(days=expected_offset_days)

    def test_trades_split_on_entry_date_boundary(self):
        window = (date(2024, 1, 1), date(2024, 1, 11))   # 10-day window, boundary = day 8
        before = _trade(1, date(2024, 1, 5), 100.0, 100.0)
        after = _trade(2, date(2024, 1, 9), 100.0, 100.0)
        mining, holdout, boundary = mining_holdout_split([before, after], window)
        assert before in mining
        assert after in holdout
        assert before not in holdout
        assert after not in mining


class TestSizeLots:
    def test_sizes_to_target_fraction_of_equity(self):
        # 10% of 100,000 equity = 10,000 target; lot costs 1,000 (10 * 100) -> 10 lots.
        assert size_lots(equity=100_000.0, cash=100_000.0, fraction=0.10,
                          entry_premium=100.0, base_lot_size=10) == 10

    def test_capped_by_spendable_cash_not_equity(self):
        # Equity is 100,000 (includes an already-open position), but only
        # 2,000 cash is actually free -- sizing must respect cash, not equity.
        assert size_lots(equity=100_000.0, cash=2_000.0, fraction=0.5,
                          entry_premium=100.0, base_lot_size=10) == 2

    def test_zero_when_even_one_lot_is_unaffordable(self):
        assert size_lots(equity=1_000.0, cash=1_000.0, fraction=0.5,
                          entry_premium=1_000.0, base_lot_size=10) == 0

    def test_zero_fraction_or_price_yields_zero_lots(self):
        assert size_lots(100_000.0, 100_000.0, fraction=0.0, entry_premium=100.0, base_lot_size=10) == 0
        assert size_lots(100_000.0, 100_000.0, fraction=0.1, entry_premium=0.0, base_lot_size=10) == 0


class TestSimulateEquityFraction:
    def test_lot_count_scales_up_as_equity_compounds(self):
        # Three profitable same-underlying trades on different days: each
        # win grows equity, so a fixed-fraction policy should buy MORE
        # lots on the later trades than the first.
        days = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
        trades = [_trade(i + 1, days[i], entry_price=100.0, exit_price=150.0, qty=10) for i in range(3)]
        result, skipped = simulate_equity_fraction(
            trades, [], days, initial_capital=100_000.0, fraction=0.5, cost_fn=ZERO_COST)
        assert skipped == []
        qtys = [p.qty for p in result.closed_positions]
        assert qtys[0] < qtys[1] < qtys[2]

    def test_skips_when_fraction_of_equity_cant_afford_one_lot(self):
        day = date(2024, 1, 1)
        trades = [_trade(1, day, entry_price=1000.0, exit_price=1000.0, qty=10)]  # 1 lot = 10,000
        # 1% of 100,000 = 1,000 target -- can't afford even 1 lot (needs 10,000).
        result, skipped = simulate_equity_fraction(
            trades, [], [day], initial_capital=100_000.0, fraction=0.01, cost_fn=ZERO_COST)
        assert result.closed_positions == []
        assert len(skipped) == 1
        assert skipped[0]["one_lot_cost"] == 10_000.0

    def test_concurrent_signals_split_available_cash(self):
        day = date(2024, 1, 1)
        nifty = [_trade(1, day, entry_price=100.0, exit_price=100.0, qty=10)]
        banknifty = [_trade(1, day, entry_price=100.0, exit_price=100.0, qty=10)]
        nifty[0].entry_date = nifty[0].entry_date.replace(hour=9)
        banknifty[0].entry_date = banknifty[0].entry_date.replace(hour=9, minute=30)
        # fraction=1.0 (all-in) on the first signal leaves nothing for the second.
        result, skipped = simulate_equity_fraction(
            nifty, banknifty, [day], initial_capital=10_000.0, fraction=1.0, cost_fn=ZERO_COST)
        assert len(result.closed_positions) == 1
        assert len(skipped) == 1

    def test_cost_fn_is_invoked_with_actual_quantity_and_deducted(self):
        day = date(2024, 1, 1)
        trades = [_trade(1, day, entry_price=100.0, exit_price=100.0, qty=10)]
        seen = {}

        def spy_cost_fn(underlying, entry_premium, exit_premium, qty, d):
            seen["qty"] = qty
            seen["underlying"] = underlying
            return 250.0

        result, _ = simulate_equity_fraction(
            trades, [], [day], initial_capital=100_000.0, fraction=1.0, cost_fn=spy_cost_fn)
        # fraction=1.0 of 100,000 equity affords 100 lots (100,000 / (10*100)=100).
        assert seen["qty"] == 1000  # 100 lots * 10 qty/lot
        assert seen["underlying"] == "NIFTY"
        assert result.final_equity == pytest.approx(100_000.0 - 250.0)   # entry==exit price, only cost applied

    def test_no_trade_days_still_produce_flat_marks(self):
        d1, d2, d3 = date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)
        trades = [_trade(1, d1, entry_price=100.0, exit_price=100.0, qty=10)]
        result, _ = simulate_equity_fraction(
            trades, [], [d1, d2, d3], initial_capital=100_000.0, fraction=0.1, cost_fn=ZERO_COST)
        assert len(result.curve) == 3
        assert result.curve[0].equity == result.curve[1].equity == result.curve[2].equity


class TestSimulateFixedLot:
    def test_matches_expected_single_lot_behavior(self):
        d1, d2 = date(2024, 1, 1), date(2024, 1, 2)
        nifty = [_trade(1, d1, entry_price=100.0, exit_price=120.0, qty=65)]
        banknifty = [_trade(1, d2, entry_price=200.0, exit_price=210.0, qty=30)]
        result, skipped = simulate_fixed_lot(nifty, banknifty, [d1, d2], initial_capital=100_000.0)
        assert skipped == []
        assert len(result.closed_positions) == 2
        assert result.final_equity == pytest.approx(100_000.0 + 1300.0 + 300.0)

    def test_never_scales_lot_count_even_when_equity_grows(self):
        days = [date(2024, 1, d) for d in range(1, 4)]
        trades = [_trade(i + 1, days[i], entry_price=100.0, exit_price=150.0, qty=10) for i in range(3)]
        result, _ = simulate_fixed_lot(trades, [], days, initial_capital=1_000_000.0)
        qtys = [p.qty for p in result.closed_positions]
        assert qtys == [10, 10, 10]
