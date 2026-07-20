"""
agent/rotation_positions.py — JSON persistence for the S8-3 rotation basket,
separate from agent/positions.py's Darvas OpenPosition store.
"""

import pytest

from agent import rotation_positions as rp


@pytest.fixture(autouse=True)
def _isolated_positions_path(tmp_path, monkeypatch):
    monkeypatch.setattr(rp, "ROTATION_POSITIONS_PATH", tmp_path / "rotation_positions.json")


class TestLoadRotationPositions:

    def test_missing_file_returns_empty_dict(self):
        assert rp.load_rotation_positions() == {}

    def test_corrupt_file_returns_empty_dict(self):
        rp.ROTATION_POSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        rp.ROTATION_POSITIONS_PATH.write_text("not json")
        assert rp.load_rotation_positions() == {}


class TestAddAndRemovePosition:

    def test_add_position_persists_and_reloads(self):
        positions = rp.load_rotation_positions()
        rp.add_position(positions, rp.RotationPosition(
            symbol="RELIANCE", quantity=10, entry_price=2500.0,
            entry_date="2026-07-20T00:00:00+00:00",
        ))

        reloaded = rp.load_rotation_positions()
        assert set(reloaded) == {"RELIANCE"}
        assert reloaded["RELIANCE"].quantity == 10
        assert reloaded["RELIANCE"].entry_price == 2500.0

    def test_remove_position(self):
        positions = rp.load_rotation_positions()
        rp.add_position(positions, rp.RotationPosition(
            symbol="TCS", quantity=5, entry_price=3500.0,
            entry_date="2026-07-20T00:00:00+00:00",
        ))

        rp.remove_position(positions, "TCS")

        assert rp.load_rotation_positions() == {}

    def test_remove_nonexistent_symbol_is_a_noop(self):
        positions = rp.load_rotation_positions()
        rp.remove_position(positions, "DOES_NOT_EXIST")
        assert rp.load_rotation_positions() == {}

    def test_multiple_positions_tracked_independently(self):
        positions = rp.load_rotation_positions()
        rp.add_position(positions, rp.RotationPosition(
            symbol="A", quantity=1, entry_price=100.0, entry_date="2026-07-20T00:00:00+00:00",
        ))
        rp.add_position(positions, rp.RotationPosition(
            symbol="B", quantity=2, entry_price=200.0, entry_date="2026-07-20T00:00:00+00:00",
        ))

        reloaded = rp.load_rotation_positions()
        assert set(reloaded) == {"A", "B"}
