"""
Index-Reconstitution Gut-Check — Leg Construction + Return Computation —
Unit Tests

Price series below are small constructed sequences (this tests the
lookup/return-arithmetic/grouping logic itself, not a data-integrity claim
about real prices -- same convention as test_pead_gutcheck.py).
"""

from datetime import date, datetime, timezone

import pytest

from core.fundamentals.pead.eq_bhavcopy import EqCloseRow
from core.rotation.nifty500_reconstitution import ReconstitutionEvent
from core.rotation.reconstitution_gutcheck import (
    EventLeg,
    _announcement_date_for,
    _parse_source_dates,
    build_legs,
    build_price_index,
    compute_anticipation_return,
    compute_post_effective_return,
    diagnose_all,
    diagnose_anticipation,
    diagnose_post_effective,
    missing_legs,
    summarize_anticipation,
    summarize_post_effective,
)


def _dt(y, m, d):
    return datetime(y, m, d, tzinfo=timezone.utc)


class TestParseSourceDates:
    def test_single_release(self):
        assert _parse_source_dates("ind_prs17082023.pdf") == [date(2023, 8, 17)]

    def test_base_plus_correction(self):
        assert _parse_source_dates("ind_prs28022024.pdf+ind_prs19032024.pdf") == [
            date(2024, 2, 28), date(2024, 3, 19),
        ]


class TestAnnouncementDateFor:
    def test_single_release_event_uses_that_date(self):
        event = ReconstitutionEvent(
            effective_date=_dt(2023, 9, 29), added=frozenset({"X"}), removed=frozenset(),
            source="ind_prs17082023.pdf",
        )
        assert _announcement_date_for(event, "X") == date(2023, 8, 17)

    def test_netted_event_default_uses_earliest_base_date(self):
        event = ReconstitutionEvent(
            effective_date=_dt(2024, 9, 30), added=frozenset(), removed=frozenset({"OTHERCO"}),
            source="ind_prs23082024.pdf+ind_prs25092024.pdf",
        )
        assert _announcement_date_for(event, "OTHERCO") == date(2024, 8, 23)

    def test_prsmjohnsn_override_uses_correction_date_not_base(self):
        # Real case: this symbol's removal was only decided in the
        # 25-Sep-2024 correction filing, not the 23-Aug-2024 base one --
        # see nifty500_reconstitution.py's own docstring.
        event = ReconstitutionEvent(
            effective_date=_dt(2024, 9, 30), added=frozenset(), removed=frozenset({"PRSMJOHNSN"}),
            source="ind_prs23082024.pdf+ind_prs25092024.pdf",
        )
        assert _announcement_date_for(event, "PRSMJOHNSN") == date(2024, 9, 25)


class TestBuildLegs:
    def test_broad_vs_adhoc_categorization_by_size(self):
        events = [
            ReconstitutionEvent(
                effective_date=_dt(2023, 9, 29), added=frozenset({"A", "B"}), removed=frozenset({"C", "D"}),
                source="ind_prs17082023.pdf",
            ),
            ReconstitutionEvent(
                effective_date=_dt(2023, 10, 26), added=frozenset({"E"}), removed=frozenset({"F"}),
                source="ind_prs17102023.pdf",
            ),
        ]
        legs = build_legs(events)
        by_symbol = {leg.symbol: leg for leg in legs}
        assert by_symbol["A"].event_category == "broad"
        assert by_symbol["A"].event_type == "add"
        assert by_symbol["C"].event_category == "broad"
        assert by_symbol["C"].event_type == "remove"
        assert by_symbol["E"].event_category == "adhoc"
        assert by_symbol["F"].event_category == "adhoc"

    def test_each_leg_carries_its_own_effective_and_announcement_date(self):
        events = [ReconstitutionEvent(
            effective_date=_dt(2023, 9, 29), added=frozenset({"A"}), removed=frozenset(),
            source="ind_prs17082023.pdf",
        )]
        leg = build_legs(events)[0]
        assert leg.effective_date == date(2023, 9, 29)
        assert leg.announcement_date == date(2023, 8, 17)


