"""
PEAD Phase 1 — Pipeline (discovery filter/dedupe/YoY join) — Unit Tests

Metadata row shapes below are trimmed real `corporates-financial-results`
rows pulled live from NSE 2026-07-23 (RELIANCE FY2018-19 quarterly
filings), field-for-field -- including the real quirk that a
`format: "New"` row can still carry a dead placeholder `xbrl` link
(RELIANCE broadcast 2018-06-13), which is why filter_usable() checks the
URL itself rather than trusting `format`.
"""

from datetime import date, datetime, timezone

import pytest

from core.fundamentals.pead.pipeline import (
    RECONSTITUTION_COVERAGE_START,
    PointInTimeFiling,
    _month_chunks,
    compute_yoy_surprise,
    dedupe_consolidated_preferred,
    filter_usable,
    restrict_to_universe,
)
from core.rotation.nifty500_reconstitution import UniverseSnapshot

# Real rows (trimmed to the fields this module reads), RELIANCE FY2018-19,
# fetched live 2026-07-23.
RELIANCE_Q4FY18_NONCONSOL = {
    "symbol": "RELIANCE", "consolidated": "Non-Consolidated", "format": "New",
    "fromDate": "01-Jan-2018", "toDate": "31-Mar-2018",
    "broadCastDate": "13-Jun-2018 11:17:49", "seqNumber": "1",
    "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/-",  # real dead link despite format=New
}
RELIANCE_Q4FY18_CONSOL = {
    "symbol": "RELIANCE", "consolidated": "Consolidated", "format": "New",
    "fromDate": "01-Jan-2018", "toDate": "31-Mar-2018",
    "broadCastDate": "13-Jun-2018 11:16:51", "seqNumber": "2",
    "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/-",
}
RELIANCE_Q3FY19_NONCONSOL = {
    "symbol": "RELIANCE", "consolidated": "Non-Consolidated", "format": "New",
    "fromDate": "01-Oct-2018", "toDate": "31-Dec-2018",
    "broadCastDate": "17-Jan-2019 19:50:01", "seqNumber": "3",
    "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INDAS_A.xml",
}
RELIANCE_Q3FY19_CONSOL = {
    "symbol": "RELIANCE", "consolidated": "Consolidated", "format": "New",
    "fromDate": "01-Oct-2018", "toDate": "31-Dec-2018",
    "broadCastDate": "17-Jan-2019 19:52:25", "seqNumber": "4",
    "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INDAS_B.xml",
}
DIXON_Q1FY19_OLD_FORMAT = {
    "symbol": "DIXON", "consolidated": "Consolidated", "format": "Old",
    "fromDate": "01-Apr-2017", "toDate": "30-Jun-2017",
    "broadCastDate": "21-Nov-2017 17:27:08", "seqNumber": "5",
    "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/-",
}


class TestFilterUsable:
    def test_drops_dead_placeholder_link_even_when_format_is_new(self):
        rows = [RELIANCE_Q4FY18_NONCONSOL, RELIANCE_Q3FY19_NONCONSOL]
        kept = filter_usable(rows)
        assert kept == [RELIANCE_Q3FY19_NONCONSOL]

    def test_drops_old_format_dead_link(self):
        assert filter_usable([DIXON_Q1FY19_OLD_FORMAT]) == []

    def test_keeps_real_link(self):
        assert filter_usable([RELIANCE_Q3FY19_CONSOL]) == [RELIANCE_Q3FY19_CONSOL]


class TestDedupeConsolidatedPreferred:
    def test_prefers_consolidated_over_nonconsolidated_same_quarter(self):
        result = dedupe_consolidated_preferred([RELIANCE_Q3FY19_NONCONSOL, RELIANCE_Q3FY19_CONSOL])
        assert result == [RELIANCE_Q3FY19_CONSOL]

    def test_order_independence(self):
        result = dedupe_consolidated_preferred([RELIANCE_Q3FY19_CONSOL, RELIANCE_Q3FY19_NONCONSOL])
        assert result == [RELIANCE_Q3FY19_CONSOL]

    def test_distinct_quarters_both_kept(self):
        result = dedupe_consolidated_preferred([RELIANCE_Q4FY18_CONSOL, RELIANCE_Q3FY19_CONSOL])
        assert len(result) == 2

    def test_same_type_duplicate_keeps_latest_broadcast(self):
        earlier = dict(RELIANCE_Q3FY19_CONSOL, seqNumber="10", broadCastDate="17-Jan-2019 10:00:00")
        later = dict(RELIANCE_Q3FY19_CONSOL, seqNumber="11", broadCastDate="17-Jan-2019 19:52:25")
        result = dedupe_consolidated_preferred([earlier, later])
        assert result == [later]


