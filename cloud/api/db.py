"""
QuantOS — Signal Database Layer
────────────────────────────────
Persistence for signals (ADR-03: user_id on every row), Postgres OR SQLite
via the same SQLAlchemy async engine — added 2026-07-31 when the project
moved off Railway (trial expired) onto self-hosting on the Oracle VM,
where SQLite (a file, no second always-on server process to fit into an
already-tight ~1GB RAM budget) was chosen over installing local Postgres.
Uses SQLAlchemy async for non-blocking DB ops within FastAPI.

Persistence is gated on a *startup connectivity check* (SignalDB.connect),
NOT on the mere presence of DATABASE_URL — gating on the env var alone
crashed production once, because Railway links a Postgres plugin (setting
DATABASE_URL) before the app code was wired to it. If the connection check
fails at boot, we log a loud warning and fall back to the in-memory store so
the app still boots; signals just won't survive a restart in that state.

SQLite has no native datetime type and (deliberately) no reliance here on
Python's sqlite3 DBAPI default datetime adapters (deprecated in 3.12+,
version-fragile even before that) — every datetime is explicitly
serialized to an ISO-8601 UTC string before binding (`_marshal_params`)
and parsed back on read (`_parse_dt`), so behavior is identical across
Python versions instead of depending on implicit DBAPI magic.
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
    # Multi-leg options signals only (cloud/api/options_routes.py execution
    # endpoints) — JSON-encoded {"expiry", "legs", "rationale", "max_profit",
    # "max_loss", "net_premium", "probability_of_profit", "regime_context"}.
    # NULL for every equity signal (Darvas/rotation). `symbol` holds the
    # underlying (e.g. "NIFTY"), `action`/`price` hold the strategy template
    # name and abs(net_premium) as the closest single-value stand-ins so
    # every other existing consumer of the signals table keeps working
    # unmodified — the real per-leg detail lives here.
    options_detail:   Optional[str] = None


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
    pnl               DOUBLE PRECISION,
    options_detail    TEXT
);
"""

_ADD_OPTIONS_DETAIL_COLUMN_SQL = (
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS options_detail TEXT;"
)

