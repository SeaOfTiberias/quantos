"""
QuantOS — Momentum + Base Quality Shortlist Routes
─────────────────────────────────────────────────────
Exposes core/discovery/momentum_shortlist.py's output (produced daily by
scripts/run_momentum_shortlist.py, deploy/systemd/quantos-momentum-shortlist.timer)
to the cockpit dashboard. Replaces the cockpit's use of the pure-Darvas
/discovery/watchlist endpoint (cloud/api/discovery_routes.py), which has had
no evidenced edge since S7-3 and no live feed since quantos-agent was
mothballed — this is a fresh feed, not a repurposing of that one, so the old
endpoint and its tests stay untouched.

This is a discretionary review aid, not a trading signal: no dry_run flag,
no execution path, nothing here is ever wired to broker.place_order().

Keyed by `universe` (2026-07-29: added a second scan, Nifty200 Momentum 30,
alongside the original Nifty Alpha 50 — a single wholesale-replace store
would have let the second script's daily sync silently clobber the first's).
The label is whatever scripts/run_momentum_shortlist.py derives from its
universe filename (e.g. "alpha50", "nifty200momentum30") — see that
script's `_universe_label()`.

Same auth split as every other read-only router in this app: POST (from the
standalone script, same "keys never leave this machine" trust boundary as
the agent) is guarded with X-Cloud-Secret; GET (from the cockpit's browser
JS) is intentionally public, same reasoning as cloud/api/discovery_routes.py.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cloud.api.auth import require_cloud_secret
from cloud.api.shortlist_history import get_history
from core.discovery.shortlist_brief import build_brief

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discovery", tags=["discovery"])

# In-memory mirrors, keyed by universe label — each replaced wholesale on
# every daily sync from that universe's scan.
_shortlist_store: dict[str, list[dict]] = {}
_last_synced_at: dict[str, datetime] = {}

# ...backed by a small JSON file, because the scan that fills these is
# expensive and rare: ~11 minutes over ~580 symbols, and (since
# quantos-token-refreshed.path) it runs on the daily Fyers token refresh.
# Without a disk copy, any API restart blanks all three cockpit tabs until
# the NEXT morning's refresh -- and deploying is itself a restart, so the
# deploy pipeline would reliably wipe the panels it just shipped.
#
# Deliberately a plain file, not the SignalDB/SQLite layer in cloud/api/db.py:
# this is a regenerable mirror of a scan, not a record of anything that
# happened, so it needs no schema, no migration, and no correctness guarantee
# beyond "better than empty". Read at import, rewritten on every sync.
#
# Read through _cache_path() rather than a module constant so tests can point
# it at a tmp_path without touching the developer's real ~/.quantos.
def _cache_path() -> Path:
    override = os.getenv("QUANTOS_SHORTLIST_CACHE")
    if override:
        return Path(override)
    return Path.home() / ".quantos" / "shortlist_cache.json"


def _save_cache() -> None:
    """Mirror the in-memory store to disk. Never raises: a cockpit panel that
    survives a restart is a nicety, and must not be able to fail the sync that
    the scan just spent 11 minutes producing."""
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            universe: {
                "entries": entries,
                "updated_at": _last_synced_at[universe].isoformat()
                if _last_synced_at.get(universe) else None,
            }
            for universe, entries in _shortlist_store.items()
        }
        # Write-then-rename so a crash mid-write can't leave a truncated file
        # that would poison the next boot's load.
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)
    except OSError as e:
        logger.warning("Could not persist shortlist cache: %s", e)


def _load_cache() -> None:
    """Repopulate the store from disk at import. Never raises: a corrupt or
    missing cache must degrade to today's behaviour (empty until next sync),
    not stop the API from booting."""
    try:
        path = _cache_path()
        if not path.exists():
            return
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning("Could not read shortlist cache: %s", e)
        return

    if not isinstance(raw, dict):
        logger.warning("Shortlist cache is not an object; ignoring it.")
        return

    for universe, blob in raw.items():
        if not isinstance(blob, dict) or not isinstance(blob.get("entries"), list):
            continue
        _shortlist_store[universe] = blob["entries"]
        stamp = blob.get("updated_at")
        if stamp:
            try:
                _last_synced_at[universe] = datetime.fromisoformat(stamp)
            except ValueError:
                pass
    if _shortlist_store:
        logger.info("Shortlist cache restored: %s",
                    {u: len(e) for u, e in _shortlist_store.items()})


_load_cache()


class VaultNoteScoreIn(BaseModel):
    """One strategy note's verdict. The cockpit renders one column per entry
    in this list; the aggregate on ShortlistEntryIn is deliberately not what
    it shows — see core/vault/shortlist_audit._note_scores for why summing
    the two bundled notes produces a near-meaningless number."""
    label:        str
    strategy_id:  str
    verdict:      str
    rules_passed: int
    rules_total:  int


class ShortlistEntryIn(BaseModel):
    symbol:         str
    close:          float
    momentum_pct:   float
    momentum_rank:  int
    momentum_tier:  str
    bucket:         str
    base_status:    str
    trend_up:       bool = False
    box_width_pct:  Optional[float] = None
    dist_to_ceil:   Optional[float] = None
    rr_ratio:       Optional[float] = None
    vol_ratio:      float = 0.0
    # Added 2026-08-11. Defaulted, not required: an entry restored from a
    # cache file written by the previous build must still validate, and the
    # cockpit degrades to "-" for a missing flag rather than erroring.
    breakout_state: str = "NO BASE"
    days_above_ceil: Optional[int] = None
    ma_cross:       Optional[str] = None
    ma_cross_days:  Optional[int] = None
    # Obsidian vault audit, added 2026-08-14 (core/vault/shortlist_audit.py).
    # These MUST be declared to survive the round trip: Pydantic drops
    # undeclared fields silently, so between 2026-08-14 and this commit the
    # scan computed a verdict, POSTed it, and the API discarded it before it
    # ever reached the store. Same defaulting rule as the block above.
    # Annotation only — the shortlist has no execution path, so a FAIL here
    # blocks nothing; it is a review aid, not a veto.
    vault_verdict:  Optional[str] = None    # PASS | FAIL | INSUFFICIENT_DATA | UNAVAILABLE
    vault_detail:   Optional[str] = None    # per-note breakdown, human-readable
    vault_rules_passed: Optional[int] = None
    vault_rules_total:  Optional[int] = None
    vault_notes: list[VaultNoteScoreIn] = []
    # Weinstein stage classification, added 2026-08-17 (core/vault/stages.py).
    # A classification, not a verdict: 1-4 are mutually exclusive and None
    # means UNCLASSIFIED, never "stage 1". Kept as its own trio rather than
    # folded into vault_notes because a stage is not a score and must not be
    # summed with one.
    stage:        Optional[int] = None
    stage_phase:  Optional[str] = None
    stage_detail: Optional[str] = None


class ShortlistSyncRequest(BaseModel):
    entries: list[ShortlistEntryIn]


@router.post("/momentum-shortlist/{universe}")
async def sync_momentum_shortlist(universe: str, payload: ShortlistSyncRequest,
                                   _auth=Depends(require_cloud_secret)):
    """Called once a day by scripts/run_momentum_shortlist.py, once per
    configured universe."""
    _shortlist_store[universe] = [e.model_dump() for e in payload.entries]
    _last_synced_at[universe] = datetime.now(timezone.utc)
    _save_cache()

    # Append today's board to the day-over-day history the Morning Brief tab
    # reads. Deliberately after _save_cache(): the cache is what the existing
    # three panels render, and a history problem must not delay or endanger
    # it. record_snapshot() swallows its own failures for the same reason.
    history = await get_history()
    recorded = await history.record_snapshot(universe,
                                             _shortlist_store[universe])

    logger.info("Momentum shortlist synced (%s): %d entries, %d recorded to history",
                universe, len(_shortlist_store[universe]), recorded)
    return {"universe": universe, "synced": len(_shortlist_store[universe]),
            "history_rows": recorded}


@router.get("/momentum-shortlist/{universe}")
async def get_momentum_shortlist(universe: str):
    """Read by the cockpit dashboard, one call per panel/universe."""
    entries = _shortlist_store.get(universe, [])
    updated_at = _last_synced_at.get(universe)
    return {
        "entries": entries,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


@router.get("/shortlist-brief/{universe}")
async def get_shortlist_brief(universe: str, note: bool = True):
    """The Morning Brief: today's tight-base board with per-name overnight
    deltas, the ranked transition flags, and (optionally) a generated
    paragraph of commentary underneath.

    `note=false` skips the Claude call entirely and returns only computed
    output — used by the cockpit's manual refresh so re-reading the tab can
    never spend money, and available to anyone who wants the deterministic
    half on its own.

    The generated note NEVER blocks the response: any failure to produce one
    is reported in `note_error` and the computed brief is returned regardless.
    The flags are the signal; the prose is commentary and the cockpit labels
    it as such.
    """
    history = await get_history()

    dates = await history.session_dates(universe, limit=1)
    if not dates:
        return {
            "universe": universe, "available": False,
            "reason": ("No scan history recorded yet for this universe. "
                       "History starts accumulating from the first sync after "
                       "2026-08-27; run scripts/backfill_shortlist_history.py "
                       "to load past sessions out of journald."),
        }

    scan_date = dates[0]
    prev_date = await history.previous_session_date(universe, scan_date)
    today = await history.fetch_session(universe, scan_date)
    prev = await history.fetch_session(universe, prev_date) if prev_date else []

    brief = build_brief(today, prev, scan_date=scan_date,
                        prev_scan_date=prev_date)
    brief["universe"] = universe
    brief["available"] = True
    brief["backend"] = history.backend

    # Cached notes are free to serve, so hand one back even when note=false.
    from cloud.analyst.shortlist_note import cached_note, generate_note, NoteUnavailable

    cached = cached_note(universe, scan_date)
    if cached is not None:
        brief["note"] = cached
    elif note:
        try:
            brief["note"] = await generate_note(universe, brief)
        except NoteUnavailable as e:
            brief["note"] = None
            brief["note_error"] = str(e)
        except Exception as e:  # noqa: BLE001 — see docstring: never blocks
            logger.warning("Shortlist note generation failed (%s): %s",
                           type(e).__name__, e)
            brief["note"] = None
            brief["note_error"] = f"{type(e).__name__}"
    else:
        brief["note"] = None

    return brief


@router.get("/shortlist-history/{universe}")
async def get_shortlist_history_dates(universe: str, limit: int = 30):
    """Scan dates held for this universe, newest first — lets the cockpit show
    how much history the brief is actually working from."""
    history = await get_history()
    return {
        "universe": universe,
        "backend": history.backend,
        "dates": await history.session_dates(universe, limit=limit),
    }
