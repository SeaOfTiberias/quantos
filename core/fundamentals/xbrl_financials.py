"""
QuantOS — P&L + share-capital fields from NSE results XBRL
───────────────────────────────────────────────────────────
For the techno-funda candidate (docs/TECHNO_FUNDA_PREREG_2026-11-01.md):
OPM, YoY profit growth and market cap, built only from figures the company
filed. Same conventions as core.fundamentals.pead.xbrl, which this
generalises from PAT to a set of fields:

  - tags matched on local name only (namespace prefixes vary by filer);
  - "OneD" = the filing's own quarter, "FourD" = year to date;
  - the same field reported twice in one context with different values
    raises XbrlParseError instead of picking one.

Financial-format filers (banks, NBFCs, insurers) are excluded upstream, so
only the standard Ind-AS (Schedule III Division II) tag names are read here.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

from core.fundamentals.pead.xbrl import XbrlParseError, _local_name

FIELDS = {
    "RevenueFromOperations": "revenue",
    "OtherIncome": "other_income",
    "Income": "income",
    "Expenses": "expenses",
    "DepreciationDepletionAndAmortisationExpense": "da",
    "FinanceCosts": "finance_costs",
    "ProfitBeforeExceptionalItemsAndTax": "pbt_pre_exceptional",
    "ProfitLossForPeriod": "pat",
    "PaidUpValueOfEquityShareCapital": "paid_up",
    "FaceValueOfEquityShareCapital": "face_value",
}
CONTEXTS = ("OneD", "FourD")


@dataclass(frozen=True)
class PeriodFigures:
    """One context's figures, raw rupees (face_value in rupees per share)."""
    revenue: Optional[float] = None
    other_income: Optional[float] = None
    income: Optional[float] = None
    expenses: Optional[float] = None
    da: Optional[float] = None
    finance_costs: Optional[float] = None
    pbt_pre_exceptional: Optional[float] = None
    pat: Optional[float] = None
    paid_up: Optional[float] = None
    face_value: Optional[float] = None

    @property
    def operating_profit(self) -> Optional[float]:
        """Revenue minus expenses other than D&A and finance costs (the
        Screener-style OPM numerator). None if any input is missing."""
        if None in (self.revenue, self.expenses, self.da, self.finance_costs):
            return None
        return self.revenue - (self.expenses - self.da - self.finance_costs)

    @property
    def shares(self) -> Optional[float]:
        if not self.paid_up or not self.face_value:
            return None
        return self.paid_up / self.face_value


def extract_figures(xbrl_bytes: bytes) -> dict[str, PeriodFigures]:
    """{context: PeriodFigures} for the OneD and FourD contexts present."""
    try:
        root = ET.fromstring(xbrl_bytes)
    except ET.ParseError as e:
        raise XbrlParseError(f"malformed XBRL XML: {e}") from e

    found: dict[str, dict[str, float]] = {c: {} for c in CONTEXTS}
    for elem in root.iter():
        field = FIELDS.get(_local_name(elem.tag))
        ctx = elem.get("contextRef")
        if field is None or ctx not in found:
            continue
        text = (elem.text or "").strip()
        if not text:
            continue
        value = float(text)
        prior = found[ctx].get(field)
        if prior is not None and prior != value:
            raise XbrlParseError(f"conflicting {field} values for context {ctx}: {prior} vs {value}")
        found[ctx][field] = value
    return {c: PeriodFigures(**v) for c, v in found.items() if v}


def arithmetic_check(p: PeriodFigures, tol: float = 0.01) -> Optional[bool]:
    """Gate D3(a): revenue + other income - total expenses is within `tol`
    of reported profit before exceptional items and tax. None if an input
    is missing (reported separately, not counted as a pass)."""
    if None in (p.revenue, p.expenses, p.pbt_pre_exceptional):
        return None
    calc = p.revenue + (p.other_income or 0.0) - p.expenses
    return abs(calc - p.pbt_pre_exceptional) <= tol * abs(p.pbt_pre_exceptional)
