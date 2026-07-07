"""
S4-1 · SignalDB persistence layer — Unit Tests

Covers the parts that run without a live Postgres:
  - connectivity gating (connect() falls back to in-memory, app still boots)
  - DSN normalization for the asyncpg driver
  - the indexed same-day dedup query on the in-memory path

The Postgres SQL paths are exercised in production against Railway; here we
only assert the in-memory fallback stays correct and the gate never crashes.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

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


# ── Connectivity gating (must never crash the app) ────────────────────────────

@pytest.mark.asyncio
async def test_connect_without_database_url_stays_in_memory(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db = SignalDB()
    ok = await db.connect()
    assert ok is False
    assert db._use_postgres is False


@pytest.mark.asyncio
async def test_connect_unreachable_db_falls_back_not_raises(monkeypatch):
    """P0-3: gate on a real connectivity check — an unreachable Postgres must
    fall back to in-memory (loud warning) rather than crash startup."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/nope")
    db = SignalDB()
    ok = await db.connect()          # must not raise
    assert ok is False
    assert db._use_postgres is False
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