class TestComputeAnticipationReturn:
    def _leg(self, announcement=date(2024, 1, 1), effective=date(2024, 1, 10)):
        return EventLeg(
            symbol="RELIANCE", event_type="add", event_category="broad",
            announcement_date=announcement, effective_date=effective, source="x",
        )

    def test_entry_strictly_after_announcement_exit_strictly_before_effective(self):
        # Ten consecutive trading days, 2024-01-01 .. 2024-01-10.
        rows = [EqCloseRow(date(2024, 1, 1 + i), "RELIANCE", 100.0 + i) for i in range(10)]
        idx = build_price_index(rows)
        lr = compute_anticipation_return(idx, self._leg())
        assert lr.entry_date == date(2024, 1, 2)   # first day strictly after announcement (01-01)
        assert lr.exit_date == date(2024, 1, 9)     # last day strictly before effective (01-10)
        assert lr.entry_close == 101.0
        assert lr.exit_close == 108.0
        assert lr.return_pct == pytest.approx((108.0 - 101.0) / 101.0 * 100)

    def test_missing_symbol_returns_none(self):
        idx = build_price_index([EqCloseRow(date(2024, 1, 1), "OTHER", 100.0)])
        assert compute_anticipation_return(idx, self._leg()) is None

    def test_single_available_day_serves_as_both_entry_and_exit(self):
        # Degenerate but not invalid: exactly one trading day exists that
        # is both strictly after announcement and strictly before
        # effective, so entry == exit == that day, giving a vacuous 0%
        # return rather than None. Essentially unreachable with real daily
        # bhavcopy coverage (every symbol trades ~250 days/year); exercised
        # here only to pin the boundary behavior explicitly.
        rows = [EqCloseRow(date(2024, 1, 2), "RELIANCE", 100.0)]
        idx = build_price_index(rows)
        lr = compute_anticipation_return(idx, self._leg())
        assert lr is not None
        assert lr.entry_date == lr.exit_date == date(2024, 1, 2)
        assert lr.return_pct == 0.0

    def test_no_trading_day_after_announcement_returns_none(self):
        rows = [EqCloseRow(date(2023, 12, 1), "RELIANCE", 100.0)]  # entirely before announcement
        idx = build_price_index(rows)
        assert compute_anticipation_return(idx, self._leg()) is None


class TestCorporateActionGuard:
    # Real case caught by a Fable review 2026-07-24: METROPOLIS (2026-03-30
    # event) showed a clean overnight Rs 1823.80 -> Rs 441.10 cliff (~4.1x)
    # in raw NSE bhavcopy -- an unadjusted stock split/scheme-of-arrangement,
    # not a real one-day price move. Both windows must reject it, not
    # compute a fake return.
    def _leg(self):
        return EventLeg(
            symbol="METROPOLIS", event_type="remove", event_category="broad",
            announcement_date=date(2024, 1, 1), effective_date=date(2024, 1, 20), source="x",
        )

    def test_anticipation_returns_none_across_a_split_like_jump(self):
        rows = [EqCloseRow(date(2024, 1, 1 + i), "METROPOLIS", 100.0) for i in range(5)]
        rows.append(EqCloseRow(date(2024, 1, 6), "METROPOLIS", 24.0))  # ~4.1x overnight drop
        rows += [EqCloseRow(date(2024, 1, 7 + i), "METROPOLIS", 24.0 + i) for i in range(10)]
        idx = build_price_index(rows)
        assert compute_anticipation_return(idx, self._leg()) is None
        assert diagnose_anticipation(idx, self._leg()) == "corporate_action_suspected"

    def test_post_effective_returns_none_across_a_split_like_jump(self):
        rows = [EqCloseRow(date(2024, 1, 20 + i), "METROPOLIS", 100.0) for i in range(3)]
        rows.append(EqCloseRow(date(2024, 1, 23), "METROPOLIS", 24.0))
        rows += [EqCloseRow(date(2024, 1, 24), "METROPOLIS", 24.0)]
        rows += [EqCloseRow(date(2024, 2, 1 + i), "METROPOLIS", 24.0 + i) for i in range(9)]
        idx = build_price_index(rows)
        leg = self._leg()
        assert compute_post_effective_return(idx, leg, horizon_trading_days=5) is None
        assert diagnose_post_effective(idx, leg, 5) == "corporate_action_suspected"

    def test_ordinary_large_but_plausible_move_is_not_flagged(self):
        # A real +40% single-day move (large but within the band) must NOT
        # be treated as a corporate action.
        rows = [EqCloseRow(date(2024, 1, 1 + i), "VOLATILE", 100.0) for i in range(3)]
        rows.append(EqCloseRow(date(2024, 1, 4), "VOLATILE", 140.0))
        rows += [EqCloseRow(date(2024, 1, 5 + i), "VOLATILE", 140.0 + i) for i in range(5)]
        idx = build_price_index(rows)
        leg = EventLeg(
            symbol="VOLATILE", event_type="add", event_category="broad",
            announcement_date=date(2024, 1, 1), effective_date=date(2024, 1, 10), source="x",
        )
        assert compute_anticipation_return(idx, leg) is not None


