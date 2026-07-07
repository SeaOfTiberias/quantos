"""
Stage A Discovery Watchlist Store — Unit Tests
──────────────────────────────────────────────────
Persistent watchlist state machine ported from DarvasTrader: protects
open-position entries from being overwritten by a fresh scan, expires
stale non-actionable ones, and flags "add to winner" candidates.
"""

from datetime import date, timedelta

import pytest

import agent.discovery_watchlist as dw
from core.darvas.weekly_discovery import DiscoveryResult


@pytest.fixture(autouse=True)
def _isolated_watchlist_path(tmp_path, monkeypatch):
    monkeypatch.setattr(dw, "WATCHLIST_PATH", tmp_path / "discovery_watchlist.json")


def _result(symbol="RELIANCE", status="APPROACHING", alert_tier="HOT",
            box_ceiling=2950.0, box_floor=2870.0) -> DiscoveryResult:
    return DiscoveryResult(
        symbol=symbol, status=status, alert_tier=alert_tier,
        close=2940.0, box_ceiling=box_ceiling, box_floor=box_floor,
        box_width_pct=2.7, dist_to_ceil=0.3, sl_price=2891.0,
        mm_target=3030.0, rr_ratio=2.1, vol_ratio=1.8, days_in_box=6,
    )


class TestLoadSave:

    def test_load_missing_file_returns_empty(self):
        assert dw.load_watchlist() == {}

    def test_merge_persists_across_load(self):
        watchlist = {}
        dw.merge_scan_results(watchlist, [_result()])
        reloaded = dw.load_watchlist()
        assert "RELIANCE" in reloaded
        assert reloaded["RELIANCE"].status == "APPROACHING"


class TestMergeScanResults:

    def test_approaching_added_when_new(self):
        watchlist = {}
        dw.merge_scan_results(watchlist, [_result(status="APPROACHING")])
        assert watchlist["RELIANCE"].status == "APPROACHING"
        assert watchlist["RELIANCE"].alert_tier == "HOT"

    def test_fresh_breakout_graduates_out(self):
        watchlist = {}
        dw.merge_scan_results(watchlist, [_result(status="APPROACHING")])
        assert "RELIANCE" in watchlist
        dw.merge_scan_results(watchlist, [_result(status="FRESH BREAKOUT")])
        assert "RELIANCE" not in watchlist

    def test_box_forming_only_updates_existing(self):
        watchlist = {}
        dw.merge_scan_results(watchlist, [_result(status="BOX FORMING", alert_tier="")])
        assert "RELIANCE" not in watchlist   # never added fresh

        dw.merge_scan_results(watchlist, [_result(status="APPROACHING")])
        dw.merge_scan_results(watchlist, [_result(status="BOX FORMING", alert_tier="")])
        assert watchlist["RELIANCE"].status == "BOX FORMING"

    def test_protected_position_not_overwritten(self):
        watchlist = {}
        dw.mark_position_open(watchlist, "RELIANCE", entry_price=2900.0, quantity=10)
        dw.merge_scan_results(watchlist, [_result(status="WATCHING")])
        assert watchlist["RELIANCE"].status == "POSITION_OPEN"
        assert watchlist["RELIANCE"].entry_price == 2900.0

    def test_stale_entries_expire(self):
        watchlist = {}
        dw.merge_scan_results(watchlist, [_result(status="WATCHING")])
        watchlist["RELIANCE"].date_added = (date.today() - timedelta(days=100)).isoformat()
        dw.merge_scan_results(watchlist, [], watchlist_days=45)
        assert "RELIANCE" not in watchlist

    def test_protected_entries_never_expire(self):
        watchlist = {}
        dw.mark_position_open(watchlist, "RELIANCE", entry_price=2900.0, quantity=10)
        watchlist["RELIANCE"].date_added = (date.today() - timedelta(days=1000)).isoformat()
        dw.merge_scan_results(watchlist, [], watchlist_days=45)
        assert "RELIANCE" in watchlist


class TestPositionLifecycle:

    def test_mark_and_clear_position(self):
        watchlist = {}
        dw.mark_position_open(watchlist, "TCS", entry_price=3800.0, quantity=5)
        assert watchlist["TCS"].status == "POSITION_OPEN"

        dw.clear_position(watchlist, "TCS")
        assert "TCS" not in watchlist

    def test_clear_position_is_a_noop_if_absent(self):
        watchlist = {}
        dw.clear_position(watchlist, "TCS")   # should not raise
        assert watchlist == {}


class TestGranularScanCandidates:

    def test_only_approaching_hot_or_warm_selected(self):
        """WATCHING is excluded even for an otherwise-close setup (it
        doubles as analyse_symbol's catch-all for "confirmed box, far
        from ceiling, no volume" — see GRANULAR_SCAN_STATUSES) and
        APPROACHING/WATCH-tier is excluded as still too far out; only
        APPROACHING + HOT/WARM qualifies."""
        watchlist = {}
        dw.merge_scan_results(watchlist, [
            _result(symbol="A", status="APPROACHING", alert_tier="HOT"),
            _result(symbol="B", status="APPROACHING", alert_tier="WARM"),
            _result(symbol="C", status="APPROACHING", alert_tier="WATCH"),
            _result(symbol="E", status="WATCHING", alert_tier="HOT"),
        ])
        dw.merge_scan_results(watchlist, [_result(symbol="F", status="BOX FORMING", alert_tier="")])
        dw.mark_position_open(watchlist, "D", entry_price=100.0, quantity=1)

        candidates = set(dw.candidates_for_granular_scan(watchlist))
        assert candidates == {"A", "B"}


class TestAddCandidates:

    def test_flags_new_higher_box_above_open_position(self):
        watchlist = {}
        dw.mark_position_open(watchlist, "RELIANCE", entry_price=2800.0, quantity=10)

        results = [_result(symbol="RELIANCE", status="APPROACHING", box_ceiling=2950.0)]
        candidates = dw.check_add_candidates(watchlist, results)

        assert len(candidates) == 1
        c = candidates[0]
        assert c["symbol"] == "RELIANCE"
        assert c["orig_entry"] == 2800.0
        assert c["new_ceiling"] == 2950.0
        assert c["gain_pct"] == round((2950.0 - 2800.0) / 2800.0 * 100, 1)

    def test_no_candidate_when_new_box_not_above_entry(self):
        watchlist = {}
        dw.mark_position_open(watchlist, "RELIANCE", entry_price=3000.0, quantity=10)

        results = [_result(symbol="RELIANCE", status="APPROACHING", box_ceiling=2950.0)]
        assert dw.check_add_candidates(watchlist, results) == []

    def test_no_candidate_without_open_positions(self):
        watchlist = {}
        dw.merge_scan_results(watchlist, [_result(status="APPROACHING")])
        results = [_result(status="APPROACHING", box_ceiling=3100.0)]
        assert dw.check_add_candidates(watchlist, results) == []


class TestFiredTracking:

    def test_mark_and_check_fired_today(self):
        watchlist = {}
        dw.merge_scan_results(watchlist, [_result(status="APPROACHING")])
        assert dw.already_fired_today(watchlist, "RELIANCE") is False

        dw.mark_fired(watchlist, "RELIANCE")
        assert dw.already_fired_today(watchlist, "RELIANCE") is True

    def test_unknown_symbol_not_fired(self):
        assert dw.already_fired_today({}, "GHOST") is False
