"""
QuantOS — Signal Database Layer
────────────────────────────────
Postgres persistence for signals (ADR-03: user_id on every row).
Uses SQLAlchemy async for non-blocking DB ops within FastAPI.
"""

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
    stop_loss:        Optional[float] = None
    executed_at:      Optional[datetime] = None
    execution_price:  Optional[float] = None


class SignalDB:
    """
    Lightweight DB wrapper. In production this uses asyncpg + SQLAlchemy.
    In development / tests it falls back to an in-memory store.
    """

    def __init__(self):
        self._store: list[Signal] = []   # dev fallback
        # NOTE: _pg_* methods below are all unimplemented stubs (raise
        # NotImplementedError) — gating on DATABASE_URL's mere presence
        # crashes every DB call in any environment where a Postgres plugin
        # happens to be linked (e.g. Railway) but the app code hasn't been
        # wired to it yet. Flip this to a real check once _pg_* is built.
        self._use_postgres = False

    async def insert_signal(self, signal: Signal) -> None:
        if self._use_postgres:
            await self._pg_insert(signal)
        else:
            self._store.append(signal)

    async def fetch_recent_signals(self, limit: int = 20, status: Optional[str] = None) -> list[dict]:
        if self._use_postgres:
            return await self._pg_fetch(limit, status)
        rows = self._store
        if status:
            rows = [s for s in rows if s.status == status]
        return [
            {
                "signal_id":        s.signal_id,
                "user_id":          s.user_id,
                "symbol":           s.symbol,
                "action":           s.action,
                "price":            s.price,
                "timeframe":        s.timeframe,
                "strategy":         s.strategy,
                "confluence_score": s.confluence_score,
                "confidence_score": s.confidence_score,
                "stop_loss":        s.stop_loss,
                "status":           s.status,
                "created_at":       s.created_at.isoformat(),
                "executed_at":      s.executed_at.isoformat() if s.executed_at else None,
                "execution_price":  s.execution_price,
            }
            for s in sorted(rows,
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

    async def mark_executed(self, signal_id: str, execution_price: float) -> None:
        if self._use_postgres:
            await self._pg_mark_executed(signal_id, execution_price)
        else:
            for s in self._store:
                if s.signal_id == signal_id:
                    s.status = "EXECUTED"
                    s.execution_price = execution_price
                    s.executed_at = datetime.now()
                    break

    async def get_signal(self, signal_id: str) -> Optional[Signal]:
        if self._use_postgres:
            return await self._pg_get(signal_id)
        for s in self._store:
            if s.signal_id == signal_id:
                return s
        return None

    # ── Postgres stubs (implemented when DATABASE_URL is set) ─────────────────

    async def _pg_insert(self, signal: Signal) -> None:
        # TODO: implement with asyncpg
        # async with get_pg_pool() as conn:
        #     await conn.execute(INSERT_SQL, signal.signal_id, signal.user_id, ...)
        raise NotImplementedError("Postgres not yet wired — set DATABASE_URL")

    async def _pg_fetch(self, limit: int, status: Optional[str] = None) -> list[dict]:
        raise NotImplementedError("Postgres not yet wired — set DATABASE_URL")

    async def _pg_update_status(self, signal_id: str, status: str) -> None:
        raise NotImplementedError("Postgres not yet wired — set DATABASE_URL")

    async def _pg_mark_executed(self, signal_id: str, execution_price: float) -> None:
        raise NotImplementedError("Postgres not yet wired — set DATABASE_URL")

    async def _pg_get(self, signal_id: str) -> Optional[Signal]:
        raise NotImplementedError("Postgres not yet wired — set DATABASE_URL")


async def get_db() -> SignalDB:
    global _db_instance
    if _db_instance is None:
        _db_instance = SignalDB()
    return _db_instance
