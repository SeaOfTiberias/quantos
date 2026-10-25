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
  - futures: a stop-out costs the stop distance plus 0.1% slippage; held
    overnight, their WORST case adds a gap of `gap_pct` of spot (the tail an
    option structure caps by construction and a stop order cannot)
  - "flat"  : the stock hasn't moved at all by the horizon -- pure time decay
              (added 2026-10-25: a slow large cap often just sits)
  - "event" : only when a results date falls inside the horizon (view.event_date,
              from core/ideas/events.py): the session after results the stock
              has gapped `event_gap_atr` ATRs AGAINST the view and every leg's
              IV has moved by `event_iv_shift` (the post-results crush). A
              daily-close stop can't help -- the gap is already through it.
Ranking metric: EV(p) / worst_case, where EV(p) = p*gain_target +
(1-p)*loss and `loss` is the WORST of the stop, stall, flat (and event) outcomes
(risk-averse) and worst_case is the most a lot can lose (premium or spread
max loss for options; stop distance + gap for futures). `be_p` is the hit
rate a structure needs just to break even: the lower, the more forgiving.

Strike rules (2026-10-25, from the HDFC Bank 670/600 review; R1, R2 and R6
need view.atr). A candidate that breaks one is still priced and shown, with
the reason in `flags`, but ranks after every candidate that breaks none:
  R1  a debit structure's long strike no more than 0.5 ATR out of the money
  R2  a debit spread's short strike at the target: not more than max(step,
      0.5 ATR) short of it (caps the trade early), nor more than max(step,
      1 ATR) beyond it (pays for a move the plan doesn't expect). A credit
      spread's short strike must sit at or beyond the stop.
  R3  financing: the short leg's bid >= 35% of the long leg's ask; a single
      long option has none
  R5  the family matches the thesis: debit / single / future express a
      "move", a credit spread expresses "hold" (won't cross the stop level)
  R6  no strike further than 3 ATR x sqrt(horizon / 10) from spot
R4 (score the no-move case) is the "flat" scenario above.
  R7  results inside the horizon and the event scenario is this candidate's
      worst outcome: the plan's stop doesn't set its loss, the results gap does

Each candidate also carries its legs' Black-Scholes deltas at today's spot and
each leg's own IV (`deltas`, per share, + = long the right; a future is +/-1),
for reading -- strikes are chosen by the ATR rules above, not by delta.
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


def bs_delta(spot: float, strike: float, t_years: float, vol: float, right: str, r: float = RISK_FREE) -> float:
    if t_years <= 0 or vol <= 0:
        itm = spot > strike if right == "CE" else spot < strike
        return (1.0 if right == "CE" else -1.0) if itm else 0.0
    d1 = (math.log(spot / strike) + (r + 0.5 * vol * vol) * t_years) / (vol * math.sqrt(t_years))
    return _ncdf(d1) if right == "CE" else _ncdf(d1) - 1.0


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
    risk_budget: Optional[float] = 10000.0   # None = research mode: no budget filter, 1 lot each
    overnight: bool = True    # held past today's close (futures gap risk applies)
    gap_pct: float = 3.5      # overnight gap through the stop. 213 F&O stocks, 52k nights to Oct 2026:
                              # |gap| p99 3.9%; a long's p99.5 adverse gap -3.5%, a short's p99 +3.1%
    vol_shift: float = 0.0    # e.g. -0.05 to model post-results IV crush
    atr: Optional[float] = None   # ATR(14) of the underlying; enables the strike rules
    thesis: str = "move"      # "move" (reaches the target) | "hold" (won't cross the stop level)
    event_date: Optional[date] = None   # results date inside the horizon (core/ideas/events.py)
    event_gap_atr: float = 1.5          # the gap against the view after results, in ATRs
    event_iv_shift: float = -0.05       # IV change after results (absolute; -0.05 = 5 vol points)


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
    flat: float = 0.0         # per lot, no move at all by the horizon
    event: Optional[float] = None   # per lot, the results-gap scenario (None = no event in the horizon)
    flags: list = field(default_factory=list)   # strike rules broken (empty = passes)
    fits: str = ""            # "move" | "hold": the thesis this family expresses
    deltas: list = field(default_factory=list)  # per leg, position-signed (short leg's delta negated)
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


def _score(c: Candidate, p: float, budget: Optional[float]) -> Candidate:
    span = c.gain_target - c.loss_stop
    c.be_p = round(-c.loss_stop / span, 3) if span > 0 else 1.0
    c.ev = p * c.gain_target + (1 - p) * c.loss_stop
    if not budget:
        c.lots = 1                                   # research mode: compare per lot, filter nothing
    else:
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
    ev_on = bool(view.event_date and view.atr and view.event_date >= chain.today
                 and (view.event_date - chain.today).days + 1 <= h_cal)
    ev_cal = (view.event_date - chain.today).days + 1 if ev_on else 0.0
    ev_spot = chain.spot - d * view.event_gap_atr * view.atr if ev_on else chain.spot

    def worst_of(*xs):
        return min(x for x in xs if x is not None)

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

    def leg_exit(key, spot, elapsed, sign, extra_vol=0.0):
        """Exit value of one leg per share, giving up half the spread."""
        expiry = key[0]
        el = min(elapsed, (expiry - chain.today).days)
        val = _option_value(chain, iv, key, spot, el, view.vol_shift + extra_vol)
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
        slip = chain.spot * 0.001                    # a normal stop-out: stop distance + slippage
        gap = chain.spot * view.gap_pct / 100 if view.overnight else slip
        loss = -(stop_dist + slip) * lot - q.half_spread * lot
        worst = (stop_dist + gap) * lot + q.half_spread * lot   # the tail: a gap through the stop
        stall = d * ((mid_spot + basis) - entry) * lot - q.half_spread * lot
        flat = d * ((chain.spot + basis) - entry) * lot - q.half_spread * lot
        ev = d * ((ev_spot + basis) - entry) * lot - q.half_spread * lot if ev_on else None
        out.append(Candidate(f"{'long' if d > 0 else 'short'} future", expiry, [("FUT", expiry)], entry,
                             gain, worst_of(loss, stall, flat, ev), worst, stall=stall, flat=flat, event=ev, note=f"stop {view.stop:g}, +{view.gap_pct if view.overnight else 0.1}% gap allowance"))

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
            fl = (leg_exit(key, chain.spot, h_cal, +1) - q.ask) * lot
            ev = (leg_exit(key, ev_spot, ev_cal, +1, view.event_iv_shift) - q.ask) * lot if ev_on else None
            out.append(Candidate(f"long {k:g} {right}", expiry, [(+1, expiry, k, right)], q.ask, g,
                                 worst_of(l, st, fl, ev, 0.0), q.ask * lot, stall=st, flat=fl, event=ev))
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
                def val(spot, el, xv=0.0):
                    return leg_exit(kl, spot, el, +1, xv) - leg_exit(ks, spot, el, -1, xv)
                g = (val(view.target, h_cal) - entry) * lot
                l = (val(view.stop, stop_cal) - entry) * lot
                st = (val(mid_spot, h_cal) - entry) * lot
                fl = (val(chain.spot, h_cal) - entry) * lot
                ev = (val(ev_spot, ev_cal, view.event_iv_shift) - entry) * lot if ev_on else None
                out.append(Candidate(f"{'bull call' if d > 0 else 'bear put'} {k1:g}/{k2:g}", expiry,
                                     [(+1, expiry, k1, right), (-1, expiry, k2, right)], entry, g,
                                     worst_of(l, st, fl, ev, 0.0), entry * lot, stall=st, flat=fl, event=ev))
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
                def val(spot, el, xv=0.0):
                    return leg_exit(kl, spot, el, +1, xv) - leg_exit(ks, spot, el, -1, xv)
                g = (val(view.target, h_cal) + credit) * lot
                l = (val(view.stop, stop_cal) + credit) * lot
                st = (val(mid_spot, h_cal) + credit) * lot
                fl = (val(chain.spot, h_cal) + credit) * lot
                ev = (val(ev_spot, ev_cal, view.event_iv_shift) + credit) * lot if ev_on else None
                out.append(Candidate(f"{'bull put' if d > 0 else 'bear call'} {k1:g}/{k2:g} (credit)", expiry,
                                     [(-1, expiry, k1, opp), (+1, expiry, k2, opp)], -credit, g,
                                     worst_of(l, st, fl, ev, 0.0), (width - credit) * lot, stall=st, flat=fl, event=ev))

    ranked = [_score(c, p, view.risk_budget) for c in out if c.worst_case > 0]
    ranked = [c for c in ranked if c.lots >= 1]           # must fit the risk budget at one lot
    for c in ranked:
        c.fits = "hold" if "credit" in c.name else "move"
        c.flags = rule_flags(c, chain, view)
        c.deltas = [float(d) if leg[0] == "FUT" else
                    round(leg[0] * bs_delta(chain.spot, leg[2], _t((leg[1] - chain.today).days), iv[leg[1:]], leg[3]), 2)
                    for leg in c.legs]
    # R7 is about the view's timing, not the structure, and can flag every candidate at once: rank on
    # the structural rules first so it never lifts a structure that breaks R1-R6 above one that doesn't.
    def broken(c):
        return (any(not f.startswith("R7") for f in c.flags), any(f.startswith("R7") for f in c.flags))
    return sorted(ranked, key=lambda c: (*broken(c), -c.score))


R1_OTM_ATR = 0.5
R2_SHORT_ATR, R2_FAR_ATR = 0.5, 1.0
R3_FINANCING = 0.35
R6_REACH_ATR = 3.0


def _step(chain: Chain, expiry: date, right: str, k: float) -> float:
    """The listed strike interval around k."""
    ks = sorted({key[1] for key in chain.options if key[0] == expiry and key[2] == right})
    gaps = [(a, b - a) for a, b in zip(ks, ks[1:]) if b > a]
    near = [g for a, g in gaps if a <= k <= a + g]
    return (near or [g for _, g in gaps] or [0.0])[0]


def rule_flags(c: Candidate, chain: Chain, view: View) -> list[str]:
    """The strike rules a candidate breaks (module docstring). Futures can only break R5; R1, R2's
    ATR tolerances and R6 need view.atr."""
    out: list[str] = []
    if c.event is not None and c.event < 0 and abs(c.event - c.loss_stop) < 1e-6:
        out.append(f"R7 results on {view.event_date:%d-%b} inside the horizon: the results gap "
                   f"({c.event:,.0f}), not the stop, sets this trade's loss")
    if c.fits != view.thesis:
        out.append(f"R5 a {c.fits!r} structure for a {view.thesis!r} thesis")
    opts = [leg for leg in c.legs if leg[0] != "FUT"]
    if not opts:
        return out
    d, spot, atr = view.direction, chain.spot, view.atr
    if atr:
        reach = R6_REACH_ATR * atr * math.sqrt(max(view.horizon_days, 1) / 10)
        for _, _, k, _ in opts:
            if abs(k - spot) > reach + 1e-9:
                out.append(f"R6 strike {k:g} is {abs(k - spot) / atr:.1f} ATR from spot (reach {reach / atr:.1f})")
    longs = [leg for leg in opts if leg[0] > 0]
    shorts = [leg for leg in opts if leg[0] < 0]
    if c.fits == "hold":
        k_short = shorts[0][2]
        if d * (k_short - view.stop) > 1e-9:
            out.append(f"R2 short strike {k_short:g} is inside the stop {view.stop:g}")
        return out
    _, e, k1, r = longs[0]
    if atr and d * (k1 - spot) / atr > R1_OTM_ATR + 1e-9:
        out.append(f"R1 long strike {k1:g} is {d * (k1 - spot) / atr:.1f} ATR out of the money (max {R1_OTM_ATR})")
    if not shorts:
        out.append("R3 no financing leg (a lone long option carries all the time decay)")
        return out
    k2 = shorts[0][2]
    step = _step(chain, e, r, k2)
    near = max(step, R2_SHORT_ATR * atr) if atr else step
    far = max(step, R2_FAR_ATR * atr) if atr else 2 * step
    beyond = d * (k2 - view.target)
    if beyond < -near - 1e-9:
        out.append(f"R2 short strike {k2:g} caps the trade {-beyond:g} before the target {view.target:g}")
    elif beyond > far + 1e-9:
        out.append(f"R2 short strike {k2:g} is {beyond:g} beyond the target {view.target:g} "
                   f"(pays for a move the plan doesn't expect)")
    ql, qs = chain.options[(e, k1, r)], chain.options[(e, k2, r)]
    fin = qs.bid / ql.ask if ql.ask > 0 else 0.0
    if fin < R3_FINANCING - 1e-9:
        out.append(f"R3 the short leg finances {fin:.0%} of the long (min {R3_FINANCING:.0%})")
    return out


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
