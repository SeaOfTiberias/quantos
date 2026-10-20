"""
QuantOS — Spread Watcher: option legs -> spreads
─────────────────────────────────────────────────
Pure. Turns ICICI Direct (Breeze) position rows into option legs, then
pairs a long and a short leg of the same stock, expiry and right with equal
quantity into one vertical spread. What can't be paired:

  - a short option with no matching long leg = UNCOVERED SHORT. Its loss is
    unlimited for a call (huge for a put), and it is exactly what was left
    by closing only the long leg of the TechM spread on 2026-10-19. The
    watcher warns about it.
  - a lone long option: not a spread; left alone here (max loss = premium).

Breeze rows, as seen on the 2026-10-19 trade book: action "Buy"/"Sell",
quantity as a string in shares (600), right "Call"/"Put", strike as a
string, expiry "27-Oct-2026", average price in `average_price` (positions)
or `average_cost` (trade book). The parser accepts all of those and a signed
quantity, so a field-name surprise on the first real position shows up as a
skipped row in the log, not a wrong spread.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Optional


@dataclass(frozen=True)
class Leg:
    stock_code: str       # ICICI's code, e.g. TECMAH
    expiry:     date
    right:      str       # "call" | "put"
    strike:     float
    qty:        int       # signed: + long, - short (shares)
    avg_price:  float

    @property
    def label(self) -> str:
        return f"{self.strike:g} {'CE' if self.right == 'call' else 'PE'}"


@dataclass(frozen=True)
class Spread:
    long:  Leg
    short: Leg

    @property
    def qty(self) -> int:
        return self.long.qty

    @property
    def key(self) -> str:
        return (f"{self.long.stock_code}|{self.long.expiry.isoformat()}|{self.long.right}|"
                f"{self.long.strike:g}|{self.short.strike:g}")

    @property
    def kind(self) -> str:
        """bull call / bear call / bear put / bull put, from which leg is long."""
        if self.long.right == "call":
            return "bull call" if self.long.strike < self.short.strike else "bear call"
        return "bear put" if self.long.strike > self.short.strike else "bull put"


def _parse_expiry(text: str) -> Optional[date]:
    text = (text or "").strip()
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:11] if fmt == "%d-%b-%Y" else text[:10], fmt).date()
        except ValueError:
            continue
    return None


def parse_leg(row: dict) -> Optional[Leg]:
    """One Breeze position row -> Leg, or None for anything that isn't an
    open stock/index option leg."""
    if str(row.get("product_type", "")).lower() not in ("options", "option"):
        return None
    right = str(row.get("right", "")).lower()
    right = {"c": "call", "p": "put"}.get(right, right)
    if right not in ("call", "put"):
        return None
    try:
        qty = int(float(row.get("quantity") or 0))
        strike = float(row.get("strike_price") or 0)
        price = float(row.get("average_price") or row.get("average_cost") or row.get("price") or 0)
    except (TypeError, ValueError):
        return None
    action = str(row.get("action", "")).lower()
    if action == "sell" and qty > 0:
        qty = -qty
    expiry = _parse_expiry(str(row.get("expiry_date", "")))
    if qty == 0 or strike <= 0 or expiry is None:
        return None
    return Leg(stock_code=str(row.get("stock_code", "")).upper(), expiry=expiry, right=right,
               strike=strike, qty=qty, avg_price=price)


def group_legs(legs: list[Leg]) -> tuple[list[Spread], list[Leg], list[Leg]]:
    """(spreads, uncovered shorts, lone longs). Within one stock/expiry/right,
    each short is paired with the nearest-strike long at least as large."""
    spreads: list[Spread] = []
    naked: list[Leg] = []
    lone: list[Leg] = []
    groups: dict[tuple, list[Leg]] = {}
    for leg in legs:
        groups.setdefault((leg.stock_code, leg.expiry, leg.right), []).append(leg)
    for group in groups.values():
        longs = [x for x in group if x.qty > 0]
        shorts = sorted((x for x in group if x.qty < 0), key=lambda x: x.strike)
        for s in shorts:
            match = [x for x in longs if x.qty >= -s.qty]
            if not match:                     # no long big enough: the whole short is uncovered
                naked.append(s)
                continue
            best = min(match, key=lambda x: abs(x.strike - s.strike))
            longs.remove(best)
            spreads.append(Spread(long=replace(best, qty=-s.qty), short=s))
            if best.qty > -s.qty:             # e.g. 2 lots long vs 1 short: the extra lot stays a lone long
                longs.append(replace(best, qty=best.qty + s.qty))
        lone.extend(longs)
    return spreads, naked, lone
