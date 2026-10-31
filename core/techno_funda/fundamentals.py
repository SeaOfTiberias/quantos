"""
Point-in-time fundamentals for the techno-funda candidate
──────────────────────────────────────────────────────────
Rules from docs/TECHNO_FUNDA_PREREG_2026-11-01.md (+ amendment 1):

  - A filing is usable on day t only if it was broadcast on a calendar day
    before t. Each revision applies from its own broadcast date.
  - Financial-format filers are ineligible. Old feed: bank/indAs fields.
    Integrated feed: the XBRL file-name prefix. No classification -> None,
    and the stock is ineligible while that filing is its latest.
  - Latest usable quarter Q; consolidated if a usable consolidated filing for
    Q exists, else standalone; comparisons only within one type.
  - Profit growth = (PAT_Q - PAT_Q-4) / PAT_Q-4, both PATs positive.
  - OPM (TTM) = sum(operating profit) / sum(revenue) over Q..Q-3.
  - Shares = paid-up capital / face value from a usable filing for Q.

Nothing is filled in: any missing input leaves the value None.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

from core.fundamentals.pead.xbrl import XbrlParseError
from core.fundamentals.xbrl_financials import PeriodFigures, extract_figures
from core.techno_funda.symbols import SymbolChain

META_DIR = Path("data_cache/pead_nse/metadata_raw")
IF_META_DIR = Path("data_cache/pead_nse/if_metadata_raw")
XBRL_DIR = Path("data_cache/pead_nse/xbrl_raw")
META_FROM, META_TO = "201804", "202610"
IF_STANDARD_PREFIX = "INTEGRATED_FILING_INDAS_"
IF_PREFIX = "INTEGRATED_FILING_"
_TS = "%d-%b-%Y %H:%M:%S"


@dataclass(frozen=True)
class Filing:
    symbol: str                      # canonical
    broadcast: datetime
    period_end: date
    consolidated: bool
    financial: Optional[bool]        # None = no classification on the filing
    quarter: Optional[PeriodFigures]  # OneD; None if not downloaded / unparseable
    ytd: Optional[PeriodFigures]      # FourD
    feed: str                        # "old" | "integrated"
    key: str                         # cache file name or seq number
    parse_error: bool = False
    relating: Optional[str] = None   # old feed only, e.g. "Fourth Quarter"


def old_feed_financial(r: dict) -> Optional[bool]:
    bank, ind = r.get("bank"), r.get("indAs")
    if bank in ("B", "F") or ind in ("NBFC-IND", "Non-Ind-AS"):
        return True
    if bank == "N" and ind == "Ind-AS New":
        return False
    return None


def integrated_financial(r: dict) -> Optional[bool]:
    name = (r.get("xbrl") or "").rsplit("/", 1)[-1]
    if name.startswith(IF_STANDARD_PREFIX):
        return False
    if name.startswith(IF_PREFIX):
        return True
    return None


def _figures(path: Path) -> tuple[Optional[PeriodFigures], Optional[PeriodFigures], bool]:
    if not path.exists():
        return None, None, False
    try:
        f = extract_figures(path.read_bytes())
    except XbrlParseError:
        return None, None, True
    return f.get("OneD"), f.get("FourD"), False


def load_filings(chain: SymbolChain, meta_dir: Path = META_DIR, if_dir: Path = IF_META_DIR,
                 xbrl_dir: Path = XBRL_DIR) -> list[Filing]:
    out: list[Filing] = []
    for p in sorted(meta_dir.glob("*.json")):
        if not META_FROM <= p.stem <= META_TO:
            continue
        for r in json.loads(p.read_text(encoding="utf-8")):
            b = datetime.strptime(r["broadCastDate"], _TS)
            fin = old_feed_financial(r)
            q, y, err = _figures(xbrl_dir / f"{r['seqNumber']}.xml") if fin is False else (None, None, False)
            out.append(Filing(chain.canonical(r["symbol"].strip(), b.date()), b,
                              datetime.strptime(r["toDate"], "%d-%b-%Y").date(),
                              r.get("consolidated") == "Consolidated", fin, q, y, "old",
                              str(r["seqNumber"]), err, r.get("relatingTo")))
    for p in sorted(if_dir.glob("*.json")):
        for r in json.loads(p.read_text(encoding="utf-8")):
            # revisions carry no broadcast_Date; revised_Date is NSE's timestamp of the revision
            b = datetime.strptime(r["broadcast_Date"] or r["revised_Date"], _TS)
            fin = integrated_financial(r)
            name = f"if_{r['seq_Id']}.xml"
            q, y, err = _figures(xbrl_dir / name) if fin is False else (None, None, False)
            out.append(Filing(chain.canonical(r["symbol"].strip(), b.date()), b,
                              datetime.strptime(r["qe_Date"], "%d-%b-%Y").date(),
                              r.get("consolidated") == "Consolidated", fin, q, y, "integrated",
                              name, err))
    return out


# ─── Point-in-time state ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class FundState:
    effective: date                  # usable from this calendar day on
    financial: Optional[bool]
    quarter_end: Optional[date]
    consolidated: Optional[bool]
    growth: Optional[float]
    growth_inputs: bool              # both PATs present (growth may still be None: a loss)
    opm: Optional[float]
    opm_inputs: bool
    shares: Optional[float]


def _ym(d: date) -> tuple[int, int]:
    return d.year, d.month


def _shift(ym: tuple[int, int], months: int) -> tuple[int, int]:
    n = ym[0] * 12 + ym[1] - 1 - months
    return n // 12, n % 12 + 1


def state_from(usable: list[Filing], effective: date) -> FundState:
    """The state a stock has on `effective`, given the filings usable then
    (each broadcast on an earlier calendar day)."""
    latest = max(usable, key=lambda f: f.broadcast)
    std = [f for f in usable if f.financial is False]
    if latest.financial is not False or not std:
        return FundState(effective, latest.financial, None, None, None, False, None, False, None)

    q = max(_ym(f.period_end) for f in std)
    cons = any(f.consolidated and _ym(f.period_end) == q for f in std)
    # latest usable version of each quarter, within the chosen type
    version: dict[tuple[int, int], Filing] = {}
    for f in sorted(std, key=lambda f: f.broadcast):
        if f.consolidated == cons:
            version[_ym(f.period_end)] = f

    def fig(ym: tuple[int, int]) -> Optional[PeriodFigures]:
        f = version.get(ym)
        return f.quarter if f else None

    cur, yago = fig(q), fig(_shift(q, 12))
    growth_inputs = bool(cur and yago and cur.pat is not None and yago.pat is not None)
    growth = None
    if growth_inputs and cur.pat > 0 and yago.pat > 0:
        growth = (cur.pat - yago.pat) / yago.pat

    quarters = [fig(_shift(q, 3 * k)) for k in range(4)]
    opm_inputs = all(x is not None and x.operating_profit is not None and x.revenue is not None
                     for x in quarters)
    opm = None
    if opm_inputs:
        rev = sum(x.revenue for x in quarters)
        if rev > 0:
            opm = sum(x.operating_profit for x in quarters) / rev

    shares = next((f.quarter.shares for f in sorted(std, key=lambda f: f.broadcast, reverse=True)
                   if _ym(f.period_end) == q and f.quarter and f.quarter.shares), None)
    return FundState(effective, False, version[q].period_end if q in version else None, cons,
                     growth, growth_inputs, opm, opm_inputs, shares)


def states_for_symbol(filings: Iterable[Filing]) -> list[FundState]:
    """One state per broadcast day, effective from the next calendar day."""
    by_day: dict[date, list[Filing]] = defaultdict(list)
    for f in filings:
        by_day[f.broadcast.date()].append(f)
    usable: list[Filing] = []
    out = []
    for d in sorted(by_day):
        usable += by_day[d]
        out.append(state_from(usable, d + timedelta(days=1)))
    return out


def all_states(filings: list[Filing]) -> dict[str, list[FundState]]:
    by_sym: dict[str, list[Filing]] = defaultdict(list)
    for f in filings:
        by_sym[f.symbol].append(f)
    return {s: states_for_symbol(fs) for s, fs in by_sym.items()}