class TestRestrictToUniverse:
    """restrict_to_universe evaluates each row against the universe AS OF
    THAT ROW'S OWN broadcast date (point-in-time), not one fixed universe
    for every row -- the S8-3-shaped bug a Fable review found in the first
    version of this function. All fixture broadcast dates below are placed
    AFTER RECONSTITUTION_COVERAGE_START (2023-09-29) specifically so they
    exercise the real per-row snapshot lookup, not the pre-coverage drop
    guard (see test_drops_rows_before_reconstitution_coverage for that)."""

    def _row(self, symbol, broadcast_date):
        return {
            "symbol": symbol, "broadCastDate": broadcast_date,
            "consolidated": "Consolidated", "fromDate": "01-Jul-2024", "toDate": "30-Sep-2024",
        }

    def test_keeps_symbol_in_universe_as_of_its_own_broadcast_date(self):
        # A single always-eligible snapshot spanning the whole test window.
        snapshots = [UniverseSnapshot(
            valid_from=datetime(2023, 9, 29, tzinfo=timezone.utc), valid_until=None,
            symbols=frozenset({"RELIANCE"}),
        )]
        rows = [self._row("RELIANCE", "17-Jan-2025 19:52:25"), self._row("DIXON", "01-Feb-2025 16:35:37")]
        result = restrict_to_universe(rows, snapshots)
        assert result == [rows[0]]

    def test_membership_change_respected_at_the_boundary(self):
        # DIXON joins Nifty 500 partway through -- a filing broadcast
        # before the join date must be excluded even though DIXON is
        # eligible later; this is the actual point of point-in-time
        # filtering, not just "is the symbol ever eligible."
        snapshots = [
            UniverseSnapshot(
                valid_from=datetime(2023, 9, 29, tzinfo=timezone.utc),
                valid_until=datetime(2024, 6, 1, tzinfo=timezone.utc),
                symbols=frozenset(),
            ),
            UniverseSnapshot(
                valid_from=datetime(2024, 6, 1, tzinfo=timezone.utc), valid_until=None,
                symbols=frozenset({"DIXON"}),
            ),
        ]
        before = self._row("DIXON", "01-Feb-2024 16:35:37")
        after = self._row("DIXON", "01-Feb-2025 16:35:37")
        result = restrict_to_universe([before, after], snapshots)
        assert result == [after]

    def test_drops_rows_before_reconstitution_coverage(self):
        # Real gotcha found by a Fable review 2026-07-23: EVENTS only goes
        # back to 2023-09-29 -- a naive frozenset check would silently
        # evaluate an earlier row against a frozen fallback snapshot
        # instead of real point-in-time membership. This must be dropped
        # outright, not silently kept/misclassified, EVEN IF the snapshot
        # list technically has the symbol.
        snapshots = [UniverseSnapshot(
            valid_from=datetime(2015, 1, 1, tzinfo=timezone.utc), valid_until=None,
            symbols=frozenset({"RELIANCE"}),
        )]
        assert RECONSTITUTION_COVERAGE_START == date(2023, 9, 29)
        pre_coverage_row = self._row("RELIANCE", "17-Jan-2019 19:52:25")
        result = restrict_to_universe([pre_coverage_row], snapshots)
        assert result == []


class TestMonthChunks:
    def test_splits_across_month_boundaries(self):
        chunks = list(_month_chunks(date(2024, 1, 15), date(2024, 3, 10)))
        assert chunks == [
            (date(2024, 1, 15), date(2024, 1, 31)),
            (date(2024, 2, 1), date(2024, 2, 29)),  # 2024 is a leap year
            (date(2024, 3, 1), date(2024, 3, 10)),
        ]

    def test_single_month_window(self):
        chunks = list(_month_chunks(date(2024, 5, 1), date(2024, 5, 31)))
        assert chunks == [(date(2024, 5, 1), date(2024, 5, 31))]


