"""
Tests for core/orb_scalping/live_positions.py -- the ORB-specific
position-state JSON store (a separate sibling of agent/positions.py's
OpenPosition, see this module's docstring for why).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.orb_scalping.live_positions import (  # noqa: E402
    OrbOpenPosition,
    add_position,
    get_position,
    load_open_positions,
    remove_position,
    update_stops,
)


def _make_position(underlying="NIFTY", trade_date="2026-09-04") -> OrbOpenPosition:
    return OrbOpenPosition(
        underlying=underlying, option_symbol="NSE:NIFTY2672129450CE",
        direction="CALL", option_type="CE", quantity=65, strike=24050.0,
        expiry="2026-09-29", dte_floor_rolled=False,
        entry_index_level=24045.0, entry_premium=50.0,
        entry_timestamp="2026-09-04T03:50:00+00:00",
        current_index_stop=23999.0, current_premium_stop=37.5, armed=False,
        entry_order_id="ORD-1", stop_order_id="SL-1", trade_date=trade_date,
    )


def test_add_and_get_position_round_trips(tmp_path, monkeypatch):
    import core.orb_scalping.live_positions as mod
    monkeypatch.setattr(mod, "ORB_OPEN_POSITIONS_PATH", tmp_path / "orb_open_positions.json")

    positions = {}
    add_position(positions, _make_position())
    fetched = get_position(positions, "NIFTY", "2026-09-04")
    assert fetched is not None
    assert fetched.option_symbol == "NSE:NIFTY2672129450CE"


def test_persists_to_disk_and_reloads(tmp_path, monkeypatch):
    import core.orb_scalping.live_positions as mod
    path = tmp_path / "orb_open_positions.json"
    monkeypatch.setattr(mod, "ORB_OPEN_POSITIONS_PATH", path)

    add_position({}, _make_position())
    assert path.exists()

    reloaded = load_open_positions()
    fetched = get_position(reloaded, "NIFTY", "2026-09-04")
    assert fetched is not None
    assert fetched.entry_premium == 50.0
    assert fetched.armed is False


def test_underlyings_and_dates_are_independent_keys(tmp_path, monkeypatch):
    import core.orb_scalping.live_positions as mod
    monkeypatch.setattr(mod, "ORB_OPEN_POSITIONS_PATH", tmp_path / "orb_open_positions.json")

    positions = {}
    add_position(positions, _make_position("NIFTY", "2026-09-04"))
    add_position(positions, _make_position("BANKNIFTY", "2026-09-04"))
    assert get_position(positions, "NIFTY", "2026-09-04") is not None
    assert get_position(positions, "BANKNIFTY", "2026-09-04") is not None
    assert get_position(positions, "NIFTY", "2026-09-05") is None


def test_update_stops_mutates_and_persists(tmp_path, monkeypatch):
    import core.orb_scalping.live_positions as mod
    monkeypatch.setattr(mod, "ORB_OPEN_POSITIONS_PATH", tmp_path / "orb_open_positions.json")

    positions = {}
    add_position(positions, _make_position())
    update_stops(positions, "NIFTY", "2026-09-04",
                  current_index_stop=24000.0, current_premium_stop=40.0, armed=True)

    fetched = get_position(positions, "NIFTY", "2026-09-04")
    assert fetched.current_index_stop == 24000.0
    assert fetched.current_premium_stop == 40.0
    assert fetched.armed is True

    reloaded = load_open_positions()
    assert get_position(reloaded, "NIFTY", "2026-09-04").armed is True


def test_update_stops_on_unknown_key_is_a_no_op(tmp_path, monkeypatch):
    import core.orb_scalping.live_positions as mod
    monkeypatch.setattr(mod, "ORB_OPEN_POSITIONS_PATH", tmp_path / "orb_open_positions.json")

    positions = {}
    update_stops(positions, "NIFTY", "2026-09-04", current_index_stop=24000.0)
    assert positions == {}


def test_remove_position(tmp_path, monkeypatch):
    import core.orb_scalping.live_positions as mod
    monkeypatch.setattr(mod, "ORB_OPEN_POSITIONS_PATH", tmp_path / "orb_open_positions.json")

    positions = {}
    add_position(positions, _make_position())
    remove_position(positions, "NIFTY", "2026-09-04")
    assert get_position(positions, "NIFTY", "2026-09-04") is None
    assert load_open_positions() == {}


def test_load_returns_empty_dict_when_file_missing(tmp_path, monkeypatch):
    import core.orb_scalping.live_positions as mod
    monkeypatch.setattr(mod, "ORB_OPEN_POSITIONS_PATH", tmp_path / "does_not_exist.json")
    assert load_open_positions() == {}


def test_load_returns_empty_dict_on_corrupt_json(tmp_path, monkeypatch):
    import core.orb_scalping.live_positions as mod
    path = tmp_path / "orb_open_positions.json"
    path.write_text("{not valid json")
    monkeypatch.setattr(mod, "ORB_OPEN_POSITIONS_PATH", path)
    assert load_open_positions() == {}
