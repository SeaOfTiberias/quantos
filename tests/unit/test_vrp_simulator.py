"""
VRP Phase 3 — Strangle P&L Simulator — Unit Tests
"""

from datetime import date

import pytest

from core.options.models import OptionType
from core.options.vrp.bhavcopy import BhavcopyOptionRow
from core.options.vrp.simulator import (
    StrangleTrade,
    compute_stats,
    simulate,
)
from core.options.vrp.strikes import StrangleSelection, StrikeSelection


def _entry_row(strike, opt_type, close, expiry, trade_date):
    return BhavcopyOptionRow(
        trade_date=trade_date, underlying="NIFTY", expiry=expiry, strike=strike,
        option_type=opt_type, open=close, high=close, low=close, close=close,
        settle_price=close, open_interest=500, volume=50, underlying_close=None,
    )


def _selection(entry_date, expiry_date, call_strike, call_premium, put_strike, put_premium) -> StrangleSelection:
    call_row = _entry_row(call_strike, OptionType.CALL, call_premium, expiry_date, entry_date)
    put_row = _entry_row(put_strike, OptionType.PUT, put_premium, expiry_date, entry_date)
    return StrangleSelection(
        entry_date=entry_date, expiry_date=expiry_date, dte=(expiry_date - entry_date).days,
        spot_estimate=20000.0,
        call=StrikeSelection(strike=call_strike, row=call_row, iv=0.15, delta=0.20, method="delta"),
        put=StrikeSelection(strike=put_strike, row=put_row, iv=0.15, delta=-0.20, method="delta"),
    )


# ─── StrangleTrade properties ────────────────────────────────────────────────

class TestStrangleTradeProperties:
    def test_pnl_points_is_credit_minus_settlement_cost(self):
        trade = StrangleTrade(
            entry_date=date(2024, 1, 4), expiry_date=date(2024, 1, 11), dte=7,
            spot_estimate=20000.0,
            call_strike=20200.0, call_entry_premium=80.0, call_delta=0.20, call_method="delta",
            put_strike=19800.0, put_entry_premium=70.0, put_delta=-0.20, put_method="delta",
            call_exit_value=10.0, put_exit_value=5.0,
        )
        # Entry credit 150, cost to settle 15 -> profit 135.
        assert trade.entry_credit == 150.0
        assert trade.pnl_points == pytest.approx(135.0)
        assert trade.pnl_pct_of_credit == pytest.approx(90.0)

    def test_pnl_is_none_when_settlement_missing(self):
        trade = StrangleTrade(
            entry_date=date(2024, 1, 4), expiry_date=date(2024, 1, 11), dte=7,
            spot_estimate=20000.0,
            call_strike=20200.0, call_entry_premium=80.0, call_delta=0.20, call_method="delta",
            put_strike=19800.0, put_entry_premium=70.0, put_delta=-0.20, put_method="delta",
            call_exit_value=None, put_exit_value=5.0,
        )
        assert trade.pnl_points is None
        assert trade.pnl_pct_of_credit is None

    def test_a_losing_trade_is_negative(self):
        # Underlying blew through the short call -- settlement cost exceeds credit.
        trade = StrangleTrade(
            entry_date=date(2024, 1, 4), expiry_date=date(2024, 1, 11), dte=7,
            spot_estimate=20000.0,
            call_strike=20200.0, call_entry_premium=80.0, call_delta=0.20, call_method="delta",
            put_strike=19800.0, put_entry_premium=70.0, put_delta=-0.20, put_method="delta",
            call_exit_value=600.0, put_exit_value=0.0,
        )
        assert trade.pnl_points == pytest.approx(150.0 - 600.0)
        assert trade.pnl_pct_of_credit < 0


# ─── simulate(): real settlement lookup ──────────────────────────────────────

def _expiry_day_row(strike, opt_type, expiry_date, underlying_settlement):
    """Models the real NSE bhavcopy shape on a contract's OWN expiry date:
    settle_price and underlying_close are both overwritten with the shared
    underlying settlement value, identically across every strike/type for
    that expiry -- confirmed by direct inspection (see simulator.py's
    module docstring), not each contract's own intrinsic payout."""
    return BhavcopyOptionRow(
        trade_date=expiry_date, underlying="NIFTY", expiry=expiry_date, strike=strike,
        option_type=opt_type, open=0.0, high=0.0, low=0.0, close=0.0,
        settle_price=underlying_settlement, open_interest=0, volume=0,
        underlying_close=underlying_settlement,
    )


