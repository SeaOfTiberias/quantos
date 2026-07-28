import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.orb_scalping.costs import (  # noqa: E402
    STRESSED_SLIPPAGE_BPS,
    clean_trade_cost,
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