class TestComputeYoySurprise:
    def _filing(self, symbol, q_start, q_end, pat, broadcast, consolidated=True):
        return PointInTimeFiling(
            symbol=symbol, broadcast_date=broadcast,
            quarter_start=q_start, quarter_end=q_end,
            consolidated=consolidated, pat=pat, seq_number="x",
        )

    def test_joins_same_quarter_one_year_apart(self):
        prior = self._filing(
            "RELIANCE", date(2017, 10, 1), date(2017, 12, 31), 1000.0,
            datetime(2018, 1, 17),
        )
        current = self._filing(
            "RELIANCE", date(2018, 10, 1), date(2018, 12, 31), 1200.0,
            datetime(2019, 1, 17),
        )
        rows = compute_yoy_surprise([prior, current])
        assert len(rows) == 1
        row = rows[0]
        assert row.symbol == "RELIANCE"
        assert row.pat == 1200.0
        assert row.pat_prior_year == 1000.0
        assert row.yoy_surprise_pct == pytest.approx(20.0)

    def test_no_prior_year_match_dropped_not_zero_filled(self):
        only_filing = self._filing(
            "RELIANCE", date(2018, 10, 1), date(2018, 12, 31), 1200.0,
            datetime(2019, 1, 17),
        )
        assert compute_yoy_surprise([only_filing]) == []

    def test_different_symbols_not_cross_joined(self):
        a = self._filing("RELIANCE", date(2017, 10, 1), date(2017, 12, 31), 1000.0, datetime(2018, 1, 17))
        b = self._filing("DIXON", date(2018, 10, 1), date(2018, 12, 31), 1200.0, datetime(2019, 1, 17))
        assert compute_yoy_surprise([a, b]) == []

    def test_zero_prior_year_pat_dropped_to_avoid_division_by_zero(self):
        prior = self._filing("RELIANCE", date(2017, 10, 1), date(2017, 12, 31), 0.0, datetime(2018, 1, 17))
        current = self._filing("RELIANCE", date(2018, 10, 1), date(2018, 12, 31), 1200.0, datetime(2019, 1, 17))
        assert compute_yoy_surprise([prior, current]) == []

    def test_negative_surprise(self):
        prior = self._filing("RELIANCE", date(2017, 10, 1), date(2017, 12, 31), 1000.0, datetime(2018, 1, 17))
        current = self._filing("RELIANCE", date(2018, 10, 1), date(2018, 12, 31), 700.0, datetime(2019, 1, 17))
        rows = compute_yoy_surprise([prior, current])
        assert rows[0].yoy_surprise_pct == pytest.approx(-30.0)

    def test_consolidated_scope_mismatch_dropped_not_joined(self):
        # Real confound found by a Fable review 2026-07-23:
        # dedupe_consolidated_preferred picks Consolidated-over-Standalone
        # PER QUARTER INDEPENDENTLY, so a company that only filed
        # Standalone the prior year but Consolidated this year (e.g. right
        # after an acquisition) would otherwise show a "surprise" driven
        # by consolidation-scope change, not organic earnings.
        prior_standalone_only = self._filing(
            "RELIANCE", date(2017, 10, 1), date(2017, 12, 31), 1000.0,
            datetime(2018, 1, 17), consolidated=False,
        )
        current_now_consolidated = self._filing(
            "RELIANCE", date(2018, 10, 1), date(2018, 12, 31), 5000.0,
            datetime(2019, 1, 17), consolidated=True,
        )
        assert compute_yoy_surprise([prior_standalone_only, current_now_consolidated]) == []

    def test_matching_consolidated_flags_still_join(self):
        prior = self._filing(
            "RELIANCE", date(2017, 10, 1), date(2017, 12, 31), 1000.0,
            datetime(2018, 1, 17), consolidated=False,
        )
        current = self._filing(
            "RELIANCE", date(2018, 10, 1), date(2018, 12, 31), 1200.0,
            datetime(2019, 1, 17), consolidated=False,
        )
        rows = compute_yoy_surprise([prior, current])
        assert len(rows) == 1
