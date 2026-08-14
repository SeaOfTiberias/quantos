"""
QuantOS — chunked daily history (synchronous)
─────────────────────────────────────────────
Fyers caps daily-resolution history at 366 days per request:

    {'code': -50, 'data': {'range_to': 'Date range cannot exceed 366 days
     for 1D, 1W, and 1M resolutions.'}, ...}

Any caller wanting more than a year has to fetch in chunks and splice. The
async version of this — scripts/validate_regime_classifier.fetch_chunked_daily
— has existed since the regime work and is what every universe-wide scan uses.
This is the synchronous sibling, for the one-symbol-at-a-time paths where an
event loop would be pure ceremony: agent/main.py's vault gate and
scripts/audit_symbol.py.

It exists because both of those shipped on 2026-08-14 doing a single 600-day
request, which Fyers rejects outright. Neither had a test that reached a real
adapter, so both looked fine: the gate's except-clause turned the rejection
into a permanent BLOCK, which is indistinguishable in the logs from a gate
doing its job.

Deliberately thinner than the async version — no semaphore, no retry, no
timeout. Those matter when hammering ~580 symbols; a single call on an entry
path wants the error to surface, not be smoothed over. Callers here fail
closed, so a swallowed error would be a silent veto.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from core.brokers.base import BrokerAdapter, OHLCV

logger = logging.getLogger(__name__)

# One less than Fyers' documented 366 to leave room for the inclusive-endpoint
# arithmetic on their side. Matches MAX_CHUNK_DAYS in the async version.
MAX_CHUNK_DAYS = 365

# The only daily-timeframe string the adapters accept. Lower case: they match
# the literal and raise BrokerError on anything else, so "1D" is not a synonym.
DAILY = "1d"


def fetch_daily(broker: BrokerAdapter, symbol: str,
                from_date: datetime, to_date: datetime) -> list[OHLCV]:
    """Daily candles for `symbol` over the full range, chunked as needed.

    Raises whatever the adapter raises — callers on money paths fail closed,
    so swallowing an error here would turn a broken feed into a silent veto.
    Candles are returned oldest-first and de-duplicated on timestamp, since
    chunk boundaries can overlap by a bar.
    """
    if from_date >= to_date:
        return []

    collected: list[OHLCV] = []
    chunk_start = from_date
    while chunk_start < to_date:
        chunk_end = min(chunk_start + timedelta(days=MAX_CHUNK_DAYS), to_date)
        collected.extend(broker.get_historical_data(symbol, DAILY, chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)

    seen: set = set()
    unique: list[OHLCV] = []
    for candle in sorted(collected, key=lambda c: c.timestamp):
        if candle.timestamp in seen:
            continue
        seen.add(candle.timestamp)
        unique.append(candle)

    logger.debug("Fetched %d daily candles for %s (%s..%s)",
                 len(unique), symbol, from_date.date(), to_date.date())
    return unique
