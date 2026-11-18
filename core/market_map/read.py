"""
QuantOS — Market Map: map_read, the one call every decision path makes
──────────────────────────────────────────────────────────────────────
docs/MARKET_MAP_ENGINE_DESIGN.md §5. Answers "where are we, and what does that
mean for this trade?": the nearest strong zone below and above, the zone price is
in, and, for a proposed trade, the first strong zone in its way (in R), whether
the target lies beyond it, and whether the stop sits inside a zone.

ONE map (user, 2026-11-18): the L1 higher-timeframe map, definitions v3
(docs/MARKET_MAP_DEFINITIONS_V3.md; v1 as amended 2026-11-11 and 2026-11-13), built
from the adjusted NSE bhavcopy in the L1 store (structure, order blocks, bases,
fair-value gaps, equal highs/lows; pivots and volume as the levels layer;
core/market_map/structure.py and htf.py). NIFTY and BANKNIFTY are read by the same
engine from NSE's index close files (core/market_map/index_bars.py). Its zones are
UNTESTED: no signal test has run.

The old 100-day price map (core/price_map, which FAILED its zone test on 2026-11-04)
is no longer a map anywhere: no fallback, no file, no build. A symbol the L1 store
and the index bars don't hold gets {"symbol", "error"}. core/price_map stays only as
a helper library (profiles, buckets) and for reproducing the 11-04 test.

    map_read("HDFCBANK")                                          # where price is
    map_read("HDFCBANK", {"side": "short", "entry": 678, "stop": 690, "target": 665})

A read informs a decision; it never blocks or moves an order by itself.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from core.market_map import structure
from core.price_map.build import nearest, rng, zone_at
from core.price_map.levels import IST, first_obstacle

UNTESTED = "untested"
MAP_NAME = "L1 higher-timeframe map (definitions v3)"
INDEX_SYMBOLS = ("NIFTY", "BANKNIFTY")                 # = core.market_map.index_bars.INDICES values
L1_ROOT = None                                         # the L1 store's root (None: its default); tests move it
INDEX_ROOT = None                                      # the index bars' root (None: its default); tests move it
ACTIONS_LOOKBACK_DAYS = 365                            # corporate actions listed with a read
NOTE = ("Higher-timeframe zones (definitions v3): built from price action only (structure, order blocks, "
        "supply/demand bases, fair-value gaps, equal highs/lows); used zones are removed. Strong = a fresh order "
        "block or base where a BOS/CHoCH started, with a pivot or volume level within 0.3 ATR(W). Untested: no "
        "signal test has run. Markers for reading a trade, never a signal or a filter.")
# What the map is built from and what it lacks, for every screen that draws it (docs/MARKET_MAP_SCREENS.md rule 3).
LAYERS = {"shown": ["monthly, weekly and daily structure (SMC: BOS, CHoCH, protected and weak levels)",
                    "demand/supply zones, order blocks, fair-value gaps, equal highs and lows (weekly, monthly)",
                    "week, month, quarter and year pivots, CPR and Camarilla (Ochoa)",
                    "money zones and volume profiles with virgin levels; 1- and 3-year profiles (approx.)",
                    "daily layer, shown beside the zones and not in them: daily pivots, CPR, Camarilla, and "
                    "session profiles with virgin levels from 5-minute bars since 2017 (stocks only)"],
          "missing": ["market backdrop (S6)",
                      "fundamentals (S6b)"]}
LAYERS_L1 = LAYERS                                     # the name earlier screens and tests use


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

def _why(z: Optional[dict]) -> str:
    return (z or {}).get("why", "")


def _zone(z: Optional[dict], price: float, atr: float, status: str = UNTESTED) -> Optional[dict]:
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
    """The read of a map dict (l1_map). `trade` = {side, entry, stop, target?}; `price` defaults to
    the trade's entry, else the map's last close."""
    if not m or "zones" not in m:
        return {"symbol": (m or {}).get("symbol"), "error": (m or {}).get("error") or "no map"}
    t = None
    if trade:
        t = {"side": side_of(trade["side"]), "entry": float(trade["entry"]),
             "stop": float(trade["stop"]) if trade.get("stop") is not None else None,
             "target": float(trade["target"]) if trade.get("target") is not None else None}
    px = float(price if price is not None else (t["entry"] if t else m["close"]))
    atr = m.get("atr") or 0
    st = m.get("status", UNTESTED)
    n = nearest(m, px)
    inside = zone_at(m, px)
    out: dict[str, Any] = {
        "symbol": m["symbol"], "built_for": m["built_for"], "close": m["close"], "price": px, "atr": m.get("atr"),
        "shifted_by": m.get("shifted_by"), "map": m.get("map", MAP_NAME),
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
    st = m.get("status", UNTESTED)
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
    `price` (0 inside)."""
    atr = m.get("atr") or 0
    st = m.get("status", UNTESTED)
    out = []
    for z in sorted(m.get("zones", []), key=lambda z: -z["high"]):
        where = "above" if z["low"] > price else "below" if z["high"] < price else "inside"
        gap = z["low"] - price if where == "above" else price - z["high"] if where == "below" else 0.0
        out.append({"low": z["low"], "high": z["high"], "range": rng(z), "strong": z["strong"],
                    "score": z.get("score", z.get("n")), "families": z["families"], "tfs": z.get("tfs"),
                    "why": _why(z), "where": where, "distance": round(gap, 2),
                    "distance_atr": round(gap / atr, 2) if atr else None,
                    "distance_pct": round(gap / price * 100, 2), "test": st})
    return out


