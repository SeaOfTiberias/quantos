"""
QuantOS — order tickets the user releases from the dashboard (user, 2026-11-16)
───────────────────────────────────────────────────────────────────────────────
The order rule is unchanged: code drafts, code checks, the user releases. A ticket is an entry
order drafted by code (scripts/ticket.py, later the strategies' evening jobs); the release page
(#/release, cloud/api/release_routes.py) replaces typing `qorder.py --yes` on the VM.

  * A ticket holds one or more order legs (core/orders/checks.Intent), why it was drafted, and
    its max loss in rupees, computed here, never by a model.
  * It can be released only while it is fresh: before `valid_until` (IST) and while the first
    leg's price (its quote mid now vs `ref_price`, the first leg's limit at the draft) has moved
    no more than `max_move_pct`.
  * The user may lower the quantity, never raise it (size is a config decision).
  * Release sends every leg through core/orders/gateway.Gateway.place, which runs the checks
    against a fresh quote and journals the attempt; in paper mode it journals "paper" and sends
    nothing. A refused leg stops the ticket there.
  * Exits are never tickets: rule-driven exits are placed by the position manager.

Stored in ~/.quantos/tickets.json (P2: household orders; 0600, never committed).
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from core.orders.checks import Intent

IST = timezone(timedelta(hours=5, minutes=30))
PATH = Path.home() / ".quantos" / "tickets.json"
DEFAULT_MAX_MOVE_PCT = 1.0


def now_ist() -> datetime:
    return datetime.now(IST)


def intent_from(d: dict) -> Intent:
    d = dict(d)
    d["expiry"] = date.fromisoformat(str(d["expiry"])[:10])
    return Intent(**d)


def intent_dict(i: Intent) -> dict:
    d = asdict(i)
    d["expiry"] = i.expiry.isoformat()
    return d


def max_loss(legs: list[Intent], stop: Optional[float], lot_qty: Optional[int] = None) -> Optional[float]:
    """Rupees at risk on the entry legs.
    * one option buy: the premium paid (price x qty);
    * a debit spread (buy + sell, same expiry and right): (long price - short price) x qty;
    * one futures leg with a stop: |entry - stop| x qty (before gaps);
    otherwise None (shown as unknown, never guessed)."""
    if len(legs) == 1:
        i = legs[0]
        if i.product == "options" and i.action == "buy":
            return round(i.price * i.qty, 2)
        if i.product == "futures" and stop is not None:
            return round(abs(i.price - stop) * i.qty, 2)
        return None
    if len(legs) == 2 and all(i.product == "options" for i in legs):
        b = [i for i in legs if i.action == "buy"]
        s = [i for i in legs if i.action == "sell"]
        if len(b) == 1 and len(s) == 1 and b[0].right == s[0].right and b[0].expiry == s[0].expiry \
                and b[0].qty == s[0].qty:
            return round(max(b[0].price - s[0].price, 0.0) * b[0].qty, 2)
    return None


class Store:
    def __init__(self, path: Path = PATH, clock: Callable[[], datetime] = now_ist):
        self.path, self.clock = path, clock

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, d: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.path)

    # ── drafting (code only) ────────────────────────────────────────────────

    def draft(self, legs: list[Intent], *, symbol: str, why: str, strategy: str, ref_price: float,
              valid_until: datetime, stop: Optional[float] = None, target: Optional[float] = None,
              max_move_pct: float = DEFAULT_MAX_MOVE_PCT, context: Optional[dict] = None) -> dict:
        if not legs or any(i.purpose != "entry" for i in legs):
            raise ValueError("a ticket is entry legs only; exits are placed by the position manager")
        tid = uuid.uuid4().hex[:10]
        t = dict(id=tid, created=self.clock().isoformat(timespec="seconds"), status="pending",
                 symbol=symbol, strategy=strategy, why=why, ref_price=float(ref_price),
                 stop=stop, target=target, valid_until=valid_until.isoformat(timespec="minutes"),
                 max_move_pct=float(max_move_pct), legs=[intent_dict(i) for i in legs],
                 max_loss=max_loss(legs, stop), context=context or {}, results=[])
        d = self._load()
        d[tid] = t
        self._save(d)
        return t

    # ── reading ─────────────────────────────────────────────────────────────

    def stale_reason(self, t: dict, price: Optional[float] = None) -> Optional[str]:
        if self.clock() > datetime.fromisoformat(t["valid_until"]):
            return f"expired at {t['valid_until'][11:16]} IST"
        if price is not None and t.get("ref_price"):
            move = abs(price / t["ref_price"] - 1) * 100
            if move > t["max_move_pct"]:
                return f"price moved {move:.1f}% since the draft (limit {t['max_move_pct']:g}%)"
        return None

    def all(self) -> list[dict]:
        """Every ticket, newest first; pending ones past their time are marked expired."""
        d, changed = self._load(), False
        for t in d.values():
            if t["status"] == "pending" and self.stale_reason(t):
                t["status"], changed = "expired", True
        if changed:
            self._save(d)
        return sorted(d.values(), key=lambda t: t["created"], reverse=True)

    def get(self, tid: str) -> Optional[dict]:
        return self._load().get(tid)

    # ── the user's decisions ────────────────────────────────────────────────

    def reject(self, tid: str, by: str = "dashboard") -> dict:
        d = self._load()
        t = d.get(tid)
        if t is None:
            raise KeyError(tid)
        if t["status"] != "pending":
            raise ValueError(f"ticket is {t['status']}, not pending")
        t.update(status="rejected", decided=self.clock().isoformat(timespec="seconds"), decided_by=by)
        self._save(d)
        return t

    def release(self, tid: str, gateway, *, qty_scale: Optional[float] = None, price: Optional[float] = None,
                by: str = "dashboard") -> dict:
        """Send the ticket's legs through the gateway (checks + journal). `qty_scale` in (0, 1]
        lowers every leg's quantity by the same factor, rounded down to whole lots; never raises.
        `price`: the underlying's price now, for the staleness check (None: time only)."""
        d = self._load()
        t = d.get(tid)
        if t is None:
            raise KeyError(tid)
        if t["status"] != "pending":
            raise ValueError(f"ticket is {t['status']}, not pending")
        why = self.stale_reason(t, price)
        if why:
            t["status"] = "expired"
            self._save(d)
            raise ValueError(why)
        legs = [intent_from(x) for x in t["legs"]]
        if qty_scale is not None:
            if not (0 < qty_scale <= 1):
                raise ValueError("quantity can only be lowered")
            out = []
            for i in legs:
                lot = max(int(gateway.lot(i.code)), 1)
                q = int(i.qty * qty_scale) // lot * lot
                if q <= 0:
                    raise ValueError("that is less than one lot")
                out.append(Intent(**{**intent_dict(i), "expiry": i.expiry, "qty": q}))
            legs = out
        t.update(status="releasing", decided=self.clock().isoformat(timespec="seconds"), decided_by=by)
        self._save(d)
        results, ok = [], True
        for i in legs:
            r = gateway.place(i)
            results.append(dict(leg=intent_dict(i), ok=r.ok, sent=r.sent, order_id=r.order_id, reasons=r.reasons))
            if not r.ok:
                ok = False
                break
        d = self._load()
        t = d[tid]
        t.update(results=results, status="released" if ok else "refused",
                 paper=not getattr(gateway, "live", False))
        self._save(d)
        return t
