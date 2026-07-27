"""
10:10 Breakout — Cost Model Unit Tests

Covers core/breakout1010/costs.py per docs/BREAKOUT_1010_METHODOLOGY.md's
"Cost model" section: composing core/risk/costs.py's CostModel mechanics
with core/options/vrp/costs.py's time-varying F&O-options rate schedule,
rather than the wrong (cash-equity) default rates.
"""

import math
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.breakout1010.costs import trade_cost  # noqa: E402
from core.options.vrp.costs import EXCHANGE_TXN_PCT, stt_sell_rate  # noqa: E402
from core.risk.costs import CostModel  # noqa: E402


def _round_to_rupee(amount: float) -> float:
    """Mirrors core/risk/costs.py's private _round_to_rupee (round-half-up,
    NOT Python's built-in round()'s banker's rounding) -- STT/stamp are
    displayed to the nearest whole rupee on a real contract note."""
    return float(math.floor(amount + 0.5))


def test_trade_cost_uses_options_stt_rate_not_equity_default():
    entry_date = date(2026, 1, 15)  # in the 0.1% STT-sell era (2024-10-01 .. 2026-03-31)
    breakdown = trade_cost(entry_premium=300.0, exit_premium=350.0, lot_size=30, entry_date=entry_date)

    equity_default = CostModel().round_trip(buy_price=300.0, sell_price=350.0, quantity=30)
    assert breakdown.stt != equity_default.stt   # options STT (0.1%) != equity STT (0.025%)

    expected_sell_turnover = 350.0 * 30
    expected_stt = _round_to_rupee(stt_sell_rate(entry_date) * expected_sell_turnover)
    assert breakdown.stt == expected_stt


def test_trade_cost_picks_up_the_2026_04_01_stt_hike():
    pre_hike = trade_cost(entry_premium=300.0, exit_premium=350.0, lot_size=30, entry_date=date(2026, 3, 31))
    post_hike = trade_cost(entry_premium=300.0, exit_premium=350.0, lot_size=30, entry_date=date(2026, 4, 1))
    assert post_hike.stt > pre_hike.stt


def test_trade_cost_uses_fo_exchange_rate():
    breakdown = trade_cost(entry_premium=100.0, exit_premium=100.0, lot_size=30, entry_date=date(2026, 1, 1))
    buy_turnover = 100.0 * 30
    sell_turnover = 100.0 * 30
    expected_exchange = EXCHANGE_TXN_PCT * (buy_turnover + sell_turnover)
    assert breakdown.exchange_txn == expected_exchange


def test_trade_cost_is_positive_for_a_normal_round_trip():
    breakdown = trade_cost(entry_premium=150.0, exit_premium=180.0, lot_size=30, entry_date=date(2025, 6, 1))
    assert breakdown.total > 0
