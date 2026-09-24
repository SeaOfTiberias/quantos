"""
core/backtest/equity_curve.py — generic Account-style equity-curve core.
Strategy-agnostic on purpose (see that module's docstring for why it's a
new module, not a reuse of core/rotation/equity_curve.py): covers cash
accounting, insufficient-cash handling, overlapping same-instrument
positions, mark-to-market fallback, and the CAGR/Sharpe/drawdown math,
all with no strategy-specific logic (no options, no equities, no
rotation) -- that comes in per-candidate adapters, tested separately.
"""

import math
from datetime import datetime, timedelta

import pytest

from core.backtest.equity_curve import (
    Account, InsufficientCash, kelly_fraction, _max_drawdown, _sharpe,
)


def _d(n: int, start=datetime(2024, 1, 1)) -> datetime:
    return start + timedelta(days=n)


class TestOpenClose:
    def test_open_deducts_cash_and_close_credits_it(self):
        acct = Account(initial_capital=100_000.0)
        pos_id = acct.open("NIFTY_CE", qty=65, price=100.0, when=_d(0))
        assert acct.cash == 100_000.0 - 65 * 100.0
        assert pos_id in acct.open_positions

        closed = acct.close(pos_id, price=120.0, when=_d(0))
        assert closed.realized_pnl == pytest.approx((120.0 - 100.0) * 65)
        assert acct.cash == pytest.approx(100_000.0 - 65 * 100.0 + 65 * 120.0)
        assert pos_id not in acct.open_positions
        assert acct.closed_positions == [closed]

    def test_close_nets_costs_from_realized_pnl_and_cash(self):
        acct = Account(initial_capital=100_000.0)
        pos_id = acct.open("NIFTY_CE", qty=65, price=100.0, when=_d(0))
        closed = acct.close(pos_id, price=120.0, when=_d(0), costs=50.0)
        assert closed.realized_pnl == pytest.approx((120.0 - 100.0) * 65 - 50.0)
        assert acct.cash == pytest.approx(100_000.0 - 65 * 100.0 + 65 * 120.0 - 50.0)

    def test_zero_or_negative_qty_rejected(self):
        acct = Account(initial_capital=100_000.0)
        with pytest.raises(ValueError):
            acct.open("X", qty=0, price=10.0, when=_d(0))
        with pytest.raises(ValueError):
            acct.open("X", qty=-1, price=10.0, when=_d(0))

    def test_initial_capital_must_be_positive(self):
        with pytest.raises(ValueError):
            Account(initial_capital=0.0)
        with pytest.raises(ValueError):
            Account(initial_capital=-1.0)


class TestInsufficientCash:
    def test_strict_open_raises_when_unaffordable(self):
        acct = Account(initial_capital=1_000.0)
        with pytest.raises(InsufficientCash):
            acct.open("NIFTY_CE", qty=65, price=100.0, when=_d(0))
        # A failed strict open must not have touched cash or created a position.
        assert acct.cash == 1_000.0
        assert acct.open_positions == {}

    def test_non_strict_open_returns_none_and_leaves_cash_untouched(self):
        acct = Account(initial_capital=1_000.0)
        pos_id = acct.open("NIFTY_CE", qty=65, price=100.0, when=_d(0), strict=False)
        assert pos_id is None
        assert acct.cash == 1_000.0
        assert acct.open_positions == {}

    def test_can_afford_matches_open_behavior(self):
        acct = Account(initial_capital=6_500.0)
        assert acct.can_afford(65, 100.0) is True     # exactly affordable
        assert acct.can_afford(65, 100.01) is False
        acct.open("A", qty=65, price=100.0, when=_d(0))
        assert acct.cash == pytest.approx(0.0)
        assert acct.can_afford(1, 0.01) is False


