"""
QuantOS — F&O Screener: what happened to each pick
───────────────────────────────────────────────────
Pure. Given one logged pick (a candidate dict from
~/.quantos/fno_screener_history.jsonl) and the F&O bhavcopies of the
sessions after it, records the stock, the picked option and each suggested
spread at every session up to MAX_SESSIONS, then summarises the log.

Measured CLOSE TO CLOSE and BEFORE COSTS: entry is the pick day's bhavcopy
close, exit the close N sessions later. A real buy happens the next morning
at the ask, so this flatters the option a little and the spread more (two
legs crossed twice). The spread ideas carry their quoted bid-ask cost where
one existed; the stats report it beside the returns rather than netting a
guess into them.

The screener has no tested edge (it's a discretionary aid), so this log IS
the test: single option vs spread on the same picks, after enough of them.
Nothing here is a pre-registered verdict; the cockpit shows N beside every
number.
"""

from __future__ import annotations

from datetime import date
from statistics import mean
from typing import Optional

from core.fno_screener.bhavcopy import FnoDay
from core.options.models import OptionType

MAX_SESSIONS = 5
HORIZONS = (1, 3, 5)


def pick_key(trade_date: str, side: str, symbol: str) -> str:
    return f"{trade_date}|{side}|{symbol}"


def _close(day: FnoDay, symbol: str, expiry: date, strike: float, side: OptionType) -> Optional[float]:
    for q in day.options.get(symbol, []):
        if q.expiry == expiry and q.strike == strike and q.option_type == side and q.close > 0:
            return q.close
    return None


def track_pick(trade_date: str, cand: dict, days_after: list[FnoDay]) -> dict:
    """One outcome record. `days_after` = bhavcopy days strictly after
    trade_date, oldest first (only the first MAX_SESSIONS are used)."""
    q = cand["contract"]["quote"]
    side = OptionType(cand["side"])
    expiry = date.fromisoformat(q["expiry"])
    strike = float(q["strike"])
    spreads = (cand.get("spreads") or {}).get("ideas") or []
    sessions = []
    for d in days_after[:MAX_SESSIONS]:
        if d.trade_date > expiry:
            break
        row = {"date": d.trade_date.isoformat(), "spot": d.spot.get(cand["symbol"]),
               "option": _close(d, cand["symbol"], expiry, strike, side), "spreads": {}}
        for idea in spreads:
            lo = row["option"]
            sh = _close(d, cand["symbol"], expiry, float(idea["short_strike"]), side)
            row["spreads"][idea["label"]] = None if lo is None or sh is None else round(lo - sh, 2)
        sessions.append(row)
    return {
        "key": pick_key(trade_date, cand["side"], cand["symbol"]),
        "trade_date": trade_date, "symbol": cand["symbol"], "side": cand["side"],
        "expiry": q["expiry"], "strike": strike, "lot": q.get("lot_size"),
        "entry_spot": cand.get("close"), "entry_option": q.get("close"),
        "spread_entries": {i["label"]: {"debit_close": i["debit_close"], "cost_pct": i.get("cost_pct"),
                                        "long_strike": i["long_strike"], "short_strike": i["short_strike"]}
                           for i in spreads},
        "spread_ideas": spreads,
        "sessions": sessions,
        "complete": len(sessions) >= MAX_SESSIONS,
    }


def returns_at(outcome: dict, h: int) -> Optional[dict]:
    """% returns at session h (1-based), or None if not there yet / unpriced.
    stock_pct is signed in the pick's direction (a put pick gains when it falls)."""
    if len(outcome["sessions"]) < h:
        return None
    s = outcome["sessions"][h - 1]
    sign = 1 if outcome["side"] == "CE" else -1
    out = {"stock_pct": None, "option_pct": None, "spreads": {}}
    if s["spot"] and outcome["entry_spot"]:
        out["stock_pct"] = round(sign * (s["spot"] / outcome["entry_spot"] - 1) * 100, 2)
    if s["option"] is not None and outcome["entry_option"]:
        out["option_pct"] = round((s["option"] / outcome["entry_option"] - 1) * 100, 1)
    for label, entry in outcome["spread_entries"].items():
        v = s["spreads"].get(label)
        if v is not None and entry["debit_close"] > 0:
            out["spreads"][label] = round((v / entry["debit_close"] - 1) * 100, 1)
    return out


def _agg(values: list[float]) -> Optional[dict]:
    if not values:
        return None
    return {"n": len(values), "mean_pct": round(mean(values), 1),
            "win_pct": round(100 * sum(v > 0 for v in values) / len(values))}


def summarize(outcomes: list[dict]) -> dict:
    """Per side and horizon: single option and each spread label, same picks."""
    out = {}
    for side in ("CE", "PE"):
        rows = [o for o in outcomes if o["side"] == side]
        by_h = {}
        for h in HORIZONS:
            rs = [r for r in (returns_at(o, h) for o in rows) if r]
            labels = sorted({lab for r in rs for lab in r["spreads"]})
            by_h[str(h)] = {
                "stock": _agg([r["stock_pct"] for r in rs if r["stock_pct"] is not None]),
                "option": _agg([r["option_pct"] for r in rs if r["option_pct"] is not None]),
                "spreads": {lab: _agg([r["spreads"][lab] for r in rs if lab in r["spreads"]]) for lab in labels},
            }
        costs = [e["cost_pct"] for o in rows for e in o["spread_entries"].values() if e.get("cost_pct") is not None]
        out[side] = {"picks": len(rows), "complete": sum(o["complete"] for o in rows), "horizons": by_h,
                     "median_spread_cost_pct": sorted(costs)[len(costs) // 2] if costs else None}
    return out
