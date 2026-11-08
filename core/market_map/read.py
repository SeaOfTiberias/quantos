"""
QuantOS — Market Map: map_read, the one call every decision path makes
──────────────────────────────────────────────────────────────────────
docs/MARKET_MAP_ENGINE_DESIGN.md §5. Answers "where are we, and what does that
mean for this trade?": the nearest strong zone below and above, the zone price is
in, and, for a proposed trade, the first strong zone in its way (in R), whether
the target lies beyond it, and whether the stop sits inside a zone.

The map (sprint plan S5 slice 7, user 2026-11-08) is the L1 higher-timeframe map:
definitions v1, built from the adjusted NSE bhavcopy in the L1 store (structure,
imbalance, liquidity, volume and pivot families; core/market_map/structure.py and
htf.py). Its zones are UNTESTED: no fidelity (§9) or signal test (S8) has run.
A symbol the L1 store doesn't hold falls back to the old 100-day price map below,
labelled as the fallback, with that map's FAILED status.

    map_read("HDFCBANK")                                          # where price is
    map_read("HDFCBANK", {"side": "short", "entry": 678, "stop": 690, "target": 665})

The fallback map comes from ~/.quantos/price_maps/<SYMBOL>.json when one was built in
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
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from core.price_map.build import build_map, nearest, render, rng, why, zone_at
from core.market_map import structure
from core.price_map.levels import IST, _d, first_obstacle

MAPS_DIR = Path.home() / ".quantos" / "price_maps"   # = scripts/price_map.py OUT
MAX_AGE_DAYS = 7                                       # = run_position_manager.MAP_MAX_AGE_DAYS
L2_LOOKBACK_DAYS = 365                                 # = build(): market.daily(symbol, 365)
CLOSE_TOL = 0.005                                      # Fyers vs bhavcopy close, L1/L2 join check
INTRADAY_DAYS = 99                                     # Fyers allows 100 days of 5-minute bars
UNTESTED = "untested"
FAILED = "failed its test"
ZONE_TEST = FAILED                                     # L2 strong zones: zone test 2026-11-04, FAIL
NOTE = ("Zones mark where price did business and turned. In the 2026-11-04 test they turned price no "
        "more often than placebo levels (docs/PRICE_MAP_ZONES_PREREG_2026-10-28.md): markers for "
        "reading a trade, never a signal or a filter.")
# What the map is built from and what it lacks, for every screen that draws it (docs/MARKET_MAP_SCREENS.md rule 3).
L1_ROOT = None                                         # the L1 store's root (None: its default); tests move it
NOTE_L1 = ("Higher-timeframe zones (definitions v1): where two or more families (structure, imbalance, liquidity, "
           "volume, pivot) agree. Untested: no fidelity or signal test has run. Markers for reading a trade, never "
           "a signal or a filter. Under v1 most zones count as strong (median 73%), so 'strong' selects little.")
LAYERS_OLD = {"shown": ["daily swings (last year)", f"5-minute volume profile (last {INTRADAY_DAYS} days)",
                        "pivots (last day, week, month)"],
              "missing": ["the higher-timeframe (L1) map: this stock is not in the L1 store, so the old 100-day "
                          "map is shown (it failed its test)",
                          "market backdrop (S6)",
                          "fundamentals (S6b)"]}
LAYERS_L1 = {"shown": ["monthly, weekly and daily structure (SMC: BOS, CHoCH, protected and weak levels)",
                       "demand/supply zones, order blocks, equal highs and lows (weekly, monthly)",
                       "week, month, quarter and year pivots, CPR and Camarilla (Ochoa)",
                       "money zones and volume profiles with virgin levels; 1- and 3-year profiles (approx.)"],
             "missing": ["daily pivots and the session (5-minute) profile: intraday layer",
                         "market backdrop (S6)",
                         "fundamentals (S6b)"]}
LAYERS = LAYERS_OLD


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

def _why(z: dict, n: int = 3) -> str:
    """A zone's members: the L1 map stores them as text, the old map as levels."""
    return z["why"] if "why" in z and "levels" not in z else why(z, n)