class TestOverlappingPositions:
    def test_same_instrument_opened_twice_tracked_independently(self):
        acct = Account(initial_capital=100_000.0)
        id1 = acct.open("RELIANCE", qty=10, price=2500.0, when=_d(0))
        id2 = acct.open("RELIANCE", qty=5, price=2600.0, when=_d(1))
        assert id1 != id2
        assert len(acct.open_positions) == 2
        assert acct.open_positions[id1].entry_price == 2500.0
        assert acct.open_positions[id2].entry_price == 2600.0

        # Closing one must not disturb the other's entry price or qty.
        acct.close(id1, price=2700.0, when=_d(2))
        assert id2 in acct.open_positions
        assert acct.open_positions[id2].qty == 5
        assert acct.open_positions[id2].entry_price == 2600.0

    def test_concurrent_positions_compete_for_the_same_cash_pool(self):
        # Two same-day signals (e.g. NIFTY + BankNifty both firing) drawing
        # from one account -- the second must fail once the first has spent
        # the cash, exactly the scenario candidate 18's adapter needs.
        acct = Account(initial_capital=10_000.0)
        acct.open("NIFTY_CE", qty=65, price=100.0, when=_d(0))   # costs 6,500
        assert acct.cash == pytest.approx(3_500.0)
        with pytest.raises(InsufficientCash):
            acct.open("BANKNIFTY_PE", qty=30, price=150.0, when=_d(0))  # needs 4,500


class TestMarkToMarket:
    def test_mark_records_cash_plus_open_positions_value(self):
        acct = Account(initial_capital=100_000.0)
        acct.open("A", qty=10, price=100.0, when=_d(0))
        point = acct.mark(_d(0), mark_prices={"A": 110.0})
        assert point.cash == pytest.approx(100_000.0 - 1_000.0)
        assert point.positions_value == pytest.approx(1_100.0)
        assert point.equity == pytest.approx(100_000.0 - 1_000.0 + 1_100.0)

    def test_mark_falls_back_to_entry_price_when_no_fresh_mark_available(self):
        acct = Account(initial_capital=100_000.0)
        acct.open("A", qty=10, price=100.0, when=_d(0))
        # "A" missing from mark_prices -- e.g. a halt/listing gap day.
        point = acct.mark(_d(1), mark_prices={})
        assert point.positions_value == pytest.approx(1_000.0)   # 10 * entry_price(100)

    def test_force_close_all_zeroes_positions_value_and_realizes_cash(self):
        acct = Account(initial_capital=100_000.0)
        acct.open("A", qty=10, price=100.0, when=_d(0))
        acct.open("B", qty=5, price=200.0, when=_d(0))
        acct.force_close_all(_d(5), mark_prices={"A": 120.0, "B": 190.0})
        assert acct.open_positions == {}
        point = acct.mark(_d(5), mark_prices={})
        assert point.positions_value == 0.0
        expected_cash = 100_000.0 - 1_000.0 - 1_000.0 + 1_200.0 + 950.0
        assert point.cash == pytest.approx(expected_cash)
        assert point.equity == pytest.approx(expected_cash)


