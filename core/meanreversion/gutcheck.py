"""
QuantOS — Mean-Reversion (Nifty Alpha 50) Gut-Check
─────────────────────────────────────────────────────
NOT a backtest — no costs, no position sizing, no threshold optimization.
Fast, cheap look (same role PEAD's gut-check played:
core/fundamentals/pead/gutcheck.py) at whether a "buy the pullback in a
leading sector" pattern precedes better-than-baseline forward returns at
all, before any execution-layer build.

**First pass (daily-RSI substitute) found literally zero qualifying days
across the whole universe** — checked directly (SBIN: 94 value-zone days
and 42 oversold days across 736 warm days, zero overlap): by the time
DAILY RSI14 drops under 35, price has almost always already fallen
through EMA50 entirely, not paused inside the EMA20/50 band. This module
now also implements the strategy AS SPECIFIED — hourly RSI —
via `hourly_rsi_crossings`/`compute_hourly_signals`/`hourly_forward_returns`,
since the daily substitute couldn't produce any signal to even evaluate.

**One remaining deliberate deviation, flagged rather than silently
absorbed:** the "sectoral EMA" trend filter uses a REAL NSE sectoral
index only for the ~half of Nifty Alpha 50 that has one (Bank, PSU Bank,
Auto, Pharma, FMCG, Metal, Energy, Infra — confirmed via real NSE archive
constituent lists, not guessed). Stocks with no matching sectoral index
(NBFCs, capital markets, chemicals, telecom, consumer durables/services —
confirmed empirically, see scripts/gutcheck_meanreversion_alpha50.py's
SECTOR_FILES) fall back to NIFTY 50's own trend as a neutral placeholder
("NIFTY 500" itself is not a fetchable Fyers index quote, confirmed live
2026-07-24).
"""

import bisect
import math
from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Optional

from core.brokers.base import OHLCV
from core.regime.fetcher import _ema

RSI_PERIOD = 14
RSI_OVERSOLD = 35.0
EMA_FAST = 20
EMA_SLOW = 50
FORWARD_HORIZONS = (5, 10, 20)


# ─── Indicators (pure, no I/O) ──────────────────────────────────────────────

def rsi14(closes: list[float], period: int = RSI_PERIOD) -> list[Optional[float]]:
    """Wilder's RSI, aligned to `closes` (index < period is None — not
    enough trailing data yet). Standard smoothing: seed with a simple
    average of the first `period` gains/losses, then exponentially
    smooth (Wilder's alpha = 1/period) through the rest."""
    n = len(closes)
    result: list[Optional[float]] = [None] * n
    if n <= period:
        return result

    deltas = [closes[i] - closes[i - 1] for i in range(1, n)]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    result[period] = _rsi_from_avgs(avg_gain, avg_loss)

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        result[i + 1] = _rsi_from_avgs(avg_gain, avg_loss)

    return result


def _rsi_from_avgs(avg_gain: float, avg_loss: float) -> float:
    if avg_gain == 0.0 and avg_loss == 0.0:
        return 50.0  # totally flat — no strength either way
    if avg_loss == 0.0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def walk_forward_emas(
    closes: list[float], fast: int = EMA_FAST, slow: int = EMA_SLOW,
) -> tuple[list[Optional[float]], list[Optional[float]]]:
    """EMA20/EMA50 at every index, using only closes up to and including
    that index (no lookahead) — reuses core.regime.fetcher._ema exactly
    the way scripts/validate_regime_classifier.py's build_nifty_data
    already does (day-by-day, re-seeded from the start of the trailing
    slice each time), for consistency with that already-validated
    pattern rather than a different rolling-window implementation."""
    n = len(closes)
    ema_fast: list[Optional[float]] = [None] * n
    ema_slow: list[Optional[float]] = [None] * n
    for i in range(n):
        if i + 1 >= fast:
            ema_fast[i] = _ema(closes[: i + 1], fast)
        if i + 1 >= slow:
            ema_slow[i] = _ema(closes[: i + 1], slow)
    return ema_fast, ema_slow


# ─── Signal + forward-return logic (pure, no I/O) ───────────────────────────

