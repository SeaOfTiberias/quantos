"""
QuantOS — Momentum + Base Quality Shortlist (discretionary swing-trading aid)
──────────────────────────────────────────────────────────────────────────────
NOT a signal, NOT a strategy, no execution path. Every attempt to *automate*
trading on a Darvas breakout has failed on turnover/cost grounds (S7-3's
"no demonstrated edge" verdict, candidate 18's live-spread stress test). The
S8-3/candidate-11 momentum family is the one ranking formula that survived
Fable's unanchored re-evaluation against VCP and Stage Analysis (memory:
quantos-fable-anchoring-vcp-stage-review) — but even that is still awaiting
its own out-of-sample verdict (quantos-momentum-turnover-walkforward-status).
So it's used here only to RANK names for a human to look at, never to size
or place an order.

Combines two independently-built, already-tested primitives:
  - core/rotation/ranker.py's 52-week-high-proximity score (close / rolling
    252-day high) — the best-evidenced relative-strength signal this project
    has found.
  - core/darvas/weekly_discovery.py's weekly box state machine — never shown
    to misidentify a genuine consolidation, only shown to have no edge when
    automated as an entry/exit trigger. Used here purely to label whether a
    name is currently basing tightly (worth a human's attention for a
    lower-risk entry) or already extended (worth watching for a pullback).
  - a daily EMA9/EMA21 trend gate (added 2026-07-29 after GLENMARK showed
    up labeled "building a base" while actively rolling over — the box
    state machine only detects sideways-ness, never direction, so a tight
    range mid-downtrend and a genuine bullish pause looked identical to it).
    A "tight" base only counts toward a bucket if the name is also in a
    short-term uptrend by this measure.

Output is a mechanical, reproducible label — not a recommendation. A human
still decides whether/when/how much to buy.
"""

import bisect
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.brokers.base import OHLCV
from core.darvas.weekly_discovery import DiscoveryResult, analyse_symbol
from core.rotation.ranker import LOOKBACK_DAYS, SymbolSeries, rolling_high_series, value_as_of

# Daily EMA9/EMA21 trend gate. Confirmed live 2026-07-29: GLENMARK had a
# "tight" weekly Darvas box (width in the narrowest tercile) while its
# daily EMA9 had already crossed under EMA21 four sessions earlier -- an
# active short-term downtrend the box detector's own logic can't see, since
# it only tracks whether price has stopped making new highs/lows, never
# which direction it's actually headed. A range that's merely "not making
# new highs or lows" is satisfied just as easily by a stock rolling over as
# by one genuinely pausing mid-uptrend, so "tight" alone isn't enough to
# call something a constructive base worth a human's attention. This is
# the same EMA9/EMA21 check a discretionary trader would eyeball on a daily
# chart, chosen over a slower filter (e.g. price vs. 50/200 SMA) precisely
# because it reacts fast enough to catch a fresh rollover like GLENMARK's.
EMA_FAST = 9
EMA_SLOW = 21

# The classic 50/200 SMA pair ("golden"/"death" cross). Purely DESCRIPTIVE
# here -- it labels a well-known chart condition a human is going to check
# anyway, and deliberately feeds no bucket, no ranking and no order. This
# project has already killed several trend-following candidates on real
# evidence, so nothing about showing this column implies it has an edge;
# it exists so the user doesn't have to open a chart to see the alignment.
#
# SMA, not EMA (see sma_series): the cross date has to agree with what
# TradingView shows when the user clicks through from the symbol link.
MA_FAST = 50
MA_SLOW = 200

# Top third of the scanned universe by 52-week-high proximity = "LEADER"
# tier. Middle/bottom thirds are still returned (nothing here hides a name),
# just ranked and labeled lower-priority for a momentum-focused review.
LEADER_TERCILE = 1 / 3