def shift(m: dict, by: float) -> dict:
    """The map moved by `by` points, e.g. onto futures prices (by = futures - cash). The map is
    built from cash (or index) bars; a futures position compares against the shifted copy."""
    if not m or "zones" not in m or not by:
        return m
    mv = (lambda x: round(x + by, 2))
    zs = [{**z, "low": mv(z["low"]), "high": mv(z["high"]), "mid": mv(z["mid"])} for z in m["zones"]]
    return {**m, "zones": zs, "close": mv(m["close"]), "shifted_by": round(by, 2)}


def markers(m: dict, price: float, entry: float, side: int, r: float, target: Optional[float]) -> list[str]:
    """Plan-message lines (position manager): the strong zones either side of `price`, and the
    first one in the trade's way. Untested markers."""
    if not m or "zones" not in m:
        return [f"• Map: none ({(m or {}).get('error', 'no read')})"]
    n = nearest(m, price)
    basis = f", futures = cash {m['shifted_by']:+g}" if m.get("shifted_by") else ""
    fmt = (lambda z: f"{rng(z)} ({_why(z)})" if z else "no strong zone")
    out = [f"• Map (v3, untested; {m['built_for']}{basis}): below {fmt(n['below'])}; above {fmt(n['above'])}"]
    ob = first_obstacle(m["zones"], entry, side, r) if r > 0 else None
    if ob is None:
        out.append("• First obstacle: none before the target" if target is not None else "• First obstacle: none")
    else:
        beyond = target is not None and (target - ob["edge"]) * side > 0
        out.append(f"• First obstacle {rng(ob['zone'])} at {ob['r']:g}R" + (" -- the target is beyond it ⚠️" if beyond else ""))
    return out


