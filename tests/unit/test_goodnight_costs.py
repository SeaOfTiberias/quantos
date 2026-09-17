"""Tests for core/goodnight_scalper/costs.py."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.goodnight_scalper.costs import (  # noqa: E402
    GOODNIGHT_MEASURED_SPREAD_PCT,
    GOODNIGHT_STRESSED_SLIPPAGE_BPS,
    clean_trade_cost,
    stressed_trade_cost,
)

ENTRY_DATE = date(2026, 9, 17)


def test_stressed_slippage_bps_matches_measured_spread_conversion():
    # slippage_bps = 50 * round_trip_spread_pct, same convention as
    # candidate 18's costs.py (CostModel charges the bps rate on both legs'
    # own turnover, so round-trip spread_pct = 2 * slippage_bps / 100).
    assert GOODNIGHT_STRESSED_SLIPPAGE_BPS == 50 * GOODNIGHT_MEASURED_SPREAD_PCT


def test_clean_cost_has_zero_slippage_component():
    clean = clean_trade_cost(entry_premium=50.0, exit_premium=55.0, lot_size=100, entry_date=ENTRY_DATE)
    stressed = stressed_trade_cost(entry_premium=50.0, exit_premium=55.0, lot_size=100, entry_date=ENTRY_DATE)
    assert stressed.total > clean.total


def test_costs_scale_with_lot_size():
    small = clean_trade_cost(entry_premium=50.0, exit_premium=55.0, lot_size=50, entry_date=ENTRY_DATE)
    large = clean_trade_cost(entry_premium=50.0, exit_premium=55.0, lot_size=500, entry_date=ENTRY_DATE)
    assert large.total > small.total


def test_stressed_cost_meaningfully_larger_than_clean_given_measured_spread():
    # The whole point of using a real measured 2%+ spread rather than
    # candidate 18's guessed 15bps: the stressed cost should be a
    # materially larger fraction of a typical small-premium trade's
    # notional, not a rounding difference.
    clean = clean_trade_cost(entry_premium=50.0, exit_premium=50.0, lot_size=100, entry_date=ENTRY_DATE)
    stressed = stressed_trade_cost(entry_premium=50.0, exit_premium=50.0, lot_size=100, entry_date=ENTRY_DATE)
    assert stressed.total - clean.total > clean.total
