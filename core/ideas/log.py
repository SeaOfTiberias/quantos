"""
Trade-idea log: every discretionary idea (Claude's, the screener's, the
user's own), written down with its levels BEFORE the outcome is known, then
scored against what the market actually did.

The point is the scoreboard. A call is judged by numbers, including the
ideas that were passed on ("avoid") -- what skipping cost or saved is as much
a result as what a taken trade made.

An idea:
  id, created_at, source, symbol, view ("bull" | "bear" | "none"),
  action  : "enter_if"  -- enter when `trigger` is met
            "enter_now" -- enter at once (trigger = the creation day)
            "avoid"     -- deliberately not taken; tracked as a counterfactual
  structure (optional): {"kind": "bull_call"|"bear_put"|"bear_call"|"bull_put",
            "expiry": "YYYY-MM-DD", "long_strike", "short_strike", "lot"}
  trigger / cancel / stop (optional): {"kind": "close_above"|"close_below", "level": x}
            or {"kind": "close_between", "low": a, "high": b}
            cancel = gives up on the idea if hit BEFORE the trigger,
            stop   = exits the paper position if hit AFTER the trigger.
  spot, debit : underlying price and quoted spread debit when the idea was made
  note        : the reasoning, in a sentence or two
  taken       : what the user actually did ({"at", "debit", "lots", "account"})
  closed      : how a taken trade ended ({"at", "value" per share, "pnl"})
  marks       : daily snapshots written by the evaluator
                [{"date", "spot", "long_bid", "long_ask", "short_bid", "short_ask"}]

Pure logic only; scripts/trade_ideas.py does the I/O (Fyers quotes and
history, the JSON file, Telegram).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

IST = timezone(timedelta(hours=5, minutes=30))
ACTIONS = ("enter_if", "enter_now", "avoid")
VIEWS = ("bull", "bear", "none")
KINDS = ("bull_call", "bear_put", "bear_call", "bull_put")
CONDITIONS = ("close_above", "close_below", "close_between")
HORIZONS = (5, 10, 20)


class IdeaError(ValueError):
    pass


def _check_condition(c: Optional[dict], name: str) -> None:
    if c is None:
        return
    if c.get("kind") not in CONDITIONS:
        raise IdeaError(f"{name}.kind must be one of {CONDITIONS}")
    if c["kind"] == "close_between":
        if not (float(c["low"]) < float(c["high"])):
            raise IdeaError(f"{name}: low must be below high")
    elif float(c.get("level") or 0) <= 0:
        raise IdeaError(f"{name}.level must be positive")


def make_idea(raw: dict, now: Optional[datetime] = None) -> dict:
    """Validate and normalise a new idea; fills id and created_at."""
    now = now or datetime.now(IST)
    idea = dict(raw)
    sym = str(idea.get("symbol", "")).upper().strip()
    if not re.fullmatch(r"[A-Z0-9&\-]{1,20}", sym):
        raise IdeaError("symbol must be an NSE ticker")
    idea["symbol"] = sym
    if idea.get("action") not in ACTIONS:
        raise IdeaError(f"action must be one of {ACTIONS}")
    if idea.get("view") not in VIEWS:
        raise IdeaError(f"view must be one of {VIEWS}")
    s = idea.get("structure")
    if s:
        if s.get("kind") not in KINDS:
            raise IdeaError(f"structure.kind must be one of {KINDS}")
        date.fromisoformat(s["expiry"])
        for k in ("long_strike", "short_strike", "lot"):
            if float(s.get(k) or 0) <= 0:
                raise IdeaError(f"structure.{k} must be positive")
    for name in ("trigger", "cancel", "stop"):
        _check_condition(idea.get(name), name)
    if idea["action"] == "enter_if" and not idea.get("trigger"):
        raise IdeaError("enter_if needs a trigger")
    idea.setdefault("source", "claude")
    idea["created_at"] = idea.get("created_at") or now.isoformat(timespec="seconds")
    day = idea["created_at"][:10]
    if s:
        tag = f"{s['kind']}-{s['long_strike']:g}-{s['short_strike']:g}"
    else:
        tag = idea["action"]
    idea["id"] = idea.get("id") or f"{day}-{sym}-{tag}"
    idea.setdefault("marks", [])
    idea.setdefault("taken", None)
    idea.setdefault("closed", None)
    return idea


def condition_met(c: dict, close: float) -> bool:
    if c["kind"] == "close_above":
        return close > float(c["level"])
    if c["kind"] == "close_below":
        return close < float(c["level"])
    return float(c["low"]) <= close <= float(c["high"])


def _is_call(kind: str) -> bool:
    return kind in ("bull_call", "bear_call")


def _debit_kind(kind: str) -> bool:
    return kind in ("bull_call", "bear_put")


def intrinsic(kind: str, long_k: float, short_k: float, spot: float) -> float:
    """Per-share expiry value of the long leg minus the short leg."""
    if _is_call(kind):
        return max(spot - long_k, 0.0) - max(spot - short_k, 0.0)
    return max(long_k - spot, 0.0) - max(short_k - spot, 0.0)


def entry_cost(mark: dict) -> Optional[float]:
    """What opening the spread costs per share at this mark: buy the long at
    the ask, sell the short at the bid (negative = a credit)."""
    try:
        return float(mark["long_ask"]) - float(mark["short_bid"])
    except (KeyError, TypeError, ValueError):
        return None


def exit_value(mark: dict) -> Optional[float]:
    """What closing it fetches per share: sell the long at the bid, buy back
    the short at the ask."""
    try:
        return float(mark["long_bid"]) - float(mark["short_ask"])
    except (KeyError, TypeError, ValueError):
        return None


def evaluate(idea: dict, closes: list[tuple[str, float]], today: Optional[date] = None) -> dict:
    """Score an idea against the underlying's daily closes from its creation
    day onward ([(YYYY-MM-DD, close)], oldest first) and its own marks.

    Returns {"status", "trigger_date", "entry_spot", "entry_cost", "exit_date",
    "exit_reason", "value", "pnl", "pnl_pct", "spot_move_pct", "fwd": {5: %, ...}}.
    `pnl` is per lot in rupees on the paper position (entry at the trigger
    day's mark, exit at the stop day's mark, at expiry intrinsic, else the
    latest mark); None when there is no structure or no usable quote.
    """
    today = today or datetime.now(IST).date()
    created = idea["created_at"][:10]
    rows = [(d, float(c)) for d, c in closes if d >= created]
    s = idea.get("structure")
    marks = {m["date"]: m for m in idea.get("marks", [])}
    out = {"status": "watching", "trigger_date": None, "entry_spot": None, "entry_cost": None,
           "exit_date": None, "exit_reason": None, "value": None, "pnl": None, "pnl_pct": None,
           "spot_move_pct": None, "fwd": {}}
    if rows and idea.get("spot"):
        out["spot_move_pct"] = round(100 * (rows[-1][1] / float(idea["spot"]) - 1), 2)

    # 1. When did the idea trigger (or get cancelled first)?
    trig_i = None
    if idea["action"] in ("enter_now", "avoid") or not idea.get("trigger"):
        trig_i = 0 if rows else None
    else:
        for i, (d, c) in enumerate(rows):
            if condition_met(idea["trigger"], c):
                trig_i = i
                break
            if idea.get("cancel") and condition_met(idea["cancel"], c):
                out.update(status="cancelled", exit_date=d, exit_reason="cancel level hit before the trigger")
                break
    expiry = date.fromisoformat(s["expiry"]) if s else None
    if trig_i is None:
        if out["status"] == "watching" and expiry and today > expiry:
            out["status"] = "expired untriggered"
        return out

    t_date, t_spot = rows[trig_i]
    out["trigger_date"], out["entry_spot"] = t_date, t_spot
    after = rows[trig_i:]
    for h in HORIZONS:
        if len(after) > h:
            out["fwd"][h] = round(100 * (after[h][1] / t_spot - 1), 2)
    out["status"] = "avoided" if idea["action"] == "avoid" else "triggered"

    # 2. Paper position on the spread.
    if not s:
        return out
    lot = float(s["lot"])
    cost = None
    if idea["action"] == "enter_now" and idea.get("debit") is not None:
        cost = float(idea["debit"])
    if cost is None and t_date in marks:
        cost = entry_cost(marks[t_date])
    if cost is None and t_date == created and idea.get("debit") is not None:
        cost = float(idea["debit"])
    out["entry_cost"] = cost

    exit_d, value, reason = None, None, None
    for d, c in after[1:]:
        if idea.get("stop") and condition_met(idea["stop"], c):
            exit_d, reason = d, "stop level hit"
            value = exit_value(marks[d]) if d in marks else None
            break
    if exit_d is None and expiry and today >= expiry:
        last_on_or_before = [r for r in rows if r[0] <= expiry.isoformat()]
        if last_on_or_before:
            exit_d, reason = last_on_or_before[-1][0], "expiry"
            value = intrinsic(s["kind"], float(s["long_strike"]), float(s["short_strike"]),
                              last_on_or_before[-1][1])
    if exit_d is None:
        for d in sorted(marks, reverse=True):
            v = exit_value(marks[d])
            if v is not None and d >= t_date:
                value = v
                break
    out["exit_date"], out["exit_reason"] = exit_d, reason
    if value is not None:
        out["value"] = round(value, 2)
    if exit_d:
        out["status"] = "avoided, would have exited" if idea["action"] == "avoid" else "exited"
    if cost is not None and value is not None:
        # Same formula for credit spreads: cost and value are then negative.
        pnl = (value - cost) * lot
        out["pnl"] = round(pnl, 0)
        width = abs(float(s["long_strike"]) - float(s["short_strike"]))
        risk = (cost if _debit_kind(s["kind"]) else width + cost) * lot
        if risk > 0:
            out["pnl_pct"] = round(100 * pnl / risk, 1)
    return out


def scoreboard(evals: list[tuple[dict, dict]]) -> dict:
    """Aggregate by action: count, how many triggered, paper P&L where known."""
    out: dict = {}
    for idea, ev in evals:
        a = out.setdefault(idea["action"], {"ideas": 0, "triggered": 0, "scored": 0, "pnl": 0.0, "wins": 0})
        a["ideas"] += 1
        if ev.get("trigger_date"):
            a["triggered"] += 1
        if ev.get("pnl") is not None:
            a["scored"] += 1
            a["pnl"] += ev["pnl"]
            a["wins"] += ev["pnl"] > 0
    return out


def option_symbol(symbol: str, expiry: str, strike: float, right: str) -> str:
    """Fyers monthly-contract symbol, e.g. NSE:NESTLEIND26NOV1250PE."""
    d = date.fromisoformat(expiry)
    return f"NSE:{symbol}{d:%y}{d.strftime('%b').upper()}{strike:g}{right}"
