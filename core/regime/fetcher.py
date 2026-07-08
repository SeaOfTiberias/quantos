"""
QuantOS — Regime Data Fetcher
───────────────────────────────
Fetches all inputs needed for regime classification:
  - Nifty 50 OHLCV + EMAs
  - India VIX level + trend
  - NSE advance / decline breadth

Runs on a schedule (morning + every 15 min during market hours).
Results feed the cached regime used by Claude pre-trade analyst.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.brokers.base import BrokerAdapter, OHLCV
from core.regime.models import (
    NiftyData, VIXData, BreadthData, RegimeInputs,
)

logger = logging.getLogger(__name__)

# NSE symbols for index data
NIFTY_SYMBOL  = "NIFTY 50"
VIX_SYMBOL    = "INDIA VIX"
BANK_NIFTY    = "NIFTY BANK"

# Minimum number of symbols whose quote must resolve for a breadth reading
# to be trusted. A universe scan that returns only a handful of names (auth
# blip, most symbols rejected) would otherwise yield a wildly skewed A/D
# ratio — better to fall back to neutral than feed the classifier noise.
MIN_BREADTH_SAMPLE = 20


async def fetch_regime_inputs(
    broker: BrokerAdapter,
    breadth_universe: Optional[list[str]] = None,
) -> RegimeInputs:
    """
    Fetch all regime inputs concurrently from the broker.
    Returns a RegimeInputs dataclass ready for classification.

    `breadth_universe` is the list of NSE equity symbols sampled for the
    advance/decline reading. When empty/None, breadth falls back to a neutral
    placeholder (the pre-S5-4 behaviour).
    """
    logger.info("Fetching regime inputs...")

    nifty_task   = _fetch_nifty(broker)
    vix_task     = _fetch_vix(broker)
    breadth_task = _fetch_breadth(broker, breadth_universe or [])

    nifty, vix, breadth = await asyncio.gather(
        nifty_task, vix_task, breadth_task,
        return_exceptions=True,
    )

    # Handle partial failures gracefully
    if isinstance(nifty, Exception):
        logger.error("Failed to fetch Nifty data: %s", nifty)
        raise nifty

    if isinstance(vix, Exception):
        logger.warning("VIX fetch failed (%s) — using default", vix)
        vix = _default_vix()

    if isinstance(breadth, Exception):
        logger.warning("Breadth fetch failed (%s) — using neutral", breadth)
        breadth = _neutral_breadth()

    return RegimeInputs(
        nifty=nifty,
        vix=vix,
        breadth=breadth,
        timestamp=datetime.now(timezone.utc),
    )


# ─── Individual fetchers ──────────────────────────────────────────────────────

async def _fetch_nifty(broker: BrokerAdapter) -> NiftyData:
    """Fetch Nifty 50 daily candles and compute EMAs + slope."""
    loop = asyncio.get_event_loop()
    to_date   = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=280)  # ~200 trading days buffer

    candles: list[OHLCV] = await loop.run_in_executor(
        None,
        lambda: broker.get_historical_data(NIFTY_SYMBOL, "1d", from_date, to_date)
    )

    if len(candles) < 50:
        raise ValueError(f"Insufficient Nifty candles: {len(candles)} (need ≥ 50)")

    closes = [c.close for c in candles]
    ltp    = closes[-1]

    ema_20  = _ema(closes, 20)
    ema_50  = _ema(closes, 50)
    ema_200 = _ema(closes, 200) if len(closes) >= 200 else _ema(closes, len(closes))

    slope_5d = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0

    highs  = [c.high for c in candles[-15:]]
    lows   = [c.low  for c in candles[-15:]]
    atr_14 = _atr(candles[-15:])
    atr_pct = atr_14 / ltp * 100

    logger.debug(
        "Nifty: ltp=%.0f ema20=%.0f ema50=%.0f ema200=%.0f slope5d=%.2f%%",
        ltp, ema_20, ema_50, ema_200, slope_5d,
    )

    return NiftyData(
        ltp=ltp,
        ema_20=ema_20,
        ema_50=ema_50,
        ema_200=ema_200,
        slope_5d=slope_5d,
        atr_14=atr_14,
        atr_pct=atr_pct,
    )


async def _fetch_vix(broker: BrokerAdapter) -> VIXData:
    """Fetch India VIX and compute trend."""
    loop = asyncio.get_event_loop()
    to_date   = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=30)

    candles: list[OHLCV] = await loop.run_in_executor(
        None,
        lambda: broker.get_historical_data(VIX_SYMBOL, "1d", from_date, to_date)
    )

    if not candles:
        return _default_vix()

    closes   = [c.close for c in candles]
    current  = closes[-1]
    ma_10    = _sma(closes, min(10, len(closes)))

    # Trend: compare current vs 5-day average
    recent_avg = _sma(closes[-5:], len(closes[-5:])) if len(closes) >= 5 else current
    if current > recent_avg * 1.05:
        trend = "RISING"
    elif current < recent_avg * 0.95:
        trend = "FALLING"
    else:
        trend = "FLAT"

    # 52-week percentile
    all_closes = closes[-252:] if len(closes) >= 252 else closes
    below = sum(1 for v in all_closes if v < current)
    percentile_52w = below / len(all_closes) * 100

    logger.debug("VIX: current=%.1f ma10=%.1f trend=%s pct52w=%.0f",
                 current, ma_10, trend, percentile_52w)

    return VIXData(
        current=current,
        ma_10=ma_10,
        trend=trend,
        percentile_52w=percentile_52w,
    )


async def _fetch_breadth(broker: BrokerAdapter, universe: list[str]) -> BreadthData:
    """
    Compute NSE advance/decline breadth from a universe sample.

    Broker quote endpoints (Fyers, Kite) carry the previous close alongside
    the LTP, so one batched `get_quotes` call yields A/D directly — no NSE
    bhavcopy download and no second historical fetch. A symbol whose LTP
    equals its previous close counts as unchanged; symbols with missing or
    non-positive reference data are dropped from the sample.

    Falls back to a neutral placeholder when the universe is empty, the
    broker doesn't support quote snapshots, or too few symbols resolve to
    trust the reading. (The caller — fetch_regime_inputs — also catches any
    exception raised here and substitutes neutral breadth.)
    """
    if not universe:
        logger.warning("Breadth: no universe configured — using neutral placeholder")
        return _neutral_breadth()

    loop = asyncio.get_event_loop()
    quotes = await loop.run_in_executor(None, lambda: broker.get_quotes(universe))

    advance = decline = unchanged = 0
    for q in quotes.values():
        if q.prev_close <= 0 or q.ltp <= 0:
            continue
        if q.ltp > q.prev_close:
            advance += 1
        elif q.ltp < q.prev_close:
            decline += 1
        else:
            unchanged += 1

    sample = advance + decline + unchanged
    if sample < MIN_BREADTH_SAMPLE:
        logger.warning(
            "Breadth: only %d/%d symbols resolved (< %d) — using neutral",
            sample, len(universe), MIN_BREADTH_SAMPLE,
        )
        return _neutral_breadth()

    logger.info(
        "Breadth: %d adv / %d dec / %d unch across %d symbols (A/D=%.2f)",
        advance, decline, unchanged, sample,
        (advance / decline) if decline else float(advance),
    )
    return BreadthData(
        advance_count=advance, decline_count=decline, unchanged_count=unchanged,
    )


# ─── Math utilities ───────────────────────────────────────────────────────────

def _ema(values: list[float], period: int) -> float:
    """Exponential Moving Average."""
    if len(values) < period:
        return _sma(values, len(values))
    k = 2 / (period + 1)
    ema = _sma(values[:period], period)
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return round(ema, 2)


def _sma(values: list[float], period: int) -> float:
    """Simple Moving Average."""
    if not values:
        return 0.0
    n = min(period, len(values))
    return sum(values[-n:]) / n


def _atr(candles: list[OHLCV], period: int = 14) -> float:
    """Average True Range."""
    if len(candles) < 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        high  = candles[i].high
        low   = candles[i].low
        prev  = candles[i - 1].close
        tr    = max(high - low, abs(high - prev), abs(low - prev))
        trs.append(tr)
    n = min(period, len(trs))
    return sum(trs[-n:]) / n


# ─── Defaults (used when fetch partially fails) ───────────────────────────────

def _default_vix() -> VIXData:
    return VIXData(current=15.0, ma_10=15.0, trend="FLAT", percentile_52w=40.0)


def _neutral_breadth() -> BreadthData:
    return BreadthData(advance_count=250, decline_count=250, unchanged_count=0)
