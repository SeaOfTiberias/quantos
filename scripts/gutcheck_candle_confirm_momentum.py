#!/usr/bin/env python3
"""
QuantOS — Candle-Confirm Momentum Gut-Check (candidate 19)
──────────────────────────────────────────────────────────────────────────────
See docs/CANDLE_CONFIRM_MOMENTUM_GUTCHECK_METHODOLOGY.md for every design
choice (fixed BEFORE this script was run). Tests whether NIFTY/BankNifty's
first two 1-minute candles predict the next 10 minutes' direction — a
cheap descriptive gut-check on the INDEX itself (no options, no stop-loss,
no costs), same sequencing as candidates 13-18 before ever reaching a full
backtest.

Needs a fresh Fyers auth token (agent/config.yaml's configured broker) --
run from the VM's whitelisted IP.

Usage
─────
    python scripts/gutcheck_candle_confirm_momentum.py
    python scripts/gutcheck_candle_confirm_momentum.py --out docs/CANDLE_CONFIRM_MOMENTUM_GUTCHECK_RESULTS.md
"""

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers.base import BrokerAdapter, OHLCV  # noqa: E402

logger = logging.getLogger(__name__)

NIFTY_SYMBOL = "NIFTY 50"
BANKNIFTY_SYMBOL = "NIFTY BANK"

# Same confirmed-safe start dates already established for 5-minute data
# in this project (candidate 14/15) -- see methodology doc.
NIFTY_WINDOW_START = date(2022, 6, 1)
BANKNIFTY_WINDOW_START = date(2021, 6, 1)

MAX_CHUNK_DAYS = 95
REQUEST_TIMEOUT_SECS = 30.0
HORIZONS = {"5min": 7, "10min": 12, "15min": 17}
MIN_CANDLES_FOR_SIGNAL = max(HORIZONS.values()) + 1  # need index 17 for the +15min readout


# ─── Fetch layer (I/O — needs a connected broker) ────────────────────────────

async def fetch_chunked_1m(
    broker: BrokerAdapter, symbol: str, from_date: datetime, to_date: datetime,
    sem: asyncio.Semaphore, delay: float = 0.5, max_retries: int = 3,
) -> list[OHLCV]:
    """Fetch 1m candles across a date range, chunked to Fyers' confirmed
    100-day intraday limit -- same throttle/retry shape as
    scripts/backtest_dow_theory_trend.py's fetch_chunked_intraday."""
    loop = asyncio.get_event_loop()
    all_candles: list[OHLCV] = []
    chunk_start = from_date
    while chunk_start < to_date:
        chunk_end = min(chunk_start + timedelta(days=MAX_CHUNK_DAYS), to_date)
        for attempt in range(max_retries):
            async with sem:
                try:
                    candles = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda cs=chunk_start, ce=chunk_end: broker.get_historical_data(symbol, "1m", cs, ce),
                        ),
                        timeout=REQUEST_TIMEOUT_SECS,
                    )
                    await asyncio.sleep(delay)
                    all_candles.extend(candles)
                    break
                except asyncio.TimeoutError:
                    if attempt < max_retries - 1:
                        wait = 3.0 * (attempt + 1)
                        logger.warning("Timed out fetching %s..%s, retrying in %.0fs", chunk_start, chunk_end, wait)
                        await asyncio.sleep(wait)
                    else:
                        raise
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait = 3.0 * (attempt + 1)
                        logger.warning("Error fetching %s..%s: %s, retrying in %.0fs", chunk_start, chunk_end, e, wait)
                        await asyncio.sleep(wait)
                    else:
                        raise
        chunk_start = chunk_end
    by_ts = {c.timestamp: c for c in all_candles}
    return sorted(by_ts.values(), key=lambda c: c.timestamp)


def group_by_day(candles: list[OHLCV]) -> dict[date, list[OHLCV]]:
    """UTC calendar date == IST trading-session date -- whole 03:45-10:00
    UTC session sits inside one UTC day, same convention as candidates 14/15."""
    by_day: dict[date, list[OHLCV]] = {}
    for c in candles:
        by_day.setdefault(c.timestamp.date(), []).append(c)
    for day_candles in by_day.values():
        day_candles.sort(key=lambda c: c.timestamp)
    return by_day


# ─── Signal + measurement (pure, unit-testable) ──────────────────────────────

@dataclass(frozen=True)
class DayResult:
    day: date
    direction: Optional[str]   # "CALL" | "PUT" | None (no signal)
    skip_reason: Optional[str]  # "doji_candle1" | "opposed_candle2" | "short_session" | None
    entry_price: Optional[float]
    fwd_return_pct: dict       # horizon label -> % return from entry_price, signed (+ = index up)


def classify_day(day_candles: list[OHLCV]) -> DayResult:
    d = day_candles[0].timestamp.date()
    if len(day_candles) < MIN_CANDLES_FOR_SIGNAL:
        return DayResult(d, None, "short_session", None, {})

    c1, c2 = day_candles[0], day_candles[1]

    if c1.close > c1.open:
        direction = "CALL"
    elif c1.close < c1.open:
        direction = "PUT"
    else:
        return DayResult(d, None, "doji_candle1", None, {})

    opposed = (c2.close < c2.open) if direction == "CALL" else (c2.close > c2.open)
    if opposed:
        return DayResult(d, None, "opposed_candle2", None, {})

    entry_price = day_candles[2].open
    fwd = {}
    for label, offset in HORIZONS.items():
        fwd[label] = (day_candles[offset].close / entry_price - 1) * 100

    return DayResult(d, direction, None, entry_price, fwd)


