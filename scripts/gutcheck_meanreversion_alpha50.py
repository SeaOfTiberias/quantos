#!/usr/bin/env python3
"""
QuantOS — Mean-Reversion (Nifty Alpha 50) Gut-Check (driver)
──────────────────────────────────────────────────────────────
Fast, cheap look at whether "buy the pullback in a leading sector"
precedes better forward returns than baseline — NOT a backtest (no costs,
no position sizing). See core/meanreversion/gutcheck.py for the pure
signal/forward-return logic.

**Runs the strategy AS SPECIFIED — hourly RSI — not a daily substitute.**
The first pass (daily RSI standing in for hourly, to move fast) found
literally zero qualifying days across the whole universe: by the time
daily RSI14 drops under 35, price has almost always already fallen
through EMA50 entirely (confirmed directly on SBIN: 94 value-zone days,
42 oversold days, zero overlap, across 736 warm days). That result
couldn't answer the real question, so this now fetches real Fyers 60m
candles (confirmed live 2026-07-24: capped at 100 days/request, real
depth to 7+ years) and detects fresh hourly RSI-oversold CROSSINGS,
keeping only those where the LAST COMPLETED daily bar's filters (sector
trend, value zone) were already true — see
core/meanreversion/gutcheck.py's compute_hourly_signals docstring for the
no-lookahead reasoning. One crossing per calendar day is kept (the
first) — a real trader wouldn't re-enter the same pullback five times in
an afternoon; pinned here, before running, not tuned after seeing a
result.

One remaining deliberate deviation: the "sectoral EMA" trend filter uses
a REAL NSE sectoral index only for the ~half of Nifty Alpha 50 that has
one. Sector mapping is built from REAL NSE archive constituent lists
(https://nsearchives.nseindia.com/content/indices/ind_nifty{sector}list.csv
— confirmed live 2026-07-24, no Akamai session bootstrap needed for this
host, unlike nseindia.com's live API), not guessed from the supplied
CSV's free-text Industry column. Confirmed real coverage: 26/50 Alpha 50
symbols map to one of 11 real sectoral indices; the other 24 (NBFCs,
capital-markets names, chemicals, telecom, consumer durables/services —
sectors NSE doesn't publish a standalone index for) fall back to NIFTY
50's own trend ("NIFTY 500" itself is not a fetchable Fyers index quote,
confirmed live 2026-07-24). Where a symbol appears in more than one
sector list (e.g. SBIN is in both NIFTY BANK and NIFTY PSU BANK),
SECTOR_FILES' fixed dict order below is the tie-break — first match
wins, pinned here rather than left to iteration-order chance.

Daily fetch pattern (fetch_chunked_daily, NIFTY_SYMBOL) reused directly
from scripts/validate_regime_classifier.py / core/regime/fetcher.py.
Hourly fetch (fetch_chunked_hourly, below) mirrors that same
chunked/throttled/retried structure with a 90-day chunk size (Fyers caps
60m-resolution requests at 100 days/request — a 90-day chunk keeps
margin under that live-confirmed cap).

Usage:
    python scripts/gutcheck_meanreversion_alpha50.py
    python scripts/gutcheck_meanreversion_alpha50.py --years 3 --out docs/S2_MEANREVERSION_GUTCHECK.md
"""

import argparse
import asyncio
import csv
import io
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers.base import BrokerAdapter, OHLCV  # noqa: E402
from core.meanreversion.gutcheck import (  # noqa: E402
    ObservedDay, compute_hourly_signals, forward_returns, hourly_forward_returns, summarize,
)
from core.regime.fetcher import NIFTY_SYMBOL  # noqa: E402
from scripts.validate_regime_classifier import fetch_chunked_daily  # noqa: E402

logger = logging.getLogger(__name__)

HOURLY_MAX_CHUNK_DAYS = 90  # Fyers hard-caps 60m-resolution requests at 100 days/request