def compute_signals(own_candles: list[OHLCV], sector_candles: list[OHLCV]) -> list[bool]:
    """One boolean per day in own_candles: sector trend up (sector's own
    EMA20>EMA50) AND today's close is in the "value zone" between own
    EMA20/EMA50 AND own daily RSI14 < 35. Every input is a trailing-only
    indicator value as of that day — no lookahead."""
    own_closes = [c.close for c in own_candles]
    own_ema20, own_ema50 = walk_forward_emas(own_closes)
    own_rsi = rsi14(own_closes)

    sector_closes = [c.close for c in sector_candles]
    sec_ema20, sec_ema50 = walk_forward_emas(sector_closes)
    sector_by_date = {c.timestamp.date(): i for i, c in enumerate(sector_candles)}

    signals: list[bool] = []
    for i, c in enumerate(own_candles):
        e20, e50, r = own_ema20[i], own_ema50[i], own_rsi[i]
        if e20 is None or e50 is None or r is None:
            signals.append(False)
            continue
        sec_i = sector_by_date.get(c.timestamp.date())
        if sec_i is None or sec_ema20[sec_i] is None or sec_ema50[sec_i] is None:
            signals.append(False)
            continue
        trend_ok = sec_ema20[sec_i] > sec_ema50[sec_i]
        lo, hi = min(e20, e50), max(e20, e50)
        value_zone = lo <= c.close <= hi
        oversold = r < RSI_OVERSOLD
        signals.append(trend_ok and value_zone and oversold)
    return signals


def forward_returns(
    candles: list[OHLCV], signal_idx: int, horizons: tuple[int, ...] = FORWARD_HORIZONS,
) -> dict[int, Optional[float]]:
    """Entry at the NEXT trading day's OPEN after signal_idx (you can't
    act on a signal until the following session — no lookahead), held
    `h` trading days, exit at that day's close. None where the window
    runs past the end of available data."""
    entry_i = signal_idx + 1
    if entry_i >= len(candles):
        return {h: None for h in horizons}
    entry_price = candles[entry_i].open
    out: dict[int, Optional[float]] = {}
    for h in horizons:
        exit_i = entry_i + h - 1
        out[h] = (
            (candles[exit_i].close - entry_price) / entry_price * 100
            if exit_i < len(candles) else None
        )
    return out


# ─── Hourly-RSI signal (strategy AS SPECIFIED) ──────────────────────────────

def hourly_rsi_crossings(hourly_closes: list[float]) -> list[int]:
    """Indices where hourly RSI14 freshly crosses below RSI_OVERSOLD (was
    >=35 the previous hour, now <35) — a transition event, not a
    persistent "is below" state, matching the spec's "must DROP below 35"
    language and this project's established signal-on-transition
    convention (S8-3: signal on first entry into the top-20, not every
    day held)."""
    rsi = rsi14(hourly_closes)
    return [
        i for i in range(1, len(rsi))
        if rsi[i] is not None and rsi[i - 1] is not None
        and rsi[i - 1] >= RSI_OVERSOLD and rsi[i] < RSI_OVERSOLD
    ]


@dataclass
class HourlySignal:
    hourly_idx: int
    date: datetime          # timestamp of the hourly candle where RSI crossed
    entry_price: float      # that hourly candle's close


def _prior_daily_index(dates_sorted: list, by_date: dict, d) -> Optional[int]:
    """Index of the latest daily bar strictly BEFORE date d — the last
    completed daily bar as of an intraday decision made during day d
    itself (today's own daily close isn't known yet intraday)."""
    pos = bisect.bisect_left(dates_sorted, d)
    if pos == 0:
        return None
    return by_date[dates_sorted[pos - 1]]


