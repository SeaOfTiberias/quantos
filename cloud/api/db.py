"""
QuantOS — Signal Database Layer
────────────────────────────────
Postgres persistence for signals (ADR-03: user_id on every row).
Uses SQLAlchemy async for non-blocking DB ops within FastAPI.

Persistence is gated on a *startup connectivity check* (SignalDB.connect),
NOT on the mere presence of DATABASE_URL — gating on the env var alone
crashed production once, because Railway links a Postgres plugin (setting
DATABASE_URL) before the app code was wired to it. If the connection check
fails at boot, we log a loud warning and fall back to the in-memory store so
the app still boots; signals just won't survive a redeploy in that state.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

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
    notified_at:      Optional[datetime] = None   # confirmation delivered on Telegram
    executed_at:      Optional[datetime] = None
    execution_price:  Optional[float] = None
    closed_at:        Optional[datetime] = None
    exit_price:       Optional[float] = None
    pnl:              Optional[float] = None


# ── SQL ──────────────────────────────────────────────────────────────────────

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS signals (
    signal_id         TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL DEFAULT 'system',
    symbol            TEXT NOT NULL,
    action            TEXT NOT NULL,
    price             DOUBLE PRECISION NOT NULL,
    timeframe         TEXT NOT NULL,
    strategy          TEXT NOT NULL,
    confluence_score  DOUBLE PRECISION NOT NULL,
    confidence_score  DOUBLE PRECISION,
    stop_loss         DOUBLE PRECISION,
    status            TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL,
    notified_at       TIMESTAMPTZ,
    executed_at       TIMESTAMPTZ,
    execution_price   DOUBLE PRECISION,
    closed_at         TIMESTAMPTZ,
    exit_price        DOUBLE PRECISION,
    pnl               DOUBLE PRECISION
);
"""

# Indexes the same-day dedup guard (cloud/api/main.py) relies on: it filters
# by symbol + status over a one-day created_at range, so a (symbol, created_at)
# index turns the old client-side 200-row scan into an index range scan.
_CREATE_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_signals_symbol_created "
    "ON signals (symbol, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_signals_status_created "
    "ON signals (status, created_at);",
]

_COLUMNS = (
    "signal_id, user_id, symbol, action, price, timeframe, strategy, "
    "confluence_score, confidence_score, stop_loss, status, created_at, "
    "notified_at, executed_at, execution_price, closed_at, exit_price, pnl"
)


def _normalize_dsn(dsn: str) -> str:
    """SQLAlchemy async needs the asyncpg driver in the scheme; Railway hands
    out `postgres://` / `postgresql://`. Also strip a `sslmode` query param —
    that's a psycopg keyword asyncpg rejects (it uses `ssl` instead)."""
    if dsn.startswith("postgres://"):
        dsn = "postgresql+asyncpg://" + dsn[len("postgres://"):]
    elif dsn.startswith("postgresql://"):
        dsn = "postgresql+asyncpg://" + dsn[len("postgresql://"):]
    # Drop libpq-only query params asyncpg doesn't understand.
    if "?" in dsn:
        base, _, query = dsn.partition("?")
        kept = [kv for kv in query.split("&")
                if kv and not kv.lower().startswith("sslmode=")]
        dsn = base + ("?" + "&".join(kept) if kept else "")
    return dsn


def _row_to_dict(row) -> dict:
    """Serialize a Postgres row to the exact dict shape the in-memory path
    returns (timestamps as ISO strings, or None)."""
    m = row._mapping
    def _iso(v):
        return v.isoformat() if v is not None else None
    return {
        "signal_id":        m["signal_id"],
        "user_id":          m["user_id"],
        "symbol":           m["symbol"],
        "action":           m["action"],
        "price":            m["price"],
        "timeframe":        m["timeframe"],
        "strategy":         m["strategy"],
        "confluence_score": m["confluence_score"],
        "confidence_score": m["confidence_score"],
        "stop_loss":        m["stop_loss"],
        "status":           m["status"],
        "created_at":       _iso(m["created_at"]),
        "notified_at":      _iso(m["notified_at"]),
        "executed_at":      _iso(m["executed_at"]),
        "execution_price":  m["execution_price"],
        "closed_at":        _iso(m["closed_at"]),
        "exit_price":       m["exit_price"],
        "pnl":              m["pnl"],
    }


def _row_to_signal(row) -> Signal:
    m = row._mapping
    return Signal(
        signal_id=m["signal_id"],
        user_id=m["user_id"],
        symbol=m["symbol"],
        action=m["action"],
        price=m["price"],
        timeframe=m["timeframe"],
        strategy=m["strategy"],
        confluence_score=m["confluence_score"],
        confidence_score=m["confidence_score"],
        stop_loss=m["stop_loss"],
        status=m["status"],
        created_at=m["created_at"],
        notified_at=m["notified_at"],
        executed_at=m["executed_at"],
        execution_price=m["execution_price"],
        closed_at=m["closed_at"],
        exit_price=m["exit_price"],
        pnl=m["pnl"],
    )


