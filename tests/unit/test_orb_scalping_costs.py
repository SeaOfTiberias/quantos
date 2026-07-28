import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.orb_scalping.costs import (  # noqa: E402
    HARSH_NEXT_WEEK_SLIPPAGE_BPS,
    STRESSED_SLIPPAGE_BPS,
    clean_trade_cost,
    harsh_trade_cost,
    stressed_trade_cost,
)


def test_stressed_cost_exceeds_clean_cost():
    entry_date = date(2026, 1, 15)
    clean = clean_trade_cost(entry_premium=100.0, exit_premium=120.0, lot_size=65, entry_date=entry_date)
    stressed = stressed_trade_cost(entry_premium=100.0, exit_premium=120.0, lot_size=65, entry_date=entry_date)
    assert stressed.total > clean.total
    assert clean.slippage == 0.0
    assert stressed.slippage > 0.0


def test_stressed_slippage_matches_15bps_per_leg():
    entry_date = date(2026, 1, 15)
    lot_size = 65
    entry_premium, exit_premium = 100.0, 120.0
    stressed = stressed_trade_cost(entry_premium, exit_premium, lot_size, entry_date)
    expected_slippage = (
        (entry_premium * lot_size + exit_premium * lot_size) * STRESSED_SLIPPAGE_BPS / 10_000.0
    )
    assert round(stressed.slippage, 6) == round(expected_slippage, 6)


def test_clean_cost_rate_schedule_matches_entry_date_not_hardcoded():
    # STT rate is time-varying (candidate 15's sourcing) -- a trade dated
    # before vs after a rate-change boundary must produce a different STT
    # component, confirming the entry_date is actually threaded through.
    before = clean_trade_cost(100.0, 120.0, 65, date(2024, 9, 30))
    after = clean_trade_cost(100.0, 120.0, 65, date(2024, 10, 1))
    assert before.stt != after.stt


# ─── Harsh (post-hoc Fable stress test) ───────────────────────────────────

def test_harsh_forces_flat_brokerage_even_on_small_premiums():
    # A small ATM premium * lot_size stays well under the turnover needed
    # for CostModel's default %-capped brokerage to hit the Rs20 flat cap --
    # harsh mode must force it there anyway.
    entry_date = date(2026, 1, 15)
    clean = clean_trade_cost(entry_premium=150.0, exit_premium=160.0, lot_size=65, entry_date=entry_date)
    harsh = harsh_trade_cost(entry_premium=150.0, exit_premium=160.0, lot_size=65, entry_date=entry_date)
    assert clean.brokerage < 20.0  # the gap Fable flagged: %-cap never binds at this size
    assert harsh.brokerage == 40.0  # Rs20 flat, both legs


def test_harsh_charges_more_slippage_on_next_week_tier():
    entry_date = date(2026, 1, 15)
    front = harsh_trade_cost(100.0, 120.0, 65, entry_date, liquidity_tier="front_week")
    next_week = harsh_trade_cost(100.0, 120.0, 65, entry_date, liquidity_tier="next_week")
    assert next_week.slippage > front.slippage
    assert next_week.total > front.total


def test_harsh_next_week_slippage_matches_documented_rate():
    entry_date = date(2026, 1, 15)
    lot_size = 65
    entry_premium, exit_premium = 100.0, 120.0
    result = harsh_trade_cost(entry_premium, exit_premium, lot_size, entry_date, liquidity_tier="next_week")
    expected_slippage = (
        (entry_premium * lot_size + exit_premium * lot_size) * HARSH_NEXT_WEEK_SLIPPAGE_BPS / 10_000.0
    )
    assert round(result.slippage, 6) == round(expected_slippage, 6)


def test_harsh_rejects_unknown_liquidity_tier():
    import pytest
    with pytest.raises(ValueError):
        harsh_trade_cost(100.0, 120.0, 65, date(2026, 1, 15), liquidity_tier="mid_week")