def compute_hourly_signals(
    own_daily: list[OHLCV], sector_daily: list[OHLCV], own_hourly: list[OHLCV],
) -> list[HourlySignal]:
    """For each fresh hourly RSI-oversold crossing, keep it only if
    YESTERDAY's daily filters (sector trend up, price in value zone) were
    true — using the last COMPLETED daily bar's EMAs, since an intraday
    decision on day d can't use day d's own (not-yet-closed) daily bar
    without lookahead. The "value zone" check compares the CURRENT
    (real, known) hourly price against those trailing daily EMA lines —
    the correct no-lookahead formulation of "is price between my EMA20
    and EMA50 right now.\""""
    own_closes = [c.close for c in own_daily]
    own_ema20, own_ema50 = walk_forward_emas(own_closes)
    sector_closes = [c.close for c in sector_daily]
    sec_ema20, sec_ema50 = walk_forward_emas(sector_closes)

    own_daily_by_date = {c.timestamp.date(): i for i, c in enumerate(own_daily)}
    sector_daily_by_date = {c.timestamp.date(): i for i, c in enumerate(sector_daily)}
    own_dates_sorted = sorted(own_daily_by_date)
    sector_dates_sorted = sorted(sector_daily_by_date)

    hourly_closes = [c.close for c in own_hourly]
    signals: list[HourlySignal] = []
    for idx in hourly_rsi_crossings(hourly_closes):
        d = own_hourly[idx].timestamp.date()
        own_i = _prior_daily_index(own_dates_sorted, own_daily_by_date, d)
        sec_i = _prior_daily_index(sector_dates_sorted, sector_daily_by_date, d)
        if own_i is None or sec_i is None:
            continue
        e20, e50 = own_ema20[own_i], own_ema50[own_i]
        s20, s50 = sec_ema20[sec_i], sec_ema50[sec_i]
        if e20 is None or e50 is None or s20 is None or s50 is None:
            continue
        trend_ok = s20 > s50
        current_price = own_hourly[idx].close
        lo, hi = min(e20, e50), max(e20, e50)
        value_zone = lo <= current_price <= hi
        if trend_ok and value_zone:
            signals.append(HourlySignal(
                hourly_idx=idx, date=own_hourly[idx].timestamp, entry_price=current_price,
            ))
    return signals


def hourly_forward_returns(
    own_daily: list[OHLCV], entry_date: datetime, entry_price: float,
    horizons: tuple[int, ...] = FORWARD_HORIZONS,
) -> dict[int, Optional[float]]:
    """Forward return from entry_price (the real intraday fill price at
    the crossing) to the daily close `h` trading days later, counting
    entry_date's own daily bar as day 1 of the hold — same day-counting
    convention as forward_returns() (there, entry_i's day is day 1, exit
    is entry_i + h - 1), so a "5-day" signal return and a "5-day"
    baseline return represent the same length of market exposure. An
    earlier version counted entry_date as day 0 and exited at +h, giving
    the signal group one extra trading day of exposure versus baseline
    at every horizon — a real, silent bias in a trending sample, caught
    by independent review (Fable, 2026-07-24) before being trusted."""
    d = entry_date.date()
    daily_by_date = {c.timestamp.date(): i for i, c in enumerate(own_daily)}
    if d not in daily_by_date:
        return {h: None for h in horizons}
    base_i = daily_by_date[d]
    out: dict[int, Optional[float]] = {}
    for h in horizons:
        exit_i = base_i + h - 1
        out[h] = (
            (own_daily[exit_i].close - entry_price) / entry_price * 100
            if exit_i < len(own_daily) else None
        )
    return out


# ─── Report ──────────────────────────────────────────────────────────────────

@dataclass
class ObservedDay:
    symbol: str
    date: datetime
    is_signal: bool
    fwd_return: dict[int, Optional[float]]
    sector_mapped: bool = True  # False => this symbol used the NIFTY 50 fallback, not a real sectoral index


def _gap_row(vals_a: list[float], vals_b: list[float], label) -> str:
    if not vals_a or not vals_b:
        return "| " + " | ".join([str(label)] + ["-"] * 6) + " |"
    mean_a, mean_b = mean(vals_a), mean(vals_b)
    win_a = sum(1 for v in vals_a if v > 0) / len(vals_a) * 100
    win_b = sum(1 for v in vals_b if v > 0) / len(vals_b) * 100
    gap = mean_a - mean_b
    return (
        f"| {label} | {len(vals_a)} | {mean_a:+.2f} | {win_a:.0f}% | "
        f"{len(vals_b)} | {mean_b:+.2f} | {win_b:.0f}% | {gap:+.2f} |"
    )


