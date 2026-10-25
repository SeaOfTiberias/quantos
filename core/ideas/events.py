"""
QuantOS — Results calendar for structure choice
────────────────────────────────────────────────
Upcoming financial-results board meetings for every NSE equity, fetched by
code from NSE's corporate-board-meetings API (one bulk call for the next ~45
days) and cached in ~/.quantos/events.json. Built 2026-10-25 because three
reviews in a row (NHPC, LICI, ADANIENT) needed a results date and the model's
web search never found one, while the endpoint had all three (04-Nov, 05-Nov,
28-Oct).

The model no longer has to look it up: pick_structure attaches the next
results date, prices an "event" scenario (core/ideas/structure.py) and the
reviewer reads it as data.

Same endpoint as core/statarb/data.fetch_results_board_meetings (per symbol,
for history); this is the forward-looking bulk version.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

URL = "https://www.nseindia.com/api/corporate-board-meetings"
DEFAULT_PATH = Path.home() / ".quantos" / "events.json"
DAYS_AHEAD = 45
MAX_AGE_HOURS = 12


def is_results(row: dict) -> bool:
    text = f"{row.get('bm_purpose') or ''} {row.get('bm_desc') or ''}".lower()
    return "financial result" in text


def parse_rows(rows: list) -> dict[str, list[str]]:
    """{symbol: sorted ISO dates of results board meetings}."""
    out: dict[str, set] = {}
    for r in rows if isinstance(rows, list) else []:
        if not is_results(r) or not r.get("bm_symbol") or not r.get("bm_date"):
            continue
        try:
            d = datetime.strptime(r["bm_date"], "%d-%b-%Y").date()
        except ValueError:
            continue
        out.setdefault(r["bm_symbol"].strip().upper(), set()).add(d.isoformat())
    return {s: sorted(v) for s, v in out.items()}


def fetch(today: date, days_ahead: int = DAYS_AHEAD) -> dict[str, list[str]]:
    from core.fundamentals.pead.nse_client import NseSession, _get_json
    params = {"index": "equities", "from_date": f"{today - timedelta(days=3):%d-%m-%Y}",
              "to_date": f"{today + timedelta(days=days_ahead):%d-%m-%Y}"}
    return parse_rows(_get_json(NseSession(), URL, params))


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def refresh(path: Path, now: Optional[datetime] = None, fetcher=fetch) -> dict:
    """The cached calendar, re-fetched when older than MAX_AGE_HOURS. A failed fetch keeps the
    old cache (and says so) rather than returning nothing."""
    now = now or datetime.now()
    cached = load(path)
    try:
        age = now - datetime.fromisoformat(cached["fetched"])
        if age < timedelta(hours=MAX_AGE_HOURS):
            return cached
    except (KeyError, ValueError, TypeError):
        pass
    try:
        ev = fetcher(now.date())
    except Exception as e:
        cached["error"] = f"refresh failed: {type(e).__name__}"
        return cached
    data = {"fetched": now.isoformat(timespec="seconds"), "source": URL, "results": ev}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=0))
    tmp.replace(path)
    return data


def trading_days_until(today: date, d: date) -> int:
    """Weekdays after today up to and including d (holidays ignored)."""
    n, x = 0, today
    while x < d:
        x += timedelta(days=1)
        n += x.weekday() < 5
    return n


def next_results(calendar: dict, symbol: str, today: date) -> Optional[date]:
    days = [date.fromisoformat(s) for s in (calendar.get("results") or {}).get(symbol.upper(), [])]
    upcoming = [d for d in days if d >= today]
    return min(upcoming) if upcoming else None


def event_context(calendar: dict, symbol: str, today: date, horizon_days: int) -> dict:
    """{"results_date", "sessions_away", "inside_horizon", "as_of"} or {"results_date": None, ...}."""
    d = next_results(calendar, symbol, today)
    out = {"results_date": d.isoformat() if d else None, "as_of": calendar.get("fetched")}
    if calendar.get("error"):
        out["error"] = calendar["error"]
    if not calendar.get("results"):
        out["error"] = out.get("error") or "no results calendar"
        return out
    if d:
        n = trading_days_until(today, d)
        out.update(sessions_away=n, inside_horizon=n <= horizon_days)
    return out
