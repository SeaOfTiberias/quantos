"""
QuantOS — Momentum Shortlist History
─────────────────────────────────────
Day-over-day memory for the shortlist scan. Added 2026-08-27, because the
scan had none: cloud/api/momentum_shortlist_routes.py replaces
`_shortlist_store[universe]` wholesale on every sync, and its JSON cache
mirrors only the latest snapshot. That cache's own comment is explicit that
it is "a regenerable mirror of a scan, not a record of anything that
happened" — which is exactly right, and exactly why the history that the
morning brief needs cannot live there. A record of what the board looked
like on a given morning IS a record of something that happened, so it goes
in the SQLite/Postgres layer next to the signals table.

Keyed on the IST calendar date of the scan, not the UTC timestamp: the scan
fires just after the daily Fyers token refresh, around 02:00 UTC / 07:30 IST,
so a UTC key is the same trading day but a confusing label, and a scan that
ever slipped past 18:30 UTC would land on the wrong day entirely.

Degradation matches SignalDB deliberately: no DATABASE_URL, or a backend
that won't connect, falls back to an in-memory dict rather than raising.
A missing brief must never be able to fail the sync that the scan just
spent 11 minutes producing.

"Previous session" is always the most recent scan_date STRICTLY BEFORE the
one being compared — read from the table, never derived from the trading
calendar. Scans get missed (a skipped token refresh, an unreachable broker,
a machine that was off), so a calendar-derived "yesterday" would silently
report "no data" on precisely the mornings a human most wants the diff.
Same trap docs/ADR notes call out for the calendar generally: do not derive
ground truth through a filter when you can read the ground truth.
"""

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# Columns carried into history. Deliberately a subset of ShortlistEntryIn:
# everything here is either ranked on, bucketed on, or something the brief
# reports a transition in. The wide vault/stage detail strings are left out —
# they are prose, they are large, and a diff of them is not readable.
# Vault scores are stored PER NOTE as JSON, never as the summed
# vault_rules_passed/vault_rules_total pair that ShortlistEntryIn also
# carries. core/vault/shortlist_audit.py sums them at line 126 but its own
# docstring says the two bundled notes are incommensurable and "must never
# be summed", and the cockpit's existing tables already refuse to show the
# aggregate for that reason. A day-over-day delta on a meaningless number
# would be a meaningless delta, so the aggregate is deliberately not carried
# here at all -- there is nothing downstream to misuse.
_FIELDS = (
    "bucket", "momentum_pct", "momentum_rank", "breakout_state", "trend_up",
    "ma_cross", "ma_cross_days", "box_width_pct", "rr_ratio",
    "vault_notes_json", "vault_verdict", "stage",
    "close",
    # Provenance. "sync" = written by the live POST from the scan and complete.
    # "journald-backfill" = reconstructed by scripts/backfill_shortlist_history.py
    # from the scan's own log lines, which do not carry `close`, `stage` or
    # `vault_verdict` — those are NULL on such rows. Recorded because a reader
    # comparing a backfilled day against a synced one is entitled to know that
    # the blanks are a limitation of the source, not a fact about the market.
    "source",
)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS shortlist_history (
    scan_date          TEXT NOT NULL,
    universe           TEXT NOT NULL,
    symbol             TEXT NOT NULL,
    bucket             TEXT NOT NULL,
    momentum_pct       DOUBLE PRECISION,
    momentum_rank      INTEGER,
    breakout_state     TEXT,
    trend_up           INTEGER,
    ma_cross           TEXT,
    ma_cross_days      INTEGER,
    box_width_pct      DOUBLE PRECISION,
    rr_ratio           DOUBLE PRECISION,
    vault_notes_json   TEXT,
    vault_verdict      TEXT,
    stage              INTEGER,
    close              DOUBLE PRECISION,
    source             TEXT NOT NULL DEFAULT 'sync',
    PRIMARY KEY (scan_date, universe, symbol)
)
"""

# One index, on the lookup the brief actually does: "the sessions for this
# universe, newest first". The primary key already covers per-session reads.
_CREATE_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_shortlist_history_universe_date "
    "ON shortlist_history (universe, scan_date DESC)",
)


def ist_today() -> date:
    """The IST calendar date right now — the scan's own sense of 'today'."""
    return datetime.now(IST).date()


