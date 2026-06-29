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
    """

    def __init__(self, broker: BrokerAdapter):
        self.broker = broker

    async def scan(self, symbol: str) -> MultiTimeframeResult:
        """
        Scan a single symbol across all timeframes.
        Returns MultiTimeframeResult with confluence score.
        """
        logger.info("Scanning %s across %s", symbol, list(TIMEFRAMES.keys()))

        # Fetch all timeframes concurrently
        tasks = {
            tf: self._fetch_and_detect(symbol, tf, cfg["candles"])
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
    ) -> Optional[DarvasSignal]:
        """Fetch OHLCV data and run breakout detection for one timeframe."""
        candles = await self._fetch_candles(symbol, timeframe, num_candles)
        if not candles:
            logger.warning("No candles returned for %s %s", symbol, timeframe)
            return None
        return detect_breakout(candles, symbol, timeframe)

    async def _fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        num_candles: int,
    ) -> list[OHLCV]:
        """
        Fetch OHLCV candles from broker.
        Runs in a thread pool since broker SDKs are synchronous.
        """
        to_date   = datetime.now(timezone.utc)
        from_date = _lookback_date(timeframe, num_candles, to_date)

        loop = asyncio.get_event_loop()
        candles = await loop.run_in_executor(
            None,
            lambda: self.broker.get_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                from_date=from_date,
                to_date=to_date,
            )
        )
        logger.debug("Fetched %d candles for %s %s", len(candles), symbol, timeframe)
        return candles


# ── Utilities ─────────────────────────────────────────────────────────────────

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