# SQLite has no DOUBLE PRECISION/TIMESTAMPTZ and no `ADD COLUMN IF NOT
# EXISTS` (unlike Postgres, both above) -- a separate schema, used only
# when SignalDB.connect() detects a sqlite DSN. options_detail is included
# from the start (no separate migration statement needed): every SQLite
# deployment here starts fresh (2026-07-31 VM self-host migration), so
# there is no pre-existing table missing the column to migrate.
# Timestamps are stored as TEXT (ISO-8601 UTC strings, see module
# docstring) rather than a native type -- see _marshal_params/_parse_dt.
_CREATE_TABLE_SQL_SQLITE = """
CREATE TABLE IF NOT EXISTS signals (
    signal_id         TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL DEFAULT 'system',
    symbol            TEXT NOT NULL,
    action            TEXT NOT NULL,
    price             REAL NOT NULL,
    timeframe         TEXT NOT NULL,
    strategy          TEXT NOT NULL,
    confluence_score  REAL NOT NULL,
    confidence_score  REAL,
    stop_loss         REAL,
    status            TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    notified_at       TEXT,
    executed_at       TEXT,
    execution_price   REAL,
    closed_at         TEXT,
    exit_price        REAL,
    pnl               REAL,
    options_detail    TEXT
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
    "notified_at, executed_at, execution_price, closed_at, exit_price, pnl, "
    "options_detail"
)


def _normalize_dsn(dsn: str) -> str:
    """SQLAlchemy async needs an explicit async driver in the scheme.
    Railway hands out `postgres://` / `postgresql://` (upgraded to
    `+asyncpg`); a local SQLite file DSN (`sqlite:///path`) is upgraded to
    `+aiosqlite` the same way. Also strip a `sslmode` query param -- that's
    a psycopg keyword asyncpg rejects (it uses `ssl` instead); harmless
    no-op for sqlite DSNs, which never carry one."""
    if dsn.startswith("postgres://"):
        dsn = "postgresql+asyncpg://" + dsn[len("postgres://"):]
    elif dsn.startswith("postgresql://"):
        dsn = "postgresql+asyncpg://" + dsn[len("postgresql://"):]
    elif dsn.startswith("sqlite://") and not dsn.startswith("sqlite+aiosqlite://"):
        dsn = "sqlite+aiosqlite://" + dsn[len("sqlite://"):]
    # Drop libpq-only query params asyncpg doesn't understand.
    if "?" in dsn:
        base, _, query = dsn.partition("?")
        kept = [kv for kv in query.split("&")
                if kv and not kv.lower().startswith("sslmode=")]
        dsn = base + ("?" + "&".join(kept) if kept else "")
    return dsn


def _marshal_params(dialect: str, params: dict) -> dict:
    """SQLite path only: serialize any datetime value to an ISO-8601 UTC
    string before binding (see module docstring for why this is explicit
    rather than relying on DBAPI default adapters). No-op for Postgres,
    which takes native datetime objects via asyncpg."""
    if dialect != "sqlite":
        return params
    out = {}
    for k, v in params.items():
        out[k] = _as_utc(v).isoformat() if isinstance(v, datetime) else v
    return out


def _parse_dt(v):
    """Accepts either a real datetime (Postgres row) or an ISO-8601 string
    (SQLite row, see _marshal_params) and always returns a datetime (or
    None) -- lets the shared row-conversion helpers below stay dialect-
    agnostic instead of threading a dialect flag through every call."""
    if v is None or isinstance(v, datetime):
        return v
    return datetime.fromisoformat(v)


def _row_to_dict(row) -> dict:
    """Serialize a Postgres OR SQLite row to the exact dict shape the
    in-memory path returns (timestamps as ISO strings, or None)."""
    m = row._mapping
    def _iso(v):
        if v is None:
            return None
        return v if isinstance(v, str) else v.isoformat()  # SQLite: already ISO text
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
        "options_detail":   m["options_detail"],
    }


def _row_to_signal(row) -> Signal:
    """Postgres OR SQLite row -> Signal. `created_at`/`notified_at`/
    `executed_at`/`closed_at` must come back as real datetimes (Signal's
    own dataclass fields are typed that way, and `_signal_to_dict` calls
    `.isoformat()` on them) -- `_parse_dt` handles SQLite's ISO-string
    rows transparently."""
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
        created_at=_parse_dt(m["created_at"]),
        notified_at=_parse_dt(m["notified_at"]),
        executed_at=_parse_dt(m["executed_at"]),
        execution_price=m["execution_price"],
        closed_at=_parse_dt(m["closed_at"]),
        exit_price=m["exit_price"],
        pnl=m["pnl"],
        options_detail=m["options_detail"],
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
        "options_detail":   s.options_detail,
    }


class SignalDB:
    """
    Lightweight DB wrapper. In production this uses SQLAlchemy async over
    either Postgres (asyncpg) or SQLite (aiosqlite) -- whichever DATABASE_URL
    points at. In development / tests it falls back to an in-memory store.
    """

    def __init__(self):
        self._store: list[Signal] = []   # dev / fallback store
        self._engine = None
        # "memory" until connect() proves a real DB reachable this boot --
        # the real persistence state, distinct from DATABASE_URL merely
        # being set (see module docstring). "memory" means every signal
        # since this boot is in-memory only and will vanish on restart.
        self._backend = "memory"
        # Exception TYPE only (e.g. "TimeoutError", "InvalidPasswordError") —
        # deliberately not str(e), which can echo the DSN (including
        # credentials) back for some asyncpg/sqlalchemy failures, and this is
        # read by a public, unauthenticated /status endpoint. Full detail
        # stays in the server-side warning log below.
        self._last_connect_error: Optional[str] = None

    @property
    def is_persistent(self) -> bool:
        """True iff connect() has proven a real DB (Postgres or SQLite)
        reachable this boot. False means every signal since this boot is
        in-memory only and will vanish on restart."""
        return self._backend != "memory"

    @property
    def backend(self) -> str:
        """"postgres" | "sqlite" | "memory" -- which persistence path is
        actually live this boot (not just which DATABASE_URL is configured)."""
        return self._backend

    @property
    def last_connect_error(self) -> Optional[str]:
        """Exception class name from the most recent failed connect(), or
        None if it hasn't failed (either never tried, or currently connected).
        See _last_connect_error's comment for why this isn't the full message."""
        return self._last_connect_error

    async def connect(self) -> bool:
        """Attempt to bring up real persistence (Postgres or SQLite, per
        DATABASE_URL's scheme). Runs a real connectivity check + CREATE
        TABLE IF NOT EXISTS; on any failure it logs a loud warning and
        leaves the wrapper on the in-memory store so the app can still
        boot. Returns True iff a real backend is now live. Idempotent."""
        if self.is_persistent:
            return True
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            logger.info("DATABASE_URL unset — SignalDB using in-memory store "
                        "(signals will NOT survive a restart)")
            return False
        try:
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine

            normalized = _normalize_dsn(dsn)
            engine = create_async_engine(
                normalized,
                pool_pre_ping=True,
                connect_args={"timeout": 5},
            )
            dialect = engine.dialect.name  # "postgresql" | "sqlite"
            # Connectivity check + schema bootstrap in one round trip.
            async with engine.begin() as conn:
                if dialect == "sqlite":
                    await conn.execute(text(_CREATE_TABLE_SQL_SQLITE))
                    # No ADD COLUMN migration needed -- every SQLite
                    # deployment starts fresh with options_detail already
                    # in the schema (see _CREATE_TABLE_SQL_SQLITE's comment).
                else:
                    await conn.execute(text(_CREATE_TABLE_SQL))
                    # Migration for tables created before options_detail
                    # existed (CREATE TABLE IF NOT EXISTS is a no-op on an
                    # already-live table) — safe every boot, IF NOT EXISTS
                    # makes it idempotent. Postgres-only syntax.
                    await conn.execute(text(_ADD_OPTIONS_DETAIL_COLUMN_SQL))
                for idx_sql in _CREATE_INDEX_SQL:
                    await conn.execute(text(idx_sql))
            self._engine = engine
            self._backend = "sqlite" if dialect == "sqlite" else "postgres"
            self._last_connect_error = None
            logger.info("SignalDB connected to %s — signals will persist "
                        "across restarts", self._backend)
            return True
        except Exception as e:
            logger.warning(
                "!!! SignalDB could not reach the configured database (%s: %s) "
                "— FALLING BACK to IN-MEMORY store. Signals will NOT survive "
                "a restart. Check DATABASE_URL / DB health.",
                type(e).__name__, e,
            )
            self._engine = None
            self._backend = "memory"
            self._last_connect_error = type(e).__name__
            return False

    async def insert_signal(self, signal: Signal) -> None:
        if self.is_persistent:
            await self._sql_insert(signal)
        else:
            self._store.append(signal)

    async def fetch_recent_signals(self, limit: int = 20, status: Optional[str] = None) -> list[dict]:
        if self.is_persistent:
            return await self._sql_fetch(limit, status)
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
        today (UTC) whose status is in `statuses`, else None. On a real
        backend this is an indexed range query (idx_signals_symbol_created);
        in-memory it scans the store. Replaces the old client-side 200-row
        scan."""
        if self.is_persistent:
            return await self._sql_find_open_today(symbol, statuses)
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
        if self.is_persistent:
            await self._sql_update_status(signal_id, new_status)
        else:
            for s in self._store:
                if s.signal_id == signal_id:
                    s.status = new_status
                    break

    async def mark_notified(self, signal_id: str) -> None:
        """Record that the Telegram confirmation for this signal was
        actually delivered — the re-notify sweep (cloud/api/main.py) only
        re-sends PENDING_CONFIRMATION signals that never got this stamp."""
        if self.is_persistent:
            await self._sql_mark_notified(signal_id)
        else:
            for s in self._store:
                if s.signal_id == signal_id:
                    s.notified_at = datetime.now()
                    break

    async def mark_executed(self, signal_id: str, execution_price: float) -> None:
        if self.is_persistent:
            await self._sql_mark_executed(signal_id, execution_price)
        else:
            for s in self._store:
                if s.signal_id == signal_id:
                    s.status = "EXECUTED"
                    s.execution_price = execution_price
                    s.executed_at = datetime.now()
                    break

    async def mark_closed(self, signal_id: str, exit_price: float, pnl: float) -> None:
        if self.is_persistent:
            await self._sql_mark_closed(signal_id, exit_price, pnl)
        else:
            for s in self._store:
                if s.signal_id == signal_id:
                    s.status = "CLOSED"
                    s.exit_price = exit_price
                    s.pnl = pnl
                    s.closed_at = datetime.now()
                    break

    async def get_signal(self, signal_id: str) -> Optional[Signal]:
        if self.is_persistent:
            return await self._sql_get(signal_id)
        for s in self._store:
            if s.signal_id == signal_id:
                return s
        return None

    async def counts_by_status_today(self) -> dict[str, int]:
        """{status: count} for signals created today (UTC) — feeds the S5-6
        observability cockpit. Empty dict on a quiet day."""
        if self.is_persistent:
            return await self._sql_counts_by_status_today()
        today = datetime.now(timezone.utc).date()
        counts: dict[str, int] = {}
        for s in self._store:
            if _as_utc(s.created_at).date() == today:
                counts[s.status] = counts.get(s.status, 0) + 1
        return counts

    # ── SQL implementations (Postgres or SQLite, live once connect() succeeds) ──
    # Every method below binds via `_marshal_params(self._backend, params)` —
    # a no-op on Postgres, ISO-string serialization on SQLite (see module
    # docstring). `NOW()`/`CURRENT_TIMESTAMP` are deliberately NOT used for
    # notified_at/executed_at/closed_at (dialect-inconsistent formats
    # between Postgres and SQLite) — the timestamp is computed once in
    # Python and bound explicitly, same as the in-memory path already does.

    async def _sql_insert(self, signal: Signal) -> None:
        from sqlalchemy import text
        sql = text(
            f"INSERT INTO signals ({_COLUMNS}) VALUES ("
            ":signal_id, :user_id, :symbol, :action, :price, :timeframe, "
            ":strategy, :confluence_score, :confidence_score, :stop_loss, "
            ":status, :created_at, :notified_at, :executed_at, "
            ":execution_price, :closed_at, :exit_price, :pnl, :options_detail) "
            "ON CONFLICT (signal_id) DO NOTHING"
        )
        params = _marshal_params(self._backend, {
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
            "options_detail":   signal.options_detail,
        })
        async with self._engine.begin() as conn:
            await conn.execute(sql, params)

    async def _sql_fetch(self, limit: int, status: Optional[str] = None) -> list[dict]:
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

    async def _sql_find_open_today(self, symbol: str, statuses: tuple) -> Optional[dict]:
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
        params = _marshal_params(self._backend, {
            "symbol": symbol,
            "statuses": list(statuses),
            "day_start": day_start,
            "day_end": day_end,
        })
        async with self._engine.begin() as conn:
            result = await conn.execute(sql, params)
            row = result.first()
            return _row_to_dict(row) if row is not None else None

    async def _sql_update_status(self, signal_id: str, status: str) -> None:
        from sqlalchemy import text
        async with self._engine.begin() as conn:
            await conn.execute(
                text("UPDATE signals SET status = :status WHERE signal_id = :id"),
                {"status": status, "id": signal_id},
            )

    async def _sql_mark_notified(self, signal_id: str) -> None:
        from sqlalchemy import text
        params = _marshal_params(self._backend, {
            "notified_at": datetime.now(timezone.utc), "id": signal_id,
        })
        async with self._engine.begin() as conn:
            await conn.execute(
                text("UPDATE signals SET notified_at = :notified_at WHERE signal_id = :id"),
                params,
            )

    async def _sql_mark_executed(self, signal_id: str, execution_price: float) -> None:
        from sqlalchemy import text
        params = _marshal_params(self._backend, {
            "price": execution_price, "executed_at": datetime.now(timezone.utc), "id": signal_id,
        })
        async with self._engine.begin() as conn:
            await conn.execute(
                text("UPDATE signals SET status = 'EXECUTED', "
                     "execution_price = :price, executed_at = :executed_at "
                     "WHERE signal_id = :id"),
                params,
            )

    async def _sql_mark_closed(self, signal_id: str, exit_price: float, pnl: float) -> None:
        from sqlalchemy import text
        params = _marshal_params(self._backend, {
            "exit_price": exit_price, "pnl": pnl,
            "closed_at": datetime.now(timezone.utc), "id": signal_id,
        })
        async with self._engine.begin() as conn:
            await conn.execute(
                text("UPDATE signals SET status = 'CLOSED', "
                     "exit_price = :exit_price, pnl = :pnl, closed_at = :closed_at "
                     "WHERE signal_id = :id"),
                params,
            )

    async def _sql_get(self, signal_id: str) -> Optional[Signal]:
        from sqlalchemy import text
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text(f"SELECT {_COLUMNS} FROM signals WHERE signal_id = :id"),
                {"id": signal_id},
            )
            row = result.first()
            return _row_to_signal(row) if row is not None else None

    async def _sql_counts_by_status_today(self) -> dict[str, int]:
        from sqlalchemy import text
        now = datetime.now(timezone.utc)
        day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        # Uses idx_signals_status_created (status, created_at).
        sql = text(
            "SELECT status, COUNT(*) AS n FROM signals "
            "WHERE created_at >= :day_start GROUP BY status"
        )
        params = _marshal_params(self._backend, {"day_start": day_start})
        async with self._engine.begin() as conn:
            result = await conn.execute(sql, params)
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
