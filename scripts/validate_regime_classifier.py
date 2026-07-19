#!/usr/bin/env python3
"""
QuantOS — S8-1: Regime Classifier Validation Harness
──────────────────────────────────────────────────────
core/regime/classifier.py has never been validated against history — its
thresholds (VIX bands, EMA-alignment points, breadth buckets) are hand-picked,
and nothing today tests whether TRENDING_BULL/TRENDING_BEAR/RANGING/VOLATILE/
UNCERTAIN actually separate real forward market outcomes. Two later Sprint 8
stories (S8-3's optional regime split, S8-4's regime-filtered NIFTY entries)
want to condition on this classifier's output — wiring either to an
unvalidated gate would be Darvas's mistake one level up. This script answers
the question empirically instead.

Method
──────
Replay core/regime/classifier.py's classify() day-by-day over historical
NIFTY + India VIX daily data, using ONLY a trailing window of data available
as of each day (no lookahead — the same 250/260-trading-day windows the live
fetcher uses, just walked forward one day at a time instead of computed once
live). For each classified day, record the regime and the NIFTY forward
return over the next 5/10/20 trading days, plus realized volatility over the
next 20. Aggregate by regime and ask: does TRENDING_BULL actually precede
better forward returns than UNCERTAIN? Does RANGING actually precede lower
realized volatility than VOLATILE?

Breadth is reconstructed from a FIXED, deterministic sample of the committed
Nifty 500 universe (every Nth symbol, not hand-picked) rather than the full
500 — fetching daily history for 500 symbols across years is thousands of
throttled API calls; a few hundred is enough to trust the reading (the live
system's own MIN_BREADTH_SAMPLE floor is 20). This is a real trailing sample
of actual close-vs-prior-close data, not the "neutral" placeholder the live
fetcher falls back to on failure.

Fyers rejects daily-resolution history requests spanning more than 366 days
in one call (see core/darvas/weekly_discovery.py's DEFAULT_CONFIG comment) —
every fetch here is chunked into <=365-day windows and concatenated.

Usage
─────
    python scripts/validate_regime_classifier.py
    python scripts/validate_regime_classifier.py --years 5 --breadth-sample 100
    python scripts/validate_regime_classifier.py --config agent/config.yaml --out docs/REGIME_VALIDATION.md

Read-only: no orders, no cloud sync — pure market-data reads via the broker
configured in agent/config.yaml. Needs a fresh Fyers auth token (the daily
token-refresh ritual was stopped when the live loop was mothballed 2026-07-19
— this one-off run needs a token same as any other broker call would).
"""

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers.base import BrokerAdapter, OHLCV  # noqa: E402
from core.regime.classifier import classify  # noqa: E402
from core.regime.fetcher import NIFTY_SYMBOL, VIX_SYMBOL, _ema, _sma  # noqa: E402
from core.regime.models import (  # noqa: E402
    NiftyData, VIXData, BreadthData, RegimeInputs, Regime,
)

logger = logging.getLogger(__name__)

MAX_CHUNK_DAYS = 365          # Fyers' daily-resolution history cap per request
NIFTY_WINDOW = 260             # trailing trading days fed to _score_trend (covers EMA200 + slope_5d)
VIX_WINDOW = 260                # trailing trading days fed to _score_vix (covers ma_10 + 52w percentile)
FORWARD_HORIZONS = (5, 10, 20)  # trading days ahead to measure NIFTY forward return


# ─── Pure replay logic (no I/O — unit-testable with synthetic candles) ────────

@dataclass
class ReplayDay:
    date:            datetime
    regime:          Regime
    confidence:      float
    trend_signal:    str
    vix_signal:      str
    breadth_signal:  str
    fwd_return:      dict[int, Optional[float]] = field(default_factory=dict)  # horizon -> % return
    fwd_vol_20d:     Optional[float] = None  # stdev of daily returns over next 20 trading days


def build_nifty_data(window: list[OHLCV]) -> NiftyData:
    """Mirrors core/regime/fetcher.py's _fetch_nifty, but over an
    already-fetched trailing window instead of a fresh broker call."""
    closes = [c.close for c in window]
    ltp = closes[-1]
    ema_20 = _ema(closes, 20)
    ema_50 = _ema(closes, 50)
    ema_200 = _ema(closes, 200) if len(closes) >= 200 else _ema(closes, len(closes))
    slope_5d = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0.0

    trs = []
    for i in range(max(1, len(window) - 14), len(window)):
        high, low, prev = window[i].high, window[i].low, window[i - 1].close
        trs.append(max(high - low, abs(high - prev), abs(low - prev)))
    atr_14 = sum(trs) / len(trs) if trs else 0.0

    return NiftyData(
        ltp=ltp, ema_20=ema_20, ema_50=ema_50, ema_200=ema_200,
        slope_5d=slope_5d, atr_14=atr_14, atr_pct=(atr_14 / ltp * 100 if ltp else 0.0),
    )