# "Tight base" is the narrowest third of box widths AMONG names that
# currently have a live weekly box, not a fixed percentage cutoff. A fixed
# 4% threshold (core/darvas/box.py's DarvasBox.is_tight, borrowed here in an
# earlier version) was calibrated for that module's short-window intraday
# boxes and never matched this weekly engine's own natural scale — a live
# run against Nifty Alpha 50 (2026-07-29) came back with confirmed-box
# widths of 8.6%-34.1% and zero names under 4%, so every name silently
# landed in WATCH/LEADER_EXTENDED regardless of how narrow its base
# actually was relative to its peers. Ranking widths against each other,
# same as the momentum tercile above, self-calibrates to whatever this
# engine's real distribution is instead of guessing a magic number.
TIGHT_BASE_TERCILE = 1 / 3

# Darvas statuses that represent an actual, currently-live box (as opposed
# to "BOX FORMING", which has no confirmed ceiling/floor yet to be tight).
_LIVE_BASE_STATUSES = ("FRESH BREAKOUT", "APPROACHING", "WATCHING")

BUCKET_PRIORITY = {
    "LEADER_TIGHT_BASE": 0,
    "LEADER_EXTENDED": 1,
    "BUILDING_BASE": 2,
    "WATCH": 3,
}


@dataclass
class VaultNoteScore:
    """One strategy note's verdict on one symbol.

    Declared here rather than in core/vault so this module keeps its promise
    of importing nothing from the vault — it is a plain data holder that the
    annotator fills in, not a vault type. See core/vault/shortlist_audit.py.
    """
    label:        str                  # column header, from the note's quantos.label
    strategy_id:  str
    verdict:      str                  # PASS | FAIL | INSUFFICIENT_DATA | UNAVAILABLE
    rules_passed: int
    rules_total:  int


@dataclass
class ShortlistEntry:
    symbol:         str
    close:          float
    momentum_pct:   float              # close / rolling_52w_high * 100
    momentum_rank:  int                # 1 = closest to its 52-week high
    momentum_tier:  str                # LEADER | MIDPACK | LAGGARD
    bucket:         str                # LEADER_TIGHT_BASE | LEADER_EXTENDED | BUILDING_BASE | WATCH
    base_status:    str                # weekly_discovery status, or "NO BASE" if analyse_symbol returned None
    trend_up:       bool               # daily EMA9 > EMA21 -- see EMA_FAST/EMA_SLOW's comment
    box_width_pct:  Optional[float] = None
    dist_to_ceil:   Optional[float] = None
    rr_ratio:       Optional[float] = None
    vol_ratio:      float = 0.0
    # Derived display fields (2026-08-11). base_status is retained above --
    # it is what Darvas actually said, and dropping it would make a stored
    # entry harder to reconcile against the engine -- but the cockpit shows
    # breakout_state instead, because base_status is ambiguous by construction.
    breakout_state: str = "NO BASE"     # FRESH | OUT | NEAR | IN BOX | NO BASE
    days_above_ceil: Optional[int] = None   # sessions closed above the box ceiling
    ma_cross:       Optional[str] = None    # BULL | BEAR (50 vs 200 SMA), None if not warmed up
    ma_cross_days:  Optional[int] = None    # sessions since the flip, None if older than our window
    # Obsidian vault audit (2026-08-14). Populated by
    # core/vault/shortlist_audit.py AFTER build_shortlist has run -- this
    # module stays pure and vault-unaware, and the annotation is optional, so
    # a missing or broken vault costs the shortlist nothing. None means the
    # audit was never attempted; see core/vault/models.py's Verdict for the
    # difference between "not attempted" and "could not be evaluated".
    vault_verdict:  Optional[str] = None    # PASS | FAIL | INSUFFICIENT_DATA | UNAVAILABLE
    vault_detail:   Optional[str] = None    # per-note verdicts, human-readable
    # Rule tally across every note audited. Both bundled notes are strict
    # conjunctive screens, so the verdict alone reads FAIL for nearly every
    # name on nearly every day and cannot separate "missed by one rule" from
    # "nowhere close". None when no audit produced results (never zero --
    # 0/0 and "not attempted" are different states).
    vault_rules_passed: Optional[int] = None
    vault_rules_total:  Optional[int] = None
    # Per-note scores, one per configured strategy note. This is what the
    # cockpit renders. The aggregate above is retained because a gate still
    # needs a single answer, but it must NOT be read as "how good is this
    # name": measured 2026-08-14 on 482 Nifty 500 names, the two bundled
    # notes' clean-pass sets were DISJOINT, because Minervini's volume dry-up
    # and Weinstein's volume expansion are opposed conditions describing
    # consecutive phases. Conjoining them asks for a name that is
    # pre-breakout and post-breakout at once.
    vault_notes: tuple["VaultNoteScore", ...] = ()
    # Weinstein stage classification (2026-08-17). Separate from the fields
    # above and deliberately so: those answer "do the note's conditions
    # hold?" and are conjunctive PASS/FAIL, this answers "where in the cycle
    # is this name?" and is a mutually-exclusive 1-4. Summing or mixing them
    # would repeat the mistake the vault_notes comment describes.
    #
    # None means UNCLASSIFIED, never "stage 1" -- a name without enough
    # history is unknown, not basing. See core/vault/stages.py.
    stage:        Optional[int] = None      # 1 Basing | 2 Advancing | 3 Topping | 4 Declining
    stage_phase:  Optional[str] = None      # optional sub-label, e.g. "pivot" / "pullback"
    stage_detail: Optional[str] = None      # which note classified it, and on what numbers


