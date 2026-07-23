"""
PEAD Phase 1 — XBRL Quarterly-PAT Extraction — Unit Tests

XBRL fixtures below are trimmed real filings pulled live from NSE
2026-07-23 (RELIANCE Q3 FY19, broadcast 2019-01-17; DIXON Q3 FY19,
broadcast 2019-02-01) -- root element, namespace declarations, and the
real OneD/FourD ProfitLossForPeriod facts are copied verbatim, not
hand-invented. See core/fundamentals/pead/xbrl.py's docstring for why
"OneD"/"FourD" aren't locally defined `<xbrli:context>` elements in these
files at all -- that absence is itself real and reproduced here, not an
artifact of trimming.
"""

import pytest

from core.fundamentals.pead.xbrl import (
    CURRENT_QUARTER_CONTEXT,
    XbrlParseError,
    extract_pat_by_context,
    extract_quarterly_pat,
    is_xbrl_available,
)

_XBRL_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<xbrli:xbrl xmlns:in-bse-fin="http://www.bseindia.com/xbrl/fin/2018-03-31/in-bse-fin" '
    'xmlns:xbrli="http://www.xbrl.org/2003/instance">\n'
)
_XBRL_FOOTER = "</xbrli:xbrl>\n"

# Real facts, trimmed from the live RELIANCE Q3 FY19 filing
# (https://nsearchives.nseindia.com/corporate/xbrl/INDAS_41556_74178_17012019065221_WEB.xml,
# fetched 2026-07-23). Confirmed against this project's own cross-check:
# OneD (this quarter) = 103760000000.00, FourD (YTD) = 294100000000.00.
RELIANCE_Q3FY19_XBRL = (
    _XBRL_HEADER
    + '<in-bse-fin:ProfitLossForPeriodFromContinuingOperations contextRef="OneD" '
      'unitRef="INR" decimals="-7">103520000000.00</in-bse-fin:ProfitLossForPeriodFromContinuingOperations>\n'
    + '<in-bse-fin:ProfitLossForPeriod contextRef="OneD" unitRef="INR" '
      'decimals="-7">103760000000.00</in-bse-fin:ProfitLossForPeriod>\n'
    + '<in-bse-fin:ProfitLossForPeriod contextRef="FourD" unitRef="INR" '
      'decimals="-7">294100000000.00</in-bse-fin:ProfitLossForPeriod>\n'
    + '<in-bse-fin:OneReportableSegmentResults01D contextRef="OneReportableSegmentResults01D" '
      'unitRef="INR" decimals="-7">173410000000.00</in-bse-fin:OneReportableSegmentResults01D>\n'
    + _XBRL_FOOTER
)

# Real facts, trimmed from the live DIXON Q3 FY19 filing
# (https://nsearchives.nseindia.com/corporate/xbrl/INDAS_41953_78852_31012019124808_WEB_2.xml).
DIXON_Q3FY19_XBRL = (
    _XBRL_HEADER
    + '<in-bse-fin:ProfitLossForPeriod contextRef="OneD" unitRef="INR" '
      'decimals="-7">176400000.00</in-bse-fin:ProfitLossForPeriod>\n'
    + '<in-bse-fin:ProfitLossForPeriod contextRef="FourD" unitRef="INR" '
      'decimals="-7">468400000.00</in-bse-fin:ProfitLossForPeriod>\n'
    + _XBRL_FOOTER
)

# Real fact, trimmed from a live HDFCBANK filing fetched during this
# session's smoke test (seq=1181774, Oct-Dec 2024 quarter) -- banks/NBFCs
# use "ProfitLossForThePeriod" ("For THE Period"), a different tag name
# from non-financials' "ProfitLossForPeriod", under the same OneD/FourD
# context convention. Discovered because the smoke test skipped all 28
# bank/NBFC Nifty 500 constituents before this fix.
HDFCBANK_XBRL_BANK_TAG_VARIANT = (
    _XBRL_HEADER
    + '<in-bse-fin:ProfitLossForThePeriod contextRef="OneD" unitRef="INR" '
      'decimals="-7">178259100000.00</in-bse-fin:ProfitLossForThePeriod>\n'
    + _XBRL_FOOTER
)


