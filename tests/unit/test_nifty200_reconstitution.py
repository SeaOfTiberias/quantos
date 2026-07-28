"""
core/rotation/nifty200_reconstitution.py — point-in-time Nifty 200
membership, reconstructed backward from today's live universe file.
Mirrors tests/unit/test_nifty500_reconstitution.py's structure for the
Nifty 200 events instead.
"""

from datetime import datetime, timezone

from core.rotation.nifty200_reconstitution import (
    build_point_in_time_nifty200, nifty200_eligible_asof,
)


def _d(y: int, m: int, day: int) -> datetime:
    return datetime(y, m, day, tzinfo=timezone.utc)


class TestBuildPointInTimeNifty200:

    def test_snapshots_are_contiguous_and_last_one_is_current(self):
        from core.rotation import nifty200_reconstitution as mod
        current = frozenset({"A", "B"})
        snapshots = build_point_in_time_nifty200(current)
        assert snapshots[-1].symbols == current
        assert snapshots[-1].valid_until is None
        assert snapshots[0].valid_from == mod._EPOCH
        for earlier, later in zip(snapshots, snapshots[1:]):
            assert earlier.valid_until == later.valid_from

    def test_aplapollo_joined_2023_09_29_and_never_left(self):
        current = frozenset({"APLAPOLLO"})
        snapshots = build_point_in_time_nifty200(current)
        assert "APLAPOLLO" not in nifty200_eligible_asof(snapshots, _d(2023, 9, 1))
        assert "APLAPOLLO" in nifty200_eligible_asof(snapshots, _d(2023, 10, 1))

    def test_ireda_substitution_correction_nets_correctly(self):
        # IREDA's inclusion (announced 2024-02-28) was revoked before its
        # 2024-03-28 effective date; BSE was substituted in instead --
        # confirms the ind_prs19032024.pdf correction was netted into the
        # base event, not double-counted or left as a separate event.
        current = frozenset({"BSE"})  # IREDA isn't in today's Nifty 200
        snapshots = build_point_in_time_nifty200(current)
        assert "IREDA" not in nifty200_eligible_asof(snapshots, _d(2024, 4, 1))
        assert "BSE" not in nifty200_eligible_asof(snapshots, _d(2024, 3, 1))
        assert "BSE" in nifty200_eligible_asof(snapshots, _d(2024, 4, 1))

    def test_centralbk_revocation_means_it_never_actually_joined(self):
        # CENTRALBK's inclusion (announced 2024-08-23) was revoked by the
        # 2024-09-25 correction before its 2024-09-30 effective date -- it
        # should never appear as a Nifty 200 member at any date.
        current = frozenset()
        snapshots = build_point_in_time_nifty200(current)
        assert "CENTRALBK" not in nifty200_eligible_asof(snapshots, _d(2024, 9, 1))
        assert "CENTRALBK" not in nifty200_eligible_asof(snapshots, _d(2024, 10, 15))

    def test_idea_exclusion_revocation_means_no_gap(self):
        # IDEA's exclusion (announced 2024-08-23) was revoked by the
        # 2024-09-25 correction -- it should remain a member throughout,
        # same "nets to no change" pattern the Nifty 500 module already
        # tests for the same real event.
        current = frozenset({"IDEA"})
        snapshots = build_point_in_time_nifty200(current)
        assert "IDEA" in nifty200_eligible_asof(snapshots, _d(2024, 8, 1))
        assert "IDEA" in nifty200_eligible_asof(snapshots, _d(2024, 10, 1))

    def test_olaelec_joined_then_left_a_later_cycle(self):
        # OLAELEC entered Nifty 200 2025-03-28 and was excluded again
        # 2025-09-30 -- two independent, real events (not a same-cycle
        # revocation), applied in chronological order.
        current = frozenset()  # OLAELEC isn't in today's list either way
        snapshots = build_point_in_time_nifty200(current)
        assert "OLAELEC" not in nifty200_eligible_asof(snapshots, _d(2025, 3, 1))
        assert "OLAELEC" in nifty200_eligible_asof(snapshots, _d(2025, 6, 1))
        assert "OLAELEC" not in nifty200_eligible_asof(snapshots, _d(2025, 10, 1))

    def test_hindzinc_cycles_out_then_back_in(self):
        # HINDZINC was excluded 2023-09-29 and re-included 2024-09-30 --
        # confirms a symbol can legitimately re-enter after leaving,
        # handled correctly by the backward-walk (not just monotonic).
        current = frozenset({"HINDZINC"})
        snapshots = build_point_in_time_nifty200(current)
        assert "HINDZINC" in nifty200_eligible_asof(snapshots, _d(2023, 9, 1))
        assert "HINDZINC" not in nifty200_eligible_asof(snapshots, _d(2024, 1, 1))
        assert "HINDZINC" in nifty200_eligible_asof(snapshots, _d(2024, 10, 1))


class TestNifty200EligibleAsofBoundaries:

    def test_date_before_earliest_snapshot_clamps_to_first(self):
        current = frozenset({"A"})
        snapshots = build_point_in_time_nifty200(current)
        result = nifty200_eligible_asof(snapshots, _d(1990, 1, 1))
        assert result == snapshots[0].symbols

    def test_date_after_latest_snapshot_clamps_to_last(self):
        current = frozenset({"A"})
        snapshots = build_point_in_time_nifty200(current)
        result = nifty200_eligible_asof(snapshots, _d(2099, 1, 1))
        assert result == snapshots[-1].symbols
