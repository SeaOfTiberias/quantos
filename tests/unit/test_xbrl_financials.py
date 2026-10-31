"""
Techno-funda — P&L + share-capital extraction from NSE results XBRL — Unit Tests

Synthetic filings in the real NSE layout (namespace-prefixed facts keyed by
OneD/FourD contextRef, no local context definitions). Round numbers so every
expected value can be checked by hand.
"""

import pytest

from core.fundamentals.pead.xbrl import XbrlParseError
from core.fundamentals.xbrl_financials import PeriodFigures, arithmetic_check, extract_figures

_HEAD = ('<?xml version="1.0" encoding="UTF-8"?>\n'
         '<xbrli:xbrl xmlns:in-bse-fin="http://www.bseindia.com/xbrl/fin/2020-03-31/in-bse-fin" '
         'xmlns:xbrli="http://www.xbrl.org/2003/instance">\n')
_FOOT = "</xbrli:xbrl>\n"


def _fact(tag: str, ctx: str, value: str) -> str:
    return f'<in-bse-fin:{tag} contextRef="{ctx}" unitRef="INR" decimals="-5">{value}</in-bse-fin:{tag}>\n'


def _filing(*facts: str) -> bytes:
    return (_HEAD + "".join(facts) + _FOOT).encode()


QUARTER = _filing(
    _fact("RevenueFromOperations", "OneD", "1000.00"),
    _fact("OtherIncome", "OneD", "50.00"),
    _fact("Expenses", "OneD", "800.00"),
    _fact("DepreciationDepletionAndAmortisationExpense", "OneD", "40.00"),
    _fact("FinanceCosts", "OneD", "10.00"),
    _fact("ProfitBeforeExceptionalItemsAndTax", "OneD", "250.00"),
    _fact("ProfitLossForPeriod", "OneD", "180.00"),
    _fact("PaidUpValueOfEquityShareCapital", "OneD", "5000000.00"),
    _fact("FaceValueOfEquityShareCapital", "OneD", "10"),
    _fact("RevenueFromOperations", "FourD", "3000.00"),
    _fact("RevenueFromOperations", "OneReportableSegmentRevenue01D", "999.00"),
)


class TestExtractFigures:
    def test_own_quarter_fields(self):
        q = extract_figures(QUARTER)["OneD"]
        assert (q.revenue, q.other_income, q.expenses) == (1000.0, 50.0, 800.0)
        assert (q.da, q.finance_costs, q.pbt_pre_exceptional, q.pat) == (40.0, 10.0, 250.0, 180.0)

    def test_year_to_date_kept_separately(self):
        assert extract_figures(QUARTER)["FourD"].revenue == 3000.0

    def test_segment_contexts_ignored(self):
        assert set(extract_figures(QUARTER)) == {"OneD", "FourD"}

    def test_conflicting_values_raise(self):
        bad = _filing(_fact("RevenueFromOperations", "OneD", "1.00"),
                      _fact("RevenueFromOperations", "OneD", "2.00"))
        with pytest.raises(XbrlParseError):
            extract_figures(bad)

    def test_repeated_identical_value_is_fine(self):
        ok = _filing(_fact("RevenueFromOperations", "OneD", "1.00"),
                     _fact("RevenueFromOperations", "OneD", "1.00"))
        assert extract_figures(ok)["OneD"].revenue == 1.0

    def test_malformed_xml_raises(self):
        with pytest.raises(XbrlParseError):
            extract_figures(b"<not-closed")


class TestDerived:
    def test_operating_profit_adds_back_da_and_finance_costs(self):
        # 1000 - (800 - 40 - 10) = 250
        assert extract_figures(QUARTER)["OneD"].operating_profit == 250.0

    def test_operating_profit_missing_input_is_none(self):
        assert PeriodFigures(revenue=1000.0, expenses=800.0, da=40.0).operating_profit is None

    def test_shares_from_paid_up_and_face_value(self):
        assert extract_figures(QUARTER)["OneD"].shares == 500_000.0

    def test_shares_missing_face_value_is_none(self):
        assert PeriodFigures(paid_up=5_000_000.0).shares is None


class TestArithmeticCheck:
    def test_passes_when_consistent(self):
        # 1000 + 50 - 800 = 250 == reported
        assert arithmetic_check(extract_figures(QUARTER)["OneD"]) is True

    def test_fails_beyond_one_percent(self):
        p = PeriodFigures(revenue=1000.0, other_income=50.0, expenses=800.0, pbt_pre_exceptional=240.0)
        assert arithmetic_check(p) is False

    def test_within_one_percent_passes(self):
        p = PeriodFigures(revenue=1000.0, other_income=50.0, expenses=800.0, pbt_pre_exceptional=248.0)
        assert arithmetic_check(p) is True

    def test_missing_input_is_none_not_pass(self):
        assert arithmetic_check(PeriodFigures(revenue=1000.0, expenses=800.0)) is None
