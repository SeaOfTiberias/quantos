"""
Tests for core/darvas_atr_stop/live_positions.py -- the Darvas ATR-stop
live position store. Mirrors the style of
tests/unit/test_orb_scalping_live_positions.py where one exists; no
network, no real filesystem paths (every test uses tmp_path).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.darvas_atr_stop.live_positions import (  # noqa: E402
    DarvasOpenPosition,
    add_position,
    get_position,
    load_open_positions,
    remove_position,
    update_trail,
)


def _position(symbol="TEST", **overrides) -> DarvasOpenPosition:
    defaults = dict(
        symbol=symbol, quantity=50, entry_price=140.0, entry_date="2024-01-02",
        box_width_pct=40.0, seen_ceiling=140.0, current_stop=130.0, current_target=180.0,
        entry_order_id="ORD-1", stop_order_id="SL-1",
    )
    defaults.update(overrides)
    return DarvasOpenPosition(**defaults)


def test_load_missing_file_returns_empty_dict(tmp_path):
    assert load_open_positions(path=tmp_path / "nope.json") == {}


def test_add_then_load_round_trips(tmp_path):
    path = tmp_path / "positions.json"
    positions = {}
    add_position(positions, _position(), path=path)

    reloaded = load_open_positions(path=path)
    assert reloaded.keys() == {"TEST"}
    assert reloaded["TEST"].current_stop == 130.0
    assert reloaded["TEST"].stop_order_id == "SL-1"


def test_get_position_returns_none_when_absent(tmp_path):
    assert get_position({}, "TEST") is None


def test_add_position_is_keyed_by_symbol_alone(tmp_path):
    """Unlike ORB's underlying+date key, a Darvas position is held for
    days-to-weeks -- there is only ever one open position per symbol."""
    path = tmp_path / "positions.json"
    positions = {}
    add_position(positions, _position(symbol="TEST", entry_date="2024-01-02"), path=path)
    add_position(positions, _position(symbol="TEST", entry_date="2024-06-01", current_stop=999.0), path=path)
    assert len(positions) == 1
    assert positions["TEST"].current_stop == 999.0


def test_update_trail_moves_stop_target_and_seen_ceiling(tmp_path):
    path = tmp_path / "positions.json"
    positions = {"TEST": _position()}
    update_trail(positions, "TEST", current_stop=150.0, current_target=210.0,
                 seen_ceiling=170.0, path=path)

    assert positions["TEST"].current_stop == 150.0
    assert positions["TEST"].current_target == 210.0
    assert positions["TEST"].seen_ceiling == 170.0
    reloaded = load_open_positions(path=path)
    assert reloaded["TEST"].current_stop == 150.0


def test_update_trail_partial_fields_leaves_others_untouched(tmp_path):
    path = tmp_path / "positions.json"
    positions = {"TEST": _position()}
    update_trail(positions, "TEST", current_stop=150.0, path=path)

    assert positions["TEST"].current_stop == 150.0
    assert positions["TEST"].current_target == 180.0   # unchanged
    assert positions["TEST"].seen_ceiling == 140.0      # unchanged


def test_update_trail_on_missing_symbol_is_a_no_op(tmp_path):
    path = tmp_path / "positions.json"
    positions = {}
    update_trail(positions, "TEST", current_stop=150.0, path=path)
    assert positions == {}
    assert not path.exists()


def test_remove_position_deletes_and_persists(tmp_path):
    path = tmp_path / "positions.json"
    positions = {"TEST": _position()}
    add_position(positions, positions["TEST"], path=path)   # persist the initial state
    remove_position(positions, "TEST", path=path)

    assert positions == {}
    assert load_open_positions(path=path) == {}


def test_remove_missing_symbol_is_a_no_op(tmp_path):
    path = tmp_path / "positions.json"
    positions = {}
    remove_position(positions, "TEST", path=path)
    assert positions == {}


def test_corrupt_file_degrades_to_empty(tmp_path):
    path = tmp_path / "positions.json"
    path.write_text("{not valid json")
    assert load_open_positions(path=path) == {}
