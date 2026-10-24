"""
QuantOS — Spread Watcher: exit rules for a vertical option spread
──────────────────────────────────────────────────────────────────
Pure, no I/O. scripts/run_spread_watcher.py feeds it the stock price and the
spread's live close-out value (long leg at the bid, short leg at the ask --
what closing both legs right now would actually pay) and turns the returned
events into Telegram messages. Stage 1: alerts only, never orders.

Rules (docs/TERMINAL_ARCHITECTURE.md §7c; starting values are guesses, to be
re-tuned on the user's own spreads once there are 20-30):

  A. Stock-price trail. Once the spread is in profit, track the stock's
     best price since (high for a bullish spread, low for a bearish one);
     the stop sits `stock_trail_pct` behind it. A per-trade level set by the
     user replaces the trail. Crossing it -> CLOSE.
     A per-trade DAILY-CLOSE level also replaces the trail: checked once a
     day at `close_check_at`, beyond it -> CLOSE, else a HOLD note. Added
     2026-10-23: a 0.8% touch trail on a stock with a ~2.3% daily range is
     noise (the TCS 22 Oct lesson); a year of breakout exits favoured a
     daily-close stop with a wider touch-level emergency.
  - Target: a per-trade stock-price target, on touch -> CLOSE (take it).
  B. Profit give-back. Once the P&L has reached `giveback_arm_pct` % of
     max profit, falling to `giveback_keep` x the best P&L seen -> CLOSE.
     (TechM 1740/1800 on 2026-10-19: best ~+Rs3,300 = 16% of max, so at
     15% this arms and fires at ~+Rs1,650; the trade was instead closed at
     about -Rs1,260. At the original 20% it would not have armed.)
  - Breakeven: after being in profit, the stock crossing back through the
    expiry breakeven -> warning (re-armed once back on the profit side).
  - Near max: P&L at `near_max_pct` % of max profit -> "little left to gain".
  - Exit day: `exit_sessions_before_expiry` weekday sessions before expiry,
    from 09:30 -> CLOSE (expiry-day spreads and settlement are avoidable risk).

Each alert fires once per spread (breakeven re-arms); the state persists
across restarts, so the peak P&L and the stock's best price survive one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import date, time
from typing import Optional

from core.spread_watcher.legs import Spread


@dataclass(frozen=True)
class SpreadRules:
    stock_trail_pct:  float = 0.8
    giveback_arm_pct: float = 15.0      # 20 -> 15 on 2026-10-20 (user), so a TechM-sized peak arms it
    giveback_keep:    float = 0.5
    near_max_pct:     float = 90.0
    exit_sessions_before_expiry: int = 1
    exit_day_from:    str = "09:30"
    close_check_at:   str = "15:20"

    @classmethod
    def from_config(cls, cfg: Optional[dict]) -> "SpreadRules":
        cfg = cfg or {}
        return cls(**{f.name: type(f.default)(cfg[f.name]) for f in fields(cls) if f.name in cfg})


def _intrinsic(right: str, strike: float, spot: float) -> float:
    return max(spot - strike, 0.0) if right == "call" else max(strike - spot, 0.0)


@dataclass(frozen=True)
class Payoff:
    entry:      float   # per share: + debit paid, - credit received
    max_profit: float   # rupees, whole position
    max_loss:   float   # rupees, positive
    breakeven:  float   # stock price at expiry
    bullish:    bool


def payoff(sp: Spread) -> Payoff:
    """Expiry payoff of the vertical. Value per share v(S) = long intrinsic -
    short intrinsic: flat below the lower strike and above the upper one,
    linear between."""
    lo, hi = sorted((sp.long.strike, sp.short.strike))
    right = sp.long.right

    def v(s: float) -> float:
        return _intrinsic(right, sp.long.strike, s) - _intrinsic(right, sp.short.strike, s)

    v_lo, v_hi = v(lo), v(hi)
    entry = sp.long.avg_price - sp.short.avg_price
    q = sp.qty
    breakeven = lo + (entry - v_lo) / (v_hi - v_lo) * (hi - lo) if v_hi != v_lo else lo
    return Payoff(entry=round(entry, 4), max_profit=round((max(v_lo, v_hi) - entry) * q, 2),
                  max_loss=round((entry - min(v_lo, v_hi)) * q, 2), breakeven=round(breakeven, 2),
                  bullish=v_hi > v_lo)


@dataclass
class SpreadState:
    key:        str
    entry:      float
    qty:        int
    max_profit: float
    max_loss:   float
    breakeven:  float
    bullish:    bool
    expiry:     str                       # ISO date
    level:      Optional[float] = None    # user's own stock-price exit level, on touch (replaces trail A)
    close_level: Optional[float] = None   # user's own stock-price stop on the DAILY close (replaces trail A)
    target:     Optional[float] = None    # user's own stock-price target, on touch
    peak_pnl:   float = 0.0
    best_spot:  Optional[float] = None    # since first in profit
    stock_stop: Optional[float] = None
    sent:       list = field(default_factory=list)   # alert kinds already sent
    be_armed:   bool = False
    last_pnl:   Optional[float] = None
    last_spot:  Optional[float] = None
    last_value: Optional[float] = None
    close_reason: Optional[str] = None    # a CLOSE the executor is acting on (orders: auto)
    close_attempts: int = 0

    @classmethod
    def open(cls, sp: Spread) -> "SpreadState":
        p = payoff(sp)
        return cls(key=sp.key, entry=p.entry, qty=sp.qty, max_profit=p.max_profit, max_loss=p.max_loss,
                   breakeven=p.breakeven, bullish=p.bullish, expiry=sp.long.expiry.isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SpreadState":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class Event:
    kind:   str      # trail_stock | giveback | exit_day | breakeven | near_max | trail_armed
    close:  bool     # an instruction to close, vs a heads-up
    detail: str


def _weekdays_after(today: date, end: date) -> int:
    from datetime import timedelta
    n, d = 0, today
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def evaluate(st: SpreadState, spot: float, value: float, today: date, now: time,
             rules: SpreadRules) -> list[Event]:
    """One observation: `value` = close-out value per share right now."""
    if not spot or spot <= 0 or value is None:
        return []
    pnl = round((value - st.entry) * st.qty, 2)
    st.last_pnl, st.last_spot, st.last_value = pnl, spot, value
    sign = 1 if st.bullish else -1
    out: list[Event] = []

    def fire(kind: str, close: bool, detail: str) -> None:
        if kind not in st.sent:
            st.sent.append(kind)
            out.append(Event(kind, close, detail))

    # A. stock-price trail (or the user's own level)
    if st.level:
        st.stock_stop = st.level
    elif st.close_level:
        pass                                  # the daily-close check below is the stop
    elif pnl > 0 or st.best_spot is not None:
        if st.best_spot is None:
            fire("trail_armed", False, f"in profit: stock trail armed {rules.stock_trail_pct:g}% behind the best price")
        st.best_spot = spot if st.best_spot is None else (max(st.best_spot, spot) if st.bullish
                                                          else min(st.best_spot, spot))
        st.stock_stop = round(st.best_spot * (1 - sign * rules.stock_trail_pct / 100), 2)
    if st.stock_stop and (spot - st.stock_stop) * sign <= 0:
        what = "your level" if st.level else f"{rules.stock_trail_pct:g}% behind best {st.best_spot:,.2f}"
        fire("trail_stock", True, f"stock {spot:,.2f} crossed stop {st.stock_stop:,.2f} ({what})")

    if st.close_level and now >= time.fromisoformat(rules.close_check_at):
        key = f"close_check_{today.isoformat()}"
        if key not in st.sent:
            st.sent.append(key)
            if (spot - st.close_level) * sign <= 0:
                out.append(Event("close_stop", True, f"stock {spot:,.2f} closing beyond your daily-close stop "
                                                     f"{st.close_level:,.2f}"))
            else:
                tgt = f", target {st.target:,.2f}" if st.target else ""
                out.append(Event("hold", False, f"daily check: stock {spot:,.2f}, stop {st.close_level:,.2f} on the "
                                                f"close not hit{tgt} -- HOLD"))
    if st.target and (spot - st.target) * sign >= 0:
        fire("target", True, f"stock {spot:,.2f} reached your target {st.target:,.2f} -- take the profit")

    # B. profit give-back
    st.peak_pnl = max(st.peak_pnl, pnl)
    armed = st.max_profit > 0 and st.peak_pnl >= rules.giveback_arm_pct / 100 * st.max_profit
    if armed and pnl <= rules.giveback_keep * st.peak_pnl:
        fire("giveback", True, f"P&L fell to ₹{pnl:,.0f} from a best of ₹{st.peak_pnl:,.0f} "
                               f"(keeps {rules.giveback_keep:.0%} once past {rules.giveback_arm_pct:g}% of max)")

    # breakeven warning, re-armed whenever the stock is back on the profit side
    profit_side = (spot - st.breakeven) * sign > 0
    if profit_side and st.peak_pnl > 0:
        st.be_armed = True
    elif st.be_armed and not profit_side:
        st.be_armed = False
        if "breakeven" in st.sent:
            st.sent.remove("breakeven")
        fire("breakeven", False, f"stock {spot:,.2f} back through the expiry breakeven {st.breakeven:,.2f}")

    if st.max_profit > 0 and pnl >= rules.near_max_pct / 100 * st.max_profit:
        fire("near_max", False, f"P&L ₹{pnl:,.0f} is {pnl / st.max_profit:.0%} of the ₹{st.max_profit:,.0f} max: "
                                "little left to gain, all of it still at risk")

    exit_from = time.fromisoformat(rules.exit_day_from)
    if _weekdays_after(today, date.fromisoformat(st.expiry)) <= rules.exit_sessions_before_expiry and now >= exit_from:
        fire("exit_day", True, f"expiry {st.expiry} is {_weekdays_after(today, date.fromisoformat(st.expiry))} "
                               "session(s) away: close before expiry day")
    return out
