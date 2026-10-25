"""
QuantOS — MCP market tools, tier T0 (docs/TERMINAL_ARCHITECTURE.md §5.3, phase 0b)
────────────────────────────────────────────────────────────────────────────────────
Read-only answers to "what about <stock>?": quote, levels, option chain, a
priced spread, the structure picker, futures OI build-up, the screener's
latest picks and the trade-idea log. Public market data (P0) and research
(P1) only -- no account positions or holdings (those are T1, later).

Every function takes a `Market` (live Fyers + the NSE bhavcopy cache) and
returns plain JSON-able dicts, so the MCP server (mcp_server/quantos_mcp.py)
stays a thin wrapper and the logic is unit-tested with a fake market.
Numbers come from code; nothing here calls a model.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

from core.brokers.base import OHLCV
from core.ideas.structure import Chain, View, best_by_family, candidates, implied_vol

IST = timezone(timedelta(hours=5, minutes=30))
QUANTOS_DIR = Path.home() / ".quantos"
INDEX = {"NIFTY": "NSE:NIFTY50-INDEX", "BANKNIFTY": "NSE:NIFTYBANK-INDEX", "NIFTYBANK": "NSE:NIFTYBANK-INDEX",
         "FINNIFTY": "NSE:FINNIFTY-INDEX", "INDIAVIX": "NSE:INDIAVIX-INDEX"}


class Market(Protocol):
    def quotes(self, fyers_symbols: list[str]) -> dict[str, dict]: ...
    def daily(self, symbol: str, days: int) -> list[OHLCV]: ...
    def chain(self, symbol: str, steps: int) -> Chain: ...
    def fno_day(self, d: date): ...                      # FnoDay or None (bhavcopy cache / archive)


def fyers_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if s.startswith("NSE:"):
        return s
    return INDEX.get(s, f"NSE:{s}-EQ")


def _r(x: Optional[float], n: int = 2) -> Optional[float]:
    return None if x is None else round(float(x), n)


# ─── quote ───────────────────────────────────────────────────────────────────

def quote(m: Market, symbols: list[str]) -> list[dict]:
    names = [fyers_symbol(s) for s in symbols]
    got = m.quotes(names)
    out = []
    for s, n in zip(symbols, names):
        v = got.get(n) or {}
        lp, prev = v.get("lp"), v.get("prev_close_price")
        out.append({"symbol": s.upper(), "fyers": n, "ltp": lp, "open": v.get("open_price"), "high": v.get("high_price"),
                    "low": v.get("low_price"), "prev_close": prev,
                    "chg_pct": _r((lp / prev - 1) * 100) if lp and prev else None,
                    "bid": v.get("bid"), "ask": v.get("ask"), "volume": v.get("volume"),
                    "session": datetime.fromtimestamp(int(float(v["tt"])), IST).date().isoformat() if v.get("tt") else None})
    return out


# ─── levels ──────────────────────────────────────────────────────────────────

def _ema(xs: list[float], n: int) -> Optional[float]:
    if len(xs) < n:
        return None
    k, e = 2 / (n + 1), sum(xs[:n]) / n
    for x in xs[n:]:
        e += k * (x - e)
    return e


def _atr(bars: list[OHLCV], n: int = 14) -> Optional[float]:
    if len(bars) < n + 1:
        return None
    tr = [max(b.high - b.low, abs(b.high - a.close), abs(b.low - a.close)) for a, b in zip(bars[-n - 1:], bars[-n:])]
    return sum(tr) / n


def levels(m: Market, symbol: str) -> dict:
    """Daily trend, volatility and Darvas box state, plus the screener's tested
    retest plan for each side. Uses completed sessions only (today's forming
    bar is reported separately)."""
    from core.darvas.weekly_discovery import analyse_symbol
    from core.fno_screener.screener import (PLAN_ENTRY_ATR, PLAN_MAX_SESSIONS, PLAN_STOP_ATR, PLAN_TARGET_R,
                                            invert_bars)
    sym = symbol.strip().upper()
    today = datetime.now(IST).date()
    allbars = m.daily(sym, 365)
    done = [b for b in allbars if b.timestamp.astimezone(IST).date() < today] if allbars else []
    if len(done) < 30:
        return {"symbol": sym, "error": f"only {len(done)} daily bars"}
    closes = [b.close for b in done]
    last = done[-1]
    yr = done[-252:]
    atr = _atr(done)
    out: dict[str, Any] = {
        "symbol": sym, "as_of": last.timestamp.astimezone(IST).date().isoformat(), "close": last.close,
        "atr14": _r(atr), "atr_pct": _r(atr / last.close * 100) if atr else None,
        "ema9": _r(_ema(closes, 9)), "ema21": _r(_ema(closes, 21)),
        "sma50": _r(sum(closes[-50:]) / 50) if len(closes) >= 50 else None,
        "sma200": _r(sum(closes[-200:]) / 200) if len(closes) >= 200 else None,
        "high_52w": max(b.high for b in yr), "low_52w": min(b.low for b in yr),
        "recent": [{"date": b.timestamp.astimezone(IST).date().isoformat(), "o": b.open, "h": b.high, "l": b.low,
                    "c": b.close, "v": b.volume} for b in done[-10:]],
    }
    if len(allbars) > len(done):
        t = allbars[-1]
        out["today"] = {"o": t.open, "h": t.high, "l": t.low, "c": t.close, "v": t.volume}
    out["trend"] = ("up" if out["ema9"] and out["ema21"] and out["ema9"] > out["ema21"] else "down")
    up = analyse_symbol(sym, done)
    dn = analyse_symbol(sym, invert_bars(done))
    floor = last.close ** 2 / dn.box_ceiling if dn and dn.box_ceiling else None
    out["box"] = {"ceiling": _r(up.box_ceiling) if up else None, "status_up": up.status if up else None,
                  "floor_put_view": _r(floor), "status_down": dn.status if dn else None,
                  "width_pct": _r(up.box_width_pct) if up and up.box_width_pct else None}
    plans = {}
    for side, level in (("call", up.box_ceiling if up else None), ("put", floor)):
        if not level or not atr:
            continue
        s = 1 if side == "call" else -1
        entry = level + s * PLAN_ENTRY_ATR * atr
        plans[side] = {"limit": _r(entry), "stop_daily_close": _r(entry - s * PLAN_STOP_ATR * atr),
                       "target_1r": _r(entry + s * PLAN_TARGET_R * PLAN_STOP_ATR * atr),
                       "valid_sessions": 3, "max_sessions": PLAN_MAX_SESSIONS,
                       "measured_edge": side == "put",
                       "distance_pct": _r((entry / last.close - 1) * 100)}
    out["retest_plans"] = plans
    return out


# ─── option chain / spread ───────────────────────────────────────────────────

def _bhav_options(m: Market, symbol: str, expiry: date) -> dict:
    """(strike, right) -> (oi_lots, volume) from the latest cached bhavcopy."""
    d = datetime.now(IST).date()
    for _ in range(7):
        d -= timedelta(days=1)
        day = m.fno_day(d)
        if day is not None:
            return {(q.strike, q.option_type.value): (q.oi_lots, q.volume)
                    for q in day.options.get(symbol, []) if q.expiry == expiry}
    return {}


def option_chain(m: Market, symbol: str, expiry: Optional[str] = None, right: Optional[str] = None,
                 strikes: int = 8) -> dict:
    sym = symbol.strip().upper()
    ch = m.chain(sym, strikes)
    exps = sorted({k[0] for k in ch.options})
    if not exps:
        return {"symbol": sym, "error": "no two-sided option quotes"}
    exp = date.fromisoformat(expiry) if expiry else exps[0]
    bhav = _bhav_options(m, sym, exp)
    t = max((exp - ch.today).days, 0) / 365
    rows = []
    for (e, k, r), q in sorted(ch.options.items(), key=lambda kv: (kv[0][2], kv[0][1])):
        if e != exp or (right and r != right.upper()):
            continue
        iv = implied_vol(q.mid, ch.spot, k, t, r) if t > 0 else None
        oi, vol = bhav.get((k, r), (None, None))
        rows.append({"strike": k, "right": r, "bid": q.bid, "ask": q.ask, "mid": _r(q.mid),
                     "spread_pct": _r((q.ask - q.bid) / q.mid * 100, 1) if q.mid else None,
                     "iv_pct": _r(iv * 100, 1) if iv else None,
                     "itm": (k < ch.spot) if r == "CE" else (k > ch.spot),
                     "oi_lots_prev": oi, "volume_prev": vol})
    fut = ch.futures.get(exp)
    return {"symbol": sym, "spot": ch.spot, "lot": ch.lot, "expiry": exp.isoformat(), "expiries": [e.isoformat() for e in exps],
            "dte": (exp - ch.today).days, "future": {"bid": fut.bid, "ask": fut.ask} if fut else None, "rows": rows}


def price_spread(m: Market, symbol: str, expiry: str, right: str, long_strike: float, short_strike: float) -> dict:
    """A vertical priced the way it fills: buy the long at the ask, sell the short at the bid."""
    sym, r, exp = symbol.strip().upper(), right.upper(), date.fromisoformat(expiry)
    ch = m.chain(sym, 15)
    ql, qs = ch.options.get((exp, float(long_strike), r)), ch.options.get((exp, float(short_strike), r))
    if not ql or not qs:
        return {"symbol": sym, "error": "no two-sided quote for one of the legs",
                "have_long": bool(ql), "have_short": bool(qs)}
    debit = ql.ask - qs.bid
    mid = ql.mid - qs.mid
    width = abs(short_strike - long_strike)
    lot = ch.lot
    sign = 1 if r == "CE" else -1
    if (short_strike - long_strike) * sign <= 0:
        return {"symbol": sym, "error": "not a debit vertical: the short strike must be further out than the long"}
    be = long_strike + sign * debit
    return {"symbol": sym, "spot": ch.spot, "expiry": expiry, "right": r, "lot": lot,
            "legs": {"buy": {"strike": long_strike, "bid": ql.bid, "ask": ql.ask},
                     "sell": {"strike": short_strike, "bid": qs.bid, "ask": qs.ask}},
            "debit": _r(debit), "debit_mid": _r(mid), "round_trip_cost_pct": _r(2 * (debit - mid) / debit * 100, 1) if debit > 0 else None,
            "max_loss": _r(debit * lot, 0), "max_profit": _r((width - debit) * lot, 0),
            "reward_risk": _r((width - debit) / debit) if debit > 0 else None,
            "breakeven": _r(be), "breakeven_move_pct": _r((be / ch.spot - 1) * 100),
            "dte": (exp - ch.today).days}


# ─── structure picker ────────────────────────────────────────────────────────

def completed_atr(m: Market, symbol: str) -> Optional[float]:
    """ATR(14) from completed daily sessions (today's forming bar excluded)."""
    today = datetime.now(IST).date()
    bars = m.daily(symbol, 45) or []
    return _atr([b for b in bars if b.timestamp.astimezone(IST).date() < today])


def structure_row(c) -> dict:
    return {"structure": c.name, "expiry": c.expiry.isoformat() if c.expiry else None, "entry": _r(c.entry),
            "if_target": _r(c.gain_target, 0), "if_stop_or_stall": _r(c.loss_stop, 0),
            "if_stall": _r(c.stall, 0), "if_flat": _r(c.flat, 0), "worst": _r(c.worst_case, 0),
            "needs_p": _r(c.be_p, 3), "ev_per_worst": _r(c.score, 3), "lots": c.lots, "fits": c.fits,
            "rules_ok": not c.flags, "flags": c.flags, "note": c.note or None}


def pick_structure(m: Market, symbol: str, direction: str, target: float, stop: float, days: int,
                   budget: float = 0, p: float = 0.5, intraday: bool = False, gap_pct: Optional[float] = None,
                   thesis: str = "move", atr: Optional[float] = None) -> dict:
    sym = symbol.strip().upper()
    ch = m.chain(sym, 10)
    atr = atr or completed_atr(m, sym)
    view = View(direction=1 if direction.lower().startswith("bu") else -1, target=target, stop=stop, horizon_days=days,
                risk_budget=budget or None, overnight=not intraday, atr=atr,
                thesis="hold" if thesis.lower().startswith("h") else "move",
                **({"gap_pct": gap_pct} if gap_pct is not None else {}))
    ranked = candidates(ch, view, p=p)
    return {"symbol": sym, "spot": ch.spot, "lot": ch.lot, "atr14": _r(atr),
            "view": {"direction": direction, "target": target, "stop": stop, "days": days, "budget": budget or None,
                     "p": p, "gap_pct": view.gap_pct, "thesis": view.thesis},
            "best_by_family": [structure_row(c) for c in best_by_family(ranked)],
            "top": [structure_row(c) for c in ranked[:8]],
            "read": "Rule-passing structures (rules_ok) rank first, then by EV per worst-case rupee. Pick the lowest "
                    "needs_p that fits; flags name the strike rule a structure breaks (R1 long strike too far OTM, "
                    "R2 short strike off the target / inside the stop, R3 short leg finances < 35%, R5 family vs "
                    "thesis, R6 strike out of reach). if_flat = no move by the horizon."}


# ─── OI build-up ─────────────────────────────────────────────────────────────

def oi_buildup(m: Market, symbol: str, lookback: int = 5) -> dict:
    from core.fno_screener.screener import oi_buildup as _oi
    sym = symbol.strip().upper()
    days, d = [], datetime.now(IST).date()
    for _ in range(lookback * 3 + 10):
        d -= timedelta(days=1)
        if d.weekday() >= 5:
            continue
        day = m.fno_day(d)
        if day is not None:
            days.append(day)
        if len(days) > lookback:
            break
    if len(days) <= lookback:
        return {"symbol": sym, "error": "not enough bhavcopies"}
    b = _oi(days[0], days[lookback], sym, 2.0)
    if b is None:
        return {"symbol": sym, "error": "no futures OI for this symbol"}
    return {"symbol": sym, "from": days[lookback].trade_date.isoformat(), "to": days[0].trade_date.isoformat(),
            "label": b.label, "price_chg_pct": b.price_chg_pct, "oi_chg_pct": b.oi_chg_pct}


# ─── screener / idea log (local files) ───────────────────────────────────────

def screener(base: Path = QUANTOS_DIR, side: Optional[str] = None) -> dict:
    try:
        rec = json.loads((base / "fno_screener_latest.json").read_text())
    except (OSError, ValueError):
        return {"error": "no screener run on file"}

    def brief(c: dict) -> dict:
        k = (c.get("contract") or {}).get("quote") or {}
        return {"symbol": c["symbol"], "side": c["side"], "close": c["close"], "state": c["breakout_state"],
                "days_out": c.get("days_out"), "box_level": c.get("box_level"), "atr": c.get("atr"),
                "oi": (c.get("oi") or {}).get("label"),
                "contract": f'{k.get("strike")} {k.get("option_type")} {k.get("expiry")}' if k else None}
    out = {"trade_date": rec.get("trade_date"), "market": rec.get("market")}
    for key in ("calls", "puts", "watch", "skipped", "dropped"):
        rows = [brief(c) for c in rec.get(key) or []]
        if side:
            rows = [r for r in rows if r["side"] == side.upper()]
        out[key] = rows
    return out


def ideas(base: Path = QUANTOS_DIR, symbol: Optional[str] = None, open_only: bool = False) -> list[dict]:
    try:
        data = json.loads((base / "trade_ideas.json").read_text())
    except (OSError, ValueError):
        return []
    rows = data if isinstance(data, list) else data.get("ideas", [])
    out = []
    for i in rows:
        if symbol and i.get("symbol", "").upper() != symbol.upper():
            continue
        ev = i.get("eval") or {}
        status = ev.get("status") or "not evaluated yet"
        if open_only and status.split(" ")[0] in ("closed", "cancelled", "avoided", "expired", "exited"):
            continue
        row = {k: i.get(k) for k in ("id", "symbol", "view", "action", "spot", "debit", "trigger", "stop",
                                     "cancel", "structure", "note", "created_at", "taken", "closed")}
        row.update(status=status, paper_pnl=ev.get("pnl"), spot_since_pct=ev.get("spot_move_pct"))
        out.append(row)
    return out
