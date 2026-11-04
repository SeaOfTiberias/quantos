"""
QuantOS — Market Map: map_read, the one call every decision path makes
──────────────────────────────────────────────────────────────────────
docs/MARKET_MAP_ENGINE_DESIGN.md §5, phase P0. Wraps the existing price map
(core/price_map/) and answers "where are we, and what does that mean for this
trade?": the nearest strong zone below and above, the zone price is in, and,
for a proposed trade, the first strong zone in its way (in R), whether the
target lies beyond it, and whether the stop sits inside a zone.

    map_read("HDFCBANK")                                          # where price is
    map_read("HDFCBANK", {"side": "short", "entry": 678, "stop": 690, "target": 665})

The map comes from ~/.quantos/price_maps/<SYMBOL>.json when one was built in
the last MAX_AGE_DAYS; otherwise it is built on demand from the market's bars
(and saved). With as_of, it is built from bars before that day only and not
saved. Every zone line carries its test status: these L2 strong zones FAILED
their pre-registered test (docs/PRICE_MAP_ZONES_PREREG_2026-10-28.md, 2026-11-04:
they turn price no more often than placebo levels). They stay on the map as
markers for reading a trade, labelled so; they never filter. A read informs a
decision; it never blocks or moves an order by itself.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Optional

from core.price_map.build import build_map, nearest, render, rng, why, zone_at
from core.price_map.levels import IST, _d, first_obstacle

MAPS_DIR = Path.home() / ".quantos" / "price_maps"   # = scripts/price_map.py OUT
MAX_AGE_DAYS = 7                                       # = run_position_manager.MAP_MAX_AGE_DAYS
INTRADAY_DAYS = 99                                     # Fyers allows 100 days of 5-minute bars
UNTESTED = "untested"
FAILED = "failed its test"
ZONE_TEST = FAILED                                     # L2 strong zones: zone test 2026-11-04, FAIL
NOTE = ("Zones mark where price did business and turned. In the 2026-11-04 test they turned price no "
        "more often than placebo levels (docs/PRICE_MAP_ZONES_PREREG_2026-10-28.md): markers for "
        "reading a trade, never a signal or a filter.")
# What the map is built from and what it lacks, for every screen that draws it (docs/MARKET_MAP_SCREENS.md rule 3).
LAYERS = {"shown": ["daily swings (last year)", f"5-minute volume profile (last {INTRADAY_DAYS} days)",
                    "pivots (last day, week, month)"],
          "missing": ["higher-timeframe structure and multi-year zones (S5)", "market backdrop (S6)",
                      "fundamentals (S6b)"]}


def side_of(x: Any) -> int:
    """+1 long / -1 short from 'long', 'buy', 'bull', 'short', 'sell', 'bear' or a signed number."""
    if isinstance(x, (int, float)):
        return 1 if x > 0 else -1
    s = str(x).strip().lower()
    if s in ("long", "buy", "bull", "bullish", "call"):
        return 1
    if s in ("short", "sell", "bear", "bearish", "put"):
        return -1
    raise ValueError(f"side must be long or short, not {x!r}")


# ─── pure: a map dict in, a read out ─────────────────────────────────────────

def _zone(z: Optional[dict], price: float, atr: float) -> Optional[dict]:
    if not z:
        return None
    edge = z["high"] if z["high"] < price else z["low"]
    return {"range": rng(z), "low": z["low"], "high": z["high"], "why": why(z),
            "distance": round(abs(edge - price), 2),
            "distance_atr": round(abs(edge - price) / atr, 2) if atr else None,
            "distance_pct": round(abs(edge - price) / price * 100, 2), "test": ZONE_TEST}


def read(m: dict, trade: Optional[dict] = None, price: Optional[float] = None) -> dict:
    """The read of a built map. `trade` = {side, entry, stop, target?}; `price` defaults to the
    trade's entry, else the map's last close."""
    if not m or "zones" not in m:
        return {"symbol": (m or {}).get("symbol"), "error": (m or {}).get("error") or "no map"}
    t = None
    if trade:
        t = {"side": side_of(trade["side"]), "entry": float(trade["entry"]),
             "stop": float(trade["stop"]) if trade.get("stop") is not None else None,
             "target": float(trade["target"]) if trade.get("target") is not None else None}
    px = float(price if price is not None else (t["entry"] if t else m["close"]))
    atr = m.get("atr") or 0
    n = nearest(m, px)
    inside = zone_at(m, px)
    out: dict[str, Any] = {
        "symbol": m["symbol"], "built_for": m["built_for"], "close": m["close"], "price": px, "atr": m.get("atr"),
        "shifted_by": m.get("shifted_by"),
        "inside": {"range": rng(inside), "why": why(inside), "test": ZONE_TEST} if inside else None,
        "below": _zone(n["below"], px, atr), "above": _zone(n["above"], px, atr),
        "status": ZONE_TEST, "note": NOTE,
    }
    if t:
        out["trade"] = trade_read(m, t)
    return out


def trade_read(m: dict, t: dict) -> dict:
    side, entry, stop, target = t["side"], t["entry"], t["stop"], t["target"]
    r = abs(entry - stop) if stop is not None else 0.0
    ob = first_obstacle(m["zones"], entry, side, r) if r > 0 else None
    beyond = bool(ob and target is not None and (target - ob["edge"]) * side > 0)
    sz = zone_at(m, stop) if stop is not None else None
    flags = []
    if beyond:
        flags.append(f"target {target:g} is beyond the strong zone {rng(ob['zone'])} at {ob['r']:g}R")
    if sz:
        flags.append(f"stop {stop:g} is inside the strong zone {rng(sz)}")
    return {"side": "long" if side > 0 else "short", "entry": entry, "stop": stop, "target": target,
            "r": round(r, 2) if r else None,
            "target_r": round(abs(target - entry) / r, 2) if r and target is not None else None,
            "first_obstacle": {"range": rng(ob["zone"]), "why": why(ob["zone"]), "edge": ob["edge"], "r": ob["r"],
                               "test": ZONE_TEST} if ob else None,
            "target_beyond_obstacle": beyond,
            "stop_in_zone": {"range": rng(sz), "why": why(sz), "test": ZONE_TEST} if sz else None,
            "flags": flags, "test": ZONE_TEST}


def ladder(m: dict, price: float) -> list[dict]:
    """Every zone of the map (strong and weak), high to low, for drawing, with its distance from
    `price` (0 inside); levels folded into `why`. Weak zones carry the same status: the 11-04 test
    ran them as its control and they turned price less often than the strong ones, which did no
    better than placebo."""
    atr = m.get("atr") or 0
    out = []
    for z in sorted(m.get("zones", []), key=lambda z: -z["high"]):
        where = "above" if z["low"] > price else "below" if z["high"] < price else "inside"
        gap = z["low"] - price if where == "above" else price - z["high"] if where == "below" else 0.0
        out.append({"low": z["low"], "high": z["high"], "range": rng(z), "strong": z["strong"], "score": z["score"],
                    "families": z["families"], "why": why(z, 6), "where": where, "distance": round(gap, 2),
                    "distance_atr": round(gap / atr, 2) if atr else None,
                    "distance_pct": round(gap / price * 100, 2), "test": ZONE_TEST})
    return out


def lines(rd: dict) -> list[str]:
    """The read as text, for the CLIs and Telegram."""
    if "error" in rd:
        return [f"MAP  {rd.get('symbol') or ''}: none ({rd['error']})"]
    fmt = (lambda z: f"{z['range']} ({z['why']}), {z['distance_pct']:g}% away" if z else "no strong zone")
    basis = f", shifted {rd['shifted_by']:+g} onto futures" if rd.get("shifted_by") else ""
    out = [f"MAP  {rd['symbol']} at {rd['price']:g} (map built for {rd['built_for']}{basis}) -- zones {ZONE_TEST} (zone test 2026-11-04)",
           f"     below: {fmt(rd['below'])}", f"     above: {fmt(rd['above'])}"]
    if rd.get("inside"):
        out.append(f"     price is inside the strong zone {rd['inside']['range']} ({rd['inside']['why']})")
    t = rd.get("trade")
    if t:
        ob = t["first_obstacle"]
        out.append(f"     {t['side']} {t['entry']:g}, stop {t['stop'] if t['stop'] is not None else '-'}"
                   f", target {t['target'] if t['target'] is not None else '-'}: first obstacle "
                   + (f"{ob['range']} at {ob['r']:g}R" if ob else "none" if t["r"] else "n/a (no stop, so no R)"))
        out += [f"     ! {f}" for f in t["flags"]]
    return out


# ─── the map: a fresh file, or built on demand ───────────────────────────────

def load(symbol: str, maps_dir: Path = MAPS_DIR, max_age_days: float = MAX_AGE_DAYS,
         now: Optional[float] = None) -> Optional[dict]:
    path = Path(maps_dir) / f"{symbol}.json"
    try:
        if (now or time.time()) - path.stat().st_mtime > max_age_days * 86400:
            return None
        m = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return m if "zones" in m else None


def build(symbol: str, market: Any, as_of: Optional[date] = None, daily: Optional[list] = None) -> dict:
    """Build from the market's bars, using only bars before `as_of` (default: today, IST).
    `market` needs daily(symbol, days); intraday(symbol, days) adds the volume profile."""
    day = as_of or datetime.now(IST).date()
    bars = daily if daily is not None else market.daily(symbol, 365)
    intra = market.intraday(symbol, INTRADAY_DAYS) if hasattr(market, "intraday") else []
    intra = [b for b in (intra or []) if _d(b) < day]
    return build_map(symbol, sorted(bars or [], key=lambda b: b.timestamp), sorted(intra, key=lambda b: b.timestamp), day)


def save(m: dict, maps_dir: Path = MAPS_DIR) -> None:
    d = Path(maps_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{m['symbol']}.json").write_text(json.dumps(m, indent=1, default=str))
    (d / f"{m['symbol']}.md").write_text(render(m), encoding="utf-8")


def map_read(symbol: str, trade: Optional[dict] = None, as_of: Optional[date] = None, *,
             market: Any = None, market_factory: Optional[Callable[[], Any]] = None,
             maps_dir: Optional[Path] = None, max_age_days: float = MAX_AGE_DAYS,
             daily: Optional[list] = None, price: Optional[float] = None, zones: bool = False) -> dict:
    """The map read for `symbol`, and for `trade` if given. Never raises: a failure comes back
    as {"symbol", "error"}, which callers that require a read (the idea log) refuse on.
    `market_factory` is called only when a build is needed (no fresh file, or as_of).
    zones=True adds the whole ladder and the layers shown/missing (the cockpit's map page)."""
    sym = symbol.strip().upper()
    maps_dir = maps_dir or MAPS_DIR                          # at call time, so tests can move it
    try:
        m = None if as_of else load(sym, maps_dir, max_age_days)
        source = "file"
        if m is None:
            mk = market if market is not None else (market_factory() if market_factory else None)
            if mk is None:
                return {"symbol": sym, "error": "no map file younger than "
                                                f"{max_age_days:g} days and no market to build one"}
            m = build(sym, mk, as_of, daily)
            source = "built"
            if "error" not in m and not as_of:
                save(m, maps_dir)
        rd = read(m, trade, price)
        if "error" not in rd:
            rd["source"] = source
            if zones:
                rd.update(zones=ladder(m, rd["price"]), zone_width=m.get("zone_width"), layers=LAYERS)
        return rd
    except Exception as e:                                   # a read must never break the tool it serves
        return {"symbol": sym, "error": f"{type(e).__name__}: {str(e)[:160]}"}


def live_market():
    """The VM's live market (Fyers), for building a map on demand."""
    from core.mcp_tools.live import LiveMarket
    root = Path(__file__).resolve().parent.parent.parent
    return LiveMarket(str(root / "agent" / "config.yaml"))


def frozen(rd: dict) -> dict:
    """The read as stored with an idea: what it said and when."""
    return {**rd, "read_at": datetime.now(IST).isoformat(timespec="seconds")}