def build_vix_data(window: list[OHLCV]) -> VIXData:
    """Mirrors core/regime/fetcher.py's _fetch_vix over a trailing window."""
    closes = [c.close for c in window]
    current = closes[-1]
    ma_10 = _sma(closes, min(10, len(closes)))
    recent_avg = _sma(closes[-5:], len(closes[-5:])) if len(closes) >= 5 else current
    if current > recent_avg * 1.05:
        trend = "RISING"
    elif current < recent_avg * 0.95:
        trend = "FALLING"
    else:
        trend = "FLAT"
    all_closes = closes[-252:] if len(closes) >= 252 else closes
    below = sum(1 for v in all_closes if v < current)
    percentile_52w = below / len(all_closes) * 100
    return VIXData(current=current, ma_10=ma_10, trend=trend, percentile_52w=percentile_52w)


def build_breadth_data(
    universe_closes: dict[str, dict[datetime, float]], date: datetime,
) -> BreadthData:
    """Advance/decline for one date from pre-indexed {symbol: {date: close}}
    maps. A symbol counts only if it has both this date's close AND the
    close of its own immediately-preceding available bar (per-symbol
    calendar, same tolerance the live fetcher has for individual listing
    gaps) — mirrors fetcher.py's close-vs-prev_close comparison, just off
    historical closes instead of live LTP-vs-prev_close ticks."""
    advance = decline = unchanged = 0
    for symbol, closes_by_date in universe_closes.items():
        dates = sorted(closes_by_date)
        if date not in closes_by_date:
            continue
        idx = dates.index(date)
        if idx == 0:
            continue
        prev_close = closes_by_date[dates[idx - 1]]
        curr_close = closes_by_date[date]
        if prev_close <= 0:
            continue
        if curr_close > prev_close:
            advance += 1
        elif curr_close < prev_close:
            decline += 1
        else:
            unchanged += 1
    return BreadthData(advance_count=advance, decline_count=decline, unchanged_count=unchanged)


def replay_regimes(
    nifty_candles: list[OHLCV],
    vix_candles: list[OHLCV],
    universe_closes: dict[str, dict[datetime, float]],
) -> list[ReplayDay]:
    """Walk NIFTY's trading calendar day by day, classifying each day from
    ONLY the trailing window available as of that day (no lookahead), then
    attach forward returns computed from the (now-known) future."""
    vix_by_date = {c.timestamp.date(): c for c in vix_candles}
    nifty_closes = [c.close for c in nifty_candles]

    days: list[ReplayDay] = []
    start_idx = max(NIFTY_WINDOW, VIX_WINDOW)
    for i in range(start_idx, len(nifty_candles)):
        date = nifty_candles[i].timestamp

        nifty_window = nifty_candles[max(0, i - NIFTY_WINDOW + 1): i + 1]
        if len(nifty_window) < 50:
            continue
        nifty_data = build_nifty_data(nifty_window)

        vix_date = date.date()
        vix_idx = None
        for j, c in enumerate(vix_candles):
            if c.timestamp.date() <= vix_date:
                vix_idx = j
            else:
                break
        if vix_idx is None:
            continue
        vix_window = vix_candles[max(0, vix_idx - VIX_WINDOW + 1): vix_idx + 1]
        if len(vix_window) < 5:
            continue
        vix_data = build_vix_data(vix_window)

        breadth_data = build_breadth_data(universe_closes, date)

        result = classify(RegimeInputs(nifty=nifty_data, vix=vix_data, breadth=breadth_data, timestamp=date))

        fwd_return = {}
        for horizon in FORWARD_HORIZONS:
            if i + horizon < len(nifty_candles):
                fwd_return[horizon] = (nifty_closes[i + horizon] - nifty_closes[i]) / nifty_closes[i] * 100
            else:
                fwd_return[horizon] = None

        fwd_vol_20d = None
        if i + 20 < len(nifty_candles):
            daily_rets = [
                (nifty_closes[k] - nifty_closes[k - 1]) / nifty_closes[k - 1] * 100
                for k in range(i + 1, i + 21)
            ]
            fwd_vol_20d = pstdev(daily_rets) if len(daily_rets) > 1 else None

        days.append(ReplayDay(
            date=date, regime=result.regime, confidence=result.confidence,
            trend_signal=result.trend_signal, vix_signal=result.vix_signal,
            breadth_signal=result.breadth_signal, fwd_return=fwd_return, fwd_vol_20d=fwd_vol_20d,
        ))

    return days


