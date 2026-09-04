"""
Tests for core/orb_scalping/contract_selection.py -- extracted from the
two existing spread probes, tests mirror
tests/unit/test_probe_orb_scalping_stopout_spreads.py's own coverage of
this logic to prove the extraction didn't change behavior.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.orb_scalping.contract_selection import (  # noqa: E402
    fetch_chain_row_near_strike,
    select_expiry,
)


# ─── select_expiry ───────────────────────────────────────────────────────

def test_select_expiry_skips_expiries_inside_the_dte_floor():
    expiries = [date(2026, 9, 4), date(2026, 9, 11), date(2026, 9, 18)]
    chosen = select_expiry(expiries, today=date(2026, 9, 3), dte_floor_days=2)
    assert chosen == date(2026, 9, 11)  # 9/4 is 1 day out -- inside the floor, rolls past it


def test_select_expiry_rolls_when_nearest_is_inside_the_floor():
    expiries = [date(2026, 9, 4), date(2026, 9, 11)]
    # today=2026-09-03 -> nearest is 1 day out, floor=2 -> must roll to the next one
    chosen = select_expiry(expiries, today=date(2026, 9, 3), dte_floor_days=2)
    assert chosen == date(2026, 9, 11)


def test_select_expiry_no_floor_returns_nearest():
    expiries = [date(2026, 9, 4), date(2026, 9, 11)]
    chosen = select_expiry(expiries, today=date(2026, 9, 3), dte_floor_days=0)
    assert chosen == date(2026, 9, 4)


def test_select_expiry_returns_none_when_every_listed_expiry_is_too_close():
    expiries = [date(2026, 9, 4)]
    chosen = select_expiry(expiries, today=date(2026, 9, 3), dte_floor_days=5)
    assert chosen is None


# ─── fetch_chain_row_near_strike ─────────────────────────────────────────

def _row(strike, option_type, bid=10.0, ask=11.0, ltp=10.5):
    return {"strike_price": strike, "option_type": option_type, "bid": bid, "ask": ask, "ltp": ltp}


class _FakeBroker:
    def __init__(self, rows):
        self._rows = rows

    def get_option_chain(self, underlying, expiry_epoch):
        return {"optionsChain": self._rows}


def test_fetch_chain_row_finds_exact_strike(monkeypatch):
    import core.orb_scalping.contract_selection as mod
    from core.options import fyers_symbol_master as sm
    monkeypatch.setattr(sm, "get_expiry_epoch", lambda *a, **k: 123)
    rows = [_row(24000.0, "CE"), _row(24050.0, "CE"), _row(24050.0, "PE")]
    broker = _FakeBroker(rows)
    row = mod.fetch_chain_row_near_strike(broker, "NIFTY", date(2026, 9, 4), 24050.0, "CE", 50.0)
    assert row["strike_price"] == 24050.0
    assert row["option_type"] == "CE"


def test_fetch_chain_row_returns_none_when_too_far_from_any_listed_strike(monkeypatch):
    from core.options import fyers_symbol_master as sm
    monkeypatch.setattr(sm, "get_expiry_epoch", lambda *a, **k: 123)
    rows = [_row(23000.0, "CE")]  # 1050pt away -- nowhere near a 50pt-interval match
    broker = _FakeBroker(rows)
    row = fetch_chain_row_near_strike(broker, "NIFTY", date(2026, 9, 4), 24050.0, "CE", 50.0)
    assert row is None


def test_fetch_chain_row_returns_none_when_option_type_absent(monkeypatch):
    from core.options import fyers_symbol_master as sm
    monkeypatch.setattr(sm, "get_expiry_epoch", lambda *a, **k: 123)
    rows = [_row(24050.0, "PE")]  # only PE listed, caller wants CE
    broker = _FakeBroker(rows)
    row = fetch_chain_row_near_strike(broker, "NIFTY", date(2026, 9, 4), 24050.0, "CE", 50.0)
    assert row is None
