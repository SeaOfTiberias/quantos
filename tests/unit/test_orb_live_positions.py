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
    has_traded_today,
    load_open_positions,
    load_traded_today,
    mark_traded_today,
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


# ─── "already traded today" (one trade per day, first breakout only) ───────

def test_mark_and_has_traded_today_round_trip(tmp_path, monkeypatch):
    import core.orb_scalping.live_positions as mod
    monkeypatch.setattr(mod, "ORB_TRADED_TODAY_PATH", tmp_path / "orb_traded_today.json")

    traded = set()
    assert has_traded_today(traded, "NIFTY", "2026-09-11") is False
    mark_traded_today(traded, "NIFTY", "2026-09-11")
    assert has_traded_today(traded, "NIFTY", "2026-09-11") is True


def test_traded_today_underlyings_and_dates_are_independent(tmp_path, monkeypatch):
    import core.orb_scalping.live_positions as mod
    monkeypatch.setattr(mod, "ORB_TRADED_TODAY_PATH", tmp_path / "orb_traded_today.json")

    traded = set()
    mark_traded_today(traded, "NIFTY", "2026-09-11")
    assert has_traded_today(traded, "BANKNIFTY", "2026-09-11") is False
    assert has_traded_today(traded, "NIFTY", "2026-09-12") is False


def test_traded_today_persists_to_disk_and_reloads(tmp_path, monkeypatch):
    import core.orb_scalping.live_positions as mod
    path = tmp_path / "orb_traded_today.json"
    monkeypatch.setattr(mod, "ORB_TRADED_TODAY_PATH", path)

    mark_traded_today(set(), "NIFTY", "2026-09-11")
    assert path.exists()

    reloaded = load_traded_today()
    assert has_traded_today(reloaded, "NIFTY", "2026-09-11") is True


def test_load_traded_today_returns_empty_set_when_file_missing(tmp_path, monkeypatch):
    import core.orb_scalping.live_positions as mod
    monkeypatch.setattr(mod, "ORB_TRADED_TODAY_PATH", tmp_path / "does_not_exist.json")
    assert load_traded_today() == set()


def test_load_traded_today_returns_empty_set_on_corrupt_json(tmp_path, monkeypatch):
    import core.orb_scalping.live_positions as mod
    path = tmp_path / "orb_traded_today.json"
    path.write_text("{not valid json")
    monkeypatch.setattr(mod, "ORB_TRADED_TODAY_PATH", path)
    assert load_traded_today() == set()


# ─── explicit path override (docs/ORB_ENTRY_FILTER_METHODOLOGY.md's
# filtered sibling needs its own store, separate from the module-level
# default the unfiltered script keeps using unchanged) ─────────────────────

def test_explicit_path_is_independent_of_the_module_default(tmp_path, monkeypatch):
    import core.orb_scalping.live_positions as mod
    default_path = tmp_path / "default.json"
    filtered_path = tmp_path / "filtered.json"
    monkeypatch.setattr(mod, "ORB_OPEN_POSITIONS_PATH", default_path)

    default_positions = {}
    add_position(default_positions, _make_position("NIFTY", "2026-09-04"))  # no path -> default

    filtered_positions = {}
    add_position(filtered_positions, _make_position("BANKNIFTY", "2026-09-04"), path=filtered_path)

    assert default_path.exists() and filtered_path.exists()
    # Each store only knows about its own write.
    assert get_position(load_open_positions(), "BANKNIFTY", "2026-09-04") is None
    assert get_position(load_open_positions(path=filtered_path), "NIFTY", "2026-09-04") is None
    assert get_position(load_open_positions(path=filtered_path), "BANKNIFTY", "2026-09-04") is not None


def test_update_stops_and_remove_position_respect_the_explicit_path(tmp_path):
    filtered_path = tmp_path / "filtered.json"
    positions = {}
    add_position(positions, _make_position(), path=filtered_path)
    update_stops(positions, "NIFTY", "2026-09-04", current_index_stop=24000.0, path=filtered_path)
    assert load_open_positions(path=filtered_path)["NIFTY:2026-09-04"].current_index_stop == 24000.0

    remove_position(positions, "NIFTY", "2026-09-04", path=filtered_path)
    assert load_open_positions(path=filtered_path) == {}


def test_traded_today_explicit_path_is_independent_of_the_module_default(tmp_path, monkeypatch):
    import core.orb_scalping.live_positions as mod
    monkeypatch.setattr(mod, "ORB_TRADED_TODAY_PATH", tmp_path / "default.json")
    filtered_path = tmp_path / "filtered.json"

    mark_traded_today(set(), "NIFTY", "2026-09-11", path=filtered_path)
    assert load_traded_today() == set()
    assert load_traded_today(path=filtered_path) == {"NIFTY:2026-09-11"}