class TestSimulate:
    def test_derives_intrinsic_payout_from_underlying_settlement(self, tmp_path):
        # Underlying settles at 20500: the 20200 short call finishes 300
        # ITM (payout 300), the 19800 short put finishes worthless (payout 0).
        entry_date, expiry_date = date(2024, 1, 4), date(2024, 1, 11)
        sel = _selection(entry_date, expiry_date, 20200.0, 80.0, 19800.0, 70.0)

        from core.options.vrp.bhavcopy import _write_parsed_cache
        expiry_rows = [
            _expiry_day_row(20200.0, OptionType.CALL, expiry_date, 20500.0),
            _expiry_day_row(19800.0, OptionType.PUT, expiry_date, 20500.0),
            # A still-live LATER expiry's row on this same date -- its own
            # settle_price must NOT be picked up as the underlying settlement.
            _entry_row(20200.0, OptionType.CALL, 55.0, date(2024, 1, 18), expiry_date),
        ]
        parsed_dir = tmp_path
        _write_parsed_cache(parsed_dir / f"{expiry_date:%Y%m%d}.csv", expiry_rows)

        trades = simulate([sel], parsed_dir)
        assert len(trades) == 1
        t = trades[0]
        assert t.call_exit_value == pytest.approx(300.0)
        assert t.put_exit_value == pytest.approx(0.0)

    def test_ignores_other_expiries_own_settle_price_that_day(self, tmp_path):
        # If the OTHER expiry's row came first and its settle_price were
        # mistakenly used as "the" underlying settlement, this cycle's own
        # payout would be wrong -- verifies expiry-filtering, not just that
        # SOME number comes back.
        entry_date, expiry_date = date(2024, 1, 4), date(2024, 1, 11)
        sel = _selection(entry_date, expiry_date, 20200.0, 80.0, 19800.0, 70.0)

        from core.options.vrp.bhavcopy import _write_parsed_cache
        expiry_rows = [
            _entry_row(20200.0, OptionType.CALL, 55.0, date(2024, 1, 18), expiry_date),  # other expiry, listed first
            _expiry_day_row(20200.0, OptionType.CALL, expiry_date, 20500.0),
            _expiry_day_row(19800.0, OptionType.PUT, expiry_date, 20500.0),
        ]
        parsed_dir = tmp_path
        _write_parsed_cache(parsed_dir / f"{expiry_date:%Y%m%d}.csv", expiry_rows)

        trades = simulate([sel], parsed_dir)
        assert trades[0].call_exit_value == pytest.approx(300.0)

    def test_missing_expiry_data_yields_none_exit_values(self, tmp_path):
        entry_date, expiry_date = date(2024, 1, 4), date(2024, 1, 11)
        sel = _selection(entry_date, expiry_date, 20200.0, 80.0, 19800.0, 70.0)
        trades = simulate([sel], tmp_path)  # empty cache dir -- no expiry-date file
        assert trades[0].call_exit_value is None
        assert trades[0].put_exit_value is None


# ─── compute_stats ───────────────────────────────────────────────────────────

def _trade(pnl_pct: float) -> StrangleTrade:
    # Build a trade whose pnl_pct_of_credit works out to exactly `pnl_pct`
    # via a credit of 100 and an exit cost of (100 - pnl_pct).
    return StrangleTrade(
        entry_date=date(2024, 1, 4), expiry_date=date(2024, 1, 11), dte=7,
        spot_estimate=20000.0,
        call_strike=20200.0, call_entry_premium=100.0, call_delta=0.20, call_method="delta",
        put_strike=19800.0, put_entry_premium=0.0, put_delta=-0.20, put_method="delta",
        call_exit_value=100.0 - pnl_pct, put_exit_value=0.0,
    )


class TestComputeStats:
    def test_known_win_rate_and_profit_factor(self):
        # Hand-computed: wins [50, 30], losses [-20, -10].
        # win_rate = 2/4 = 0.5; profit_factor = 80/30 = 2.6667
        trades = [_trade(50), _trade(30), _trade(-20), _trade(-10)]
        stats = compute_stats(trades)
        assert stats.n_trades == 4
        assert stats.n_missing_settlement == 0
        assert stats.win_rate == pytest.approx(0.5)
        assert stats.avg_pnl_pct == pytest.approx(12.5)
        assert stats.profit_factor == pytest.approx(80 / 30, rel=1e-3)

    def test_counts_missing_settlement_separately_from_priced_trades(self):
        missing = StrangleTrade(
            entry_date=date(2024, 1, 4), expiry_date=date(2024, 1, 11), dte=7,
            spot_estimate=20000.0,
            call_strike=20200.0, call_entry_premium=100.0, call_delta=0.20, call_method="delta",
            put_strike=19800.0, put_entry_premium=0.0, put_delta=-0.20, put_method="delta",
            call_exit_value=None, put_exit_value=None,
        )
        stats = compute_stats([_trade(50), missing])
        assert stats.n_trades == 1
        assert stats.n_missing_settlement == 1

    def test_empty_trades_yields_zeroed_stats_not_a_crash(self):
        stats = compute_stats([])
        assert stats.n_trades == 0
        assert stats.profit_factor == 0.0
        assert stats.sharpe == 0.0

    def test_all_wins_gives_infinite_profit_factor(self):
        stats = compute_stats([_trade(10), _trade(20)])
        assert stats.profit_factor == float("inf")
