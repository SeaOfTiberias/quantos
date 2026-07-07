"""
QuantOS Local Agent — Discovery Watchlist Store
──────────────────────────────────────────────────
Persists Stage A (weekly discovery, core/darvas/weekly_discovery.py)
results across agent restarts/days. Same on-disk pattern as
agent/positions.py. Ports DarvasTrader's watchlist state machine:
protects entries tied to an open position (a fresh scan never overwrites
them), auto-expires stale non-actionable ones, and flags "ADD to winner"
candidates when an open position has a new, higher box forming above its
entry price.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from core.darvas.weekly_discovery import DiscoveryResult

logger = logging.getLogger("quantos.agent")

WATCHLIST_PATH = Path.home() / ".quantos" / "discovery_watchlist.json"

# Set once a real position is open against an entry — a fresh discovery
# scan must never overwrite these (mirrors DarvasTrader's PROTECTED_STATUSES).
PROTECTED_STATUSES = {"POSITION_OPEN"}

# Discovery-scan statuses worth handing to Stage B (core/darvas/scanner.py)
# for precise intraday entry timing. BOX FORMING is too early; FRESH
# BREAKOUT is already too late — exactly the problem this pipeline fixes.
# WATCHING is excluded even though analyse_symbol() can assign it to
# APPROACHING-adjacent setups, because it also doubles as a catch-all for
# "confirmed box, far from ceiling, no volume surge" (see
# core/darvas/weekly_discovery.py's analyse_symbol) — including it live
# ballooned a 247-symbol universe into a 130-symbol "shortlist", defeating
# the point of narrowing down to a short, high-relevance list.
GRANULAR_SCAN_STATUSES = {"APPROACHING"}

# Within APPROACHING, only HOT/WARM (close to the ceiling AND showing
# volume confirmation) qualify — WATCH-tier APPROACHING is still too far
# out to be worth granular intraday timing yet.
GRANULAR_SCAN_TIERS = {"HOT", "WARM"}


@dataclass
class WatchlistEntry:
    symbol:          str
    date_added:      str             # ISO date
    date_updated:    str             # ISO date
    status:          str             # FRESH BREAKOUT | APPROACHING | WATCHING | BOX FORMING | POSITION_OPEN
    prev_status:     str = ""
    alert_tier:      str = ""        # HOT | WARM | WATCH | VOL-SURGE | ""
    box_ceiling:     Optional[float] = None
    box_floor:       Optional[float] = None
    box_width_pct:   Optional[float] = None
    dist_to_ceil:    Optional[float] = None
    sl_price:        Optional[float] = None
    mm_target:       Optional[float] = None
    rr_ratio:        Optional[float] = None
    days_in_box:     Optional[int] = None
    last_fired_date: str = ""        # ISO date Stage B last POSTed a signal for this symbol
    last_fired_signal_id:  str = ""              # signal_id returned by /webhook/tradingview
    last_fired_confluence: Optional[float] = None
    last_fired_status:     str = ""              # e.g. PENDING_CONFIRMATION, REJECTED_DUPLICATE
    entry_price:     Optional[float] = None   # set once a position is opened against this entry
    quantity:        Optional[int] = None


def load_watchlist() -> dict[str, WatchlistEntry]:
    if not WATCHLIST_PATH.exists():
        return {}
    try:
        raw = json.loads(WATCHLIST_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {sym: WatchlistEntry(**data) for sym, data in raw.items()}


def _save(watchlist: dict[str, WatchlistEntry]) -> None:
    WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    WATCHLIST_PATH.write_text(
        json.dumps({sym: asdict(e) for sym, e in watchlist.items()}, indent=2)
    )


def mark_fired(watchlist: dict[str, WatchlistEntry], symbol: str,
               signal_id: str = "", confluence: Optional[float] = None,
               signal_status: str = "") -> None:
    """Record that Stage B already POSTed a signal for this symbol today,
    so the ~5-min granular scan doesn't re-fire on every pass. The
    signal_id/confluence/status are carried along purely for display —
    see cloud/api/discovery_routes.py — so the cockpit can show what
    fired without needing authenticated access to /signals."""
    if symbol in watchlist:
        entry = watchlist[symbol]
        entry.last_fired_date = date.today().isoformat()
        entry.last_fired_signal_id = signal_id
        entry.last_fired_confluence = confluence
        entry.last_fired_status = signal_status
        _save(watchlist)


def already_fired_today(watchlist: dict[str, WatchlistEntry], symbol: str) -> bool:
    entry = watchlist.get(symbol)
    return bool(entry and entry.last_fired_date == date.today().isoformat())


def mark_position_open(watchlist: dict[str, WatchlistEntry], symbol: str,
                        entry_price: float, quantity: int) -> None:
    """Protect this entry from being overwritten by future scans once a
    real position is open against it."""
    today = date.today().isoformat()
    existing = watchlist.get(symbol)
    watchlist[symbol] = WatchlistEntry(
        symbol=symbol,
        date_added=existing.date_added if existing else today,
        date_updated=today,
        status="POSITION_OPEN",
        prev_status=existing.status if existing else "",
        box_ceiling=existing.box_ceiling if existing else None,
        box_floor=existing.box_floor if existing else None,
        entry_price=entry_price, quantity=quantity,
    )
    _save(watchlist)


def clear_position(watchlist: dict[str, WatchlistEntry], symbol: str) -> None:
    """Position closed — release the protection so the next scan can
    manage this symbol normally again."""
    if symbol in watchlist:
        del watchlist[symbol]
        _save(watchlist)


def merge_scan_results(
    watchlist: dict[str, WatchlistEntry],
    results: list[DiscoveryResult],
    watchlist_days: int = 45,
) -> dict[str, WatchlistEntry]:
    """
    Merge a fresh Stage A scan into the persistent watchlist.

    FRESH BREAKOUT       -> graduate (remove) — already too late for
                             discovery purposes; Stage B/live price action
                             is the only thing that matters from here.
    APPROACHING/WATCHING -> add if new, update if already tracked.
    BOX FORMING          -> update only if already tracked.
    PROTECTED_STATUSES (open positions) are never overwritten by a scan.
    Entries older than watchlist_days auto-expire.
    """
    today = date.today().isoformat()

    for r in results:
        existing = watchlist.get(r.symbol)
        if existing and existing.status in PROTECTED_STATUSES:
            continue

        if r.status == "FRESH BREAKOUT":
            watchlist.pop(r.symbol, None)
            continue

        if r.status in ("APPROACHING", "WATCHING"):
            watchlist[r.symbol] = WatchlistEntry(
                symbol=r.symbol,
                date_added=existing.date_added if existing else today,
                date_updated=today,
                status=r.status,
                prev_status=existing.status if existing else "",
                alert_tier=r.alert_tier,
                box_ceiling=r.box_ceiling, box_floor=r.box_floor,
                box_width_pct=r.box_width_pct, dist_to_ceil=r.dist_to_ceil,
                sl_price=r.sl_price,
                mm_target=r.mm_target, rr_ratio=r.rr_ratio,
                days_in_box=r.days_in_box,
                last_fired_date=existing.last_fired_date if existing else "",
                last_fired_signal_id=existing.last_fired_signal_id if existing else "",
                last_fired_confluence=existing.last_fired_confluence if existing else None,
                last_fired_status=existing.last_fired_status if existing else "",
            )
        elif r.status == "BOX FORMING" and existing:
            existing.date_updated = today
            existing.status = r.status

    _expire_stale(watchlist, watchlist_days)
    _save(watchlist)
    return watchlist


def candidates_for_granular_scan(watchlist: dict[str, WatchlistEntry]) -> list[str]:
    """Symbols worth handing to Stage B (core/darvas/scanner.py) for
    precise intraday entry timing — the whole point of narrowing a broad
    universe scan down to a short, high-relevance shortlist."""
    return [
        sym for sym, e in watchlist.items()
        if e.status in GRANULAR_SCAN_STATUSES and e.alert_tier in GRANULAR_SCAN_TIERS
    ]


def check_add_candidates(watchlist: dict[str, WatchlistEntry],
                          results: list[DiscoveryResult]) -> list[dict]:
    """
    Cross-reference today's scan against open positions: flag a symbol
    where a *new, higher* weekly box has formed above the original entry
    price and is now APPROACHING or breaking out — "this winner is setting
    up for another leg, consider adding."
    """
    open_positions = {
        sym: e for sym, e in watchlist.items()
        if e.status == "POSITION_OPEN" and e.entry_price
    }
    if not open_positions:
        return []

    result_map = {r.symbol: r for r in results}
    candidates = []
    for sym, pos in open_positions.items():
        scan = result_map.get(sym)
        if not scan or not scan.box_ceiling:
            continue
        if scan.box_ceiling <= pos.entry_price:
            continue
        if scan.status not in ("FRESH BREAKOUT", "APPROACHING"):
            continue
        candidates.append({
            "symbol": sym, "orig_entry": pos.entry_price, "orig_qty": pos.quantity,
            "new_ceiling": scan.box_ceiling, "new_floor": scan.box_floor,
            "new_sl": scan.sl_price, "new_target": scan.mm_target,
            "rr_ratio": scan.rr_ratio, "status": scan.status,
            "alert_tier": scan.alert_tier, "dist_to_ceil": scan.dist_to_ceil,
            "gain_pct": round((scan.box_ceiling - pos.entry_price) / pos.entry_price * 100, 1),
        })
    return candidates


def _expire_stale(watchlist: dict[str, WatchlistEntry], watchlist_days: int) -> None:
    today = date.today()
    expired = [
        sym for sym, e in watchlist.items()
        if e.status not in PROTECTED_STATUSES
        and (today - date.fromisoformat(e.date_added)).days > watchlist_days
    ]
    for sym in expired:
        del watchlist[sym]
    if expired:
        logger.info("Expired from discovery watchlist (%dd): %s",
                     watchlist_days, ", ".join(expired))