def ema_series(closes: list[float], period: int) -> list[Optional[float]]:
    """Standard EMA, SMA-seeded: None for the first `period`-1 bars (not
    warmed up), then the seed SMA, then the usual recursive smoothing."""
    if len(closes) < period:
        return [None] * len(closes)
    k = 2 / (period + 1)
    result: list[Optional[float]] = [None] * (period - 1)
    prev = sum(closes[:period]) / period
    result.append(prev)
    for c in closes[period:]:
        prev = c * k + prev * (1 - k)
        result.append(prev)
    return result


def is_uptrend(daily: list[OHLCV], as_of_date: datetime,
                 fast: int = EMA_FAST, slow: int = EMA_SLOW) -> bool:
    """EMA(fast) > EMA(slow) on daily closes, evaluated at the most recent
    bar at or before as_of_date. False (not just "unknown") when there
    isn't enough history to warm up either EMA -- a base can't be called
    constructive on data we don't have."""
    dates = [c.timestamp for c in daily]
    idx = bisect.bisect_right(dates, as_of_date) - 1
    if idx < 0:
        return False
    closes = [c.close for c in daily[:idx + 1]]
    ema_fast = ema_series(closes, fast)
    ema_slow = ema_series(closes, slow)
    if ema_fast[-1] is None or ema_slow[-1] is None:
        return False
    return ema_fast[-1] > ema_slow[-1]


def sma_series(closes: list[float], period: int) -> list[Optional[float]]:
    """Simple moving average, None until warmed up. Kept separate from
    ema_series because the 50/200 cross is conventionally an SMA cross —
    using an EMA here would silently report cross dates that disagree with
    every chart the user cross-checks against."""
    if len(closes) < period:
        return [None] * len(closes)
    result: list[Optional[float]] = [None] * (period - 1)
    window = sum(closes[:period])
    result.append(window / period)
    for i in range(period, len(closes)):
        window += closes[i] - closes[i - period]
        result.append(window / period)
    return result


