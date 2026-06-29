"""
QuantOS — Regime Service
──────────────────────────
Public interface for the regime engine.
Handles caching (ADR-04: 15-min TTL) and refresh scheduling.

Usage:
    from core.regime.service import RegimeService
    from core.brokers import get_broker

    broker  = get_broker(config)
    service = RegimeService(broker)

    result = await service.get_regime()
    print(result.summary())
    # → "Regime: TRENDING_BULL | Confidence: 82 | Size: 100% | Darvas: ✅"

    if result.darvas_enabled:
        scanner.scan(symbol)
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from core.regime.classifier import classify
from core.regime.fetcher import fetch_regime_inputs
from core.regime.models import Regime, RegimeResult, RegimeInputs

logger = logging.getLogger(__name__)

CACHE_TTL = int(os.getenv("REGIME_CACHE_TTL", "900"))   # 15 min default (ADR-04)


class RegimeService:
    """
    Wraps regime classification with caching and refresh logic.
    One instance should be shared across the app (singleton pattern).
    """

    def __init__(self, broker):
        self._broker        = broker
        self._cached:        Optional[RegimeResult] = None
        self._cached_at:     Optional[float]        = None
        self._refresh_lock   = asyncio.Lock()

    async def get_regime(self, force_refresh: bool = False) -> RegimeResult:
        """
        Get current regime. Returns cached result if within TTL.
        Thread-safe — concurrent callers wait for a single refresh.

        ADR-04: Only one Claude call per 15 minutes for regime classification.
        """
        now = datetime.now(timezone.utc).timestamp()

        if (
            not force_refresh
            and self._cached is not None
            and self._cached_at is not None
            and (now - self._cached_at) < CACHE_TTL
        ):
            age = int(now - self._cached_at)
            logger.debug("Regime cache hit: %s (age %ds)", self._cached.regime.value, age)
            return self._cached

        async with self._refresh_lock:
            # Double-check after acquiring lock (another coroutine may have refreshed)
            now = datetime.now(timezone.utc).timestamp()
            if (
                not force_refresh
                and self._cached is not None
                and self._cached_at is not None
                and (now - self._cached_at) < CACHE_TTL
            ):
                return self._cached

            return await self._refresh()

    async def _refresh(self) -> RegimeResult:
        """Fetch fresh data and reclassify."""
        logger.info("Refreshing regime classification...")
        try:
            inputs  = await fetch_regime_inputs(self._broker)
            result  = classify(inputs)
            self._cached    = result
            self._cached_at = datetime.now(timezone.utc).timestamp()

            logger.info(
                "Regime updated: %s (confidence=%.0f, strategies=%s)",
                result.regime.value, result.confidence,
                result.allowed_strategies,
            )
            return result

        except Exception as e:
            logger.error("Regime refresh failed: %s", e)
            if self._cached:
                logger.warning("Returning stale regime cache")
                return self._cached
            # Last resort — return UNCERTAIN
            return _uncertain_fallback()

    def is_stale(self) -> bool:
        """True if cache is expired or empty."""
        if not self._cached_at:
            return True
        age = datetime.now(timezone.utc).timestamp() - self._cached_at
        return age >= CACHE_TTL

    def cache_age_seconds(self) -> int:
        if not self._cached_at:
            return -1
        return int(datetime.now(timezone.utc).timestamp() - self._cached_at)


def format_regime_whatsapp(result: RegimeResult) -> str:
    """
    Format regime result as a WhatsApp morning brief section.
    Called by the scheduler at 9:00 AM IST.
    """
    emoji = {
        Regime.TRENDING_BULL: "🟢",
        Regime.TRENDING_BEAR: "🔴",
        Regime.RANGING:       "🟡",
        Regime.VOLATILE:      "🟠",
        Regime.UNCERTAIN:     "⚪",
    }

    lines = [
        f"🧭 *Market Regime*",
        f"━━━━━━━━━━━━━━",
        f"{emoji.get(result.regime, '•')} *{result.regime.value.replace('_', ' ')}*",
        f"Confidence:  {result.confidence:.0f}%",
        f"Trend:       {result.trend_signal}",
        f"VIX:         {result.vix_signal}",
        f"Breadth:     {result.breadth_signal}",
        f"Size mult:   {result.size_multiplier:.0%}",
        f"Darvas:      {'✅ ENABLED' if result.darvas_enabled else '❌ GATED'}",
        f"━━━━━━━━━━━━━━",
    ]

    if result.allowed_strategies:
        lines.append("Active strategies:")
        for s in result.allowed_strategies:
            lines.append(f"  • {s}")
    else:
        lines.append("⚠️ No strategies active — stand aside")

    if result.notes:
        lines.append("━━━━━━━━━━━━━━")
        for note in result.notes:
            lines.append(f"  {note}")

    return "\n".join(lines)


def _uncertain_fallback() -> RegimeResult:
    from core.regime.models import STRATEGY_GATE, SIZE_MULTIPLIER
    return RegimeResult(
        regime=Regime.UNCERTAIN,
        confidence=0,
        allowed_strategies=[],
        size_multiplier=0.0,
        timestamp=datetime.now(timezone.utc),
        trend_signal="UNKNOWN",
        vix_signal="UNKNOWN",
        breadth_signal="UNKNOWN",
        notes=["⚠️ Regime classification failed — standing aside"],
    )
