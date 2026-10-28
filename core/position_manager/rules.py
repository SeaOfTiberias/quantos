"""
QuantOS — Position Manager: the plan for a futures position, and its checks
────────────────────────────────────────────────────────────────────────────
Pure. The 22 Oct 2026 TCS trade was the right direction lost to the exit;
this holds the exit to a written plan instead of the P&L on screen.

The default plan is the exit tested on a year of the screener's signals
(scripts/backtest_fno_exits.py, scripts/backtest_fno_entries.py,
docs/FNO_ENTRY_SEARCH_PREREG_2026-10-23.md):

  stop       a DAILY close beyond entry -/+ 0.75 x ATR(14)  -- checked once, near the close
  emergency  a TOUCH 1 ATR beyond the stop                   -- checked all day
  target     entry +/- 1R (R = the stop distance), touch     -- meant as a resting limit order
  time       out at the close of session 10
  profit     a ratchet on the best price seen (TRAIL): +0.5R moves a touch stop to
             entry +0.1R, +0.75R to entry +0.25R. It only tightens. Not part of the
             tested exit: added 28 Oct 2026 after a short gave back a large open
             gain with nothing to hold it.

A per-position override (levels file) replaces stop / target for a
discretionary plan, e.g. {"TCS": {"stop": 2495, "target": 2614}}.

Breeze futures rows (trade book, 2026-10-22): product_type "Futures",
right "Others", strike "0", expiry "23-Nov-2026", quantity in shares as a
string, action "Buy"/"Sell", price in average_price (positions) or
average_cost (trade book).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Optional

STOP_ATR = 0.75
EMERGENCY_ATR = 1.0
TARGET_R = 1.0
MAX_SESSIONS = 10
TRAIL = ((0.5, 0.1), (0.75, 0.25))      # (best move reached, in R; stop locked at entry + this R)


@dataclass(frozen=True)
class FutPosition:
    code:      str         # ICICI stock code, e.g. TCS, POWFIN
    expiry:    date
    qty:       int         # signed shares: + long, - short
    avg_price: float

    @property
    def key(self) -> str:
        return f"{self.code}|{self.expiry.isoformat()}"

    @property
    def side(self) -> int:
        return 1 if self.qty > 0 else -1


def _expiry(text: str) -> Optional[date]:
    text = (text or "").strip()
    for fmt, n in (("%d-%b-%Y", 11), ("%Y-%m-%d", 10), ("%d-%m-%Y", 10)):
        try:
            return datetime.strptime(text[:n], fmt).date()
        except ValueError:
            continue
    return None


def parse_future(row: dict) -> Optional[FutPosition]:
    """One Breeze position row -> FutPosition, or None if it isn't an open future."""
    if str(row.get("product_type", "")).lower() not in ("futures", "future"):
        return None
    try:
        qty = int(float(row.get("quantity") or 0))
        price = float(row.get("average_price") or row.get("average_cost") or row.get("price") or 0)
    except (TypeError, ValueError):
        return None
    if str(row.get("action", "")).lower() == "sell" and qty > 0:
        qty = -qty
    expiry = _expiry(str(row.get("expiry_date", "")))
    if qty == 0 or price <= 0 or expiry is None:
        return None
    return FutPosition(code=str(row.get("stock_code", "")).upper(), expiry=expiry, qty=qty, avg_price=price)


@dataclass
class Plan:
    code:        str
    symbol:      str            # NSE symbol (for history), e.g. PFC for POWFIN
    expiry:      date
    side:        int
    qty:         int
    entry:       float
    atr:         Optional[float]
    stop:        float          # daily-close stop
    emergency:   Optional[float]
    target:      Optional[float]
    entry_date:  date
    source:      str = "tested"     # tested | override
    sent:        list = field(default_factory=list)     # alert keys already sent
    last_price:  Optional[float] = None
    last_check:  Optional[str] = None                   # date of the last daily-close check
    gtt_id:      Optional[str] = None                   # the resting OCO at the broker (orders: auto)
    best:        Optional[float] = None                 # best price seen since the plan was made
    trail:       Optional[float] = None                 # profit stop (touch), set by update_trail

    @property
    def r(self) -> float:
        return abs(self.entry - self.stop)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["expiry"], d["entry_date"] = self.expiry.isoformat(), self.entry_date.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Plan":
        d = dict(d)
        d["expiry"], d["entry_date"] = date.fromisoformat(d["expiry"]), date.fromisoformat(d["entry_date"])
        return cls(**d)


