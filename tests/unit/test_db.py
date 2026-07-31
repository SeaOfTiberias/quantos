"""
S4-1 · SignalDB persistence layer — Unit Tests

Covers:
  - connectivity gating (connect() falls back to in-memory, app still boots)
  - DSN normalization for the asyncpg AND aiosqlite drivers
  - the indexed same-day dedup query on the in-memory path
  - the FULL SQLite SQL path end-to-end, against a real temp-file DB (no
    external dependency needed, unlike Postgres) — added 2026-07-31 when
    the project moved off Railway onto self-hosting the cloud API on the
    Oracle VM with SQLite instead of Postgres. Specifically exercises the
    datetime marshal/parse round-trip (_marshal_params/_parse_dt in
    cloud/api/db.py), since that's the one place a subtle bug could
    silently corrupt timestamps.

The Postgres SQL path itself has no local/CI-reachable database and is not
covered here (previously exercised in production against Railway); only
the in-memory fallback and the connectivity gate are asserted for it.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from cloud.api.db import SignalDB, Signal, _normalize_dsn

_STATUSES = ("PENDING_CONFIRMATION", "CONFIRMED", "EXECUTED", "BLOCKED_EVENT_RISK")


def _sig(symbol: str, status: str, created_at: datetime) -> Signal:
    return Signal(
        signal_id=f"SIG-TEST-{uuid.uuid4().hex[:8].upper()}",
        user_id="system", symbol=symbol, action="BUY", price=100.0,
        timeframe="1h", strategy="darvas_breakout", confluence_score=90,
        confidence_score=80.0, stop_loss=95.0, status=status,
        created_at=created_at,
    )


# ── DSN normalization ─────────────────────────────────────────────────────────

def test_normalize_dsn_swaps_postgres_scheme():
    assert _normalize_dsn("postgres://u:p@host:5432/db") == \
        "postgresql+asyncpg://u:p@host:5432/db"


def test_normalize_dsn_swaps_postgresql_scheme():
    assert _normalize_dsn("postgresql://u:p@host:5432/db") == \
        "postgresql+asyncpg://u:p@host:5432/db"


def test_normalize_dsn_strips_sslmode_param():
    out = _normalize_dsn("postgresql://u:p@host/db?sslmode=require")
    assert "sslmode" not in out
    assert out == "postgresql+asyncpg://u:p@host/db"


def test_normalize_dsn_keeps_other_params():
    out = _normalize_dsn("postgres://u:p@host/db?sslmode=require&application_name=q")
    assert out == "postgresql+asyncpg://u:p@host/db?application_name=q"


def test_normalize_dsn_swaps_sqlite_scheme():
    assert _normalize_dsn("sqlite:///data/quantos.db") == \
        "sqlite+aiosqlite:///data/quantos.db"


def test_normalize_dsn_leaves_already_correct_sqlite_scheme_alone():
    assert _normalize_dsn("sqlite+aiosqlite:///data/quantos.db") == \
        "sqlite+aiosqlite:///data/quantos.db"


# ── Connectivity gating (must never crash the app) ────────────────────────────

@pytest.mark.asyncio
async def test_connect_without_database_url_stays_in_memory(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db = SignalDB()
    ok = await db.connect()
    assert ok is False
    assert db.is_persistent is False
    assert db.backend == "memory"


@pytest.mark.asyncio
async def test_connect_unreachable_db_falls_back_not_raises(monkeypatch):
    """P0-3: gate on a real connectivity check — an unreachable database must
    fall back to in-memory (loud warning) rather than crash startup."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/nope")
    db = SignalDB()
    ok = await db.connect()          # must not raise
    assert ok is False
    assert db.is_persistent is False
    # Fallback store is still fully functional after a failed connect.
    await db.insert_signal(_sig("RELIANCE", "PENDING_CONFIRMATION",
                                datetime.now(timezone.utc)))
    rows = await db.fetch_recent_signals(limit=10)
    assert len(rows) == 1


# ── Indexed same-day dedup query (in-memory path) ─────────────────────────────

@pytest.mark.asyncio
async def test_find_open_signal_today_matches_live_status():
    db = SignalDB()
    sym = f"AAA{uuid.uuid4().hex[:6].upper()}"
    await db.insert_signal(_sig(sym, "PENDING_CONFIRMATION", datetime.now(timezone.utc)))
    hit = await db.find_open_signal_today(sym, _STATUSES)
    assert hit is not None
    assert hit["symbol"] == sym