async def fetch_chunked_hourly(
    broker: BrokerAdapter, symbol: str, from_date: datetime, to_date: datetime,
    sem: asyncio.Semaphore, delay: float = 0.5, max_retries: int = 3,
) -> list[OHLCV]:
    """Same chunked/throttled/retried structure as fetch_chunked_daily,
    just at "1h" resolution with a 100-day-capped chunk size instead of
    daily's 366-day one."""
    loop = asyncio.get_event_loop()
    all_candles: list[OHLCV] = []
    chunk_start = from_date
    while chunk_start < to_date:
        chunk_end = min(chunk_start + timedelta(days=HOURLY_MAX_CHUNK_DAYS), to_date)
        for attempt in range(max_retries):
            async with sem:
                try:
                    candles = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda cs=chunk_start, ce=chunk_end: broker.get_historical_data(symbol, "1h", cs, ce),
                        ),
                        timeout=30.0,
                    )
                    await asyncio.sleep(delay)
                    all_candles.extend(candles)
                    break
                except asyncio.TimeoutError:
                    if attempt < max_retries - 1:
                        wait = 3.0 * (attempt + 1)
                        logger.warning("Timed out fetching %s..%s for %s, retrying in %.0fs",
                                        chunk_start.date(), chunk_end.date(), symbol, wait)
                        await asyncio.sleep(wait)
                        continue
                    logger.warning("Failed hourly chunk %s..%s for %s: timed out after %d attempts",
                                    chunk_start.date(), chunk_end.date(), symbol, max_retries)
                    break
                except Exception as e:
                    if "429" in str(e) and attempt < max_retries - 1:
                        wait = 3.0 * (attempt + 1)
                        await asyncio.sleep(wait)
                        continue
                    logger.warning("Failed hourly chunk %s..%s for %s: %s",
                                    chunk_start.date(), chunk_end.date(), symbol, e)
                    break
        chunk_start = chunk_end

    dedup = {c.timestamp: c for c in all_candles}
    return [dedup[k] for k in sorted(dedup)]

# "NIFTY 500" is NOT a fetchable Fyers index quote (confirmed live
# 2026-07-24 -- core/brokers/fyers.py's _INDEX_SYMBOL_MAP has never had an
# entry for it; even S8-3's own "Nifty 500 benchmark" is actually NIFTY 50
# used as a stand-in, see scripts/backtest_equity_curve.py). NIFTY_SYMBOL
# ("NIFTY 50") is the real, already-proven broad-market fallback.

# core.brokers.fyers._INDEX_SYMBOL_MAP already carries the Fyers base
# symbol for each of these (added alongside this script, confirmed live).
SECTOR_FILES = {
    "NIFTY BANK":      "ind_niftybanklist.csv",
    "NIFTY AUTO":      "ind_niftyautolist.csv",
    "NIFTY PHARMA":    "ind_niftypharmalist.csv",
    "NIFTY FMCG":      "ind_niftyfmcglist.csv",
    "NIFTY METAL":     "ind_niftymetallist.csv",
    "NIFTY ENERGY":    "ind_niftyenergylist.csv",
    "NIFTY PSU BANK":  "ind_niftypsubanklist.csv",
    "NIFTY INFRA":     "ind_niftyinfralist.csv",
    "NIFTY IT":        "ind_niftyitlist.csv",
    "NIFTY REALTY":    "ind_niftyrealtylist.csv",
    "NIFTY MEDIA":     "ind_niftymedialist.csv",
}
NSE_ARCHIVE_BASE = "https://nsearchives.nseindia.com/content/indices/"
FALLBACK_TREND = NIFTY_SYMBOL


def build_sector_map(universe: list[str]) -> dict[str, str]:
    """symbol -> friendly sector index name, for symbols with a real match.
    Symbols not present in any list are left unmapped (caller falls back
    to FALLBACK_TREND)."""
    universe_set = set(universe)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    symbol_to_sector: dict[str, str] = {}
    for sector, fname in SECTOR_FILES.items():
        r = requests.get(NSE_ARCHIVE_BASE + fname, headers=headers, timeout=15)
        r.raise_for_status()
        reader = csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")))
        members = {row["Symbol"].strip().upper() for row in reader if row.get("Symbol")}
        for sym in universe_set & members:
            symbol_to_sector.setdefault(sym, sector)
    return symbol_to_sector


