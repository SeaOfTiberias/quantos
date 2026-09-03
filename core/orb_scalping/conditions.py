"""
QuantOS — ORB condition-mining: the six pre-registered features
──────────────────────────────────────────────────────────────────
Pure, I/O-free functions computing the values pinned in
docs/ORB_CONDITION_MINING_METHODOLOGY.md. Every function reads only bars up
to and including the trade's own entry day — no lookahead, same discipline
as core/orb_scalping/signal.py.

Condition 1 (index trend stage) reuses core/vault/stages.py's classifier
unmodified, applied to the index's own daily bars in place of a single
stock's — the same mechanism, a different "symbol". Nothing here
re-implements Weinstein's rules; they are read from
obsidian_vault/QuantOS/brain/Stan_Weinstein_Stage_Analysis.md via
core/vault/parser.py, so a future edit to that note (a hand-authored,
brain/-layer change) changes this mining pass too, rather than drifting
from a private copy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional, Sequence

from core.brokers.base import OHLCV
from core.vault.facts import MarketFacts
from core.vault.models import Stage, StageClause
from core.vault.parser import parse_note
from core.vault.stages import classify

WEINSTEIN_NOTE_PATH = Path("obsidian_vault/QuantOS/brain/Stan_Weinstein_Stage_Analysis.md")
RANGE_TRAILING_WINDOW = 20   # trading days, entry day excluded — pinned in the methodology doc

DTE_BUCKETS = ("0-1", "2-4", "5-9", "10+")


@dataclass(frozen=True)
class TradeConditions:
    """One trade's six condition values, per the methodology doc's list.
    Any field may be None (stage, range_width_ratio, gap_pct) when there
    isn't enough trailing history to compute it — reported as
    unclassified/unavailable, never guessed."""
    entry_date:         date
    stage:              Optional[Stage]     # condition 1
    day_of_week:        str                 # condition 2
    range_width_ratio:  Optional[float]     # condition 3
    gap_pct:            Optional[float]     # condition 4
    days_to_expiry:     int                 # condition 5, raw
    dte_bucket:         str                 # condition 5, bucketed
    exit_reason:        str                 # condition 6, diagnostic only


def load_weinstein_clauses(vault_dir: Optional[Path] = None) -> tuple[StageClause, ...]:
    """Read Weinstein's stage clauses straight from the brain/ note. Raises
    if the note is missing or unparseable — a silent empty-clauses fallback
    would make every trade unclassified without saying why."""
    note = parse_note(WEINSTEIN_NOTE_PATH, vault_dir=vault_dir)
    if not note.stage_clauses:
        raise ValueError(f"{WEINSTEIN_NOTE_PATH} has no quantos-stages block")
    return note.stage_clauses


def opening_range_width(day_candles: Sequence[OHLCV], n_candles: int = 3) -> float:
    """High−low across the first `n_candles` of one day's 5-minute series —
    the same window core/orb_scalping/signal.py's simulate_day uses, just
    exposed as a standalone value for condition 3."""
    range_candles = day_candles[:n_candles]
    return max(c.high for c in range_candles) - min(c.low for c in range_candles)


def index_stage_at(
    daily_bars: Sequence[OHLCV], entry_date: date, clauses: Sequence[StageClause],
) -> Optional[Stage]:
    """Weinstein stage of the index as of `entry_date`, computed from the
    FULL daily series but addressed at the bar offset for that date — sma()
    is a trailing (backward-only) average, so this never reads a bar after
    entry_date. None if entry_date isn't in the series, or the classifier
    can't resolve it (unclassified — not a guessed stage)."""
    dates = [b.timestamp.date() for b in daily_bars]
    if entry_date not in dates:
        return None
    idx = dates.index(entry_date)
    offset = len(daily_bars) - 1 - idx
    facts = MarketFacts("INDEX", list(daily_bars))
    return classify(clauses, facts, offset=offset).stage


def day_of_week(entry_date: date) -> str:
    return entry_date.strftime("%A")


def range_width_ratio(
    day_candles: Sequence[OHLCV], trailing_widths: Sequence[float],
) -> Optional[float]:
    """Today's opening-range width vs the trailing average of the entry
    day's own history of opening-range widths (caller supplies the last
    RANGE_TRAILING_WINDOW days' widths, entry day excluded — no lookahead).
    None with no trailing history yet. >1 = today's range is wider than
    usual for this index."""
    if not trailing_widths:
        return None
    avg = sum(trailing_widths) / len(trailing_widths)
    if avg <= 0:
        return None
    return opening_range_width(day_candles) / avg


def gap_pct(today_first_candle_open: float, prior_daily_close: Optional[float]) -> Optional[float]:
    """Signed % gap: today's first 5-minute candle's open vs the prior
    trading day's daily close. None if there's no prior close (first bar
    of the series)."""
    if not prior_daily_close:
        return None
    return (today_first_candle_open - prior_daily_close) / prior_daily_close * 100.0


def bucket_dte(days_to_expiry: int) -> str:
    """Four buckets, pinned before any result exists (methodology doc)."""
    if days_to_expiry <= 1:
        return "0-1"
    if days_to_expiry <= 4:
        return "2-4"
    if days_to_expiry <= 9:
        return "5-9"
    return "10+"