def _signal_to_dict(s: Signal) -> dict:
    return {
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
        "notified_at":      s.notified_at.isoformat() if s.notified_at else None,
        "executed_at":      s.executed_at.isoformat() if s.executed_at else None,
        "execution_price":  s.execution_price,
        "closed_at":        s.closed_at.isoformat() if s.closed_at else None,
        "exit_price":       s.exit_price,
        "pnl":              s.pnl,
    }


class SignalDB:
    """
    Lightweight DB wrapper. In production this uses asyncpg + SQLAlchemy.
    In development / tests it falls back to an in-memory store.
    """

    def __init__(self):
        self._store: list[Signal] = []   # dev / fallback store
        self._engine = None
        # Stays False until connect() proves Postgres is actually reachable.
        # Gating on DATABASE_URL's mere presence crashed production once (see
        # module docstring), so the flag flips only on a real connectivity
        # check — never on env-var presence.
        self._use_postgres = False

    async def connect(self) -> bool:
        """Attempt to bring up Postgres persistence. Runs a real connectivity
        check + CREATE TABLE IF NOT EXISTS; on any failure it logs a loud
        warning and leaves the wrapper on the in-memory store so the app can
        still boot. Returns True iff Postgres is now live. Idempotent."""
        if self._use_postgres:
            return True
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            logger.info("DATABASE_URL unset — SignalDB using in-memory store "
                        "(signals will NOT survive a redeploy)")
            return False
        try:
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine

            engine = create_async_engine(
                _normalize_dsn(dsn),
                pool_pre_ping=True,
                connect_args={"timeout": 5},
            )
            # Connectivity check + schema bootstrap in one round trip.
            async with engine.begin() as conn:
                await conn.execute(text(_CREATE_TABLE_SQL))
                for idx_sql in _CREATE_INDEX_SQL:
                    await conn.execute(text(idx_sql))
            self._engine = engine
            self._use_postgres = True
            logger.info("SignalDB connected to Postgres — signals will persist "
                        "across redeploys")
            return True
        except Exception as e:
            logger.warning(
                "!!! SignalDB could not reach Postgres (%s: %s) — FALLING BACK "
                "to IN-MEMORY store. Signals will NOT survive a redeploy. "
                "Check DATABASE_URL / DB health.",
                type(e).__name__, e,
            )
            self._engine = None
            self._use_postgres = False
            return False

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
            _signal_to_dict(s)
            for s in sorted(rows,
                            key=lambda x: x.created_at, reverse=True)[:limit]
        ]

    async def find_open_signal_today(self, symbol: str, statuses: tuple) -> Optional[dict]:
        """Same-day dedup lookup for `symbol`: the most recent signal created
        today (UTC) whose status is in `statuses`, else None. On Postgres this
        is an indexed range query (idx_signals_symbol_created); in-memory it
        scans the store. Replaces the old client-side 200-row scan."""
        if self._use_postgres:
            return await self._pg_find_open_today(symbol, statuses)
        today = datetime.now(timezone.utc).date()
        matches = [
            s for s in self._store
            if s.symbol == symbol
            and s.status in statuses
            and _as_utc(s.created_at).date() == today
        ]
        if not matches:
            return None
        return _signal_to_dict(max(matches, key=lambda x: x.created_at))

    async def update_signal_status(self, signal_id: str, new_status: str) -> None:
        if self._use_postgres:
            await self._pg_update_status(signal_id, new_status)
        else:
            for s in self._store:
                if s.signal_id == signal_id:
                    s.status = new_status
                    break

    async def mark_notified(self, signal_id: str) -> None:
        """Record that the Telegram confirmation for this signal was
        actually delivered — the re-notify sweep (cloud/api/main.py) only
        re-sends PENDING_CONFIRMATION signals that never got this stamp."""
        if self._use_postgres:
            await self._pg_mark_notified(signal_id)
        else:
            for s in self._store:
                if s.signal_id == signal_id:
                    s.notified_at = datetime.now()
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

    async def mark_closed(self, signal_id: str, exit_price: float, pnl: float) -> None:
        if self._use_postgres:
            await self._pg_mark_closed(signal_id, exit_price, pnl)
        else:
            for s in self._store:
                if s.signal_id == signal_id:
                    s.status = "CLOSED"
                    s.exit_price = exit_price
                    s.pnl = pnl
                    s.closed_at = datetime.now()
                    break

    async def get_signal(self, signal_id: str) -> Optional[Signal]:
        if self._use_postgres:
            return await self._pg_get(signal_id)
        for s in self._store:
            if s.signal_id == signal_id:
                return s
        return None

    async def counts_by_status_today(self) -> dict[str, int]:
        """{status: count} for signals created today (UTC) — feeds the S5-6
        observability cockpit. Empty dict on a quiet day."""
        if self._use_postgres:
            return await self._pg_counts_by_status_today()
        today = datetime.now(timezone.utc).date()
        counts: dict[str, int] = {}
        for s in self._store:
            if _as_utc(s.created_at).date() == today:
                counts[s.status] = counts.get(s.status, 0) + 1
        return counts

    # ── Postgres implementations (live once connect() succeeds) ───────────────

    async def _pg_insert(self, signal: Signal) -> None:
        from sqlalchemy import text
        sql = text(
            f"INSERT INTO signals ({_COLUMNS}) VALUES ("
            ":signal_id, :user_id, :symbol, :action, :price, :timeframe, "
            ":strategy, :confluence_score, :confidence_score, :stop_loss, "
            ":status, :created_at, :notified_at, :executed_at, "
            ":execution_price, :closed_at, :exit_price, :pnl) "
            "ON CONFLICT (signal_id) DO NOTHING"
        )
        async with self._engine.begin() as conn:
            await conn.execute(sql, {
                "signal_id":        signal.signal_id,
                "user_id":          signal.user_id,
                "symbol":           signal.symbol,
                "action":           signal.action,
                "price":            signal.price,
                "timeframe":        signal.timeframe,
                "strategy":         signal.strategy,
                "confluence_score": signal.confluence_score,
                "confidence_score": signal.confidence_score,
                "stop_loss":        signal.stop_loss,
                "status":           signal.status,
                "created_at":       _as_utc(signal.created_at),
                "notified_at":      signal.notified_at,
                "executed_at":      signal.executed_at,
                "execution_price":  signal.execution_price,
                "closed_at":        signal.closed_at,
                "exit_price":       signal.exit_price,
                "pnl":              signal.pnl,
            })

    async def _pg_fetch(self, limit: int, status: Optional[str] = None) -> list[dict]:
        from sqlalchemy import text
        where = "WHERE status = :status " if status else ""
        sql = text(
            f"SELECT {_COLUMNS} FROM signals {where}"
            "ORDER BY created_at DESC LIMIT :limit"
        )
        params = {"limit": limit}
        if status:
            params["status"] = status
        async with self._engine.begin() as conn:
            result = await conn.execute(sql, params)
            return [_row_to_dict(r) for r in result]

    async def _pg_find_open_today(self, symbol: str, statuses: tuple) -> Optional[dict]:
        from sqlalchemy import bindparam, text
        now = datetime.now(timezone.utc)
        day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        sql = text(
            f"SELECT {_COLUMNS} FROM signals "
            "WHERE symbol = :symbol "
            "AND status IN :statuses "
            "AND created_at >= :day_start AND created_at < :day_end "
            "ORDER BY created_at DESC LIMIT 1"
        ).bindparams(bindparam("statuses", expanding=True))
        async with self._engine.begin() as conn:
            result = await conn.execute(sql, {
                "symbol": symbol,
                "statuses": list(statuses),
                "day_start": day_start,
                "day_end": day_end,
            })
            row = result.first()
            return _row_to_dict(row) if row is not None else None

    async def _pg_update_status(self, signal_id: str, status: str) -> None:
        from sqlalchemy import text
        async with self._engine.begin() as conn:
            await conn.execute(
                text("UPDATE signals SET status = :status WHERE signal_id = :id"),
                {"status": status, "id": signal_id},
            )

    async def _pg_mark_notified(self, signal_id: str) -> None:
        from sqlalchemy import text
        async with self._engine.begin() as conn:
            await conn.execute(
                text("UPDATE signals SET notified_at = NOW() WHERE signal_id = :id"),
                {"id": signal_id},
            )

    async def _pg_mark_executed(self, signal_id: str, execution_price: float) -> None:
        from sqlalchemy import text
        async with self._engine.begin() as conn:
            await conn.execute(
                text("UPDATE signals SET status = 'EXECUTED', "
                     "execution_price = :price, executed_at = NOW() "
                     "WHERE signal_id = :id"),
                {"price": execution_price, "id": signal_id},
            )

    async def _pg_mark_closed(self, signal_id: str, exit_price: float, pnl: float) -> None:
        from sqlalchemy import text
        async with self._engine.begin() as conn:
            await conn.execute(
                text("UPDATE signals SET status = 'CLOSED', "
                     "exit_price = :exit_price, pnl = :pnl, closed_at = NOW() "
                     "WHERE signal_id = :id"),
                {"exit_price": exit_price, "pnl": pnl, "id": signal_id},
            )

    async def _pg_get(self, signal_id: str) -> Optional[Signal]:
        from sqlalchemy import text
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text(f"SELECT {_COLUMNS} FROM signals WHERE signal_id = :id"),
                {"id": signal_id},
            )
            row = result.first()
            return _row_to_signal(row) if row is not None else None

    async def _pg_counts_by_status_today(self) -> dict[str, int]:
        from sqlalchemy import text
        now = datetime.now(timezone.utc)
        day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        # Uses idx_signals_status_created (status, created_at).
        sql = text(
            "SELECT status, COUNT(*) AS n FROM signals "
            "WHERE created_at >= :day_start GROUP BY status"
        )
        async with self._engine.begin() as conn:
            result = await conn.execute(sql, {"day_start": day_start})
            return {r._mapping["status"]: r._mapping["n"] for r in result}


def _as_utc(dt: datetime) -> datetime:
    """Treat naive datetimes (in-memory mark_* stamps) as UTC so date math and
    timestamptz binding stay consistent."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def get_db() -> SignalDB:
    global _db_instance
    if _db_instance is None:
        _db_instance = SignalDB()
    return _db_instance