def _gap_table(header: str, signal_days: list[ObservedDay], baseline_days: list[ObservedDay]) -> list[str]:
    """One raw + one market-adjusted table for a given signal/baseline
    population pair — reused for the full sample and for sub-splits."""
    raw = [
        f"## {header}",
        "",
        "| Horizon | Signal n | Signal mean % | Signal win% | Baseline n | Baseline mean % | Baseline win% | Gap (signal − baseline) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    adjusted = [
        "",
        f"### {header} — market-adjusted (demeaned by this sample's own "
        "cross-sectional mean per horizon, signal+baseline combined)",
        "",
        "| Horizon | Signal n | Signal mean % | Signal win% | Baseline n | Baseline mean % | Baseline win% | Gap (signal − baseline) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for h in FORWARD_HORIZONS:
        sig_vals = [o.fwd_return[h] for o in signal_days if o.fwd_return.get(h) is not None]
        base_vals = [o.fwd_return[h] for o in baseline_days if o.fwd_return.get(h) is not None]
        raw.append(_gap_row(sig_vals, base_vals, h))
        pooled = sig_vals + base_vals
        if pooled:
            pooled_mean = mean(pooled)
            adjusted.append(_gap_row(
                [v - pooled_mean for v in sig_vals], [v - pooled_mean for v in base_vals], h,
            ))
        else:
            adjusted.append(_gap_row([], [], h))
    return raw + adjusted


def summarize(observations: list[ObservedDay]) -> str:
    signal_days = [o for o in observations if o.is_signal]
    baseline_days = [o for o in observations if not o.is_signal]

    lines = [
        "# Mean-Reversion (Nifty Alpha 50) Gut-Check",
        "",
        f"**{len(observations)} total observed days** across the universe "
        f"({len(signal_days)} signal days, {len(baseline_days)} baseline days).",
        "",
        "NOT a backtest — no costs, no position sizing, no threshold tuning. "
        "See core/meanreversion/gutcheck.py's module docstring for the "
        "remaining flagged deviation from the strategy as specified (NIFTY "
        "50 fallback trend for stocks with no matching real sectoral index).",
        "",
    ]

    # ── Clustering diagnostic (Fable review, 2026-07-24): are the signal
    # days independent events, or a small number of shared market/sector
    # dips firing many stocks on the same date at once? ──────────────────
    signal_dates = {o.date.date() for o in signal_days}
    dates_counter: dict = {}
    for o in signal_days:
        dates_counter[o.date.date()] = dates_counter.get(o.date.date(), 0) + 1
    max_cluster = max(dates_counter.values()) if dates_counter else 0
    avg_per_date = (len(signal_days) / len(signal_dates)) if signal_dates else 0.0
    lines += [
        "## Signal clustering",
        "",
        f"**{len(signal_days)} signal-day observations fall on only "
        f"{len(signal_dates)} distinct calendar dates** "
        f"({avg_per_date:.1f} stocks/date on average, largest single-date "
        f"cluster: {max_cluster} stocks). If this ratio is well above 1, the "
        "effective number of independent events is closer to the distinct-date "
        "count than to the raw signal-day count — read the `n` in the tables "
        "below with that in mind.",
        "",
    ]

    lines += _gap_table("Forward return: signal vs baseline (full sample)", signal_days, baseline_days)

    # ── Sector-mapped vs NIFTY-50-fallback split (Fable review, 2026-07-24) ──
    mapped_signal = [o for o in signal_days if o.sector_mapped]
    mapped_baseline = [o for o in baseline_days if o.sector_mapped]
    fallback_signal = [o for o in signal_days if not o.sector_mapped]
    fallback_baseline = [o for o in baseline_days if not o.sector_mapped]
    lines += [""]
    lines += _gap_table(
        "Sector-mapped stocks only (real NSE sectoral index, not NIFTY 50 fallback)",
        mapped_signal, mapped_baseline,
    )
    lines += [""]
    lines += _gap_table(
        "NIFTY-50-fallback stocks only (no matching real sectoral index)",
        fallback_signal, fallback_baseline,
    )

    lines += [
        "",
        "## Verdict",
        "",
        "Read the gaps above against the sample sizes (`n`) in the tables — "
        "a few points on a handful of days is noise, not signal, and the "
        "clustering count above matters more than the raw signal-day `n`. "
        "This report presents the numbers; it does not compute a significance "
        "test, matching the zero-code, direct-arithmetic style of "
        "docs/REGIME_VALIDATION.md and the PEAD gut-check.",
    ]

    return "\n".join(lines)