class TestSparseTradingGapGuard:
    # Real case caught by a Fable review 2026-07-24: KIRLFER/KENNAMET/JSWHL
    # had cached rows spaced ~12-140 days apart (thin trading/ASM), turning
    # a claimed "20-trading-day" post-effective window into an actual
    # multi-hundred-day span. Must be excluded, not silently pooled
    # alongside genuine ~30-calendar-day windows.
    def test_sparse_series_rejects_implausible_calendar_span(self):
        # Only 6 rows total, spaced ~30 real calendar days apart each --
        # "5 trading days" later lands ~150 calendar days out.
        rows = [EqCloseRow(date(2024, 1, 10) + (date(2024, 2, 9) - date(2024, 1, 10)) * i, "THIN", 100.0 + i)
                for i in range(6)]
        idx = build_price_index(rows)
        leg = EventLeg(
            symbol="THIN", event_type="remove", event_category="broad",
            announcement_date=date(2024, 1, 1), effective_date=date(2024, 1, 10), source="x",
        )
        assert compute_post_effective_return(idx, leg, horizon_trading_days=5) is None
        assert diagnose_post_effective(idx, leg, 5) == "sparse_trading_gap"

    def test_dense_series_within_a_holiday_cluster_is_not_flagged(self):
        # Normal daily trading with a plausible holiday gap -- must NOT be
        # flagged even though real calendar days exceed the naive
        # weekends-only estimate somewhat.
        rows = [EqCloseRow(date(2024, 1, 10 + i), "NORMAL", 100.0 + i) for i in range(10)]
        idx = build_price_index(rows)
        leg = EventLeg(
            symbol="NORMAL", event_type="add", event_category="broad",
            announcement_date=date(2024, 1, 1), effective_date=date(2024, 1, 10), source="x",
        )
        assert compute_post_effective_return(idx, leg, horizon_trading_days=5) is not None


class TestDiagnoseAll:
    def test_groups_legs_by_exclusion_reason(self):
        events = [ReconstitutionEvent(
            effective_date=_dt(2024, 1, 10), added=frozenset({"COVERED", "MISSING"}), removed=frozenset(),
            source="ind_prs01012024.pdf",
        )]
        legs = build_legs(events)
        idx = build_price_index([EqCloseRow(date(2024, 1, 2), "COVERED", 100.0)])
        by_reason = diagnose_all(legs, idx, "anticipation")
        assert {leg.symbol for leg in by_reason["no_price_series"]} == {"MISSING"}
        assert "COVERED" not in {leg.symbol for legs_ in by_reason.values() for leg in legs_}


