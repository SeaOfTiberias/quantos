"""
QuantOS — F&O Screener: debit-spread alternatives for each pick
────────────────────────────────────────────────────────────────
For every call pick, a bull call spread; for every put pick, a bear put
spread. Both are DEBIT spreads, so the most a lot can lose is what was paid.
The long leg is the screener's own contract (core/fno_screener/screener.py
pick_contract); only the short leg varies.

Rules, not a model, choose the strike pairs. The short strike is the listed
strike nearest to spot +/- k x the expected move to expiry, k in
WIDTH_MULTIPLES, where expected move = spot x IV x sqrt(dte / 365) and IV is
the long leg's implied vol. So "near / mid / far" mean the same thing in
volatility terms for a quiet stock and a wild one.

The PRIMARY idea is HORIZON_LABEL ("h5"), sized to the holding period, not
the contract: long the at-the-money strike, short the strike nearest to
spot +/- 1 x the move expected over HORIZON_SESSIONS (spot x IV x
sqrt(HORIZON_CALENDAR_DAYS / 365); IV is per calendar day, as everywhere
here). An expected move to a 30-day expiry put the "mid" short strike ~8%
away (TCS 2500/2700 on 22 Oct 2026) -- too far to pay for a 1-5 day hold.
near / mid / far stay in the log so the comparison keeps running.

Pricing:
  - "quotes": both legs have a two-sided Fyers quote. Buy the long leg at
    the ask, sell the short at the bid, the way a real order fills.
  - "close": no usable quote, so bhavcopy closes are used and the bid-ask
    cost is unknown. Shown as such, never as a quoted price.
Round-trip bid-ask cost = 2 x (real debit - mid debit), as a % of the real
debit. Candidate 23 found narrow stock-option spreads lose to exactly this
cost (docs/SURGE_SPREAD_STAGE2_RESULTS.md), so each idea carries it and is
flagged above COST_FLAG_PCT.

Day-5 scenario: the spread's and the single option's P&L if the stock sits
at the short strike after SCENARIO_SESSIONS sessions, Black-Scholes with the
long leg's IV on both legs (no skew) and nothing else changed. It answers
"how much of a quick move does the spread actually keep", which matters
here: the screener holds 1-5 days, and a 30-day spread's legs offset each
other until close to expiry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from core.fno_screener.bhavcopy import FnoDay
from core.options.greeks import compute_greeks
from core.options.models import OptionType

WIDTH_MULTIPLES = (("near", 0.5), ("mid", 1.0), ("far", 1.5))
HORIZON_LABEL = "h5"
HORIZON_SESSIONS = 5
HORIZON_CALENDAR_DAYS = 7     # 5 sessions ~ one calendar week
COST_FLAG_PCT = 10.0
FALLBACK_IV = 0.30            # only when the long leg's IV couldn't be solved; marked iv_assumed
SCENARIO_SESSIONS = 5
SCENARIO_CALENDAR_DAYS = 7    # 5 sessions ~ one calendar week


@dataclass(frozen=True)
class SpreadIdea:
    label:          str                 # h5 | near | mid | far
    long_strike:    float
    short_strike:   float
    width:          float
    debit:          float               # per share, as priced (quotes or close)
    debit_close:    float               # per share at bhavcopy closes, what outcomes are measured from
    priced_from:    str                 # quotes | close
    max_loss:       float               # per lot, rupees
    max_profit:     float               # per lot, rupees
    reward_risk:    float
    breakeven:      float
    breakeven_move_pct: float           # signed % move from spot to breakeven at expiry
    target_move_pct:    float           # signed % move from spot to the short strike
    cost_pct:       Optional[float]     # round-trip bid-ask as % of debit; None when priced from close
    cost_flag:      bool
    day5_spread_pnl: float              # per lot, stock at short strike after 5 sessions
    day5_single_pnl: float              # per lot, the single long option in the same scenario


@dataclass(frozen=True)
class SpreadSet:
    kind:           str                 # bull_call | bear_put
    symbol:         str
    expiry:         date
    spot:           float
    lot:            int
    dte:            int
    iv:             float
    iv_assumed:     bool
    expected_move:  float               # rupees, 1 sd to expiry
    ideas:          list[SpreadIdea] = field(default_factory=list)


def _bs(spot: float, strike: float, days: int, iv: float, side: OptionType) -> float:
    return compute_greeks(spot, strike, days, iv, side).theoretical_price


def _two_sided(q: Optional[tuple[float, float]]) -> bool:
    return q is not None and q[0] > 0 and q[1] > 0 and q[1] >= q[0]


def build_spreads(day: FnoDay, symbol: str, side: OptionType, expiry: date, long_strike: float,
                  dte: int, iv: Optional[float],
                  quotes: Optional[dict[float, tuple[float, float]]] = None) -> Optional[SpreadSet]:
    """Pure. `quotes` maps strike -> (bid, ask) for this symbol/expiry/side.
    None when the long leg isn't on the bhavcopy or there's no spot."""
    spot = day.spot.get(symbol)
    chain = {q.strike: q for q in day.options.get(symbol, [])
             if q.expiry == expiry and q.option_type == side and q.close > 0}
    long_q = chain.get(long_strike)
    if not spot or long_q is None or dte <= 0:
        return None
    quotes = quotes or {}
    iv_assumed = iv is None or iv <= 0
    vol = FALLBACK_IV if iv_assumed else iv
    em = spot * vol * math.sqrt(dte / 365)
    sign = 1 if side == OptionType.CALL else -1
    out = SpreadSet(kind="bull_call" if side == OptionType.CALL else "bear_put", symbol=symbol,
                    expiry=expiry, spot=spot, lot=long_q.lot_size, dte=dte, iv=round(vol, 4), iv_assumed=iv_assumed,
                    expected_move=round(em, 2))

    def beyond(k_long: float) -> list[float]:
        return sorted((k for k in chain if (k - k_long) * sign > 0), key=lambda k: k * sign)

    def nearest(strikes: list[float], target: float) -> Optional[float]:
        return min(strikes, key=lambda k: abs(k - target)) if strikes else None

    # Primary: ATM long, short at the holding-period expected move.
    atm = nearest(list(chain), spot)
    short_h = nearest(beyond(atm), spot + sign * spot * vol * math.sqrt(HORIZON_CALENDAR_DAYS / 365))
    if short_h is not None:
        idea = _idea(HORIZON_LABEL, chain[atm], chain[short_h], spot, sign, dte, vol, quotes)
        if idea:
            out.ideas.append(idea)

    used: set[float] = set()
    for label, k in WIDTH_MULTIPLES:
        short_strike = nearest(beyond(long_strike), spot + sign * k * em)
        if short_strike is None or short_strike in used:
            continue
        used.add(short_strike)
        idea = _idea(label, long_q, chain[short_strike], spot, sign, dte, vol, quotes)
        if idea:
            out.ideas.append(idea)
    return out


def _idea(label: str, long_q, short_q, spot: float, sign: int, dte: int, vol: float,
          quotes: dict[float, tuple[float, float]]) -> Optional[SpreadIdea]:
    long_strike, short_strike, lot = long_q.strike, short_q.strike, long_q.lot_size
    side = long_q.option_type
    ql, qs = quotes.get(long_strike), quotes.get(short_strike)
    quoted = _two_sided(ql) and _two_sided(qs)
    debit_close = long_q.close - short_q.close
    if quoted:
        debit = ql[1] - qs[0]
        mid = (ql[0] + ql[1]) / 2 - (qs[0] + qs[1]) / 2
    else:
        debit, mid = debit_close, None
    width = abs(short_strike - long_strike)
    if not 0 < debit < width:
        return None
    cost_pct = round(2 * (debit - mid) / debit * 100, 1) if quoted else None
    breakeven = long_strike + sign * debit
    days5 = max(dte - SCENARIO_CALENDAR_DAYS, 0)
    spread5 = _bs(short_strike, long_strike, days5, vol, side) - _bs(short_strike, short_strike, days5, vol, side)
    single_entry = ql[1] if _two_sided(ql) else long_q.close
    single5 = _bs(short_strike, long_strike, days5, vol, side)
    return SpreadIdea(
        label=label, long_strike=long_strike, short_strike=short_strike, width=width,
        debit=round(debit, 2), debit_close=round(debit_close, 2),
        priced_from="quotes" if quoted else "close",
        max_loss=round(debit * lot), max_profit=round((width - debit) * lot),
        reward_risk=round((width - debit) / debit, 2),
        breakeven=round(breakeven, 2),
        breakeven_move_pct=round((breakeven / spot - 1) * 100, 1),
        target_move_pct=round((short_strike / spot - 1) * 100, 1),
        cost_pct=cost_pct, cost_flag=cost_pct is not None and cost_pct > COST_FLAG_PCT,
        day5_spread_pnl=round((spread5 - debit) * lot),
        day5_single_pnl=round((single5 - single_entry) * lot),
    )


def spread_line(s: SpreadSet) -> Optional[str]:
    """One Telegram line: the h5 idea, else mid, else the first one."""
    if not s.ideas:
        return None
    i = next((x for lab in (HORIZON_LABEL, "mid") for x in s.ideas if x.label == lab), s.ideas[0])
    verb = "bull call" if s.kind == "bull_call" else "bear put"
    sized = f" ({HORIZON_SESSIONS}-day move)" if i.label == HORIZON_LABEL else f" ({i.label})"
    cost = ("bid-ask n/a (close prices)" if i.cost_pct is None
            else f"bid-ask {i.cost_pct:g}% of debit" + (" ⚠" if i.cost_flag else ""))
    return (f"   ➜ {verb} {i.long_strike:g}/{i.short_strike:g}{sized} · risk ₹{i.max_loss:,.0f} → "
            f"max ₹{i.max_profit:,.0f} (R:R {i.reward_risk:g}) · BE {i.breakeven:g} "
            f"({i.breakeven_move_pct:+.1f}%) · {cost}")
