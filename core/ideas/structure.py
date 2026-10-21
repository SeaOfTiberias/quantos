"""
Structure selector: given a directional view (entry, target, stop, horizon)
and a live option chain, price every candidate way of expressing it --
futures with a stop, single options, debit and credit verticals, in each
listed expiry -- and rank them by expected rupees per rupee of worst-case
loss, sized to a risk budget.

The view is the prediction; this module only does the arithmetic of turning
a view into the most money for the risk. It does not know whether the view
is right. That is what the trade-idea log measures (core/ideas/log.py), and
its target-before-stop hit rate is the `p` fed back in here.

Scenario model (deliberately simple, stated so it can be argued with):
  - "target": the stock is at `target` after `horizon_days` trading days
  - "stop"  : the stock is at `stop` after half the horizon (stops tend to
              come sooner; for long options a later stop would be worse)
  - "stall" : the stock gets halfway to the target and sits there until the
              horizon -- the outcome that punishes time decay and near-expiry
              structures that need the move to arrive on time
  - each option leg is repriced with Black-Scholes at its OWN implied vol,
    solved from today's mid, held constant (no vol crush unless asked)
  - entry pays the ask on longs and receives the bid on shorts; exit gives up
    half of today's bid/ask spread on every leg again
  - futures lose more than the stop distance when held overnight: a gap of
    `gap_pct` of spot is added to their stop-scenario loss and worst case
Ranking metric: EV(p) / worst_case, where EV(p) = p*gain_target +
(1-p)*loss and `loss` is the WORSE of the stop and stall outcomes (risk-averse) and worst_case is the most a lot can lose (premium or spread
max loss for options; stop distance + gap for futures). `be_p` is the hit
rate a structure needs just to break even: the lower, the more forgiving.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

RISK_FREE = 0.065
TRADING_TO_CAL = 7 / 5


def _ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_price(spot: float, strike: float, t_years: float, vol: float, right: str, r: float = RISK_FREE) -> float:
    if t_years <= 0 or vol <= 0:
        return max(spot - strike, 0.0) if right == "CE" else max(strike - spot, 0.0)
    sq = vol * math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * vol * vol) * t_years) / sq
    d2 = d1 - sq
    if right == "CE":
        return spot * _ncdf(d1) - strike * math.exp(-r * t_years) * _ncdf(d2)
    return strike * math.exp(-r * t_years) * _ncdf(-d2) - spot * _ncdf(-d1)


def implied_vol(price: float, spot: float, strike: float, t_years: float, right: str) -> Optional[float]:
    """Bisection; None when the price is below intrinsic or otherwise not invertible."""
    intrinsic = max(spot - strike, 0.0) if right == "CE" else max(strike - spot, 0.0)
    if t_years <= 0 or price <= intrinsic + 1e-6:
        return None
    lo, hi = 0.01, 3.0
    if bs_price(spot, strike, t_years, hi, right) < price:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if bs_price(spot, strike, t_years, mid, right) > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


@dataclass
class Quote:
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def half_spread(self) -> float:
        return max(self.ask - self.bid, 0.0) / 2


@dataclass
class Chain:
    """Everything the selector needs about one underlying right now."""
    symbol: str
    spot: float
    lot: int
    today: date
    options: dict = field(default_factory=dict)     # (expiry: date, strike: float, right) -> Quote
    futures: dict = field(default_factory=dict)     # expiry: date -> Quote


@dataclass
class View:
    direction: int            # +1 bull, -1 bear
    target: float
    stop: float
    horizon_days: int         # trading days
    risk_budget: float = 10000.0
    overnight: bool = True    # held past today's close (futures gap risk applies)
    gap_pct: float = 2.0
    vol_shift: float = 0.0    # e.g. -0.05 to model post-results IV crush


@dataclass
class Candidate:
    name: str
    expiry: Optional[date]
    legs: list                # [(qty_sign, expiry, strike, right)] or [("FUT", expiry)]
    entry: float              # per share; + = paid, - = received
    gain_target: float        # per lot, rupees, after exit costs
    loss_stop: float          # per lot (negative): worse of stop and stall
    worst_case: float         # per lot, positive rupees
    stall: float = 0.0        # per lot, the stall outcome on its own
    be_p: float = 0.0
    lots: int = 0
    score: float = 0.0
    ev: float = 0.0
    note: str = ""


def _t(days_cal: float) -> float:
    return max(days_cal, 0.0) / 365.0


def _option_value(chain: Chain, iv: dict, key, spot: float, elapsed_cal: float, vol_shift: float) -> float:
    expiry, strike, right = key
    t = _t((expiry - chain.today).days - elapsed_cal)
    return bs_price(spot, strike, t, max(iv[key] + vol_shift, 0.01), right)


def _score(c: Candidate, p: float, budget: float) -> Candidate:
    span = c.gain_target - c.loss_stop
    c.be_p = round(-c.loss_stop / span, 3) if span > 0 else 1.0
    c.ev = p * c.gain_target + (1 - p) * c.loss_stop
    c.lots = int(budget // c.worst_case) if c.worst_case > 0 else 0
    c.score = c.ev / c.worst_case if c.worst_case > 0 else float("-inf")
    return c


def candidates(chain: Chain, view: View, p: float = 0.5, min_days_left: int = 2) -> list[Candidate]:
    """All priced candidates, best first.

    A structure must outlive the view: an expiry that falls inside the
    horizon would need the target to arrive before it expires, which is a
    different (much less likely) bet than the `p` the view is scored at.
    Debit structures priced under 5% of their width (or a single option
    under Rs 1) are dropped -- at that price the quote is usually stale and
    the "needs 2%" hit rate it implies is an artefact."""
    d, lot = view.direction, chain.lot
    h_cal = view.horizon_days * TRADING_TO_CAL
    min_days_left = max(min_days_left, math.ceil(h_cal) + 1)
    stop_cal = h_cal / 2
    mid_spot = (chain.spot + view.target) / 2
    out: list[Candidate] = []

    # Implied vol per listed option, from its mid.
    iv = {}
    for key, q in chain.options.items():
        if q.bid <= 0 or q.ask <= 0:
            continue
        expiry, strike, right = key
        v = implied_vol(q.mid, chain.spot, strike, _t((expiry - chain.today).days), right)
        if v:
            iv[key] = v

    def leg_exit(key, spot, elapsed, sign):
        """Exit value of one leg per share, giving up half the spread."""
        expiry = key[0]
        el = min(elapsed, (expiry - chain.today).days)
        val = _option_value(chain, iv, key, spot, el, view.vol_shift)
        hs = chain.options[key].half_spread
        return val - hs if sign > 0 else val + hs

    # Futures with a stop.
    for expiry, q in chain.futures.items():
        if (expiry - chain.today).days < min_days_left:
            continue
        basis = q.mid - chain.spot
        entry = q.ask if d > 0 else q.bid
        gain = d * ((view.target + basis) - entry) * lot - q.half_spread * lot
        stop_dist = abs(view.stop - chain.spot)
        gap = chain.spot * view.gap_pct / 100 if view.overnight else chain.spot * 0.001
        loss = -(stop_dist + gap) * lot - q.half_spread * lot
        stall = d * ((mid_spot + basis) - entry) * lot - q.half_spread * lot
        out.append(Candidate(f"{'long' if d > 0 else 'short'} future", expiry, [("FUT", expiry)], entry,
                             gain, min(loss, stall), -loss, stall=stall, note=f"stop {view.stop:g}, +{view.gap_pct if view.overnight else 0.1}% gap allowance"))

    expiries = sorted({k[0] for k in iv if (k[0] - chain.today).days >= min_days_left})
    right = "CE" if d > 0 else "PE"
    opp = "PE" if d > 0 else "CE"
    for expiry in expiries:
        strikes = sorted({k[1] for k in iv if k[0] == expiry and k[2] == right})
        ostrikes = sorted({k[1] for k in iv if k[0] == expiry and k[2] == opp})
        # Single long option.
        for k in strikes:
            key = (expiry, k, right)
            q = chain.options[key]
            if q.ask < 1.0:
                continue
            g = (leg_exit(key, view.target, h_cal, +1) - q.ask) * lot
            l = (leg_exit(key, view.stop, stop_cal, +1) - q.ask) * lot
            st = (leg_exit(key, mid_spot, h_cal, +1) - q.ask) * lot
            out.append(Candidate(f"long {k:g} {right}", expiry, [(+1, expiry, k, right)], q.ask, g, min(l, st, 0.0),
                                 q.ask * lot, stall=st))
        # Debit vertical: long k1, short k2 further in the view's direction.
        for k1 in strikes:
            for k2 in strikes:
                if d * (k2 - k1) <= 0:
                    continue
                kl, ks = (expiry, k1, right), (expiry, k2, right)
                entry = chain.options[kl].ask - chain.options[ks].bid
                width = abs(k2 - k1)
                if entry < 0.05 * width or entry >= width:
                    continue
                def val(spot, el):
                    return leg_exit(kl, spot, el, +1) - leg_exit(ks, spot, el, -1)
                g = (val(view.target, h_cal) - entry) * lot
                l = (val(view.stop, stop_cal) - entry) * lot
                st = (val(mid_spot, h_cal) - entry) * lot
                out.append(Candidate(f"{'bull call' if d > 0 else 'bear put'} {k1:g}/{k2:g}", expiry,
                                     [(+1, expiry, k1, right), (-1, expiry, k2, right)], entry, g, min(l, st, 0.0),
                                     entry * lot, stall=st))
        # Credit vertical on the other side: short k1, long k2 further away from the view.
        for k1 in ostrikes:
            for k2 in ostrikes:
                if d * (k1 - k2) <= 0:
                    continue
                ks, kl = (expiry, k1, opp), (expiry, k2, opp)
                credit = chain.options[ks].bid - chain.options[kl].ask
                width = abs(k1 - k2)
                if credit < 0.05 * width or credit >= width:
                    continue
                def val(spot, el):
                    return leg_exit(kl, spot, el, +1) - leg_exit(ks, spot, el, -1)
                g = (val(view.target, h_cal) + credit) * lot
                l = (val(view.stop, stop_cal) + credit) * lot
                st = (val(mid_spot, h_cal) + credit) * lot
                out.append(Candidate(f"{'bull put' if d > 0 else 'bear call'} {k1:g}/{k2:g} (credit)", expiry,
                                     [(-1, expiry, k1, opp), (+1, expiry, k2, opp)], -credit, g, min(l, st, 0.0),
                                     (width - credit) * lot, stall=st))

    ranked = [_score(c, p, view.risk_budget) for c in out if c.worst_case > 0]
    ranked = [c for c in ranked if c.lots >= 1]           # must fit the risk budget at one lot
    return sorted(ranked, key=lambda c: c.score, reverse=True)


def best_by_family(ranked: list[Candidate]) -> list[Candidate]:
    """The top candidate of each family (future / single / debit / credit),
    so a report shows the trade-off instead of 40 near-duplicates."""
    seen, out = set(), []
    for c in ranked:
        fam = ("future" if "future" in c.name else "credit" if "credit" in c.name
               else "single" if c.name.startswith("long ") else "debit")
        if fam not in seen:
            seen.add(fam)
            out.append(c)
    return out