def summarize(days: list[ReplayDay]) -> str:
    """Build the markdown report body from a completed replay."""
    by_regime: dict[Regime, list[ReplayDay]] = {}
    for d in days:
        by_regime.setdefault(d.regime, []).append(d)

    # Compute per-regime stats first, then render the table in one pass.
    regime_stats = {}
    for regime in Regime:
        rd = by_regime.get(regime, [])
        if not rd:
            continue
        means = {}
        for h in FORWARD_HORIZONS:
            vals = [d.fwd_return[h] for d in rd if d.fwd_return.get(h) is not None]
            means[h] = mean(vals) if vals else None
        vols = [d.fwd_vol_20d for d in rd if d.fwd_vol_20d is not None]
        mean_vol = mean(vols) if vols else None
        regime_stats[regime] = {"n": len(rd), "means": means, "mean_vol": mean_vol}

    header = (
        f"**Replayed {len(days)} trading days** "
        f"({days[0].date.date()} to {days[-1].date.date()})."
        if days else "**No days replayed.**"
    )
    lines = [
        "# S8-1 Regime Classifier Validation",
        "",
        header,
        "",
        "## Forward NIFTY return by regime",
        "",
        "| Regime | n | Mean 5d fwd % | Mean 10d fwd % | Mean 20d fwd % | Mean 20d realized vol |",
        "|---|---|---|---|---|---|",
    ]
    for regime in Regime:
        st = regime_stats.get(regime)
        if not st:
            lines.append(f"| {regime.value} | 0 | - | - | - | - |")
            continue
        m5 = f"{st['means'][5]:.2f}" if st["means"].get(5) is not None else "-"
        m10 = f"{st['means'][10]:.2f}" if st["means"].get(10) is not None else "-"
        m20 = f"{st['means'][20]:.2f}" if st["means"].get(20) is not None else "-"
        mv = f"{st['mean_vol']:.2f}" if st["mean_vol"] is not None else "-"
        lines.append(f"| {regime.value} | {st['n']} | {m5} | {m10} | {m20} | {mv} |")

    lines += ["", "## Verdict", ""]

    bull = regime_stats.get(Regime.TRENDING_BULL)
    bear = regime_stats.get(Regime.TRENDING_BEAR)
    uncertain = regime_stats.get(Regime.UNCERTAIN)
    ranging = regime_stats.get(Regime.RANGING)
    volatile = regime_stats.get(Regime.VOLATILE)

    if bull and uncertain and bull["means"].get(10) is not None and uncertain["means"].get(10) is not None:
        gap = bull["means"][10] - uncertain["means"][10]
        lines.append(
            f"- TRENDING_BULL's mean 10-day forward return "
            f"({bull['means'][10]:.2f}%, n={bull['n']}) vs UNCERTAIN's "
            f"({uncertain['means'][10]:.2f}%, n={uncertain['n']}): gap = {gap:+.2f}pp."
        )
    if bear and uncertain and bear["means"].get(10) is not None and uncertain["means"].get(10) is not None:
        gap = bear["means"][10] - uncertain["means"][10]
        lines.append(
            f"- TRENDING_BEAR's mean 10-day forward return "
            f"({bear['means'][10]:.2f}%, n={bear['n']}) vs UNCERTAIN's "
            f"({uncertain['means'][10]:.2f}%, n={uncertain['n']}): gap = {gap:+.2f}pp."
        )
    if ranging and volatile and ranging["mean_vol"] is not None and volatile["mean_vol"] is not None:
        lines.append(
            f"- RANGING's mean 20-day realized vol ({ranging['mean_vol']:.2f}) vs "
            f"VOLATILE's ({volatile['mean_vol']:.2f}) — RANGING should be lower if the "
            f"classifier is actually separating calm from turbulent regimes."
        )
    lines.append(
        ""
        "Read the gaps above against the sample sizes (`n`) in the table — a few "
        "percentage points on a handful of days is noise, not signal. This report "
        "presents the numbers; it does not compute a significance test, matching "
        "the zero-code, direct-arithmetic style of docs/EXPECTANCY_CHECK.md."
    )

    return "\n".join(lines)