def classify_day_unconditional(day_candles: list[OHLCV]) -> dict:
    """Same entry point/horizons as classify_day, but ignores the signal --
    used only to build the no-filter baseline (methodology doc)."""
    if len(day_candles) < MIN_CANDLES_FOR_SIGNAL:
        return {}
    entry_price = day_candles[2].open
    return {label: (day_candles[offset].close / entry_price - 1) * 100 for label, offset in HORIZONS.items()}


# ─── Report ───────────────────────────────────────────────────────────────

def _stats_block(rets: list, signed_for_direction: Optional[str]) -> dict:
    if not rets:
        return {"n": 0}
    if signed_for_direction == "PUT":
        win = sum(1 for r in rets if r < 0) / len(rets)
    elif signed_for_direction == "CALL":
        win = sum(1 for r in rets if r > 0) / len(rets)
    else:
        win = None
    return {
        "n": len(rets),
        "win_rate": win,
        "mean_return": mean(rets),
        "mean_abs_return": mean(abs(r) for r in rets),
    }


def summarize(underlying: str, day_results: list, unconditional: list) -> str:
    lines = [f"## {underlying}", ""]

    total_days = len(day_results)
    reasons = {"doji_candle1": 0, "opposed_candle2": 0, "short_session": 0}
    for r in day_results:
        if r.skip_reason in reasons:
            reasons[r.skip_reason] += 1
    signaled = [r for r in day_results if r.direction is not None]
    no_signal = total_days - len(signaled)
    lines.append(
        f"Trading days: {total_days}. No-signal days: {no_signal} "
        f"(doji candle1: {reasons['doji_candle1']}, candle2 opposed: {reasons['opposed_candle2']}, "
        f"short session: {reasons['short_session']}). Signal rate: {len(signaled)/total_days:.1%}."
        if total_days else "*(no trading days in window)*"
    )
    lines.append("")

    baseline_10 = _stats_block([u["10min"] for u in unconditional if "10min" in u], None)

    for direction in ("CALL", "PUT"):
        dir_days = [r for r in signaled if r.direction == direction]
        lines.append(f"### {direction} bias (n={len(dir_days)})")
        lines.append("")
        if not dir_days:
            lines.append("*(no signal days)*")
            lines.append("")
            continue
        lines.append("| Horizon | n | Win rate | Mean return % | Mean \\|return\\| % |")
        lines.append("|---|---|---|---|---|")
        for label in HORIZONS:
            rets = [r.fwd_return_pct[label] for r in dir_days]
            st = _stats_block(rets, direction)
            win_str = f"{st['win_rate']:.1%}" if st["win_rate"] is not None else "-"
            lines.append(f"| {label} | {st['n']} | {win_str} | {st['mean_return']:+.3f} | {st['mean_abs_return']:.3f} |")
        lines.append("")

    lines.append(
        f"**Baseline (unconditional, no signal filter, +10min, n={baseline_10['n']}):** "
        f"mean return {baseline_10['mean_return']:+.3f}%, mean |return| {baseline_10['mean_abs_return']:.3f}%."
    )
    lines.append("")
    return "\n".join(lines)


# ─── Orchestration ────────────────────────────────────────────────────────

async def main_async(args) -> int:
    from core.brokers import get_broker

    config = load_config(args.config)
    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')} ...")
    broker.connect()
    print(f"Broker connected: {broker}\n")

    sem = asyncio.Semaphore(3)
    now = datetime.now(timezone.utc)

    report_sections = []
    for label, symbol, window_start in (
        ("NIFTY", NIFTY_SYMBOL, NIFTY_WINDOW_START),
        ("BankNifty", BANKNIFTY_SYMBOL, BANKNIFTY_WINDOW_START),
    ):
        frm = datetime(window_start.year, window_start.month, window_start.day, tzinfo=timezone.utc)
        print(f"Fetching {label} 1m candles {frm.date()} .. {now.date()} ...")
        candles = await fetch_chunked_1m(broker, symbol, frm, now, sem)
        print(f"  {len(candles)} candles")
        by_day = group_by_day(candles)
        print(f"  {len(by_day)} trading days")

        day_results = [classify_day(day_candles) for day_candles in by_day.values()]
        unconditional = [classify_day_unconditional(day_candles) for day_candles in by_day.values()]
        report_sections.append(summarize(label, day_results, unconditional))

    report = "\n".join([
        "# Candle-Confirm Momentum Gut-Check Results (candidate 19)",
        "",
        "Methodology: docs/CANDLE_CONFIRM_MOMENTUM_GUTCHECK_METHODOLOGY.md.",
        "",
        *report_sections,
    ])
    out_path = Path(args.out)
    out_path.write_text(report + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--out", default="docs/CANDLE_CONFIRM_MOMENTUM_GUTCHECK_RESULTS.md")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