class TestFinalize:
    def test_no_marks_returns_flat_noop_result(self):
        acct = Account(initial_capital=50_000.0)
        result = acct.finalize()
        assert result.final_equity == 50_000.0
        assert result.curve == []
        assert result.sharpe == 0.0
        assert result.max_drawdown_pct == 0.0

    def test_flat_equity_curve_has_zero_sharpe_and_zero_drawdown(self):
        acct = Account(initial_capital=100_000.0)
        for i in range(10):
            acct.mark(_d(i), mark_prices={})
        result = acct.finalize()
        assert result.sharpe == 0.0
        assert result.max_drawdown_pct == 0.0
        assert result.total_return_pct == 0.0
        assert result.final_equity == 100_000.0

    def test_total_return_and_cagr_from_a_simple_doubling(self):
        acct = Account(initial_capital=100_000.0)
        pos_id = acct.open("A", qty=1000, price=100.0, when=_d(0))
        acct.mark(_d(0), mark_prices={"A": 100.0})
        acct.close(pos_id, price=200.0, when=_d(365))
        acct.mark(_d(365), mark_prices={})
        result = acct.finalize()
        assert result.final_equity == pytest.approx(200_000.0)
        assert result.total_return_pct == pytest.approx(100.0)
        # Exactly 365 days span -> years=1.0 -> CAGR == total return here.
        assert result.cagr_pct == pytest.approx(100.0, abs=0.5)

    def test_drawdown_is_bounded_to_100_percent_even_after_a_wipeout(self):
        # The exact trap this module exists to avoid (see module docstring):
        # a real account cannot lose more than 100% of its capital, unlike
        # core/backtest/parser.py's summed-per-trade-% drawdown, which can
        # exceed 100% because it isn't a real compounding balance.
        acct = Account(initial_capital=100_000.0)
        pos_id = acct.open("A", qty=1000, price=100.0, when=_d(0))
        acct.mark(_d(0), mark_prices={"A": 100.0})
        # Total wipeout: exits worthless.
        acct.close(pos_id, price=0.0, when=_d(1))
        acct.mark(_d(1), mark_prices={})
        result = acct.finalize()
        assert result.final_equity == pytest.approx(0.0)
        assert result.max_drawdown_pct == pytest.approx(100.0)
        assert result.max_drawdown_pct <= 100.0

    def test_max_drawdown_tracks_peak_to_trough_not_start_to_end(self):
        acct = Account(initial_capital=100_000.0)
        # Equity path: 100k -> 150k (new peak) -> 90k (40% DD from peak) -> 120k (recovers some).
        acct.mark(_d(0), mark_prices={})
        acct.cash = 150_000.0
        acct.mark(_d(1), mark_prices={})
        acct.cash = 90_000.0
        acct.mark(_d(2), mark_prices={})
        acct.cash = 120_000.0
        acct.mark(_d(3), mark_prices={})
        result = acct.finalize()
        assert result.max_drawdown_pct == pytest.approx((150_000 - 90_000) / 150_000 * 100)
        assert result.max_drawdown_rs == pytest.approx(60_000.0)


class TestKellyFraction:
    def test_matches_classical_double_or_nothing_formula(self):
        # Classical Kelly for a bet that either doubles the stake (r=+1.0)
        # with probability p or loses it entirely (r=-1.0) otherwise has a
        # closed-form optimum f* = 2p - 1. p=0.6 -> f*=0.2.
        p = 0.6
        returns = [1.0] * 60 + [-1.0] * 40
        assert kelly_fraction(returns, step=0.001) == pytest.approx(2 * p - 1, abs=0.01)

    def test_unfavorable_bet_has_zero_kelly_fraction(self):
        # p=0.4 on the same double-or-nothing bet has negative expectancy
        # for any long-only fraction -- optimal is to not bet at all.
        returns = [1.0] * 40 + [-1.0] * 60
        assert kelly_fraction(returns) == 0.0

    def test_empty_returns_is_zero(self):
        assert kelly_fraction([]) == 0.0

    def test_rejects_a_return_worse_than_total_loss(self):
        with pytest.raises(ValueError):
            kelly_fraction([0.1, -1.5, 0.2])

    def test_exact_total_loss_is_allowed(self):
        # -1.0 (100% loss of what was allocated) is the worst real outcome
        # for a long option/equity position -- must not raise.
        assert kelly_fraction([0.5, -1.0, 0.3]) >= 0.0

    def test_higher_win_probability_yields_higher_fraction(self):
        low_p = kelly_fraction([1.0] * 55 + [-1.0] * 45)
        high_p = kelly_fraction([1.0] * 70 + [-1.0] * 30)
        assert high_p > low_p


class TestSharpeAndDrawdownHelpers:
    def test_sharpe_matches_hand_computed_value(self):
        returns = [0.01, -0.005, 0.02, 0.0, -0.01]
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(variance)
        expected = mean / std * math.sqrt(252)
        assert _sharpe(returns) == pytest.approx(expected)

    def test_sharpe_needs_at_least_two_returns(self):
        assert _sharpe([]) == 0.0
        assert _sharpe([0.01]) == 0.0

    def test_sharpe_zero_when_std_is_zero(self):
        assert _sharpe([0.01, 0.01, 0.01]) == 0.0

    def test_max_drawdown_zero_on_monotonic_rise(self):
        from core.backtest.equity_curve import EquityCurvePoint
        curve = [EquityCurvePoint(date=_d(i), cash=100_000.0 + i * 1000, positions_value=0.0)
                 for i in range(5)]
        dd_pct, dd_rs = _max_drawdown(curve)
        assert dd_pct == 0.0
        assert dd_rs == 0.0