@pytest.mark.asyncio
async def test_find_open_signal_today_ignores_settled_status():
    db = SignalDB()
    sym = f"BBB{uuid.uuid4().hex[:6].upper()}"
    await db.insert_signal(_sig(sym, "SKIPPED", datetime.now(timezone.utc)))
    assert await db.find_open_signal_today(sym, _STATUSES) is None


@pytest.mark.asyncio
async def test_find_open_signal_today_ignores_prior_days():
    db = SignalDB()
    sym = f"CCC{uuid.uuid4().hex[:6].upper()}"
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    await db.insert_signal(_sig(sym, "EXECUTED", yesterday))
    assert await db.find_open_signal_today(sym, _STATUSES) is None


@pytest.mark.asyncio
async def test_find_open_signal_today_returns_most_recent():
    db = SignalDB()
    sym = f"DDD{uuid.uuid4().hex[:6].upper()}"
    now = datetime.now(timezone.utc)
    await db.insert_signal(_sig(sym, "PENDING_CONFIRMATION", now - timedelta(hours=2)))
    newer = _sig(sym, "EXECUTED", now - timedelta(minutes=5))
    await db.insert_signal(newer)
    hit = await db.find_open_signal_today(sym, _STATUSES)
    assert hit["signal_id"] == newer.signal_id


@pytest.mark.asyncio
async def test_find_open_signal_today_isolates_symbols():
    db = SignalDB()
    a = f"EEE{uuid.uuid4().hex[:6].upper()}"
    b = f"FFF{uuid.uuid4().hex[:6].upper()}"
    await db.insert_signal(_sig(a, "CONFIRMED", datetime.now(timezone.utc)))
    assert await db.find_open_signal_today(b, _STATUSES) is None


@pytest.mark.asyncio
async def test_find_open_signal_today_handles_naive_created_at():
    """mark_* stamps use naive datetimes; the dedup date math must treat them
    as UTC rather than raising on aware/naive comparison."""
    db = SignalDB()
    sym = f"GGG{uuid.uuid4().hex[:6].upper()}"
    # Naive but genuinely UTC-clocked, so the date match is deterministic
    # regardless of the test host's local timezone.
    naive_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.insert_signal(_sig(sym, "PENDING_CONFIRMATION", naive_utc))
    hit = await db.find_open_signal_today(sym, _STATUSES)
    assert hit is not None


# ── SQLite path, end-to-end against a real temp-file DB ───────────────────────

@pytest_asyncio.fixture
async def sqlite_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_quantos.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    db = SignalDB()
    ok = await db.connect()
    assert ok is True
    assert db.backend == "sqlite"
    return db


@pytest.mark.asyncio
async def test_sqlite_connect_creates_schema_and_reports_backend(sqlite_db):
    assert sqlite_db.is_persistent is True
    assert sqlite_db.last_connect_error is None


@pytest.mark.asyncio
async def test_sqlite_insert_and_fetch_round_trips_all_fields(sqlite_db):
    sig = _sig("RELIANCE", "PENDING_CONFIRMATION", datetime.now(timezone.utc))
    await sqlite_db.insert_signal(sig)
    rows = await sqlite_db.fetch_recent_signals(limit=10)
    assert len(rows) == 1
    row = rows[0]
    assert row["signal_id"] == sig.signal_id
    assert row["symbol"] == "RELIANCE"
    assert row["price"] == 100.0
    assert row["confluence_score"] == 90
    # created_at must come back as a real ISO string (not a raw sqlite3
    # object repr) -- the whole point of _marshal_params/_parse_dt.
    assert isinstance(row["created_at"], str)
    datetime.fromisoformat(row["created_at"])  # must not raise


@pytest.mark.asyncio
async def test_sqlite_insert_ignores_duplicate_signal_id(sqlite_db):
    sig = _sig("TCS", "PENDING_CONFIRMATION", datetime.now(timezone.utc))
    await sqlite_db.insert_signal(sig)
    await sqlite_db.insert_signal(sig)  # ON CONFLICT DO NOTHING
    rows = await sqlite_db.fetch_recent_signals(limit=10)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_sqlite_find_open_signal_today_matches_and_isolates(sqlite_db):
    sym = f"AAA{uuid.uuid4().hex[:6].upper()}"
    await sqlite_db.insert_signal(_sig(sym, "PENDING_CONFIRMATION", datetime.now(timezone.utc)))
    hit = await sqlite_db.find_open_signal_today(sym, _STATUSES)
    assert hit is not None
    assert hit["symbol"] == sym
    assert await sqlite_db.find_open_signal_today("NOPE", _STATUSES) is None


