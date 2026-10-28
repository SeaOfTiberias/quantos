"""
QuantOS — Position Manager executor: the plan's exits as real orders
─────────────────────────────────────────────────────────────────────
Runs only when the VM config says `position_manager: {orders: auto}`; with
`alerts` (the default) the manager stays alerts only. Orders go through
core/orders/gateway.py, so every one is checked and journalled, and the
`orders: {live: false}` switch or ~/.quantos/ORDERS_OFF stop them.

What it does with a Plan (core/position_manager/rules.py):

  position appears / levels change   rest a GTT OCO at the broker: the TARGET as a
                                     limit at the target, the EMERGENCY stop as a
                                     stop-limit 1% through the emergency level.
                                     It survives the night, so a gap-up through
                                     the target fills at the open (the TCS lesson).
  first pass each day                confirm the GTT is still in the broker's book;
                                     re-place it if it's gone and the position isn't
  no GTT on record                   adopt one already resting at the broker for the same
                                     contract, side and qty (placed by hand with qorder,
                                     the 27-Oct SUPIND case) instead of placing a second:
                                     two OCOs would buy twice at the target and flip the position.
                                     If the book can't be read, nothing is placed or cancelled.
  profit stop ratchets (TRAIL)       cancel the OCO and rest it again with its stop leg at the
                                     profit stop, so ICICI holds the locked gain even if the VM
                                     is down. A cancel that fails leaves the old OCO and places
                                     nothing (never two). No OCO at all -> the code exits on touch.
  15:20 CLOSE / TIME / expiry       cancel the GTT, then exit at the touch with a
                                     re-priced marketable limit (gateway.work_exit)
  position gone                      cancel the GTT (harmless if it already fired)

The daily-close stop stays a 15:20 decision in code, not a resting order:
a resting stop would fire on an intraday dip, which is what the tested
rule deliberately ignores.
"""

from __future__ import annotations

from typing import Callable, Optional

from core.orders.checks import Intent, round_tick
from core.position_manager.rules import Plan

STOP_SLIP = 0.01          # the emergency stop's limit sits this far beyond its trigger


def stop_level(p: Plan) -> Optional[float]:
    """The resting stop: the profit stop once it's set (always the tighter), else the emergency."""
    return p.trail if getattr(p, "trail", None) is not None else p.emergency


def oco_legs(p: Plan, account: str) -> Optional[tuple[Intent, Intent]]:
    stop = stop_level(p)
    if p.target is None or stop is None:
        return None
    act = "sell" if p.side > 0 else "buy"
    up = p.side < 0                                   # a buy-to-close rounds its prices up
    base = dict(account=account, product="futures", code=p.code, expiry=p.expiry, action=act,
                qty=abs(p.qty), gtt=True)
    tgt = round_tick(p.target, up=up)
    trig = round_tick(stop, up=up)
    lim = round_tick(stop * (1 - p.side * STOP_SLIP), up=up)
    return (Intent(price=tgt, purpose="target", trigger=tgt, **base),
            Intent(price=lim, purpose="stop", trigger=trig, **base))


class Executor:
    def __init__(self, gateway, notify: Callable[[str], None], account: str = "icici-spouse"):
        self.gw, self.notify, self.account = gateway, notify, account
        self.verified: set[str] = set()               # plan keys whose GTT was checked today

    def rest(self, key: str, p: Plan, positions: Optional[dict] = None) -> None:
        """Place (or replace) the plan's resting OCO; adopt one already at the broker."""
        if getattr(p, "gtt_id", None):
            c = self.gw.cancel_gtt(p.gtt_id)
            if not c.ok:                              # placing anyway could leave two OCOs at the broker
                self.notify(f"❗ {p.symbol}: couldn't cancel the resting OCO {p.gtt_id} ({'; '.join(c.reasons)}), "
                            "so it stays as it is and I placed no new one. Its stop is NOT the new level.")
                return
            p.gtt_id = None
        else:
            try:
                found = self.gw.find_gtt(p.code, p.expiry, "sell" if p.side > 0 else "buy", abs(p.qty))
            except Exception as e:
                self.notify(f"❗ {p.symbol}: couldn't read the broker's GTT book ({e}), so I placed no OCO "
                            "(it could double one already there). Check the GTT book and place target/stop by hand.")
                return
            if found:
                p.gtt_id = found
                self.verified.add(key)
                self.notify(f"📌 {p.symbol}: adopted the resting OCO {found} already at the broker -- not placing "
                            "another. Its levels are whatever it was placed with; I cancel it when I exit.")
                return
        legs = oco_legs(p, self.account)
        if legs is None:
            self.notify(f"⚠️ {p.symbol}: no target/emergency level, so no resting order -- alerts only for this one.")
            return
        r = self.gw.place_oco(*legs, positions=positions)
        if r.ok:
            p.gtt_id = r.order_id
            self.verified.add(key)
            kind = "profit stop" if getattr(p, "trail", None) is not None else "emergency stop"
            self.notify(f"📌 {p.symbol}: resting OCO {'placed' if r.sent else '(paper)'} -- target {legs[0].price:g}, "
                        f"{kind} {legs[1].trigger:g} (limit {legs[1].price:g}). GTT {r.order_id}.")
        else:
            self.notify(f"❗ {p.symbol}: resting OCO NOT placed -- {'; '.join(r.reasons)}. Place target/stop by hand.")

    def daily_check(self, key: str, p: Plan) -> None:
        """Once a day per position: no OCO yet (opened before auto was on) -> place one;
        one recorded but missing from the broker's book -> re-place it."""
        if key in self.verified:
            return
        self.verified.add(key)
        if not getattr(p, "gtt_id", None):
            self.rest(key, p)
            return
        if str(p.gtt_id).startswith("paper"):
            return
        try:
            held = self.gw.verify_gtt(p.gtt_id)
        except Exception as e:
            self.notify(f"❗ {p.symbol}: couldn't read the broker's GTT book ({e}); leaving OCO {p.gtt_id} as it is.")
            return
        if held is None:
            self.notify(f"🔁 {p.symbol}: the resting OCO {p.gtt_id} isn't in the broker's GTT book -- re-placing it.")
            p.gtt_id = None
            self.rest(key, p)

    def exit_now(self, p: Plan, why: str) -> bool:
        if getattr(p, "gtt_id", None):
            self.gw.cancel_gtt(p.gtt_id)
            p.gtt_id = None
        ex = Intent(account=self.account, product="futures", code=p.code, expiry=p.expiry,
                    action="sell" if p.side > 0 else "buy", qty=abs(p.qty),
                    price=p.last_price or p.entry, purpose="exit")
        r = self.gw.work_exit(ex)
        if r.ok:
            self.notify(f"✅ {p.symbol}: {why} -- exit {'sent and filled' if r.sent else '(paper)'}, order {r.order_id}.")
        else:
            self.notify(f"🚨 {p.symbol}: {why} -- EXIT NOT DONE ({'; '.join(r.reasons)}). Close it by hand before 15:30.")
        return r.ok

    def gone(self, p: Plan) -> None:
        if getattr(p, "gtt_id", None):
            self.gw.cancel_gtt(p.gtt_id)