async def main_async(args) -> int:
    config = load_config(args.config)
    from core.brokers import get_broker
    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')} ...")
    broker.connect()
    print(f"Broker connected: {broker}\n")

    universe = [
        ln.strip() for ln in Path(args.universe).read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    print(f"Universe: {len(universe)} symbols from {args.universe}")

    print("Building sector map from real NSE archive constituent lists ...")
    sector_map = build_sector_map(universe)
    mapped = sorted(sector_map)
    unmapped = sorted(set(universe) - set(sector_map))
    print(f"  {len(mapped)}/{len(universe)} mapped to a real sectoral index")
    print(f"  {len(unmapped)}/{len(universe)} fall back to {FALLBACK_TREND}: {unmapped}")

    needed_sectors = sorted(set(sector_map.values()))
    print(f"  Sectors actually in use: {needed_sectors}")

    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=365 * args.years + 60)  # +60d warmup for EMA50/RSI14
    sem = asyncio.Semaphore(2)

    print(f"\nFetching {FALLBACK_TREND} daily candles {from_date.date()} -> {to_date.date()} ...")
    fallback_candles = await fetch_chunked_daily(broker, FALLBACK_TREND, from_date, to_date, sem)
    print(f"  {len(fallback_candles)} candles")

    sector_candles: dict[str, list[OHLCV]] = {}
    for sector in needed_sectors:
        print(f"Fetching {sector} daily candles ...")
        candles = await fetch_chunked_daily(broker, sector, from_date, to_date, sem)
        print(f"  {len(candles)} candles")
        sector_candles[sector] = candles

    # Same from_date as the daily fetch, deliberately -- signal days and
    # baseline days must be drawn from the identical window, or the
    # comparison is comparing different populations, not signal-vs-not.
    hourly_from_date = from_date

    observations: list[ObservedDay] = []
    for i, symbol in enumerate(universe, 1):
        own_daily = await fetch_chunked_daily(broker, symbol, from_date, to_date, sem)
        if len(own_daily) < 60:
            print(f"  [{i}/{len(universe)}] {symbol}: only {len(own_daily)} daily candles, skipping")
            continue
        sector = sector_map.get(symbol)
        sec_candles = sector_candles[sector] if sector else fallback_candles

        own_hourly = await fetch_chunked_hourly(broker, symbol, hourly_from_date, to_date, sem)

        hourly_signals = compute_hourly_signals(own_daily, sec_candles, own_hourly)
        # First crossing per calendar day only -- see module docstring.
        first_per_day: dict = {}
        for s in hourly_signals:
            d = s.date.date()
            if d not in first_per_day:
                first_per_day[d] = s
        signal_dates = set(first_per_day)

        for idx, candle in enumerate(own_daily):
            d = candle.timestamp.date()
            if d in signal_dates:
                s = first_per_day[d]
                fwd = hourly_forward_returns(own_daily, s.date, s.entry_price)
            else:
                fwd = forward_returns(own_daily, idx)
            if all(v is None for v in fwd.values()):
                continue
            observations.append(ObservedDay(
                symbol=symbol, date=candle.timestamp, is_signal=(d in signal_dates), fwd_return=fwd,
                sector_mapped=(sector is not None),
            ))

        if i % 10 == 0 or i == len(universe):
            print(f"  [{i}/{len(universe)}] {symbol}: {len(own_daily)} daily / {len(own_hourly)} hourly "
                  f"candles, {len(signal_dates)} signal days")

    print(f"\n{len(observations)} total observed days across the universe")
    report = summarize(observations)
    Path(args.out).write_text(report + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--years", type=int, default=3, help="years of history to replay")
    parser.add_argument("--universe", default="agent/universe_alpha50.txt")
    parser.add_argument("--out", default="docs/S2_MEANREVERSION_GUTCHECK.md")
    args = parser.parse_args()

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
