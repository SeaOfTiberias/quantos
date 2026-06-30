"""
QuantOS — Correlation Portfolio Service
───────────────────────────────────────────
US-08: Public interface that pulls price history via the broker adapter
and runs the correlation check. Called by the webhook pipeline (US-01)
right before order execution — after Claude approval, before sizing.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.brokers.base import BrokerAdapter
from core.risk.correlation import (
    check_portfolio_correlation, PortfolioCheckResult,
    CORRELATION_THRESHOLD, LOOKBACK_DAYS,
)

logger = logging.getLogger(__name__)


class CorrelationPortfolioService:
    """
    Fetches price history for open positions and a candidate symbol,
    then checks correlation. Wraps the broker adapter so callers
    don't need to manage data fetching themselves.
    """

    def __init__(self, broker: BrokerAdapter):
        self.broker = broker
        self._price_cache: dict[str, tuple[list[float], float]] = {}  # symbol -> (prices, cached_at)
        self._cache_ttl = 3600  # 1 hour — daily closes don't change intraday

    async def check_candidate(
        self,
        candidate_symbol: str,
        open_position_symbols: list[str],
        threshold: float = CORRELATION_THRESHOLD,
        manual_override: bool = False,
    ) -> PortfolioCheckResult:
        """
        Check if a candidate symbol is too correlated with current open positions.

        Args:
            candidate_symbol: symbol being considered for a new position
            open_position_symbols: list of symbols currently held
            threshold: correlation threshold (default 0.75)
            manual_override: if True, skip the block (logged for audit)

        Returns:
            PortfolioCheckResult
        """
        if manual_override:
            logger.warning(
                "Correlation check OVERRIDDEN by user for %s", candidate_symbol
            )

        candidate_prices = await self._get_prices(candidate_symbol)
        if not candidate_prices:
            logger.warning(
                "No price history for %s — cannot check correlation, allowing trade",
                candidate_symbol,
            )
            return PortfolioCheckResult(
                candidate_symbol=candidate_symbol,
                is_blocked=False,
                max_correlation=0.0,
                notes=["⚠️ No price history available — correlation check skipped"],
            )

        # Fetch prices for all open positions concurrently
        open_positions = {}
        tasks = {
            symbol: self._get_prices(symbol)
            for symbol in open_position_symbols
            if symbol.upper() != candidate_symbol.upper()
        }

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for symbol, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.warning("Failed to fetch prices for %s: %s", symbol, result)
                continue
            if result:
                open_positions[symbol] = result

        check_result = check_portfolio_correlation(
            candidate_symbol, candidate_prices, open_positions, threshold,
        )

        if manual_override and check_result.is_blocked:
            check_result.is_blocked = False
            check_result.notes.append("✅ Override applied by user")

        return check_result

    # ── Internal ─────────────────────────────────────────────────────────────

    async def _get_prices(self, symbol: str) -> list[float]:
        """Fetch daily close prices for a symbol, with simple time-based caching."""
        now = datetime.now(timezone.utc).timestamp()
        cached = self._price_cache.get(symbol)
        if cached and (now - cached[1]) < self._cache_ttl:
            return cached[0]

        loop = asyncio.get_event_loop()
        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(days=LOOKBACK_DAYS + 10)  # buffer for weekends

        try:
            candles = await loop.run_in_executor(
                None,
                lambda: self.broker.get_historical_data(symbol, "1d", from_date, to_date)
            )
            prices = [c.close for c in candles]
            self._price_cache[symbol] = (prices, now)
            return prices
        except Exception as e:
            logger.error("Failed to fetch price history for %s: %s", symbol, e)
            return []

    def clear_cache(self) -> None:
        self._price_cache = {}


def format_correlation_block_whatsapp(result: PortfolioCheckResult) -> str:
    """Format a blocked correlation check for WhatsApp."""
    lines = [
        "⛔ *Signal Blocked — Correlation Risk*",
        "━━━━━━━━━━━━━━",
        f"Symbol: *{result.candidate_symbol}*",
        f"Max correlation: {result.max_correlation:+.2f}",
        "",
    ]
    for note in result.notes:
        lines.append(note)

    lines += [
        "━━━━━━━━━━━━━━",
        "Reply *override* to add anyway",
        "Reply *skip* to pass on this signal",
    ]
    return "\n".join(lines)


def format_portfolio_correlation_matrix(
    symbols: list[str],
    results: list[PortfolioCheckResult],
) -> str:
    """Format a portfolio-wide correlation summary for the cockpit / morning brief."""
    if not results:
        return "📊 *Portfolio Correlation*\nNo open positions to analyze."

    lines = [
        "📊 *Portfolio Correlation Summary*",
        "━━━━━━━━━━━━━━",
    ]
    for r in results:
        flag = "🔴" if r.is_blocked else "🟢"
        lines.append(f"{flag} {r.candidate_symbol}: max corr {r.max_correlation:+.2f}")

    return "\n".join(lines)