def _zone(z: Optional[dict], price: float, atr: float, status: str = ZONE_TEST) -> Optional[dict]:
    if not z:
        return None
    edge = z["high"] if z["high"] < price else z["low"]
    out = {"range": rng(z), "low": z["low"], "high": z["high"], "why": _why(z),
           "distance": round(abs(edge - price), 2),
           "distance_atr": round(abs(edge - price) / atr, 2) if atr else None,
           "distance_pct": round(abs(edge - price) / price * 100, 2), "test": status}
    if "families" in z:
        out["families"] = z["families"]
    return out


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
    st = m.get("status", ZONE_TEST)
    n = nearest(m, px)
    inside = zone_at(m, px)
    out: dict[str, Any] = {
        "symbol": m["symbol"], "built_for": m["built_for"], "close": m["close"], "price": px, "atr": m.get("atr"),
        "shifted_by": m.get("shifted_by"), "map": m.get("map", "old 100-day price map"),
        "inside": {"range": rng(inside), "why": _why(inside), "test": st} if inside else None,
        "below": _zone(n["below"], px, atr, st), "above": _zone(n["above"], px, atr, st),
        "status": st, "note": m.get("note", NOTE),
    }
    if m.get("atr_w"):
        out["atr_w"] = m["atr_w"]
    if t:
        out["trade"] = trade_read(m, t)
    return out


def trade_read(m: dict, t: dict) -> dict:
    side, entry, stop, target = t["side"], t["entry"], t["stop"], t["target"]
    st = m.get("status", ZONE_TEST)
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
            "first_obstacle": {"range": rng(ob["zone"]), "why": _why(ob["zone"]), "edge": ob["edge"], "r": ob["r"],
                               "test": st} if ob else None,
            "target_beyond_obstacle": beyond,
            "stop_in_zone": {"range": rng(sz), "why": _why(sz), "test": st} if sz else None,
            "flags": flags, "test": st}


def ladder(m: dict, price: float) -> list[dict]:
    """Every zone of the map (strong and weak), high to low, for drawing, with its distance from
    `price` (0 inside); levels folded into `why`. Weak zones carry the same status: the 11-04 test
    ran them as its control and they turned price less often than the strong ones, which did no
    better than placebo."""
    atr = m.get("atr") or 0
    st = m.get("status", ZONE_TEST)
    out = []
    for z in sorted(m.get("zones", []), key=lambda z: -z["high"]):
        where = "above" if z["low"] > price else "below" if z["high"] < price else "inside"
        gap = z["low"] - price if where == "above" else price - z["high"] if where == "below" else 0.0
        out.append({"low": z["low"], "high": z["high"], "range": rng(z), "strong": z["strong"],
                    "score": z.get("score", z.get("n")), "families": z["families"], "tfs": z.get("tfs"),
                    "why": _why(z, 6), "where": where, "distance": round(gap, 2),
                    "distance_atr": round(gap / atr, 2) if atr else None,
                    "distance_pct": round(gap / price * 100, 2), "test": st})
    return out


def lines(rd: dict) -> list[str]:
    """The read as text, for the CLIs and Telegram."""
    if "error" in rd:
        return [f"MAP  {rd.get('symbol') or ''}: none ({rd['error']})"]
    fmt = (lambda z: f"{z['range']} ({z['why']}), {z['distance_pct']:g}% away" if z else "no strong zone")
    basis = f", shifted {rd['shifted_by']:+g} onto futures" if rd.get("shifted_by") else ""
    if str(rd.get("map", "")).startswith("L1"):
        head = (f"MAP  {rd['symbol']} at {rd['price']:g} (higher-timeframe map, bhavcopy to {rd['built_for']}) "
                f"-- zones {rd['status']} (no fidelity or signal test yet)")
    else:
        head = (f"MAP  {rd['symbol']} at {rd['price']:g} (old 100-day map, built for {rd['built_for']}{basis}; "
                f"not in the L1 store) -- zones {rd['status']} (zone test 2026-11-04)")
    out = [head,
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
    if "l1" in rd:
        out += structure.lines(rd["l1"])
    for f in (rd.get("join") or {}).get("flags", []):
        out.append(f"     ! join: {f}")
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
             daily: Optional[list] = None, price: Optional[float] = None, zones: bool = False,
             l1_store: Any = None) -> dict:
    """The map read for `symbol`, and for `trade` if given. Never raises: a failure comes back
    as {"symbol", "error"}, which callers that require a read (the idea log) refuse on.
    `market_factory` is called only when a build is needed (no fresh file, or as_of).
    zones=True adds the whole ladder and the layers shown/missing (the cockpit's map page).
    rd["l1"] is the L1 structure read (M/W/D state, protected and weak levels, alignment)
    from the L1 price store (`l1_store`, default ~/.quantos/l1_store), or {"error"}."""
    sym = symbol.strip().upper()
    maps_dir = maps_dir or MAPS_DIR                          # at call time, so tests can move it
    try:
        l1 = l1_for(sym, as_of or datetime.now(IST).date(), l1_store)
        if "error" not in l1 and (l1.get("htf") or {}).get("zones"):
            m = l1_map(sym, l1)
            rd = read(m, trade, price)
            rd["source"] = "l1"
            if zones:
                rd.update(zones=ladder(m, rd["price"]), zone_width=m["zone_width"], layers=LAYERS_L1)
            rd["l1"] = l1
            return rd
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
            rd["fallback"] = f"not in the L1 store ({l1.get('error', 'no HTF zones')})"
            if zones:
                rd.update(zones=ladder(m, rd["price"]), zone_width=m.get("zone_width"), layers=LAYERS_OLD)
            rd["l1"] = l1
            rd["join"] = join_checks(rd)
        return rd
    except Exception as e:                                   # a read must never break the tool it serves
        return {"symbol": sym, "error": f"{type(e).__name__}: {str(e)[:160]}"}