def _row_to_entry(row) -> dict:
    m = row._mapping
    out = {"symbol": m["symbol"]}
    for f in _FIELDS:
        v = m[f]
        # SQLite has no bool; trend_up round-trips as 0/1 and must come back
        # out as a bool or the cockpit renders "0" as a truthy string.
        out[f] = bool(v) if f == "trend_up" and v is not None else v
    out["vault_notes"] = _parse_notes(out.pop("vault_notes_json", None))
    return out


def _parse_notes(raw) -> list[dict]:
    """JSON text column -> list of per-note score dicts. A corrupt or absent
    value degrades to no notes, never to an exception: a brief that renders
    without one name's vault column beats a brief that 500s."""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


class ShortlistHistory:
    """Append-only daily snapshots of the shortlist, one row per symbol per
    universe per scan date. Re-syncing the same day overwrites that day (the
    scan is idempotent and a re-run is a correction, not a second session)."""

    def __init__(self):
        self._engine = None
        self._backend = "memory"
        # (scan_date, universe) -> list[entry dict]; the fallback store.
        self._mem: dict[tuple[str, str], list[dict]] = {}

    @property
    def is_persistent(self) -> bool:
        return self._backend != "memory"

    @property
    def backend(self) -> str:
        return self._backend

    async def connect(self) -> bool:
        """Bring up real persistence and bootstrap the schema. Idempotent.
        Never raises — a failure leaves the in-memory fallback in place and
        logs, exactly as SignalDB.connect does."""
        if self.is_persistent:
            return True
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            logger.info("DATABASE_URL unset — shortlist history using in-memory "
                        "store (the morning brief will have no day-over-day "
                        "deltas after a restart)")
            return False
        try:
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine

            from cloud.api.db import _normalize_dsn

            engine = create_async_engine(
                _normalize_dsn(dsn), pool_pre_ping=True,
                connect_args={"timeout": 5},
            )
            async with engine.begin() as conn:
                await conn.execute(text(_CREATE_TABLE_SQL))
                for idx in _CREATE_INDEX_SQL:
                    await conn.execute(text(idx))
            self._engine = engine
            self._backend = "sqlite" if engine.dialect.name == "sqlite" else "postgres"
            logger.info("Shortlist history connected to %s", self._backend)
            return True
        except Exception as e:
            logger.warning(
                "!!! Shortlist history could not reach the database (%s: %s) — "
                "falling back to IN-MEMORY. Day-over-day deltas will not "
                "survive a restart.", type(e).__name__, e,
            )
            self._engine = None
            self._backend = "memory"
            return False

    async def record_snapshot(self, universe: str, entries: list[dict],
                              scan_date: Optional[date] = None,
                              source: str = "sync") -> int:
        """Store one scan's entries for one universe. Returns rows written.

        Never raises: this is called from inside the sync endpoint, and a
        history write that fails must not lose the scan itself."""
        day = (scan_date or ist_today()).isoformat()
        rows = [self._project(e, source) for e in entries]
        rows = [r for r in rows if r["symbol"]]
        try:
            if self.is_persistent:
                await self._sql_replace_day(universe, day, rows)
            else:
                self._mem[(day, universe)] = rows
            return len(rows)
        except Exception as e:
            logger.warning("Shortlist history write failed for %s %s (%s: %s) — "
                           "the sync itself is unaffected.",
                           universe, day, type(e).__name__, e)
            return 0

    @staticmethod
    def _project(entry: dict, source: str = "sync") -> dict:
        out = {"symbol": entry.get("symbol")}
        for f in _FIELDS:
            out[f] = entry.get(f)
        out["source"] = source
        # vault_notes arrives as a list of dicts on the entry; flatten to the
        # three fields a delta needs. Stored as JSON text so the schema stays
        # one row per symbol rather than growing a second table for two notes.
        notes = entry.get("vault_notes") or []
        out["vault_notes_json"] = json.dumps([
            {"label": n.get("label"),
             "rules_passed": n.get("rules_passed"),
             "rules_total": n.get("rules_total")}
            for n in notes if isinstance(n, dict)
        ]) if notes else None
        # bucket is NOT NULL in the schema; an entry that somehow lacks one
        # is stored as UNKNOWN rather than failing the whole day's write.
        out["bucket"] = out.get("bucket") or "UNKNOWN"
        return out

    async def session_dates(self, universe: str, limit: int = 30) -> list[str]:
        """Scan dates held for `universe`, newest first."""
        if self.is_persistent:
            from sqlalchemy import text
            async with self._engine.begin() as conn:
                res = await conn.execute(text(
                    "SELECT DISTINCT scan_date FROM shortlist_history "
                    "WHERE universe = :u ORDER BY scan_date DESC LIMIT :n"
                ), {"u": universe, "n": limit})
                return [r._mapping["scan_date"] for r in res]
        days = sorted({d for (d, u) in self._mem if u == universe}, reverse=True)
        return days[:limit]

    async def fetch_session(self, universe: str, scan_date: str) -> list[dict]:
        """Every stored entry for one universe on one scan date."""
        if self.is_persistent:
            from sqlalchemy import text
            async with self._engine.begin() as conn:
                res = await conn.execute(text(
                    f"SELECT symbol, {', '.join(_FIELDS)} FROM shortlist_history "
                    "WHERE universe = :u AND scan_date = :d "
                    "ORDER BY momentum_rank"
                ), {"u": universe, "d": scan_date})
                return [_row_to_entry(r) for r in res]
        return list(self._mem.get((scan_date, universe), []))

    async def previous_session_date(self, universe: str,
                                    before: str) -> Optional[str]:
        """The most recent scan date STRICTLY BEFORE `before`, or None.

        Read, never derived — see the module docstring. A gap of any length
        (weekend, holiday, missed refresh, machine off) resolves to the last
        session that actually ran, so the diff is always against real data."""
        if self.is_persistent:
            from sqlalchemy import text
            async with self._engine.begin() as conn:
                res = await conn.execute(text(
                    "SELECT MAX(scan_date) AS d FROM shortlist_history "
                    "WHERE universe = :u AND scan_date < :b"
                ), {"u": universe, "b": before})
                row = res.first()
                return row._mapping["d"] if row else None
        earlier = sorted(d for (d, u) in self._mem
                         if u == universe and d < before)
        return earlier[-1] if earlier else None

    async def _sql_replace_day(self, universe: str, day: str,
                               rows: list[dict]) -> None:
        from sqlalchemy import text
        cols = ("scan_date", "universe", "symbol") + _FIELDS
        placeholders = ", ".join(f":{c}" for c in cols)
        insert = text(f"INSERT INTO shortlist_history ({', '.join(cols)}) "
                      f"VALUES ({placeholders})")
        async with self._engine.begin() as conn:
            # Replace rather than upsert: a re-run of the same day is a
            # correction of that day, and the symbol set can shrink between
            # runs (a name drops out of the universe), which an upsert would
            # leave behind as a phantom row.
            await conn.execute(text(
                "DELETE FROM shortlist_history "
                "WHERE universe = :u AND scan_date = :d"
            ), {"u": universe, "d": day})
            if not rows:
                return
            await conn.execute(insert, [
                {"scan_date": day, "universe": universe,
                 # SQLite has no bool type; bind 0/1 explicitly rather than
                 # relying on the DBAPI to coerce, same rule as db.py's
                 # _marshal_params applies to datetimes.
                 **{k: (int(v) if k == "trend_up" and v is not None else v)
                    for k, v in r.items()}}
                for r in rows
            ])


_history: Optional[ShortlistHistory] = None


async def get_history() -> ShortlistHistory:
    global _history
    if _history is None:
        _history = ShortlistHistory()
    return _history
