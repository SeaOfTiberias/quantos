"""
QuantOS — F&O Screener Picks Route
───────────────────────────────────
GET /fno-picks: the evening F&O screener's picks for the cockpit's #/picks
page, read from scripts/run_fno_screener.py's own files in ~/.quantos on
this same box:

  - fno_screener_latest.json     tonight's picks, each with its spread ideas
  - fno_screener_history.jsonl   every evening's picks (a re-run replaces that day)
  - fno_screener_outcomes.json   each pick tracked through 5 sessions

Returns {latest, history, stats}. `stats` is core/fno_screener/outcomes.py's
summarize(): close-to-close, before costs, with N beside every number. The
screener has no tested edge; the page says so and this route never ranks or
recommends beyond what the screener logged.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter

from core.fno_screener.outcomes import HORIZONS, pick_key, returns_at, summarize

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/fno-picks", tags=["fno-picks"])

HISTORY_DAYS = 30


def _quantos_dir() -> Path:
    override = os.getenv("QUANTOS_HOME_DIR")
    return Path(override) if override else Path.home() / ".quantos"


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as e:
        logger.info("fno-picks: %s unreadable: %s", path.name, e)
        return None


def _records(path: Path) -> list[dict]:
    """One record per trade date (the last run of a day wins), newest first."""
    by_date: dict[str, dict] = {}
    try:
        for line in path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                by_date[r["trade_date"]] = r
    except (OSError, ValueError) as e:
        logger.info("fno-picks: history unreadable: %s", e)
    return [by_date[d] for d in sorted(by_date, reverse=True)]


def _pick_view(trade_date: str, cand: dict, outcomes: dict) -> dict:
    out = outcomes.get(pick_key(trade_date, cand["side"], cand["symbol"]))
    spreads = cand.get("spreads")
    if not spreads and out and out.get("spread_ideas"):              # logged before spreads existed
        spreads = {"ideas": out["spread_ideas"], "rebuilt": True}
    return {
        **{k: cand.get(k) for k in ("symbol", "side", "close", "setup_rank", "breakout_state", "days_out",
                                    "momentum_pct", "box_level", "box_width_pct", "oi", "contract")},
        "spreads": spreads,
        "outcome": None if not out else {
            "sessions": len(out["sessions"]), "complete": out["complete"],
            "returns": {str(h): returns_at(out, h) for h in HORIZONS},
        },
    }


@router.get("")
async def fno_picks(days: int = HISTORY_DAYS):
    base = _quantos_dir()
    outcomes = _read_json(base / "fno_screener_outcomes.json") or {}
    records = _records(base / "fno_screener_history.jsonl")
    latest = _read_json(base / "fno_screener_latest.json") or (records[0] if records else None)

    def view(r: dict) -> dict:
        return {"trade_date": r["trade_date"], "generated_at": r.get("generated_at"),
                "scanned": r.get("scanned"),
                "calls": [_pick_view(r["trade_date"], c, outcomes) for c in r.get("calls", [])],
                "puts": [_pick_view(r["trade_date"], c, outcomes) for c in r.get("puts", [])]}

    return {
        "latest": view(latest) if latest else None,
        "history": [view(r) for r in records[:max(1, min(days, 120))]],
        "stats": summarize(list(outcomes.values())),
        "outcomes_tracked": len(outcomes),
    }
