"""
QuantOS — Multi-Timeframe Darvas Scanner
─────────────────────────────────────────
US-02: Scans a symbol across 15m / 1H / Daily timeframes.
       Returns a confluence-scored MultiTimeframeResult.

Usage:
    from core.darvas.scanner import DarvasScanner
    from core.brokers import get_broker

    broker  = get_broker(config)
    broker.connect()
    scanner = DarvasScanner(broker)
    result  = await scanner.scan("RELIANCE")

    if result.should_fire:
        print(f"Signal! Score: {result.confluence_score}")
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.brokers.base import BrokerAdapter, OHLCV
from core.darvas.box import (
    DarvasSignal,
    MultiTimeframeResult,
    detect_breakout,
    score_confluence,
)

logger = logging.getLogger(__name__)

# Timeframes to scan and how many candles to fetch per TF
TIMEFRAMES = {
    "15m": {"candles": 120},   # ~30 trading hours
    "1h":  {"candles": 120},   # ~15 trading days
    "1d":  {"candles": 120},   # ~6 months
}


class DarvasScanner:
    """
    Multi-timeframe Darvas Box scanner.
    Wraps the broker adapter for data fetching and
    coordinates detection across all configured timeframes.

    Throttled the same way core/darvas/weekly_discovery.py's
    WeeklyDiscoveryScanner is: confirmed live that Fyers' history endpoint
    rate-limits hard well below what an unthrottled asyncio.gather() fires.
    scan_watchlist() feeds this scanner a shortlist that can run to 100+
    symbols (from Stage A's discovery scan) and scan() alone already fires
    3 concurrent requests per symbol (15m/1h/1d) — unthrottled, a 100+
    symbol watchlist means hundreds of simultaneous requests.
    """

    MAX_RETRIES = 3
    RETRY_BACKOFF_SECONDS = 3.0

    def __init__(self, broker: BrokerAdapter, max_concurrent: int = 2):
        self.broker = broker
        self._max_concurrent = max_concurrent
        self._sem: Optional[asyncio.Semaphore] = None

    async def scan(self, symbol: str) -> MultiTimeframeResult:
        """
        Scan a single symbol across all timeframes.
        Returns MultiTimeframeResult with confluence score.
        """
        logger.info("Scanning %s across %s", symbol, list(TIMEFRAMES.keys()))

        # Falls back to a fresh semaphore when called standalone (not via
        # scan_watchlist) — created here, inside the running coroutine, for
        # the same reason WeeklyDiscoveryScanner constructs its semaphore
        # inside scan_universe() rather than __init__: binding it at
        # construction time can attach it to a different event loop than
        # the one that ends up running it.
        sem = self._sem or asyncio.Semaphore(self._max_concurrent)

        # Fetch all timeframes concurrently (throttled via `sem`)
        tasks = {
            tf: self._fetch_and_detect(symbol, tf, cfg["candles"], sem)
            for tf, cfg in TIMEFRAMES.items()
        }

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        tf_names = list(tasks.keys())

        signals: list[DarvasSignal] = []
        for tf, result in zip(tf_names, results):
            if isinstance(result, Exception):
                logger.warning("Error scanning %s %s: %s", symbol, tf, result)
                continue
            if result is not None:
                logger.info("✅ Breakout detected: %s %s | score=%.0f vol=%.1f×",
                            symbol, tf, result.quality_score, result.volume_ratio)
                signals.append(result)
            else:
                logger.debug("No breakout: %s %s", symbol, tf)

        result = score_confluence(signals)
        result.symbol = symbol

        logger.info(
            "Scan complete: %s | confluence=%.0f | TFs=%s | fire=%s",
            symbol, result.confluence_score,
            result.timeframes_triggered, result.should_fire,
        )
        return result

    async def scan_watchlist(
        self,
        symbols: list[str],
        min_confluence: float = 70.0,
    ) -> list[MultiTimeframeResult]:
        """
        Scan a list of symbols. Returns only results above min_confluence,
        sorted by score descending.
        Used by US-03 (TradingView Screener → Claude Ranker).
        """
        logger.info("Scanning watchlist: %d symbols", len(symbols))

        # One shared semaphore across the whole watchlist, so total
        # concurrent Fyers requests stay bounded regardless of how many
        # symbols are being scanned in parallel (each scan() fires up to
        # 3 requests on its own). Constructed here rather than __init__ —
        # see scan()'s comment for why.
        self._sem = asyncio.Semaphore(self._max_concurrent)
        tasks = [self.scan(symbol) for symbol in symbols]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        fired = []
        for symbol, result in zip(symbols, all_results):
            if isinstance(result, Exception):
                logger.warning("Watchlist scan error for %s: %s", symbol, result)
                continue
            if result.confluence_score >= min_confluence:
                fired.append(result)

        fired.sort(key=lambda r: r.confluence_score, reverse=True)
        logger.info(
            "Watchlist scan complete: %d/%d above threshold %.0f",
            len(fired), len(symbols), min_confluence,
        )
        return fired

    # ── Internal ─────────────────────────────────────────────────────────────

    async def _fetch_and_detect(
        self,
        symbol: str,
        timeframe: str,
        num_candles: int,
        sem: asyncio.Semaphore,
    ) -> Optional[DarvasSignal]:
        """Fetch OHLCV data and run breakout detection for one timeframe."""
        candles = await self._fetch_candles(symbol, timeframe, num_candles, sem)
        if not candles:
            logger.warning("No candles returned for %s %s", symbol, timeframe)
            return None
        # History is fetched up to now(), so mid-session the last candle is
        # still forming — detect_breakout treats candles[-1] as the breakout
        # candle, and an intrabar wick that retraces by close is exactly the
        # false-breakout class Darvas filters out. Pine already fires on bar
        # close only (alert.freq_once_per_bar_close); this makes the internal
        # path match. Also keeps the forming candle's partial volume out of
        # the volume-confirmation ratio.
        candles = _drop_forming_candle(candles, timeframe)
        if not candles:
            return None
        return detect_breakout(candles, symbol, timeframe)

    async def _fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        num_candles: int,
        sem: asyncio.Semaphore,
    ) -> list[OHLCV]:
        """
        Fetch OHLCV candles from broker.
        Runs in a thread pool since broker SDKs are synchronous. Throttled
        via `sem` and retried on Fyers 429s — see the class docstring.
        """
        to_date   = datetime.now(timezone.utc)
        from_date = _lookback_date(timeframe, num_candles, to_date)
        loop = asyncio.get_event_loop()

        for attempt in range(self.MAX_RETRIES):
            async with sem:
                try:
                    candles = await loop.run_in_executor(
                        None,
                        lambda: self.broker.get_historical_data(
                            symbol=symbol,
                            timeframe=timeframe,
                            from_date=from_date,
                            to_date=to_date,
                        )
                    )
                    await asyncio.sleep(0.5)   # be polite to the Fyers API
                    logger.debug("Fetched %d candles for %s %s", len(candles), symbol, timeframe)
                    return candles
                except Exception as e:
                    is_rate_limited = "429" in str(e)
                    if is_rate_limited and attempt < self.MAX_RETRIES - 1:
                        wait = self.RETRY_BACKOFF_SECONDS * (attempt + 1)
                        logger.debug(
                            "Rate limited fetching %s %s (attempt %d/%d) — retrying in %.0fs",
                            symbol, timeframe, attempt + 1, self.MAX_RETRIES, wait,
                        )
                        await asyncio.sleep(wait)
                        continue
                    logger.warning("Failed to fetch %s candles for %s: %s", timeframe, symbol, e)
                    return []
        return []


# ── Utilities ─────────────────────────────────────────────────────────────────

# NSE cash session close — a daily candle is only closed once this has passed.
_IST = timezone(timedelta(hours=5, minutes=30))
_NSE_CLOSE = (15, 30)


def _drop_forming_candle(
    candles: list[OHLCV],
    timeframe: str,
    now: Optional[datetime] = None,
) -> list[OHLCV]:
    """
    Return `candles` without the final candle if its time bucket hasn't
    closed yet. Candle timestamps are bar-open times; intraday buckets
    close open+15m/60m, daily buckets close at that session's NSE close
    (15:30 IST). Naive timestamps are assumed UTC (FyersBroker returns
    tz-aware UTC; this keeps other adapters/tests from crashing the
    comparison).
    """
    if not candles:
        return candles
    now = now or datetime.now(timezone.utc)
    last_open = candles[-1].timestamp
    if last_open.tzinfo is None:
        last_open = last_open.replace(tzinfo=timezone.utc)

    if timeframe == "1d":
        closes_at = last_open.astimezone(_IST).replace(
            hour=_NSE_CLOSE[0], minute=_NSE_CLOSE[1], second=0, microsecond=0)
    else:
        minutes = {"15m": 15, "1h": 60}.get(timeframe)
        if minutes is None:
            return candles  # unknown timeframe — don't guess at bucket size
        closes_at = last_open + timedelta(minutes=minutes)

    return candles[:-1] if closes_at > now else candles


def _lookback_date(timeframe: str, num_candles: int, to_date: datetime) -> datetime:
    """Calculate from_date based on timeframe and desired candle count."""
    minutes_per_candle = {
        "15m": 15,
        "1h":  60,
        "1d":  375,   # ~6.25 hrs NSE trading day
    }
    mins = minutes_per_candle.get(timeframe, 60)
    # Add 40% buffer for weekends / market holidays
    total_mins = int(num_candles * mins * 1.4)
    return to_date - timedelta(minutes=total_mins)