def l1_map(symbol: str, l1: dict) -> dict:
    """The L1 read as a map dict for read(), trade_read() and ladder(): every HTF zone
    (strong = 2+ families), distances in ATR(D), the zone width in ATR(W)."""
    h = l1["htf"]
    return dict(symbol=symbol, built_for=l1.get("last_date"), close=l1["price"],
                atr=(l1["tf"].get("D") or {}).get("atr"), atr_w=h.get("atr_w"), zone_width=h.get("width"),
                zones=[dict(z) for z in h["zones"]], status=UNTESTED, note=NOTE_L1,
                map="L1 higher-timeframe map (definitions v1)")


def l1_for(symbol: str, as_of: date, store: Any = None) -> dict:
    """The L1 structure read from the price store; never raises."""
    try:
        from core.market_map.l1_store import Store
        st = store if store is not None else Store(L1_ROOT)
        adj, _ = st.adjusted(symbol)
        if adj.empty:
            return {"error": f"{symbol} is not in the L1 store at {st.root}"}
        from core.market_map.m5_store import M5Store
        m5 = M5Store(st.root).adjusted(symbol, adj, st.actions().get(symbol, []))
        rd = structure.l1_read(adj, as_of, m5 if len(m5) else None)
        lo = (as_of - timedelta(days=L2_LOOKBACK_DAYS)).isoformat()
        rd["actions_l2_window"] = [a for a in st.actions().get(symbol, []) if lo <= a["ex"] < as_of.isoformat()]
        rd["last_date"] = adj["date"][adj["date"] < str(as_of)].iat[-1].date().isoformat()
        return rd
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:160]}"}


def join_checks(rd: dict) -> dict:
    """L1/L2 join (sprint plan S5): L1 owns the week/month/quarter/year levels, built from
    the NSE bhavcopy; L2 is the price map from Fyers' daily and 5-minute bars. Checks that
    the two sources agree on the last close, and flags a split or bonus inside L2's lookback
    (L2's older levels then rest on Fyers' own adjustment)."""
    l1 = rd.get("l1") or {}
    out = dict(l1_source="NSE bhavcopy (adjusted), L1 store", l2_source="Fyers daily + 5-minute (price map)",
               flags=[])
    if "error" in l1:
        return out
    if l1.get("price") is not None and rd.get("close"):
        diff = abs(rd["close"] - l1["price"]) / l1["price"]
        out["close_check"] = dict(l2_close=rd["close"], l1_close=l1["price"], l1_date=l1.get("last_date"),
                                  ok=diff <= CLOSE_TOL)
        if diff > CLOSE_TOL:
            out["flags"].append(f"Fyers close {rd['close']:g} vs bhavcopy {l1['price']:g} ({l1.get('last_date')}): "
                                f"{diff:.1%} apart (dates may differ, or a corporate action)")
    for a in l1.get("actions_l2_window", []):
        out["flags"].append(f"{a['purpose']} ex {a['ex']} inside L2's {L2_LOOKBACK_DAYS}-day lookback: "
                            "L2 levels before it rest on Fyers' adjustment")
    return out


def live_market():
    """The VM's live market (Fyers), for building a map on demand."""
    from core.mcp_tools.live import LiveMarket
    root = Path(__file__).resolve().parent.parent.parent
    return LiveMarket(str(root / "agent" / "config.yaml"))


def frozen(rd: dict) -> dict:
    """The read as stored with an idea: what it said and when."""
    return {**rd, "read_at": datetime.now(IST).isoformat(timespec="seconds")}
