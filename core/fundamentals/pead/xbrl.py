"""
QuantOS — PEAD Phase 1: XBRL Quarterly-PAT Extraction
────────────────────────────────────────────────────────
Extracts net profit ("ProfitLossForPeriod") from NSE's per-filing XBRL
XML, confirmed live 2026-07-23 against real filings spanning market-cap
tiers (RELIANCE, DIXON, PVRINOX, CENTURYPLY).

**Context-ID convention, confirmed empirically, not assumed from a spec**:
these NSE "_WEB" XBRL renderings do NOT locally define the base entity-level
contexts ("OneD", "FourD", ...) the way they define document-specific
segment/OCI contexts -- they're referenced directly with no local
`<xbrli:context id="OneD">` in the file at all. This means the standard
context IDs are an implicit convention NSE's own backend (and this module)
must hardcode, not something derivable per-file from an explicit date
range:

  - "OneD" = the filing's OWN reporting quarter (e.g. Oct-Dec for a Q3
    filing) -- this is the figure PEAD needs.
  - "FourD" = year-to-date cumulative from the start of that financial
    year through the end of the reporting quarter (e.g. Apr-Dec for a Q3
    filing) -- NOT the quarter alone. Confirmed by cross-checking
    magnitude against OneD on a real RELIANCE Q3 filing (FourD ~= 2.8x
    OneD, consistent with 3 quarters' cumulative vs 1).

**No prior-year comparative figure is present in this file at all** --
"TwoD"/"ThreeD"/"FiveD"/"SixD" (which would carry sequential- or
YoY-comparison periods under the same naming family) were checked and are
absent from every context tested. YoY surprise is NOT computable from a
single filing; core.fundamentals.pead.pipeline computes it by joining two
separate filings (this quarter's + the same quarter one year prior) from
its own point-in-time table.

Tag namespace prefixes are NOT assumed stable across filers (banks/NBFCs
use different taxonomy extensions than non-financials) -- this module
matches on local tag name only, via a namespace-agnostic parse rather than
a hardcoded `in-bse-fin:` prefix.

**Banks/NBFCs use a DIFFERENT tag name, confirmed live 2026-07-23**: a real
HDFCBANK filing (and, by the same live smoke-test run, every one of 28
other bank/NBFC Nifty 500 constituents -- SBIN, ICICIBANK, KOTAKBANK,
AXISBANK, etc.) tags its quarterly PAT as `ProfitLossForThePeriod` ("For
THE Period"), not `ProfitLossForPeriod` -- same "OneD"/"FourD" context
convention, just a different local name under the banking taxonomy
extension. Cross-checked HDFCBANK's OneD value (Rs 17,825.91 crore for a
real Oct-Dec 2024 quarter) as a sane real figure before trusting the tag.
Both names are treated as equivalent below; skipping this would have
silently zeroed out PEAD coverage for the entire banking/NBFC sector, a
large chunk of Nifty 500 by weight.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

_PAT_LOCAL_NAMES = ("ProfitLossForPeriod", "ProfitLossForThePeriod")

# See module docstring: fixed by NSE's own filing convention, not derived
# per-file. Only OneD is currently used by the pipeline; FourD is kept
# here (rather than discarded) so a caller can sanity-check the ratio, and
# TwoD/ThreeD/FiveD/SixD are included in case a future filing generation
# starts populating them.
STANDARD_CONTEXT_IDS = ("OneD", "TwoD", "ThreeD", "FourD", "FiveD", "SixD")
CURRENT_QUARTER_CONTEXT = "OneD"

DEAD_XBRL_LINK_SUFFIX = "/xbrl/-"


class XbrlParseError(Exception):
    """Raised when a filing's XBRL is malformed or reports conflicting
    values for the same context -- surfaced immediately rather than
    silently picking one, same discipline as the VRP settle_price bug
    (see memory: quantos-vrp-data-feasibility)."""


def is_xbrl_available(xbrl_url: str) -> bool:
    """False for `format == "Old"` filings, whose `xbrl` field is a dead
    placeholder link (confirmed live: every pre-2018 "Old" filing tested
    carried this exact suffix, never a real file)."""
    return bool(xbrl_url) and not xbrl_url.rstrip().endswith(DEAD_XBRL_LINK_SUFFIX)


def _local_name(tag: str) -> str:
    # ElementTree renders namespaced tags as "{uri}LocalName".
    return tag.rsplit("}", 1)[-1]


@dataclass(frozen=True)
class QuarterlyPat:
    context_id: str
    value: float  # raw rupees


def extract_pat_by_context(xbrl_bytes: bytes) -> dict[str, QuarterlyPat]:
    """Every ProfitLossForPeriod fact found, keyed by contextRef. Only
    context IDs in STANDARD_CONTEXT_IDS are returned -- segment-breakdown
    variants (e.g. "OneReportableSegmentResults01D") are a different
    concept and explicitly excluded.

    Raises XbrlParseError if the same standard context ID appears more
    than once with different values (should never happen; if it does, the
    file's structure isn't what this module assumes and that needs
    investigating, not silently resolving)."""
    try:
        root = ET.fromstring(xbrl_bytes)
    except ET.ParseError as e:
        raise XbrlParseError(f"malformed XBRL XML: {e}") from e

    found: dict[str, float] = {}
    for elem in root.iter():
        if _local_name(elem.tag) not in _PAT_LOCAL_NAMES:
            continue
        ctx = elem.get("contextRef")
        if ctx not in STANDARD_CONTEXT_IDS:
            continue
        text = (elem.text or "").strip()
        if not text:
            continue
        value = float(text)
        if ctx in found and found[ctx] != value:
            raise XbrlParseError(
                f"conflicting PAT values for context {ctx}: "
                f"{found[ctx]} vs {value}"
            )
        found[ctx] = value

    return {ctx: QuarterlyPat(context_id=ctx, value=v) for ctx, v in found.items()}


def extract_quarterly_pat(xbrl_bytes: bytes) -> float:
    """The single figure PEAD needs: this filing's OWN reporting-quarter
    PAT (context "OneD"). Raises XbrlParseError if absent -- callers
    should treat that as "this filing can't be used," not silently skip."""
    facts = extract_pat_by_context(xbrl_bytes)
    if CURRENT_QUARTER_CONTEXT not in facts:
        raise XbrlParseError(
            f"no PAT fact ({'/'.join(_PAT_LOCAL_NAMES)}) found for context "
            f"{CURRENT_QUARTER_CONTEXT!r} (found contexts: {sorted(facts)})"
        )
    return facts[CURRENT_QUARTER_CONTEXT].value