@pytest.mark.asyncio
async def test_sqlite_find_open_signal_today_ignores_prior_days(sqlite_db):
    sym = f"BBB{uuid.uuid4().hex[:6].upper()}"
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    await sqlite_db.insert_signal(_sig(sym, "EXECUTED", yesterday))
    assert await sqlite_db.find_open_signal_today(sym, _STATUSES) is None


@pytest.mark.asyncio
async def test_sqlite_update_status(sqlite_db):
    sig = _sig("INFY", "PENDING_CONFIRMATION", datetime.now(timezone.utc))
    await sqlite_db.insert_signal(sig)
    await sqlite_db.update_signal_status(sig.signal_id, "CONFIRMED")
    got = await sqlite_db.get_signal(sig.signal_id)
    assert got.status == "CONFIRMED"


@pytest.mark.asyncio
async def test_sqlite_mark_notified_sets_real_datetime(sqlite_db):
    sig = _sig("HDFC", "PENDING_CONFIRMATION", datetime.now(timezone.utc))
    await sqlite_db.insert_signal(sig)
    await sqlite_db.mark_notified(sig.signal_id)
    got = await sqlite_db.get_signal(sig.signal_id)
    # get_signal returns a Signal dataclass -- notified_at must be a real
    # datetime (not the ISO string it's stored as), same contract as the
    # Postgres/in-memory paths, since callers call .isoformat() on it.
    assert isinstance(got.notified_at, datetime)


@pytest.mark.asyncio
async def test_sqlite_mark_executed_sets_status_price_and_timestamp(sqlite_db):
    sig = _sig("WIPRO", "CONFIRMED", datetime.now(timezone.utc))
    await sqlite_db.insert_signal(sig)
    await sqlite_db.mark_executed(sig.signal_id, 123.45)
    got = await sqlite_db.get_signal(sig.signal_id)
    assert got.status == "EXECUTED"
    assert got.execution_price == 123.45
    assert isinstance(got.executed_at, datetime)


@pytest.mark.asyncio
async def test_sqlite_mark_closed_sets_status_pnl_and_timestamp(sqlite_db):
    sig = _sig("ITC", "EXECUTED", datetime.now(timezone.utc))
    await sqlite_db.insert_signal(sig)
    await sqlite_db.mark_closed(sig.signal_id, 110.0, 500.0)
    got = await sqlite_db.get_signal(sig.signal_id)
    assert got.status == "CLOSED"
    assert got.exit_price == 110.0
    assert got.pnl == 500.0
    assert isinstance(got.closed_at, datetime)


@pytest.mark.asyncio
async def test_sqlite_counts_by_status_today(sqlite_db):
    await sqlite_db.insert_signal(_sig("A", "PENDING_CONFIRMATION", datetime.now(timezone.utc)))
    await sqlite_db.insert_signal(_sig("B", "PENDING_CONFIRMATION", datetime.now(timezone.utc)))
    await sqlite_db.insert_signal(_sig("C", "CONFIRMED", datetime.now(timezone.utc)))
    counts = await sqlite_db.counts_by_status_today()
    assert counts["PENDING_CONFIRMATION"] == 2
    assert counts["CONFIRMED"] == 1


@pytest.mark.asyncio
async def test_sqlite_options_detail_column_present_from_fresh_schema(sqlite_db):
    """The SQLite schema bakes options_detail in from the start (see
    _CREATE_TABLE_SQL_SQLITE's comment) rather than relying on the
    Postgres-only ADD COLUMN IF NOT EXISTS migration."""
    sig = _sig("NIFTY", "PENDING_CONFIRMATION", datetime.now(timezone.utc))
    sig.options_detail = '{"legs": []}'
    await sqlite_db.insert_signal(sig)
    got = await sqlite_db.get_signal(sig.signal_id)
    assert got.options_detail == '{"legs": []}'
