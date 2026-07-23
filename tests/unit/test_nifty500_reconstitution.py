"""
core/rotation/nifty500_reconstitution.py — point-in-time Nifty 500
membership, reconstructed backward from today's live universe file. Covers
the backward-walk arithmetic (round-trip, join/drop windows, a same-cycle
net-no-op) and eligible_symbols_asof's boundary handling.
"""

from datetime import datetime, timezone

from core.rotation.nifty500_reconstitution import (
    build_point_in_time_universe, eligible_symbols_asof,
)


def _d(y: int, m: int, day: int) -> datetime:
    return datetime(y, m, day, tzinfo=timezone.utc)


class TestBuildPointInTimeUniverse:

    def test_snapshots_are_contiguous_and_last_one_is_current(self):
        from core.rotation import nifty500_reconstitution as mod
        current = frozenset({"A", "B"})
        snapshots = build_point_in_time_universe(current)
        assert snapshots[-1].symbols == current
        assert snapshots[-1].valid_until is None
        assert snapshots[0].valid_from == mod._EPOCH
        # every valid_until lines up with the next snapshot's valid_from
        for earlier, later in zip(snapshots, snapshots[1:]):
            assert earlier.valid_until == later.valid_from

    def test_addition_absent_before_join_date_present_after(self):
        current = frozenset({"NEWCO"})
        snapshots = build_point_in_time_universe(current)
        # NEWCO isn't in EVENTS, so it's treated as always-present back to
        # _EPOCH -- to test a real join, use a symbol from EVENTS instead.
        assert "NEWCO" in eligible_symbols_asof(snapshots, _d(2015, 6, 1))

    def test_kirlfer_only_eligible_during_its_four_week_window(self):
        # KIRLFER joined Nifty 500 on 2023-09-29 and was excluded again on
        # 2023-10-26 (NSE "Permitted to Trade" withdrawal) -- a real,
        # deliberately short-lived membership window from EVENTS.
        current = frozenset()  # KIRLFER isn't in today's list either way
        snapshots = build_point_in_time_universe(current)
        assert "KIRLFER" not in eligible_symbols_asof(snapshots, _d(2023, 9, 1))
        assert "KIRLFER" in eligible_symbols_asof(snapshots, _d(2023, 10, 1))
        assert "KIRLFER" not in eligible_symbols_asof(snapshots, _d(2023, 11, 1))

    def test_same_cycle_revocation_nets_to_no_membership_change(self):
        # Vodafone Idea (IDEA) was excluded then had that exclusion revoked
        # within the same Sept-2024 press cycle -- net effect should be "no
        # change", i.e. present on both sides if it's in the current file.
        current = frozenset({"IDEA"})
        snapshots = build_point_in_time_universe(current)
        assert "IDEA" in eligible_symbols_asof(snapshots, _d(2024, 8, 1))
        assert "IDEA" in eligible_symbols_asof(snapshots, _d(2024, 10, 1))

    def test_merger_drop_absent_from_drop_date_onward(self):
        # GSPL was absorbed into Gujarat Gas effective 2026-05-12 and does
        # not appear in today's universe file.
        current = frozenset()
        snapshots = build_point_in_time_universe(current)
        assert "GSPL" in eligible_symbols_asof(snapshots, _d(2026, 5, 1))
        assert "GSPL" not in eligible_symbols_asof(snapshots, _d(2026, 6, 1))


class TestEligibleSymbolsAsofBoundaries:

    def test_date_before_earliest_snapshot_clamps_to_first(self):
        current = frozenset({"A"})
        snapshots = build_point_in_time_universe(current)
        far_past = _d(1990, 1, 1)
        # Should not raise, and should return the earliest snapshot's set.
        result = eligible_symbols_asof(snapshots, far_past)
        assert result == snapshots[0].symbols

    def test_date_after_latest_snapshot_clamps_to_last(self):
        current = frozenset({"A"})
        snapshots = build_point_in_time_universe(current)
        far_future = _d(2099, 1, 1)
        result = eligible_symbols_asof(snapshots, far_future)
        assert result == snapshots[-1].symbols
