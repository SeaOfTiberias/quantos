"""
PEAD Phase 1 — Pipeline (discovery filter/dedupe/YoY join) — Unit Tests

Metadata row shapes below are trimmed real `corporates-financial-results`
rows pulled live from NSE 2026-07-23 (RELIANCE FY2018-19 quarterly
filings), field-for-field -- including the real quirk that a
`format: "New"` row can still carry a dead placeholder `xbrl` link
(RELIANCE broadcast 2018-06-13), which is why filter_usable() checks the
URL itself rather than trusting `format`.
"""

from datetime import date, datetime

import pytest

from core.fundamentals.pead.pipeline import (
    PointInTimeFiling,
    _month_chunks,
    compute_yoy_surprise,
    dedupe_consolidated_preferred,
    filter_usable,
    restrict_to_universe,
)

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
    def test_filters_by_symbol_membership(self):
        rows = [RELIANCE_Q3FY19_CONSOL, DIXON_Q1FY19_OLD_FORMAT]
        result = restrict_to_universe(rows, frozenset({"RELIANCE"}))
        assert result == [RELIANCE_Q3FY19_CONSOL]


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
    def _filing(self, symbol, q_start, q_end, pat, broadcast):
        return PointInTimeFiling(
            symbol=symbol, broadcast_date=broadcast,
            quarter_start=q_start, quarter_end=q_end,
            consolidated=True, pat=pat, seq_number="x",
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
