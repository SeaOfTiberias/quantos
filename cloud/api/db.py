"""
QuantOS — Signal Database Layer
────────────────────────────────
Postgres persistence for signals (ADR-03: user_id on every row).
Uses SQLAlchemy async for non-blocking DB ops within FastAPI.
"""

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# Simple async DB wrapper — swap for full SQLAlchemy in production
_db_instance = None


@dataclass
class Signal:
    signal_id:        str
    user_id:          str
    symbol:           str
    action:           str
    price:            float
    timeframe:        str
    strategy:         str
    confluence_score: float
    status:           str
    created_at:       datetime
    confidence_score: Optional[float] = None
    executed_at:      Optional[datetime] = None
    execution_price:  Optional[float] = None


class SignalDB:
    """
    Lightweight DB wrapper. In production this uses asyncpg + SQLAlchemy.
    In development / tests it falls back to an in-memory store.
    """

    def __init__(self):
        self._store: list[Signal] = []   # dev fallback
        self._use_postgres = bool(os.getenv("DATABASE_URL"))

    async def insert_signal(self, signal: Signal) -> None:
        if self._use_postgres:
            await self._pg_insert(signal)
        else:
            self._store.append(signal)

    async def fetch_recent_signals(self, limit: int = 20) -> list[dict]:
        if self._use_postgres:
            return await self._pg_fetch(limit)
        return [
            {
                "signal_id":        s.signal_id,
                "user_id":          s.user_id,
                "symbol":           s.symbol,
                "action":           s.action,
                "price":            s.price,
                "strategy":         s.strategy,
                "confluence_score": s.confluence_score,
                "confidence_score": s.confidence_score,
                "status":           s.status,
                "created_at":       s.created_at.isoformat(),
            }
            for s in sorted(self._store,
                            key=lambda x: x.created_at, reverse=True)[:limit]
        ]

    async def update_signal_status(self, signal_id: str, new_status: str) -> None:
        if self._use_postgres:
            await self._pg_update_status(signal_id, new_status)
        else:
            for s in self._store:
                if s.signal_id == signal_id:
                    s.status = new_status
                    break

    # ── Postgres stubs (implemented when DATABASE_URL is set) ─────────────────

    async def _pg_insert(self, signal: Signal) -> None:
        # TODO: implement with asyncpg
        # async with get_pg_pool() as conn:
        #     await conn.execute(INSERT_SQL, signal.signal_id, signal.user_id, ...)
        raise NotImplementedError("Postgres not yet wired — set DATABASE_URL")

    async def _pg_fetch(self, limit: int) -> list[dict]:
        raise NotImplementedError("Postgres not yet wired — set DATABASE_URL")

    async def _pg_update_status(self, signal_id: str, status: str) -> None:
        raise NotImplementedError("Postgres not yet wired — set DATABASE_URL")


async def get_db() -> SignalDB:
    global _db_instance
    if _db_instance is None:
        _db_instance = SignalDB()
    return _db_instance