# ─── Fetch layer (I/O — needs a connected broker) ──────────────────────────────

async def fetch_chunked_daily(
    broker: BrokerAdapter, symbol: str, from_date: datetime, to_date: datetime,
    sem: asyncio.Semaphore, delay: float = 0.5, max_retries: int = 3,
) -> list[OHLCV]:
    """Fetch daily candles across a date range, chunked to Fyers' <=366-day
    limit per request, throttled + retried like weekly_discovery.py."""
    loop = asyncio.get_event_loop()
    all_candles: list[OHLCV] = []
    chunk_start = from_date
    while chunk_start < to_date:
        chunk_end = min(chunk_start + timedelta(days=MAX_CHUNK_DAYS), to_date)
        for attempt in range(max_retries):
            async with sem:
                try:
                    candles = await loop.run_in_executor(
                        None,
                        lambda cs=chunk_start, ce=chunk_end: broker.get_historical_data(symbol, "1d", cs, ce),
                    )
                    await asyncio.sleep(delay)
                    all_candles.extend(candles)
                    break
                except Exception as e:
                    if "429" in str(e) and attempt < max_retries - 1:
                        wait = 3.0 * (attempt + 1)
                        await asyncio.sleep(wait)
                        continue
                    logger.warning("Failed chunk %s..%s for %s: %s",
                                    chunk_start.date(), chunk_end.date(), symbol, e)
                    break
        chunk_start = chunk_end

    dedup = {c.timestamp: c for c in all_candles}
    return [dedup[k] for k in sorted(dedup)]


def read_breadth_universe(path: Path, sample_size: int) -> list[str]:
    """Fixed, deterministic sample: every Nth symbol from the committed
    universe file, not hand-picked — reproducible and not cherry-picked."""
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("#")]
    if sample_size >= len(lines):
        return lines
    step = len(lines) / sample_size
    return [lines[int(i * step)] for i in range(sample_size)]


async def main_async(args) -> int:
    config = load_config(args.config)
    from core.brokers import get_broker
    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')} ...")
    broker.connect()
    print(f"Broker connected: {broker}\n")

    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=365 * args.years + 400)  # +400d warmup for the 260d windows
    sem = asyncio.Semaphore(2)

    print(f"Fetching NIFTY daily candles {from_date.date()} -> {to_date.date()} ...")
    nifty_candles = await fetch_chunked_daily(broker, NIFTY_SYMBOL, from_date, to_date, sem)
    print(f"  {len(nifty_candles)} candles")

    print(f"Fetching India VIX daily candles ...")
    vix_candles = await fetch_chunked_daily(broker, VIX_SYMBOL, from_date, to_date, sem)
    print(f"  {len(vix_candles)} candles")

    universe = read_breadth_universe(Path(args.universe), args.breadth_sample)
    print(f"Fetching breadth universe sample: {len(universe)} symbols "
          f"(this is the slow part - throttled 2-concurrent) ...")
    universe_closes: dict[str, dict[datetime, float]] = {}
    for n, symbol in enumerate(universe, 1):
        candles = await fetch_chunked_daily(broker, symbol, from_date, to_date, sem)
        if candles:
            universe_closes[symbol] = {c.timestamp: c.close for c in candles}
        if n % 20 == 0:
            print(f"  {n}/{len(universe)} symbols fetched")
    print(f"  Breadth data ready: {len(universe_closes)}/{len(universe)} symbols resolved")

    if len(nifty_candles) < NIFTY_WINDOW + 10:
        print(f"ERROR: only {len(nifty_candles)} NIFTY candles - need at least "
              f"{NIFTY_WINDOW + 10} for a meaningful replay. Try --years higher "
              f"or check broker connectivity.")
        return 1

    print("Replaying classifier day-by-day (no lookahead) ...")
    days = replay_regimes(nifty_candles, vix_candles, universe_closes)
    print(f"  {len(days)} days classified")

    report = summarize(days)
    Path(args.out).write_text(report + "\n", encoding="utf-8")
    print(f"\nWrote {args.out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--years", type=int, default=5, help="years of history to replay")
    parser.add_argument("--universe", default="agent/universe_nifty500.txt")
    parser.add_argument("--breadth-sample", type=int, default=100,
                         help="fixed deterministic sample size from the universe for breadth reconstruction")
    parser.add_argument("--out", default="docs/REGIME_VALIDATION.md")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