def ma_cross_state(daily: list[OHLCV], as_of_date: datetime,
                   fast: int = MA_FAST, slow: int = MA_SLOW,
                   ) -> tuple[Optional[str], Optional[int]]:
    """(state, sessions_since_cross) for the classic 50/200 SMA pair.

    state is "BULL" (fast above slow) or "BEAR", or None when there isn't
    enough history to warm up the slow SMA. sessions_since_cross is how many
    bars ago the pair last flipped, or None if it never flipped inside the
    data we hold — the honest answer for a stock that has been in the same
    alignment longer than our ~400-calendar-day fetch window, and the reason
    the cockpit renders a bare "BULL" rather than inventing an age.

    Only ranked symbols reach this, and ranking already requires >=252 daily
    bars, so the slow SMA is defined for at least ~50 bars in practice.
    """
    dates = [c.timestamp for c in daily]
    idx = bisect.bisect_right(dates, as_of_date) - 1
    if idx < 0:
        return None, None
    closes = [c.close for c in daily[:idx + 1]]

    fast_ma = sma_series(closes, fast)
    slow_ma = sma_series(closes, slow)
    if fast_ma[-1] is None or slow_ma[-1] is None:
        return None, None

    state = "BULL" if fast_ma[-1] > slow_ma[-1] else "BEAR"

    # Walk back to the most recent bar whose alignment differs from today's;
    # the cross happened on the bar after it.
    current_above = fast_ma[-1] > slow_ma[-1]
    for age, i in enumerate(range(len(closes) - 2, -1, -1), start=1):
        if fast_ma[i] is None or slow_ma[i] is None:
            break
        if (fast_ma[i] > slow_ma[i]) != current_above:
            return state, age
    return state, None


def breakout_state(base: Optional[DiscoveryResult], daily: list[OHLCV],
                   as_of_date: datetime) -> tuple[str, Optional[int]]:
    """(state, sessions_above_ceiling) — the unambiguous version of
    DiscoveryResult.status.

    weekly_discovery's own status collapses three different situations into
    "WATCHING": broke out days ago on volume, sits above the ceiling without
    a volume surge, and sits inside the box. dist_to_ceil already carries the
    distinction (negative = above the ceiling) and the label discards it, so
    a name that cleared its box a fortnight ago is indistinguishable from one
    still consolidating. This recovers that.

    States: FRESH (defer to Darvas's own first-day-out + volume test),
    OUT (above the ceiling, with how many sessions), NEAR (below but within
    Darvas's proximity band), IN BOX, NO BASE.
    """
    if base is None or base.box_ceiling is None or base.dist_to_ceil is None:
        return "NO BASE", None

    if base.status == "FRESH BREAKOUT":
        return "FRESH", _sessions_above(daily, base.box_ceiling, as_of_date)
    if base.dist_to_ceil < 0:
        return "OUT", _sessions_above(daily, base.box_ceiling, as_of_date)
    if base.status == "APPROACHING":
        return "NEAR", None
    return "IN BOX", None


def _sessions_above(daily: list[OHLCV], ceiling: float,
                    as_of_date: datetime) -> Optional[int]:
    """Consecutive daily closes above `ceiling`, counting back from as_of_date.
    None if the latest bar isn't above it at all."""
    dates = [c.timestamp for c in daily]
    idx = bisect.bisect_right(dates, as_of_date) - 1
    if idx < 0 or daily[idx].close <= ceiling:
        return None
    count = 0
    while idx >= 0 and daily[idx].close > ceiling:
        count += 1
        idx -= 1
    return count


def _momentum_tier(rank: int, total: int) -> str:
    tercile_size = max(1, round(total * LEADER_TERCILE))
    if rank <= tercile_size:
        return "LEADER"
    if rank <= total - tercile_size:
        return "MIDPACK"
    return "LAGGARD"


def _tight_base_symbols(base_by_symbol: dict[str, Optional[DiscoveryResult]]) -> set[str]:
    """Symbols in the narrowest TIGHT_BASE_TERCILE of box width, among only
    those with a currently-live base (a symbol with no base, or one still
    BOX FORMING, is never "tight" regardless of any width value)."""
    live = sorted(
        (base.box_width_pct, symbol)
        for symbol, base in base_by_symbol.items()
        if base is not None
        and base.status in _LIVE_BASE_STATUSES
        and base.box_width_pct is not None
    )
    if not live:
        return set()
    tercile_size = max(1, round(len(live) * TIGHT_BASE_TERCILE))
    return {symbol for _, symbol in live[:tercile_size]}


def _bucket(momentum_tier: str, has_tight_base: bool) -> str:
    if momentum_tier == "LEADER":
        return "LEADER_TIGHT_BASE" if has_tight_base else "LEADER_EXTENDED"
    return "BUILDING_BASE" if has_tight_base else "WATCH"


