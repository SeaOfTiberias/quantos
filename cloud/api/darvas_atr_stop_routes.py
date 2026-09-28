"""
QuantOS — Darvas ATR-Stop (Bucket B) Reporting Route
──────────────────────────────────────────────────────
Read-only cockpit visibility into scripts/run_darvas_atr_stop_live.py, which
runs as two systemd timers on this same box (18:00 IST scan -> plan file,
09:45 IST execute -> open positions + dry-run trade log). Until 2026-09-28 none
of that state reached the cockpit: the "Breakout Candidates" panel runs
analyse_symbol with the default max_box_width of 35%, which by construction
drops every Bucket B (35-50%) box this strategy trades.

Nothing here influences a trading decision. The API holds no broker (ADR-01),
so there is no live price and no unrealised P&L -- only the levels the
executor itself recorded.

The three files are read straight off disk, not synced over HTTP like the
rotation/shortlist routes: the API and the executor share ~/.quantos on the
VM. Every read degrades to "empty" rather than raising, same convention as
core/darvas_atr_stop's own loaders.
"""

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter

from core.darvas_atr_stop.dry_run_log import load_dry_run_trades
from core.darvas_atr_stop.live_positions import load_open_positions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/darvas-atr-stop", tags=["darvas-atr-stop"])


# Resolved at call time (not module constants) so tests can point them at a
# tmp_path without touching the real ~/.quantos.
def _quantos_dir() -> Path:
    override = os.getenv("QUANTOS_HOME_DIR")
    return Path(override) if override else Path.home() / ".quantos"


def _plan_path() -> Path:
    return _quantos_dir() / "darvas_atr_stop_plan.json"


def _positions_path() -> Path:
    return _quantos_dir() / "darvas_atr_stop_open_positions.json"


def _trades_path() -> Path:
    return _quantos_dir() / "darvas_atr_stop_dry_run_trades.jsonl"


def _config_path() -> Path:
    return Path(os.getenv("QUANTOS_AGENT_CONFIG", "agent/config.yaml"))


def _load_plan() -> Optional[dict]:
    path = _plan_path()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning("Could not read Darvas ATR-stop plan: %s", e)
        return None
    return raw if isinstance(raw, dict) else None


def _load_settings() -> dict:
    """Only the non-secret darvas_atr_stop keys -- agent/config.yaml also
    holds broker credentials, which must never reach a response."""
    try:
        raw = yaml.safe_load(_config_path().read_text(encoding="utf-8")) or {}
        block = raw.get("darvas_atr_stop") or {}
    except (OSError, yaml.YAMLError, AttributeError) as e:
        logger.warning("Could not read darvas_atr_stop config: %s", e)
        return {}
    return {k: block.get(k) for k in ("enabled", "dry_run", "equity_fraction", "starting_capital")}


def _pct(a: float, b: float) -> Optional[float]:
    return round((a - b) / b * 100.0, 2) if b else None


@router.get("/status")
async def get_status():
    plan = _load_plan()
    plan_out = None
    if plan is not None:
        failures = plan.get("failures") or {}
        plan_out = {
            "generated_at":    plan.get("generated_at"),
            "bars_as_of":      plan.get("bars_as_of"),
            "executed_on":     plan.get("executed_on"),
            "symbols_scanned": plan.get("symbols_scanned"),
            "entries":         plan.get("entries") or [],
            "position_actions": plan.get("position_actions") or {},
            "failed_symbols":  sorted(failures.keys()),
        }

    positions = []
    for p in load_open_positions(_positions_path()).values():
        d = asdict(p)
        d.pop("entry_order_id", None)
        d.pop("stop_order_id", None)
        d["notional"] = round(p.quantity * p.entry_price, 2)
        d["risk_pct"] = _pct(p.current_stop, p.entry_price)
        d["reward_pct"] = _pct(p.current_target, p.entry_price)
        positions.append(d)
    positions.sort(key=lambda d: d["entry_date"])

    closed = []
    for t in load_dry_run_trades(_trades_path()):
        d = asdict(t)
        d["pnl_pct"] = _pct(t.boundary_price, t.entry_price)
        d["pnl"] = round((t.boundary_price - t.entry_price) * t.quantity, 2)
        closed.append(d)
    closed.sort(key=lambda d: d["exit_timestamp"], reverse=True)

    return {
        "settings": _load_settings(),
        "plan": plan_out,
        "open_positions": positions,
        "closed_trades": closed,
    }
