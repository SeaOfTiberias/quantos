"""
QuantOS — Order checks: the deterministic gate every order passes
──────────────────────────────────────────────────────────────────
Pure: no broker, no clock, no file. core/orders/gateway.py builds an Intent
and a Context from live data and refuses the order if check() returns any
reason. A model may draft an Intent; it never gets past this without the
user's release (qorder) or a rule in code (the position manager).

What is refused, and why:

  kill switch       ~/.quantos/ORDERS_OFF exists
  account           anything but the allowed accounts -- never the son's (SEBI family rule)
  shape             qty not a positive multiple of the lot, too many lots, bad price, bad tick
  hours             an immediate order outside 09:15-15:30 IST (GTTs may rest any time)
  stale quote       an immediate order priced off a quote older than QUOTE_MAX_AGE_S
  price band        a limit far from the market: a buy above ask + band (overpaying) or
                    more than FAR_PCT below the bid (a typo), mirrored for a sell
  exits reduce      purpose exit/target/stop must be opposite the position and no larger
  no naked short    an option sell must close a long or be covered by a long of the same
                    stock, expiry and right (the short leg of a vertical)
  size              a futures entry's notional, or an option buy's premium, over its cap
  daily cap         more than MAX_ORDERS_PER_DAY orders sent today
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Optional

TICK = 0.05
QUOTE_MAX_AGE_S = 30
SESSION = (time(9, 15), time(15, 30))
PURPOSES = ("entry", "exit", "target", "stop")


@dataclass(frozen=True)
class Limits:
    accounts:          tuple = ("icici-spouse",)
    max_lots:          int = 4
    max_fut_notional:  float = 1_000_000.0    # rupees, futures entry
    max_opt_premium:   float = 50_000.0       # rupees, an option buy
    band_pct:          float = 0.01           # a marketable limit may sit this far through the touch
    far_pct:           float = 0.20           # a limit further than this from the touch is a typo
    max_orders_per_day: int = 40


@dataclass(frozen=True)
class Intent:
    account:  str
    product:  str              # futures | options
    code:     str              # ICICI stock code
    expiry:   date
    action:   str              # buy | sell
    qty:      int              # shares, positive
    price:    float            # limit price (for a stop: the limit after the trigger)
    purpose:  str              # entry | exit | target | stop
    right:    str = "others"   # call | put | others
    strike:   float = 0.0
    trigger:  Optional[float] = None   # stop-loss trigger
    gtt:      bool = False     # resting at the broker until triggered (no hours / quote check)

    @property
    def side(self) -> int:
        return 1 if self.action == "buy" else -1

    @property
    def instrument(self) -> tuple:
        return (self.code, self.expiry, self.right, float(self.strike))


@dataclass
class Context:
    now:            datetime                      # IST
    lot:            int
    positions:      dict = field(default_factory=dict)   # instrument tuple -> signed qty (shares)
    bid:            Optional[float] = None
    ask:            Optional[float] = None
    quote_age_s:    Optional[float] = None
    kill_switch:    bool = False
    orders_today:   int = 0


def _on_tick(x: float) -> bool:
    return abs(round(x / TICK) * TICK - x) < 1e-6


def round_tick(x: float, up: bool) -> float:
    """Round to the 0.05 tick, up for a buy limit and down for a sell."""
    n = round(x / TICK, 6)                     # 782.05 / 0.05 is 15640.999...; snap the float noise first
    return round((math.ceil(n) if up else math.floor(n)) * TICK, 2)


def check(i: Intent, c: Context, lim: Limits = Limits()) -> list[str]:
    """Every reason the order must not be sent; empty means it may go."""
    out: list[str] = []
    if c.kill_switch:
        out.append("kill switch is on (~/.quantos/ORDERS_OFF)")
    if i.account not in lim.accounts:
        out.append(f"account {i.account!r} is not allowed to trade")
    if i.action not in ("buy", "sell"):
        out.append(f"action {i.action!r}")
    if i.purpose not in PURPOSES:
        out.append(f"purpose {i.purpose!r}")
    if i.product not in ("futures", "options"):
        out.append(f"product {i.product!r}")
    if i.product == "options" and (i.right not in ("call", "put") or i.strike <= 0):
        out.append("an option needs right call/put and a strike")
    if c.lot <= 0 or i.qty <= 0 or i.qty % c.lot:
        out.append(f"qty {i.qty} is not a positive multiple of the lot {c.lot}")
    elif i.qty // c.lot > lim.max_lots:
        out.append(f"{i.qty // c.lot} lots is over the cap of {lim.max_lots}")
    if i.price <= 0 or not _on_tick(i.price):
        out.append(f"price {i.price} must be positive and on the {TICK} tick")
    if i.trigger is not None and (i.trigger <= 0 or not _on_tick(i.trigger)):
        out.append(f"trigger {i.trigger} must be positive and on the {TICK} tick")
    if c.orders_today >= lim.max_orders_per_day:
        out.append(f"{c.orders_today} orders sent today, the cap is {lim.max_orders_per_day}")
    if out:
        return out

    if not i.gtt:
        if not (SESSION[0] <= c.now.time() <= SESSION[1]) or c.now.weekday() >= 5:
            out.append(f"market closed at {c.now:%a %H:%M} IST")
        if c.bid is None or c.ask is None or c.bid <= 0 or c.ask <= 0:
            out.append("no live bid/ask")
        elif c.quote_age_s is None or c.quote_age_s > QUOTE_MAX_AGE_S:
            out.append(f"quote is {c.quote_age_s}s old (max {QUOTE_MAX_AGE_S}s)")
        elif i.trigger is None:
            if i.side > 0:
                if i.price > c.ask * (1 + lim.band_pct) + TICK:
                    out.append(f"buy limit {i.price} is more than {lim.band_pct:.0%} over the ask {c.ask}")
                if i.price < c.bid * (1 - lim.far_pct):
                    out.append(f"buy limit {i.price} is over {lim.far_pct:.0%} below the bid {c.bid} -- typo?")
            else:
                if i.price < c.bid * (1 - lim.band_pct) - TICK:
                    out.append(f"sell limit {i.price} is more than {lim.band_pct:.0%} under the bid {c.bid}")
                if i.price > c.ask * (1 + lim.far_pct):
                    out.append(f"sell limit {i.price} is over {lim.far_pct:.0%} above the ask {c.ask} -- typo?")

    held = c.positions.get(i.instrument, 0)
    if i.purpose != "entry":
        if held == 0 or (held > 0) == (i.side > 0):
            out.append(f"an {i.purpose} must reduce a position; held {held}")
        elif i.qty > abs(held):
            out.append(f"{i.purpose} qty {i.qty} is more than the {abs(held)} held")

    if i.product == "options" and i.side < 0 and not (held > 0 and i.qty <= held):
        cover = sum(q for (code, exp, right, _), q in c.positions.items()
                    if (code, exp, right) == (i.code, i.expiry, i.right) and q > 0)
        shorts = -sum(q for (code, exp, right, _), q in c.positions.items()
                      if (code, exp, right) == (i.code, i.expiry, i.right) and q < 0)
        if i.qty + shorts > cover:
            out.append(f"option sell of {i.qty} would be uncovered: long {cover} vs short {shorts} "
                       f"in {i.code} {i.expiry} {i.right}")

    if i.purpose == "entry":
        value = i.qty * i.price
        if i.product == "futures" and value > lim.max_fut_notional:
            out.append(f"futures notional ₹{value:,.0f} over the cap ₹{lim.max_fut_notional:,.0f}")
        if i.product == "options" and i.side > 0 and value > lim.max_opt_premium:
            out.append(f"option premium ₹{value:,.0f} over the cap ₹{lim.max_opt_premium:,.0f}")
    return out