class TestComputePostEffectiveReturn:
    def test_entry_at_or_after_effective_horizon_in_trading_days(self):
        rows = [EqCloseRow(date(2024, 1, 10 + i), "RELIANCE", 100.0 + i) for i in range(10)]
        idx = build_price_index(rows)
        leg = EventLeg(
            symbol="RELIANCE", event_type="remove", event_category="broad",
            announcement_date=date(2024, 1, 1), effective_date=date(2024, 1, 10), source="x",
        )
        lr = compute_post_effective_return(idx, leg, horizon_trading_days=3)
        assert lr.entry_date == date(2024, 1, 10)
        assert lr.exit_date == date(2024, 1, 13)
        assert lr.return_pct == pytest.approx((103.0 - 100.0) / 100.0 * 100)

    def test_horizon_runs_past_series_end_returns_none(self):
        rows = [EqCloseRow(date(2024, 1, 10 + i), "RELIANCE", 100.0 + i) for i in range(3)]
        idx = build_price_index(rows)
        leg = EventLeg(
            symbol="RELIANCE", event_type="add", event_category="broad",
            announcement_date=date(2024, 1, 1), effective_date=date(2024, 1, 10), source="x",
        )
        assert compute_post_effective_return(idx, leg, horizon_trading_days=5) is None


class TestSummarizeGrouping:
    def _events(self):
        return [
            ReconstitutionEvent(
                effective_date=_dt(2024, 1, 10), added=frozenset({"UP1"}), removed=frozenset({"DOWN1"}),
                source="ind_prs01012024.pdf",
            ),
        ]

    def _price_rows(self):
        # UP1 rises, DOWN1 falls -- announcement 01-01, effective 01-10.
        rows = []
        for i in range(15):
            d = date(2024, 1, 1 + i)
            rows.append(EqCloseRow(d, "UP1", 100.0 + i))
            rows.append(EqCloseRow(d, "DOWN1", 100.0 - i))
        return rows

    def test_add_and_remove_groups_split_correctly(self):
        # A single-symbol-per-side event self-classifies as "adhoc" (see
        # build_legs's >1 threshold) -- exactly like every real ad-hoc
        # correction in EVENTS.
        legs = build_legs(self._events())
        idx = build_price_index(self._price_rows())
        summaries = summarize_anticipation(legs, idx)
        add_adhoc = next(s for s in summaries if s.event_type == "add" and s.event_category == "adhoc")
        remove_adhoc = next(s for s in summaries if s.event_type == "remove" and s.event_category == "adhoc")
        assert add_adhoc.n_legs == 1
        assert add_adhoc.mean_return_pct > 0
        assert remove_adhoc.n_legs == 1
        assert remove_adhoc.mean_return_pct < 0
        broad = next(s for s in summaries if s.event_category == "broad" and s.event_type == "add")
        assert broad.n_legs == 0

    def test_n_events_counts_distinct_effective_dates_not_legs(self):
        events = [
            ReconstitutionEvent(
                effective_date=_dt(2024, 1, 10), added=frozenset({"A", "B"}), removed=frozenset(),
                source="ind_prs01012024.pdf",
            ),
            ReconstitutionEvent(
                effective_date=_dt(2024, 6, 10), added=frozenset({"C", "D"}), removed=frozenset(),
                source="ind_prs01062024.pdf",
            ),
        ]
        legs = build_legs(events)
        rows = []
        for sym in ("A", "B", "C", "D"):
            for i in range(15):
                rows.append(EqCloseRow(date(2024, 1, 1 + i) if sym in ("A", "B") else date(2024, 6, 1 + i), sym, 100.0 + i))
        idx = build_price_index(rows)
        summaries = summarize_anticipation(legs, idx)
        add_broad = next(s for s in summaries if s.event_type == "add" and s.event_category == "broad")
        assert add_broad.n_legs == 4
        assert add_broad.n_events == 2

    def test_market_adjustment_is_per_event_not_global(self):
        # Two events in very different "regimes": event 1 everyone drifts
        # up strongly, event 2 everyone drifts down strongly. A GLOBAL
        # demean would wrongly blend these; a PER-EVENT demean should
        # correctly reveal that within each event, add beat remove.
        events = [
            ReconstitutionEvent(
                effective_date=_dt(2024, 1, 10), added=frozenset({"UP_A"}), removed=frozenset({"UP_B"}),
                source="ind_prs01012024.pdf",
            ),
            ReconstitutionEvent(
                effective_date=_dt(2024, 6, 10), added=frozenset({"DN_A"}), removed=frozenset({"DN_B"}),
                source="ind_prs01062024.pdf",
            ),
        ]
        legs = build_legs(events)
        rows = []
        # Event 1 regime: both symbols rally, but UP_A rallies harder than UP_B.
        for i in range(15):
            rows.append(EqCloseRow(date(2024, 1, 1 + i), "UP_A", 100.0 + i * 3))
            rows.append(EqCloseRow(date(2024, 1, 1 + i), "UP_B", 100.0 + i * 1))
        # Event 2 regime: both symbols sell off, but DN_A sells off less than DN_B.
        for i in range(15):
            rows.append(EqCloseRow(date(2024, 6, 1 + i), "DN_A", 100.0 - i * 1))
            rows.append(EqCloseRow(date(2024, 6, 1 + i), "DN_B", 100.0 - i * 3))
        idx = build_price_index(rows)

        raw = summarize_anticipation(legs, idx, market_adjusted=False)
        adjusted = summarize_anticipation(legs, idx, market_adjusted=True)

        # Single-symbol-per-side events self-classify as "adhoc" -- category
        # isn't the point of this test, per-event demeaning is.
        raw_add = next(s for s in raw if s.event_type == "add" and s.event_category == "adhoc")
        raw_remove = next(s for s in raw if s.event_type == "remove" and s.event_category == "adhoc")
        # Raw: DN_A (add, -i) beats DN_B in its own event, but pooled
        # across both events the sign of "add" overall isn't guaranteed
        # positive since event 2 is a broad selloff -- the whole point of
        # needing adjustment.
        adj_add = next(s for s in adjusted if s.event_type == "add" and s.event_category == "adhoc")
        adj_remove = next(s for s in adjusted if s.event_type == "remove" and s.event_category == "adhoc")
        assert adj_add.mean_return_pct > 0   # beats its own event's mean in BOTH events
        assert adj_remove.mean_return_pct < 0  # trails its own event's mean in BOTH events
        assert raw_add.market_adjusted is False
        assert adj_add.market_adjusted is True


