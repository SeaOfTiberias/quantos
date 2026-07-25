"""
Pairs Trading — F&O Futures Cost Model Unit Tests

Covers core/pairs/costs.py's time-varying STT/GST schedules per
docs/PAIRS_TRADING_METHODOLOGY.md's "Cost model" section.
"""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.pairs.costs import (  # noqa: E402
    buy_leg_cost, position_cost, sell_leg_cost, stt_sell_rate,
)


def test_stt_schedule_pre_2024_10_01():
    assert stt_sell_rate(date(2024, 1, 1)) == pytest.approx(0.000125)
    assert stt_sell_rate(date(2024, 9, 30)) == pytest.approx(0.000125)


def test_stt_schedule_2024_10_01_hike():
    assert stt_sell_rate(date(2024, 10, 1)) == pytest.approx(0.0002)
    assert stt_sell_rate(date(2026, 3, 31)) == pytest.approx(0.0002)


def test_stt_schedule_2026_04_01_hike():
    assert stt_sell_rate(date(2026, 4, 1)) == pytest.approx(0.0005)
    assert stt_sell_rate(date(2026, 7, 25)) == pytest.approx(0.0005)


def test_sell_leg_cost_includes_stt_buy_leg_does_not():
    sell = sell_leg_cost(1000.0, lot_size=100, num_lots=1, trade_date=date(2026, 1, 1))
    buy = buy_leg_cost(1000.0, lot_size=100, num_lots=1, trade_date=date(2026, 1, 1))
    assert sell.stt > 0
    assert buy.stt == 0.0
    assert buy.stamp > 0
    assert sell.stamp == 0.0


def test_gst_excludes_sebi_before_cutover():
    d = date(2025, 1, 1)
    leg = buy_leg_cost(1000.0, lot_size=100, num_lots=1, trade_date=d)
    expected_gst = 0.18 * (leg.brokerage + leg.exchange)
    assert leg.gst == pytest.approx(expected_gst)


def test_gst_includes_sebi_after_cutover():
    d = date(2025, 4, 1)
    leg = buy_leg_cost(1000.0, lot_size=100, num_lots=1, trade_date=d)
    expected_gst = 0.18 * (leg.brokerage + leg.exchange + leg.sebi)
    assert leg.gst == pytest.approx(expected_gst)


def test_position_cost_long_is_buy_then_sell():
    cost = position_cost(
        entry_price=1000.0, exit_price=1010.0, lot_size=100, num_lots=1,
        direction="BUY", entry_date=date(2026, 1, 1), exit_date=date(2026, 1, 10),
    )
    manual = (
        buy_leg_cost(1000.0, 100, 1, date(2026, 1, 1)).total
        + sell_leg_cost(1010.0, 100, 1, date(2026, 1, 10)).total
    )
    assert cost == pytest.approx(manual)


def test_position_cost_short_is_sell_then_buy():
    cost = position_cost(
        entry_price=1000.0, exit_price=990.0, lot_size=100, num_lots=1,
        direction="SELL", entry_date=date(2026, 1, 1), exit_date=date(2026, 1, 10),
    )
    manual = (
        sell_leg_cost(1000.0, 100, 1, date(2026, 1, 1)).total
        + buy_leg_cost(990.0, 100, 1, date(2026, 1, 10)).total
    )
    assert cost == pytest.approx(manual)


def test_brokerage_cap_binds_above_threshold():
    # turnover = 1000 * 1000 * 1 = 1,000,000 -> 0.03% = 300, capped at 20
    leg = buy_leg_cost(1000.0, lot_size=1000, num_lots=1, trade_date=date(2026, 1, 1))
    assert leg.brokerage == pytest.approx(20.0)
