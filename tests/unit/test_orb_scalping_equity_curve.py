"""
scripts/simulate_orb_scalping_equity_curve.py's `simulate()` -- candidate
18's capital-tracking adapter over core/backtest/equity_curve.py's generic
Account. No network/broker calls: exercises the merge-by-day, capital-
sufficiency skip, and daily-marking logic against synthetic BacktestTrade
objects standing in for real NIFTY/BankNifty ORB signals.
"""

from datetime import date, datetime, timezone

import pytest

from core.backtest.parser import BacktestTrade
from scripts.simulate_orb_scalping_equity_curve import simulate


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


class TestMergeAndCapitalSufficiency:
    def test_profitable_trades_across_both_indices_compound_into_one_account(self):
        d1, d2 = date(2024, 1, 1), date(2024, 1, 2)
        nifty = [_trade(1, d1, entry_price=100.0, exit_price=120.0)]         # +1300
        banknifty = [_trade(1, d2, entry_price=200.0, exit_price=210.0, qty=30)]  # +300
        result, skipped = simulate(nifty, banknifty, trading_days=[d1, d2],
                                    initial_capital=100_000.0)
        assert skipped == []
        assert len(result.closed_positions) == 2
        assert result.final_equity == pytest.approx(100_000.0 + 1300.0 + 300.0)

    def test_same_day_signals_from_both_indices_share_one_cash_pool(self):
        day = date(2024, 1, 1)
        # NIFTY costs 65*100=6,500; BankNifty costs 30*150=4,500 -- together
        # 11,000, more than the 10,000 account has, so BankNifty (processed
        # second, chronologically later intraday) must be skipped.
        nifty = [_trade(1, day, entry_price=100.0, exit_price=100.0)]
        banknifty = [_trade(1, day, entry_price=150.0, exit_price=150.0, qty=30)]
        # Make BankNifty's entry timestamp later in the day than NIFTY's.
        banknifty[0].entry_date = banknifty[0].entry_date.replace(hour=10)
        nifty[0].entry_date = nifty[0].entry_date.replace(hour=9)

        result, skipped = simulate(nifty, banknifty, trading_days=[day], initial_capital=10_000.0)
        assert len(result.closed_positions) == 1
        assert result.closed_positions[0].instrument_id.startswith("NIFTY")
        assert len(skipped) == 1
        assert skipped[0]["underlying"] == "BANKNIFTY"
        assert skipped[0]["needed"] == 4_500.0

    def test_unaffordable_trade_is_skipped_not_partially_filled_or_on_margin(self):
        day = date(2024, 1, 1)
        nifty = [_trade(1, day, entry_price=1000.0, exit_price=1200.0)]  # needs 65,000
        result, skipped = simulate(nifty, [], trading_days=[day], initial_capital=50_000.0)
        assert result.closed_positions == []
        assert len(skipped) == 1
        assert skipped[0]["needed"] == 65_000.0
        assert skipped[0]["cash_available"] == 50_000.0
        # Cash must be completely untouched by a skipped trade.
        assert result.final_equity == 50_000.0

    def test_a_loss_can_still_leave_enough_cash_for_a_later_signal(self):
        d1, d2 = date(2024, 1, 1), date(2024, 1, 2)
        # First trade loses 3,250 (65 * -50), leaving 46,750 -- still enough
        # for a second 65-lot trade at premium 500 (32,500).
        nifty = [
            _trade(1, d1, entry_price=100.0, exit_price=50.0),
            _trade(2, d2, entry_price=500.0, exit_price=520.0),
        ]
        result, skipped = simulate(nifty, [], trading_days=[d1, d2], initial_capital=50_000.0)
        assert skipped == []
        assert len(result.closed_positions) == 2

    def test_costs_are_deducted_from_the_account(self):
        day = date(2024, 1, 1)
        nifty = [_trade(1, day, entry_price=100.0, exit_price=100.0, costs=50.0)]
        result, skipped = simulate(nifty, [], trading_days=[day], initial_capital=100_000.0)
        assert result.final_equity == pytest.approx(100_000.0 - 50.0)


class TestDailyMarking:
    def test_no_trade_days_still_produce_flat_marks(self):
        d1, d2, d3 = date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)
        nifty = [_trade(1, d1, entry_price=100.0, exit_price=100.0)]
        result, _ = simulate(nifty, [], trading_days=[d1, d2, d3], initial_capital=100_000.0)
        assert len(result.curve) == 3
        # Equity is flat (unchanged) on the two no-trade days.
        assert result.curve[1].equity == result.curve[2].equity == result.curve[0].equity

    def test_curve_has_exactly_one_point_per_trading_day(self):
        days = [date(2024, 1, d) for d in range(1, 6)]
        nifty = [_trade(i, days[i - 1], entry_price=100.0, exit_price=110.0) for i in range(1, 4)]
        result, _ = simulate(nifty, [], trading_days=days, initial_capital=1_000_000.0)
        assert len(result.curve) == len(days)