class TestMissingLegs:
    def test_symbol_with_no_price_series_is_reported(self):
        events = [ReconstitutionEvent(
            effective_date=_dt(2024, 1, 10), added=frozenset(), removed=frozenset({"GSPL"}),
            source="ind_prs01012024.pdf",
        )]
        legs = build_legs(events)
        idx = build_price_index([EqCloseRow(date(2024, 1, 1), "OTHER", 100.0)])
        gaps = missing_legs(legs, idx)
        assert len(gaps) == 1
        assert gaps[0].symbol == "GSPL"

    def test_covered_symbol_not_reported(self):
        events = [ReconstitutionEvent(
            effective_date=_dt(2024, 1, 10), added=frozenset({"COVERED"}), removed=frozenset(),
            source="ind_prs01012024.pdf",
        )]
        legs = build_legs(events)
        idx = build_price_index([EqCloseRow(date(2024, 1, 1), "COVERED", 100.0)])
        assert missing_legs(legs, idx) == []


class TestSummarizePostEffective:
    def test_multiple_horizons_each_produce_a_full_set_of_groups(self):
        events = [ReconstitutionEvent(
            effective_date=_dt(2024, 1, 10), added=frozenset({"A"}), removed=frozenset(),
            source="ind_prs01012024.pdf",
        )]
        legs = build_legs(events)
        rows = [EqCloseRow(date(2024, 1, 10 + i), "A", 100.0 + i) for i in range(10)]
        idx = build_price_index(rows)
        summaries = summarize_post_effective(legs, idx, horizons=(3, 5))
        windows = {s.window for s in summaries}
        assert windows == {"post_effective_3d", "post_effective_5d"}
        # 4 groups (add/remove x broad/adhoc) per horizon
        assert len(summaries) == 8
