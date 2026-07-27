"""
QuantOS — Nifty 500 Index-Reconstitution Gut-Check
────────────────────────────────────────────────────────────────────────────
Fable's explicit recommendation (2026-07-24, see memory:
quantos-index-reconstitution-effect-feasibility) before considering any
backtest: a cheap gut-check on whether addition/removal from the Nifty 500
correlates with a return effect around the announcement and effective
dates, mirroring core/fundamentals/pead/gutcheck.py's role for PEAD.
Deliberately minimal -- descriptive group statistics only. NOT a backtest:
no transaction costs, no position sizing, no Sharpe/profit-factor, no
signal threshold.

**The honest sample size, stated up front (see feasibility memory for full
derivation)**: core.rotation.nifty500_reconstitution.EVENTS has 11 events,
162 addition-legs and 162 removal-legs -- but the real independent sample
is ~6 semi-annual "broad" review dates (18-33 symbols each). The 5 "adhoc"
single-symbol events (n=1 each) are reported separately as spot-checks,
never pooled into the broad-review statistic -- pooling all 11 as one
n=162 sample would overstate statistical power the same way PEAD's "3
horizons on 840 rows" did before a Fable review caught that they weren't
independent either.

**Two windows, deliberately kept separate**:
- "anticipation": entry = first trading day strictly after the event's
  announcement date (see _announcement_date_for), exit = last trading day
  strictly BEFORE the effective date. Tests the literature's core claim --
  passive-fund buying/selling pressure anticipated ahead of the effective
  date.
- "post_effective": entry = first trading day at/after the effective date,
  exit = N trading days later (a small fixed horizon set, a diagnostic
  eyeball like PEAD's, not a parameter sweep). Tests whether any
  anticipatory move reverses once passive flows are done.
The effective date's own trading day is deliberately excluded from the
anticipation window and used to open the post_effective window instead,
so a single day's price move is never double-counted in both windows.

**Market adjustment, a deliberate design change from PEAD's, not a copy**:
PEAD's gut-check demeaned by ONE sample-wide mean return, defensible there
because its 2 quarters were 3 months apart. These 11 events span almost 3
years of very different market regimes, so a single global mean would
blend unrelated periods together. Instead, each leg is demeaned by the
mean return of every OTHER matched leg from the SAME event (added +
removed combined, since they share the exact announcement/effective
dates) -- a per-event confound control, not a new tunable parameter.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date
from typing import Optional

from core.fundamentals.pead.eq_bhavcopy import EqCloseRow
from core.fundamentals.pead.gutcheck import PriceIndex, build_price_index  # noqa: F401 (re-exported)
from core.rotation.nifty500_reconstitution import EVENTS, ReconstitutionEvent

# Diagnostic eyeball horizons for the post-effective window, not a
# parameter sweep -- same discipline as PEAD's DEFAULT_HORIZONS_TRADING_DAYS.
DEFAULT_POST_EFFECTIVE_HORIZONS = (5, 10, 20)

_SOURCE_DATE_RE = re.compile(r"ind_prs(\d{2})(\d{2})(\d{4})")

# Per-symbol announcement-date overrides for the 2 "netted" events (see
# nifty500_reconstitution.py's module docstring). Confirmed against each
# event's own docstring by a Fable review 2026-07-24: the 2024-03-28
# event's correction (IREDA/V-Guard) fully CANCELLED both entries, so
# neither appears in that event's added/removed sets at all -- no override
# needed there. The 2024-09-30 event's correction genuinely changed the
# outcome for ONE symbol: PRSMJOHNSN's removal was only decided in the
# 25-Sep-2024 correction filing, not the 23-Aug-2024 base filing, and it
# DOES appear in that event's removed set -- using the base date for it
# would overstate its true announcement lead time by 33 days.
_ANNOUNCEMENT_OVERRIDES: dict[tuple[date, str], date] = {
    (date(2024, 9, 30), "PRSMJOHNSN"): date(2024, 9, 25),
}


def _parse_source_dates(source: str) -> list[date]:
    """Every press-release date embedded in a `source` filename string,
    e.g. "ind_prs28022024.pdf+ind_prs19032024.pdf" -> [2024-02-28,
    2024-03-19]. Filenames encode DDMMYYYY, not the effective date."""
    return [date(int(y), int(m), int(d)) for d, m, y in _SOURCE_DATE_RE.findall(source)]


def _announcement_date_for(event: ReconstitutionEvent, symbol: str) -> date:
    """The real public-announcement date for one symbol's membership
    change within `event`. Defaults to the EARLIEST parsed source date
    (the base release, before any same-cycle correction) except for the
    handful of symbols in _ANNOUNCEMENT_OVERRIDES whose outcome was only
    decided by a later correction filing."""
    override = _ANNOUNCEMENT_OVERRIDES.get((event.effective_date.date(), symbol))
    if override is not None:
        return override
    return min(_parse_source_dates(event.source))


@dataclass(frozen=True)
class EventLeg:
    symbol: str
    event_type: str          # "add" or "remove"
    event_category: str      # "broad" (semi-annual review) or "adhoc" (single-symbol correction)
    announcement_date: date
    effective_date: date
    source: str


def build_legs(events: list[ReconstitutionEvent] = EVENTS) -> list[EventLeg]:
    """One EventLeg per symbol per membership change. `event_category` is
    derived from event size, not a hand-maintained flag -- every real
    broad review has 18+ symbols on each side, every real ad-hoc
    correction has exactly 1 (confirmed by hand-count against live EVENTS,
    see feasibility memory), so a >1 threshold cleanly separates them
    without needing a new field on ReconstitutionEvent itself."""
    legs: list[EventLeg] = []
    for event in events:
        effective = event.effective_date.date()
        category = "broad" if len(event.added) > 1 else "adhoc"
        for symbol in sorted(event.added):
            legs.append(EventLeg(
                symbol=symbol, event_type="add", event_category=category,
                announcement_date=_announcement_date_for(event, symbol),
                effective_date=effective, source=event.source,
            ))
        for symbol in sorted(event.removed):
            legs.append(EventLeg(
                symbol=symbol, event_type="remove", event_category=category,
                announcement_date=_announcement_date_for(event, symbol),
                effective_date=effective, source=event.source,
            ))
    return legs


@dataclass(frozen=True)
class LegReturn:
    leg: EventLeg
    window: str  # "anticipation" or "post_effective"
    entry_date: date
    exit_date: date
    entry_close: float
    exit_close: float
    return_pct: float


# A single-day close ratio outside this band almost certainly reflects an
# UNADJUSTED corporate action (stock split/bonus/scheme-of-arrangement) in
# NSE's raw bhavcopy, not a real one-day price move -- a Fable review
# 2026-07-24 caught this live: METROPOLIS (2026-03-30 event) shows a clean
# overnight Rs 1823.80 -> Rs 441.10 cliff (~4.1x) with zero gradual decline
# before it. NSE bhavcopy closes are NOT corporate-action-adjusted (unlike
# Fyers, see memory: quantos-sprint5-progress's S5-3 finding) -- this is a
# defensive skip, not an attempt to reconstruct the true split-adjusted
# series (which would need the actual split ratio, out of scope for a
# gut-check).
_CORPORATE_ACTION_DAY_RATIO_BAND = (0.5, 2.0)

# Real trading-day cadence for a liquid NSE main-board stock is close to
# calendar_days / 1.4 (weekends + holidays). Thinly-traded/ASM-flagged
# names can have cached rows spaced weeks apart, silently turning a
# "N-trading-day" horizon into months or years. Same Fable review found
# this live: KIRLFER/KENNAMET/JSWHL each had rows spaced ~12-140 days
# apart, turning a claimed 20-trading-day post-effective window into an
# actual ~937-day span for one symbol. Cap generously (3x the naive
# weekends-only calendar estimate) so real holiday clusters don't trip it,
# but a genuine multi-week gap does.
_MAX_CALENDAR_DAYS_MULTIPLIER = 3


def _has_corporate_action_jump(series: list[tuple[date, float]], start_idx: int, end_idx: int) -> bool:
    for i in range(start_idx, end_idx):
        prev_close, next_close = series[i][1], series[i + 1][1]
        if prev_close == 0:
            continue
        ratio = next_close / prev_close
        if not (_CORPORATE_ACTION_DAY_RATIO_BAND[0] <= ratio <= _CORPORATE_ACTION_DAY_RATIO_BAND[1]):
            return True
    return False


def _implausible_calendar_span(entry_date: date, exit_date: date, horizon_trading_days: int) -> bool:
    expected_calendar_days = horizon_trading_days * 7 / 5  # weekends only, ignoring holidays
    return (exit_date - entry_date).days > expected_calendar_days * _MAX_CALENDAR_DAYS_MULTIPLIER


def _anticipation_window_indices(series: list[tuple[date, float]], leg: EventLeg) -> Optional[tuple[int, int]]:
    entry_idx = next((i for i, (d, _) in enumerate(series) if d > leg.announcement_date), None)
    if entry_idx is None:
        return None
    exit_idx = None
    for i, (d, _) in enumerate(series):
        if d < leg.effective_date:
            exit_idx = i
        else:
            break
    if exit_idx is None or exit_idx < entry_idx:
        return None
    return entry_idx, exit_idx


def _post_effective_window_indices(
    series: list[tuple[date, float]], leg: EventLeg, horizon_trading_days: int,
) -> Optional[tuple[int, int]]:
    entry_idx = next((i for i, (d, _) in enumerate(series) if d >= leg.effective_date), None)
    if entry_idx is None:
        return None
    exit_idx = entry_idx + horizon_trading_days
    if exit_idx >= len(series):
        return None
    return entry_idx, exit_idx


def compute_anticipation_return(price_index: PriceIndex, leg: EventLeg) -> Optional[LegReturn]:
    """None (not zero-filled) on missing price data, a suspected unadjusted
    corporate action within the window, or no valid window at all -- a
    symbol like GSPL (absorbed into Gujarat Gas right around its own
    2026-05-12 removal, see nifty500_reconstitution.py's test suite)
    legitimately has no price series covering part of its own event
    window; that's a real data gap to skip and report, not paper over."""
    series = price_index.get(leg.symbol)
    if not series:
        return None
    idxs = _anticipation_window_indices(series, leg)
    if idxs is None:
        return None
    entry_idx, exit_idx = idxs
    if _has_corporate_action_jump(series, entry_idx, exit_idx):
        return None

    entry_date, entry_close = series[entry_idx]
    exit_date, exit_close = series[exit_idx]
    if entry_close == 0:
        return None
    return LegReturn(
        leg=leg, window="anticipation", entry_date=entry_date, exit_date=exit_date,
        entry_close=entry_close, exit_close=exit_close,
        return_pct=(exit_close - entry_close) / entry_close * 100,
    )


def compute_post_effective_return(
    price_index: PriceIndex, leg: EventLeg, horizon_trading_days: int,
) -> Optional[LegReturn]:
    series = price_index.get(leg.symbol)
    if not series:
        return None
    idxs = _post_effective_window_indices(series, leg, horizon_trading_days)
    if idxs is None:
        return None
    entry_idx, exit_idx = idxs
    if _has_corporate_action_jump(series, entry_idx, exit_idx):
        return None

    entry_date, entry_close = series[entry_idx]
    exit_date, exit_close = series[exit_idx]
    if _implausible_calendar_span(entry_date, exit_date, horizon_trading_days):
        return None
    if entry_close == 0:
        return None
    return LegReturn(
        leg=leg, window="post_effective", entry_date=entry_date, exit_date=exit_date,
        entry_close=entry_close, exit_close=exit_close,
        return_pct=(exit_close - entry_close) / entry_close * 100,
    )


def diagnose_anticipation(price_index: PriceIndex, leg: EventLeg) -> Optional[str]:
    """None if compute_anticipation_return would succeed for `leg`;
    otherwise a short reason string. For driver-script reporting only --
    so a leg silently dropped for a real reason (corporate action, no
    valid window) is visible rather than just quietly lowering n, the
    "0 symbols entirely missing" message being misleadingly reassuring
    otherwise (a Fable review 2026-07-24 flagged this: it only catches
    TOTAL absence, not partial-coverage gaps from e.g. NSE's ASM
    trade-for-trade filtering)."""
    series = price_index.get(leg.symbol)
    if not series:
        return "no_price_series"
    idxs = _anticipation_window_indices(series, leg)
    if idxs is None:
        return "no_valid_window"
    entry_idx, exit_idx = idxs
    if _has_corporate_action_jump(series, entry_idx, exit_idx):
        return "corporate_action_suspected"
    return None


def diagnose_post_effective(price_index: PriceIndex, leg: EventLeg, horizon_trading_days: int) -> Optional[str]:
    series = price_index.get(leg.symbol)
    if not series:
        return "no_price_series"
    idxs = _post_effective_window_indices(series, leg, horizon_trading_days)
    if idxs is None:
        return "no_valid_window"
    entry_idx, exit_idx = idxs
    if _has_corporate_action_jump(series, entry_idx, exit_idx):
        return "corporate_action_suspected"
    entry_date, _ = series[entry_idx]
    exit_date, _ = series[exit_idx]
    if _implausible_calendar_span(entry_date, exit_date, horizon_trading_days):
        return "sparse_trading_gap"
    return None


def diagnose_all(
    legs: list[EventLeg], price_index: PriceIndex, window: str, horizon_trading_days: Optional[int] = None,
) -> dict[str, list[EventLeg]]:
    """Groups legs by why they were excluded from `window` ("anticipation"
    or "post_effective", the latter requiring horizon_trading_days).
    Excludes legs that succeeded (reason is None)."""
    out: dict[str, list[EventLeg]] = defaultdict(list)
    for leg in legs:
        if window == "anticipation":
            reason = diagnose_anticipation(price_index, leg)
        else:
            reason = diagnose_post_effective(price_index, leg, horizon_trading_days)
        if reason is not None:
            out[reason].append(leg)
    return dict(out)


def _demean_by_event(pairs: list[LegReturn]) -> list[LegReturn]:
    """Replaces each return with (return - that SAME event's own
    cross-sectional mean return, across every matched leg from that event
    regardless of add/remove/category), grouped by effective_date. See
    module docstring for why this is per-event rather than one global
    mean."""
    by_event: dict[date, list[float]] = defaultdict(list)
    for lr in pairs:
        by_event[lr.leg.effective_date].append(lr.return_pct)
    event_means = {d: statistics.mean(v) for d, v in by_event.items()}
    return [replace(lr, return_pct=lr.return_pct - event_means[lr.leg.effective_date]) for lr in pairs]


@dataclass(frozen=True)
class GroupSummary:
    window: str               # "anticipation" or "post_effective_{h}d"
    event_type: str           # "add" or "remove"
    event_category: str       # "broad" or "adhoc"
    n_legs: int
    n_events: int              # distinct effective_dates contributing -- the REAL sample-size caveat
    mean_return_pct: Optional[float]
    win_rate: Optional[float]
    market_adjusted: bool


def _group_summaries(
    window_label: str, pairs: list[LegReturn], *, market_adjusted: bool,
) -> list[GroupSummary]:
    if market_adjusted:
        pairs = _demean_by_event(pairs)

    out = []
    for event_type in ("add", "remove"):
        for category in ("broad", "adhoc"):
            group = [lr for lr in pairs if lr.leg.event_type == event_type and lr.leg.event_category == category]
            returns = [lr.return_pct for lr in group]
            n_events = len({lr.leg.effective_date for lr in group})
            out.append(GroupSummary(
                window=window_label, event_type=event_type, event_category=category,
                n_legs=len(group), n_events=n_events,
                mean_return_pct=statistics.mean(returns) if returns else None,
                win_rate=(sum(1 for r in returns if r > 0) / len(returns)) if returns else None,
                market_adjusted=market_adjusted,
            ))
    return out


def summarize_anticipation(
    legs: list[EventLeg], price_index: PriceIndex, *, market_adjusted: bool = False,
) -> list[GroupSummary]:
    pairs = [lr for leg in legs if (lr := compute_anticipation_return(price_index, leg)) is not None]
    return _group_summaries("anticipation", pairs, market_adjusted=market_adjusted)


def summarize_post_effective(
    legs: list[EventLeg], price_index: PriceIndex,
    horizons: tuple[int, ...] = DEFAULT_POST_EFFECTIVE_HORIZONS, *, market_adjusted: bool = False,
) -> list[GroupSummary]:
    out = []
    for h in horizons:
        pairs = [
            lr for leg in legs
            if (lr := compute_post_effective_return(price_index, leg, h)) is not None
        ]
        out.extend(_group_summaries(f"post_effective_{h}d", pairs, market_adjusted=market_adjusted))
    return out


def missing_legs(legs: list[EventLeg], price_index: PriceIndex) -> list[EventLeg]:
    """Legs with no price series in price_index at all -- surfaced
    explicitly (not silently folded into a lower n) so a real gap like
    GSPL's is visible in the report, same discipline Fable's review
    checked for (0/58 other removed symbols were missing -- GSPL is a
    genuine, confirmed outlier, not a systemic gap)."""
    return [leg for leg in legs if leg.symbol not in price_index]
