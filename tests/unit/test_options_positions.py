"""
core/options/positions.py — open options spread tracking, separate from
Darvas/rotation position stores. Exit rule is hold-to-expiry, so this
store's main job is dedup: don't fire a second suggestion for an
underlying that already has one open.
"""

from datetime import date, timedelta

import pytest

from core.options import positions as pos


@pytest.fixture(autouse=True)
def _isolated_path(tmp_path, monkeypatch):
    monkeypatch.setattr(pos, "OPTIONS_POSITIONS_PATH", tmp_path / "options_positions.json")


def _position(underlying="NIFTY", expiry=None, **overrides):
    expiry = expiry or (date.today() + timedelta(days=7)).isoformat()
    data = dict(
        signal_id="SIG-OPT-TEST0001", underlying=underlying, strategy="bull_call_spread",
        expiry=expiry, legs=[{"symbol": "NSE:NIFTY2672124800CE"}], entry_date="2026-07-21T10:00:00",
    )
    data.update(overrides)
    return pos.OptionsPosition(**data)


class TestLoadAndSave:

    def test_load_missing_file_returns_empty(self):
        assert pos.load_positions() == {}

    def test_add_then_load_roundtrips(self):
        positions = pos.load_positions()
        pos.add_position(positions, _position())

        reloaded = pos.load_positions()
        assert "NIFTY" in reloaded
        assert reloaded["NIFTY"].strategy == "bull_call_spread"
        assert reloaded["NIFTY"].legs == [{"symbol": "NSE:NIFTY2672124800CE"}]

    def test_remove_position(self):
        positions = pos.load_positions()
        pos.add_position(positions, _position())
        pos.remove_position(positions, "NIFTY")

        reloaded = pos.load_positions()
        assert "NIFTY" not in reloaded

    def test_corrupt_file_treated_as_empty(self, tmp_path):
        pos.OPTIONS_POSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        pos.OPTIONS_POSITIONS_PATH.write_text("{not json")
        assert pos.load_positions() == {}


class TestHasOpenPosition:

    def test_no_position_returns_false(self):
        assert pos.has_open_position({}, "NIFTY") is False

    def test_future_expiry_counts_as_open(self):
        positions = {"NIFTY": _position(expiry=(date.today() + timedelta(days=5)).isoformat())}
        assert pos.has_open_position(positions, "NIFTY") is True

    def test_today_expiry_still_counts_as_open(self):
        positions = {"NIFTY": _position(expiry=date.today().isoformat())}
        assert pos.has_open_position(positions, "NIFTY") is True

    def test_past_expiry_no_longer_blocks(self):
        positions = {"NIFTY": _position(expiry=(date.today() - timedelta(days=1)).isoformat())}
        assert pos.has_open_position(positions, "NIFTY") is False

    def test_different_underlying_unaffected(self):
        positions = {"NIFTY": _position()}
        assert pos.has_open_position(positions, "SBIN") is False