class TestExtractPatByContext:
    def test_reliance_q3fy19_oned_and_fourd(self):
        facts = extract_pat_by_context(RELIANCE_Q3FY19_XBRL.encode("utf-8"))
        assert facts["OneD"].value == 103760000000.00
        assert facts["FourD"].value == 294100000000.00

    def test_segment_breakdown_context_excluded(self):
        # OneReportableSegmentResults01D is a real context ID in the live
        # file but is NOT one of the six standard whole-company periods --
        # must never be confused with OneD.
        facts = extract_pat_by_context(RELIANCE_Q3FY19_XBRL.encode("utf-8"))
        assert "OneReportableSegmentResults01D" not in facts

    def test_dixon_q3fy19_smaller_company_same_tag_shape(self):
        facts = extract_pat_by_context(DIXON_Q3FY19_XBRL.encode("utf-8"))
        assert facts["OneD"].value == 176400000.00
        assert facts["FourD"].value == 468400000.00

    def test_bank_uses_profitlossforetheperiod_tag_variant(self):
        facts = extract_pat_by_context(HDFCBANK_XBRL_BANK_TAG_VARIANT.encode("utf-8"))
        assert facts["OneD"].value == 178259100000.00

    def test_namespace_prefix_agnostic(self):
        # Confirmed live only against in-bse-fin filers; this synthetic
        # case exercises the local-name-only matching for a hypothetical
        # different taxonomy prefix (e.g. a bank/NBFC extension), which
        # this module's docstring explicitly designs for.
        xbrl = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<xbrli:xbrl xmlns:in-capmkt="http://example.org/in-capmkt" '
            'xmlns:xbrli="http://www.xbrl.org/2003/instance">\n'
            '<in-capmkt:ProfitLossForPeriod contextRef="OneD" unitRef="INR">5000000.00'
            '</in-capmkt:ProfitLossForPeriod>\n'
            '</xbrli:xbrl>\n'
        )
        facts = extract_pat_by_context(xbrl.encode("utf-8"))
        assert facts["OneD"].value == 5000000.00

    def test_malformed_xml_raises(self):
        with pytest.raises(XbrlParseError):
            extract_pat_by_context(b"<not><valid xml")

    def test_conflicting_values_for_same_context_raises(self):
        xbrl = (
            _XBRL_HEADER
            + '<in-bse-fin:ProfitLossForPeriod contextRef="OneD">100.00</in-bse-fin:ProfitLossForPeriod>\n'
            + '<in-bse-fin:ProfitLossForPeriod contextRef="OneD">200.00</in-bse-fin:ProfitLossForPeriod>\n'
            + _XBRL_FOOTER
        )
        with pytest.raises(XbrlParseError):
            extract_pat_by_context(xbrl.encode("utf-8"))


class TestExtractQuarterlyPat:
    def test_returns_oned_not_fourd(self):
        assert extract_quarterly_pat(RELIANCE_Q3FY19_XBRL.encode("utf-8")) == 103760000000.00
        assert CURRENT_QUARTER_CONTEXT == "OneD"

    def test_bank_tag_variant_also_works_end_to_end(self):
        assert extract_quarterly_pat(HDFCBANK_XBRL_BANK_TAG_VARIANT.encode("utf-8")) == 178259100000.00

    def test_missing_oned_raises(self):
        xbrl = (
            _XBRL_HEADER
            + '<in-bse-fin:ProfitLossForPeriod contextRef="FourD">100.00</in-bse-fin:ProfitLossForPeriod>\n'
            + _XBRL_FOOTER
        )
        with pytest.raises(XbrlParseError):
            extract_quarterly_pat(xbrl.encode("utf-8"))


class TestIsXbrlAvailable:
    def test_dead_placeholder_link_confirmed_live_on_old_format_filings(self):
        # Real value seen on every "Old"-format filing tested (RELIANCE/
        # DIXON/PVRINOX/CENTURYPLY, 2026-07-23), and even on some "New"
        # rows (RELIANCE broadcast 2018-06-13) -- format alone is NOT a
        # reliable signal, this URL check is load-bearing.
        assert not is_xbrl_available("https://nsearchives.nseindia.com/corporate/xbrl/-")

    def test_real_xbrl_link_available(self):
        assert is_xbrl_available(
            "https://nsearchives.nseindia.com/corporate/xbrl/INDAS_41556_74178_17012019065221_WEB.xml"
        )

    def test_empty_link_not_available(self):
        assert not is_xbrl_available("")