def lines(rd: dict) -> list[str]:
    """The read as text, for the CLIs and Telegram."""
    if "error" in rd:
        return [f"MAP  {rd.get('symbol') or ''}: none ({rd['error']})"]
    fmt = (lambda z: f"{z['range']} ({z['why']}), {z['distance_pct']:g}% away" if z else "no strong zone")
    basis = f", shifted {rd['shifted_by']:+g} onto futures" if rd.get("shifted_by") else ""
    out = [f"MAP  {rd['symbol']} at {rd['price']:g} (higher-timeframe map v3, bhavcopy to {rd['built_for']}{basis}) "
           f"-- zones {rd['status']} (no signal test yet)",
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
    return out


# ─── the map from the L1 store (or the index bars) ───────────────────────────

def map_read(symbol: str, trade: Optional[dict] = None, as_of: Optional[date] = None, *,
             price: Optional[float] = None, zones: bool = False, l1_store: Any = None,
             index_root: Optional[Path] = None) -> dict:
    """The map read for `symbol`, and for `trade` if given, from bars before `as_of` (default
    today, IST). Never raises: a failure comes back as {"symbol", "error"}, which callers that
    require a read (the idea log) refuse on. `price` reads at that price (live, or a futures
    limit) instead of the map's close. zones=True adds the whole ladder and the layers
    (the cockpit's map page). rd["l1"] is the L1 structure read (M/W/D state, protected and
    weak levels, alignment)."""
    sym = symbol.strip().upper()
    try:
        m, l1 = current_map(sym, as_of, l1_store=l1_store, index_root=index_root, with_l1=True)
        if "error" in m:
            return {"symbol": sym, "error": m["error"]}
        rd = read(m, trade, price)
        rd["source"] = "index" if sym in INDEX_SYMBOLS else "l1"
        if zones:
            rd.update(zones=ladder(m, rd["price"]), zone_width=m["zone_width"], layers=LAYERS)
        rd["l1"] = l1
        return rd
    except Exception as e:                                   # a read must never break the tool it serves
        return {"symbol": sym, "error": f"{type(e).__name__}: {str(e)[:160]}"}


def current_map(symbol: str, as_of: Optional[date] = None, *, l1_store: Any = None,
                index_root: Optional[Path] = None, with_l1: bool = False):
    """The v3 map dict for `symbol` (for read(), shift(), markers()), or {"error"}.
    with_l1=True returns (map, l1 read)."""
    sym = symbol.strip().upper()
    l1 = l1_for(sym, as_of or datetime.now(IST).date(), l1_store, index_root)
    if "error" in l1:
        m = {"symbol": sym, "error": l1["error"]}
    elif not (l1.get("htf") or {}).get("zones"):
        m = {"symbol": sym, "error": "the L1 map has no higher-timeframe zones (too little history?)"}
    else:
        m = l1_map(sym, l1)
    return (m, l1) if with_l1 else m


def l1_map(symbol: str, l1: dict) -> dict:
    """The L1 read as a map dict for read(), trade_read() and ladder(): every HTF zone
    (strong by definitions v3 H3), distances in ATR(D), the zone width in ATR(W)."""
    h = l1["htf"]
    return dict(symbol=symbol, built_for=l1.get("last_date"), close=l1["price"],
                atr=(l1["tf"].get("D") or {}).get("atr"), atr_w=h.get("atr_w"), zone_width=h.get("width"),
                zones=[dict(z) for z in h["zones"]], status=UNTESTED, note=NOTE, map=MAP_NAME)


def l1_for(symbol: str, as_of: date, store: Any = None, index_root: Optional[Path] = None) -> dict:
    """The L1 structure read from the price store, or for NIFTY/BANKNIFTY from the index bars;
    never raises."""
    try:
        import pandas as pd
        if symbol in INDEX_SYMBOLS:
            from core.market_map.index_bars import IndexBars
            ib = IndexBars(index_root if index_root is not None else INDEX_ROOT)
            df = ib.load(symbol)
            if df.empty:
                return {"error": f"{symbol}: no index bars at {ib.root}"}
            rd = structure.l1_read(df, as_of, None)
            rd["actions_recent"] = []
        else:
            from core.market_map.l1_store import Store
            st = store if store is not None else Store(L1_ROOT)
            df, _ = st.adjusted(symbol)
            if df.empty:
                return {"error": f"{symbol} is not in the L1 store at {st.root}"}
            from core.market_map.m5_store import M5Store
            m5 = M5Store(st.root).adjusted(symbol, df, st.actions().get(symbol, []))
            rd = structure.l1_read(df, as_of, m5 if len(m5) else None)
            lo = (as_of - timedelta(days=ACTIONS_LOOKBACK_DAYS)).isoformat()
            rd["actions_recent"] = [a for a in st.actions().get(symbol, []) if lo <= a["ex"] < as_of.isoformat()]
        before = pd.to_datetime(df["date"]) < pd.Timestamp(as_of)
        if not before.any():
            return {"error": f"{symbol}: no bars before {as_of}"}
        rd["last_date"] = pd.to_datetime(df["date"])[before].iat[-1].date().isoformat()
        return rd
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:160]}"}


def frozen(rd: dict) -> dict:
    """The read as stored with an idea: what it said and when."""
    return {**rd, "read_at": datetime.now(IST).isoformat(timespec="seconds")}
