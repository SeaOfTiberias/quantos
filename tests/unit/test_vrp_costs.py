"""
VRP Phase 4 — Options Transaction Cost Model — Unit Tests
"""

from datetime import date

import pytest

from core.options.vrp.costs import (
    entry_leg_cost,
    exit_leg_cost,
    net_pnl_points,
    net_pnl_pct_of_credit,
    stt_exercise_rate,
    stt_sell_rate,
    trade_cost_points,
)
from core.options.vrp.simulator import StrangleTrade


# ─── Rate schedules ───────────────────────────────────────────────────────────

class TestSttSellRate:
    def test_pre_2024_10_01_rate(self):
        assert stt_sell_rate(date(2023, 7, 24)) == pytest.approx(0.000625)
        assert stt_sell_rate(date(2024, 9, 30)) == pytest.approx(0.000625)

    def test_2024_10_01_hike(self):
        assert stt_sell_rate(date(2024, 10, 1)) == pytest.approx(0.001)
        assert stt_sell_rate(date(2026, 3, 31)) == pytest.approx(0.001)

    def test_2026_04_01_hike(self):
        assert stt_sell_rate(date(2026, 4, 1)) == pytest.approx(0.0015)
        assert stt_sell_rate(date(2026, 7, 22)) == pytest.approx(0.0015)


class TestSttExerciseRate:
    def test_stable_across_the_2024_10_01_sell_side_hike(self):
        # Exercise STT was untouched by the 2024-10-01 revision (only the
        # sell-side rate changed then) -- same rate on both sides of it.
        assert stt_exercise_rate(date(2024, 9, 30)) == pytest.approx(0.00125)
        assert stt_exercise_rate(date(2024, 10, 1)) == pytest.approx(0.00125)

    def test_2026_04_01_hike(self):
        assert stt_exercise_rate(date(2026, 4, 1)) == pytest.approx(0.0015)


# ─── entry_leg_cost / exit_leg_cost ──────────────────────────────────────────

class TestEntryLegCost:
    def test_known_breakdown_pre_hike(self):
        # 100-point premium, entry pre-2024-10-01 (STT 0.0625%).
        c = entry_leg_cost(100.0, date(2024, 1, 4))
        assert c.brokerage == pytest.approx(100.0 * 0.0003)
        assert c.stt == pytest.approx(100.0 * 0.000625)
        assert c.exchange == pytest.approx(100.0 * 0.0003503)
        assert c.sebi == pytest.approx(100.0 * 0.000001)
        assert c.gst == pytest.approx(0.18 * (c.brokerage + c.exchange + c.sebi))
        assert c.total == pytest.approx(c.brokerage + c.stt + c.exchange + c.sebi + c.gst)

    def test_uses_post_hike_stt_after_2024_10_01(self):
        c_before = entry_leg_cost(100.0, date(2024, 9, 30))
        c_after = entry_leg_cost(100.0, date(2024, 10, 1))
        assert c_after.stt > c_before.stt
        assert c_after.stt == pytest.approx(100.0 * 0.001)


class TestExitLegCost:
    def test_zero_cost_when_otm(self):
        c = exit_leg_cost(0.0, date(2024, 1, 11))
        assert c.total == 0.0
        assert c.brokerage == 0.0 and c.exchange == 0.0 and c.sebi == 0.0 and c.gst == 0.0

    def test_only_exercise_stt_applies_when_itm(self):
        c = exit_leg_cost(50.0, date(2024, 1, 11))
        assert c.stt == pytest.approx(50.0 * 0.00125)
        assert c.brokerage == 0.0 and c.exchange == 0.0 and c.sebi == 0.0 and c.gst == 0.0
        assert c.total == pytest.approx(c.stt)


# ─── net_pnl_points / net_pnl_pct_of_credit / trade_cost_points ─────────────

def _trade(call_exit, put_exit, entry_date=date(2024, 1, 4), expiry_date=date(2024, 1, 11)):
    return StrangleTrade(
        entry_date=entry_date, expiry_date=expiry_date, dte=(expiry_date - entry_date).days,
        spot_estimate=20000.0,
        call_strike=20200.0, call_entry_premium=80.0, call_delta=0.20, call_method="delta",
        put_strike=19800.0, put_entry_premium=70.0, put_delta=-0.20, put_method="delta",
        call_exit_value=call_exit, put_exit_value=put_exit,
    )


class TestNetPnl:
    def test_both_legs_expire_worthless_costs_only_entry_side(self):
        trade = _trade(0.0, 0.0)
        cost = trade_cost_points(trade)
        # Entry side only: two legs' entry_leg_cost, no exit cost at all.
        expected = entry_leg_cost(80.0, trade.entry_date).total + entry_leg_cost(70.0, trade.entry_date).total
        assert cost == pytest.approx(expected)
        assert net_pnl_points(trade) == pytest.approx(trade.pnl_points - cost)

    def test_one_leg_itm_adds_exercise_cost_on_top(self):
        trade = _trade(120.0, 0.0)  # call breached, finishes 120 ITM
        cost = trade_cost_points(trade)
        expected = (
            entry_leg_cost(80.0, trade.entry_date).total + entry_leg_cost(70.0, trade.entry_date).total
            + exit_leg_cost(120.0, trade.expiry_date).total + exit_leg_cost(0.0, trade.expiry_date).total
        )
        assert cost == pytest.approx(expected)

    def test_net_pnl_is_strictly_less_than_gross(self):
        trade = _trade(0.0, 0.0)
        assert net_pnl_points(trade) < trade.pnl_points

    def test_none_when_trade_unpriced(self):
        trade = _trade(None, 5.0)
        assert trade_cost_points(trade) is None
        assert net_pnl_points(trade) is None
        assert net_pnl_pct_of_credit(trade) is None

    def test_net_pct_of_credit_matches_points_conversion(self):
        trade = _trade(10.0, 0.0)
        net_pts = net_pnl_points(trade)
        assert net_pnl_pct_of_credit(trade) == pytest.approx(net_pts / trade.entry_credit * 100.0)