def make_plan(pos: FutPosition, symbol: str, atr: Optional[float], today: date,
              override: Optional[dict] = None) -> Plan:
    """The tested plan from ATR, or the override's stop/target when given.
    With neither an ATR nor an override stop there's no stop to watch: the
    plan still exists (so the position is announced) with stop = entry."""
    s, e = pos.side, pos.avg_price
    override = override or {}
    if "stop" in override:
        stop = float(override["stop"])
        target = float(override["target"]) if override.get("target") else None
        emergency = (stop - s * EMERGENCY_ATR * atr) if atr else None
        source = "override"
    else:
        stop = e - s * STOP_ATR * atr if atr else e
        target = e + s * TARGET_R * STOP_ATR * atr if atr else None
        emergency = stop - s * EMERGENCY_ATR * atr if atr else None
        source = "tested"
    rnd = (lambda x: None if x is None else round(x, 2))
    return Plan(code=pos.code, symbol=symbol, expiry=pos.expiry, side=s, qty=pos.qty, entry=e,
                atr=rnd(atr), stop=round(stop, 2), emergency=rnd(emergency), target=rnd(target),
                entry_date=today, source=source)


@dataclass(frozen=True)
class Event:
    key:    str
    kind:   str      # TARGET | EMERGENCY | CLOSE | TIME | HOLD
    detail: str


def update_trail(p: Plan, price: float) -> Optional[float]:
    """Track the best price and ratchet the profit stop (TRAIL). Returns the new
    level when it moved, else None. It never loosens."""
    if p.r <= 0:
        return None
    if p.best is None or (price - p.best) * p.side > 0:
        p.best = price
    gain = (p.best - p.entry) * p.side / p.r
    locks = [lock for reach, lock in TRAIL if gain >= reach - 1e-9]
    if not locks:
        return None
    level = round(p.entry + p.side * max(locks) * p.r, 2)
    if p.trail is not None and (level - p.trail) * p.side <= 0:
        return None
    p.trail = level
    return level


def check_intraday(p: Plan, price: float) -> list[Event]:
    """Touch levels, each alerted once per position."""
    p.last_price = price
    out = []
    if p.trail is not None and (price - p.trail) * p.side <= 0 and "trail" not in p.sent:
        p.sent.append("trail")
        out.append(Event("trail", "TRAIL", f"price {price:g} came back to the profit stop {p.trail:g} -- out, keeping the gain"))
    if p.emergency is not None and (price - p.emergency) * p.side <= 0 and "emergency" not in p.sent:
        p.sent.append("emergency")
        out.append(Event("emergency", "EMERGENCY",
                         f"price {price:g} through the emergency stop {p.emergency:g} -- close now, don't wait for the close"))
    if p.target is not None and (price - p.target) * p.side >= 0 and "target" not in p.sent:
        p.sent.append("target")
        out.append(Event("target", "TARGET", f"price {price:g} reached the target {p.target:g} (1R) -- take the profit"))
    return out


def check_close(p: Plan, price: float, today: date, session_no: int) -> Event:
    """The once-a-day check near the close: stop on the close, time stop, else hold."""
    p.last_price = price
    p.last_check = today.isoformat()
    pnl = (price - p.entry) * p.qty
    if (price - p.stop) * p.side <= 0:
        return Event(f"close-{today}", "CLOSE",
                     f"closing near {price:g}, {'below' if p.side > 0 else 'above'} the stop {p.stop:g} -- exit before 15:30 "
                     f"(P&L ≈ ₹{pnl:,.0f})")
    if session_no >= MAX_SESSIONS:
        return Event(f"time-{today}", "TIME",
                     f"session {session_no} of {MAX_SESSIONS}: time's up -- exit before 15:30 (P&L ≈ ₹{pnl:,.0f})")
    if p.expiry <= today:
        return Event(f"expiry-{today}", "TIME", f"expiry day -- exit or roll before 15:30 (P&L ≈ ₹{pnl:,.0f})")
    tgt = f", target {p.target:g}" if p.target is not None else ""
    return Event(f"hold-{today}", "HOLD",
                 f"no rule broken -- HOLD. Price {price:g} (P&L ≈ ₹{pnl:,.0f}); stop {p.stop:g} on the daily close{tgt}; "
                 f"session {session_no} of {MAX_SESSIONS}")