def build_shortlist(
    daily_by_symbol: dict[str, list[OHLCV]],
    as_of_date: datetime,
    momentum_window: int = LOOKBACK_DAYS,
    ema_fast: int = EMA_FAST,
    ema_slow: int = EMA_SLOW,
    ma_fast: int = MA_FAST,
    ma_slow: int = MA_SLOW,
) -> list[ShortlistEntry]:
    """Pure, no-I/O: given each symbol's daily candles, rank by 52-week-high
    proximity and overlay each symbol's current Darvas base state.

    Symbols without enough warmed-up history for the momentum score (fewer
    than `momentum_window` daily bars) are silently excluded from ranking —
    same rule core/rotation/ranker.py's rank_universe uses. `momentum_window`
    defaults to the real 252-day lookback; tests pass a smaller value to
    warm up on compact fixtures, same pattern as
    tests/unit/test_rotation_ranker.py's own helper. `ema_fast`/`ema_slow`
    default to the real EMA9/EMA21 trend gate; tests pass smaller values for
    the same reason.

    A symbol only counts toward the "tight base" tercile if it's ALSO in an
    uptrend (ema_fast > ema_slow) — a name that's merely range-bound but
    rolling over (see EMA_FAST/EMA_SLOW's module comment) never qualifies
    as a base worth a human's attention, regardless of how narrow its box
    is. It still falls through to LEADER_EXTENDED or WATCH via _bucket()'s
    existing "not tight" path — base_status/box_width_pct etc. stay as
    whatever Darvas actually detected; only bucket eligibility changes.
    """
    momentum_scores: list[tuple[str, float, float]] = []
    base_by_symbol: dict[str, Optional[DiscoveryResult]] = {}
    uptrend_by_symbol: dict[str, bool] = {}

    for symbol, daily in daily_by_symbol.items():
        series = SymbolSeries(
            dates=[c.timestamp for c in daily],
            closes=[c.close for c in daily],
            highs=rolling_high_series(daily, window=momentum_window),
        )
        v = value_as_of(series, as_of_date)
        if v is None:
            continue
        close, high = v
        if high > 0:
            momentum_scores.append((symbol, close, close / high * 100))
            base_by_symbol[symbol] = analyse_symbol(symbol, daily)
            uptrend_by_symbol[symbol] = is_uptrend(daily, as_of_date, ema_fast, ema_slow)

    momentum_scores.sort(key=lambda x: -x[2])
    total = len(momentum_scores)
    uptrending_bases = {
        symbol: base for symbol, base in base_by_symbol.items()
        if uptrend_by_symbol[symbol]
    }
    tight_symbols = _tight_base_symbols(uptrending_bases)

    entries = []
    for rank, (symbol, close, pct) in enumerate(momentum_scores, start=1):
        tier = _momentum_tier(rank, total)
        base = base_by_symbol[symbol]
        tight = symbol in tight_symbols
        bucket = _bucket(tier, tight)
        daily = daily_by_symbol[symbol]
        bo_state, days_above = breakout_state(base, daily, as_of_date)
        cross, cross_days = ma_cross_state(daily, as_of_date, ma_fast, ma_slow)
        entries.append(ShortlistEntry(
            symbol=symbol, close=round(close, 2),
            momentum_pct=round(pct, 2), momentum_rank=rank, momentum_tier=tier,
            bucket=bucket,
            base_status=base.status if base else "NO BASE",
            trend_up=uptrend_by_symbol[symbol],
            box_width_pct=base.box_width_pct if base else None,
            dist_to_ceil=base.dist_to_ceil if base else None,
            rr_ratio=base.rr_ratio if base else None,
            vol_ratio=base.vol_ratio if base else 0.0,
            breakout_state=bo_state,
            days_above_ceil=days_above,
            ma_cross=cross,
            ma_cross_days=cross_days,
        ))

    entries.sort(key=lambda e: (BUCKET_PRIORITY[e.bucket], -e.momentum_pct))
    return entries
