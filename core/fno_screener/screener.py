"""
QuantOS — F&O Option-Buy Candidate Screener (discretionary aid)
────────────────────────────────────────────────────────────────
NOT a signal, NOT a strategy, no execution path. Ranks stock F&O names a
human might BUY a call or a put on for a 1-5 day swing, and names the
contract worth looking at. The human decides; the trade watcher
(scripts/run_trade_watcher.py) manages the exit once a position exists.

Setup (direction):
  - CALLS: core/discovery/momentum_shortlist.build_shortlist on the real
    daily bars -- 52-week-high proximity, weekly Darvas box breakout state,
    EMA9>EMA21 trend gate. Same, already-reviewed primitives; nothing new.
  - PUTS: the same function on price-INVERTED bars (p -> C^2/p, C = last
    close, high/low swapped). A new high of the inverted series is a new
    low of the real one, so 52w-high proximity becomes 52w-low proximity,
    a box breakout becomes a box breakdown and the uptrend gate becomes a
    downtrend gate. Mirroring assumes falls behave like rises; they are
    usually faster -- a known simplification for a screening aid.

Confirmation: futures OI build-up over `oi_lookback_sessions` (NSE F&O
bhavcopy). Summed over the expiries listed TODAY only, so a contract that
expired inside the window doesn't read as long unwinding. Ranked, never a
hard gate.

Contract: one strike in-the-money (up to `max_itm_strikes` deep), from the
NEXT monthly expiry when it is liquid, else the current one -- never one
with fewer than `min_dte` days left. Why not always next month (the theta
argument): measured on bhavcopies 2026-09-08..28 and 2026-10-09, next-month
one-ITM stock options are almost untradeable until ~7-10 days before the
current expiry (13-15 of 210 names liquid at 14-21 DTE of the current
month, 141-148 in its last 4 days). So the next month is used once it
trades and the current month bridges the gap, with theta shown per day.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, timedelta, timezone
from typing import Optional

from core.brokers.base import OHLCV
from core.darvas.weekly_discovery import analyse_symbol
from core.discovery.momentum_shortlist import ShortlistEntry, build_shortlist
from core.fno_screener.bhavcopy import FnoDay, OptionQuote
from core.options.greeks import ImpliedVolatilityError, compute_greeks, implied_volatility
from core.options.models import OptionType
from core.trade_watcher.rules import ExitRules

IST = timezone(timedelta(hours=5, minutes=30))


def bar_date(c: OHLCV) -> date:
    """Session date of a daily bar. Fyers stamps candles in UTC epochs; read
    them in IST so a midnight-IST stamp can't land on the previous day."""
    return c.timestamp.astimezone(IST).date() if c.timestamp.tzinfo else c.timestamp.date()


@dataclass(frozen=True)
class ScreenerConfig:
    min_dte:              int = 10       # never recommend a contract with fewer calendar days left
    min_oi_lots:          int = 50       # contract OI, in lots
    min_volume:           int = 20       # contracts traded on the bhavcopy day
    max_lot_cost:         float = 25000.0 # premium x lot size, rupees
    max_itm_strikes:      int = 2        # how deep in the money to look (1 = nearest ITM strike only)
    max_delta:            float = 0.80   # deeper than this is mostly intrinsic, not "slightly ITM"
    oi_lookback_sessions: int = 5
    oi_flat_pct:          float = 2.0    # |OI change| below this % = no build-up either way
    max_out_sessions:     int = 5        # a breakout older than this is no longer a setup
    top_n:                int = 5        # per side

    @classmethod
    def from_config(cls, cfg: Optional[dict]) -> "ScreenerConfig":
        cfg = cfg or {}
        return cls(**{f.name: type(f.default)(cfg[f.name]) for f in fields(cls) if f.name in cfg})


# ─── OI build-up ─────────────────────────────────────────────────────────────

LONG_BUILDUP, SHORT_BUILDUP = "long build-up", "short build-up"
SHORT_COVERING, LONG_UNWINDING = "short covering", "long unwinding"
OI_FLAT = "OI flat"

# Lower = stronger confirmation for that side.
_OI_RANK = {
    OptionType.CALL: {LONG_BUILDUP: 0, SHORT_COVERING: 1, OI_FLAT: 2, None: 2, LONG_UNWINDING: 3, SHORT_BUILDUP: 3},
    OptionType.PUT:  {SHORT_BUILDUP: 0, LONG_UNWINDING: 1, OI_FLAT: 2, None: 2, SHORT_COVERING: 3, LONG_BUILDUP: 3},
}


@dataclass(frozen=True)
class OiBuildup:
    label:         str
    price_chg_pct: float
    oi_chg_pct:    float


def classify_buildup(price_chg_pct: float, oi_chg_pct: float, flat_pct: float) -> str:
    if abs(oi_chg_pct) < flat_pct:
        return OI_FLAT
    if oi_chg_pct > 0:
        return LONG_BUILDUP if price_chg_pct >= 0 else SHORT_BUILDUP
    return SHORT_COVERING if price_chg_pct >= 0 else LONG_UNWINDING


def oi_buildup(today: FnoDay, past: Optional[FnoDay], symbol: str, flat_pct: float) -> Optional[OiBuildup]:
    if past is None:
        return None
    now = today.futures_oi.get(symbol)
    then = past.futures_oi.get(symbol)
    spot_now, spot_then = today.spot.get(symbol), past.spot.get(symbol)
    if not now or not then or not spot_now or not spot_then:
        return None
    oi_now = sum(now.values())
    oi_then = sum(then.get(expiry, 0) for expiry in now)
    if oi_then <= 0:
        return None
    price_chg = (spot_now / spot_then - 1) * 100
    oi_chg = (oi_now / oi_then - 1) * 100
    return OiBuildup(classify_buildup(price_chg, oi_chg, flat_pct), round(price_chg, 1), round(oi_chg, 1))


# ─── Setup ───────────────────────────────────────────────────────────────────

def invert_bars(daily: list[OHLCV]) -> list[OHLCV]:
    """p -> C^2/p with high/low swapped; C = last close, so the inverted
    series ends at the real price and absolute ATR-style filters stay sane."""
    k = daily[-1].close ** 2
    return [OHLCV(timestamp=c.timestamp, open=k / c.open, high=k / c.low, low=k / c.high,
                  close=k / c.close, volume=c.volume) for c in daily]


def setup_rank(entry: ShortlistEntry, max_out_sessions: int) -> Optional[int]:
    """0 fresh breakout, 1 broke out <=3 sessions ago, 2 near the box edge,
    3 broke out 4..max_out_sessions ago; None = not a setup."""
    if not entry.trend_up or entry.momentum_tier == "LAGGARD":
        return None
    state, days = entry.breakout_state, entry.days_above_ceil
    if state == "FRESH":
        return 0
    if state == "OUT" and days is not None and days <= 3:
        return 1
    if state == "NEAR":
        return 2
    if state == "OUT" and days is not None and days <= max_out_sessions:
        return 3
    return None


# ─── Contract ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Contract:
    quote:        OptionQuote
    dte:          int
    lot_cost:     float
    iv:           Optional[float]
    delta:        Optional[float]
    theta_pct:    Optional[float]     # % of premium lost per calendar day, everything else equal
    note:         str = ""
    fyers_symbol: str = ""


def next_weekday(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _is_itm(q: OptionQuote, spot: float) -> bool:
    return q.strike <= spot if q.option_type == OptionType.CALL else q.strike >= spot


def pick_contract(day: FnoDay, symbol: str, side: OptionType,
                  cfg: ScreenerConfig) -> tuple[Optional[Contract], str]:
    """(contract, "") or (None, why not)."""
    spot = day.spot.get(symbol)
    quotes = [q for q in day.options.get(symbol, []) if q.option_type == side]
    if not spot or not quotes:
        return None, "no option quotes"
    entry = next_weekday(day.trade_date)                            # the day you'd actually buy
    listed = sorted({q.expiry for q in quotes})[:2]                 # current, next month
    eligible = [e for e in listed if (e - entry).days >= cfg.min_dte]
    if not eligible:
        return None, f"no expiry with {cfg.min_dte}+ days left"

    why = "illiquid"
    for expiry in reversed(eligible):                               # next month first
        itm = sorted((q for q in quotes if q.expiry == expiry and _is_itm(q, spot)),
                     key=lambda q: abs(q.strike - spot))
        for q in itm[:cfg.max_itm_strikes]:
            if q.close <= 0 or q.oi_lots < cfg.min_oi_lots or q.volume < cfg.min_volume:
                continue
            lot_cost = q.close * q.lot_size
            if lot_cost > cfg.max_lot_cost:
                why = f"lot over ₹{cfg.max_lot_cost:,.0f}"
                continue
            dte = (expiry - entry).days
            iv = delta = theta_pct = None
            try:
                iv = implied_volatility(q.close, spot, q.strike, dte, side, strict=True)
                g = compute_greeks(spot, q.strike, dte, iv, side)
                delta, theta_pct = g.delta, abs(g.theta) / q.close * 100
            except ImpliedVolatilityError:
                pass
            if delta is not None and abs(delta) > cfg.max_delta:
                continue
            note = ""
            if expiry != listed[-1] and listed[-1] in eligible:
                note = f"{listed[-1]:%b} not liquid"
            return Contract(quote=q, dte=dte, lot_cost=round(lot_cost), iv=iv, delta=delta,
                            theta_pct=None if theta_pct is None else round(theta_pct, 1), note=note), ""
    return None, why


# ─── Candidates ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Candidate:
    symbol:        str
    side:          OptionType
    close:         float
    setup_rank:    int
    breakout_state: str
    days_out:      Optional[int]
    momentum_pct:  float             # calls: close / 52w high; puts: 52w low / close (x100)
    box_level:     Optional[float]   # calls: box ceiling; puts: box floor (real prices)
    box_width_pct: Optional[float]
    oi:            Optional[OiBuildup]
    contract:      Optional[Contract]
    skip_reason:   str = ""

    @property
    def sort_key(self) -> tuple:
        return (self.setup_rank, _OI_RANK[self.side][self.oi.label if self.oi else None], -self.momentum_pct)


@dataclass
class ScreenResult:
    trade_date: date
    calls:      list[Candidate]
    puts:       list[Candidate]
    skipped:    list[Candidate]       # a setup, but no contract passed liquidity/cost
    scanned:    int


def build_candidates(daily_by_symbol: dict[str, list[OHLCV]], today: FnoDay,
                     past: Optional[FnoDay], cfg: ScreenerConfig) -> ScreenResult:
    """Pure: bars must already be cut to <= today.trade_date; symbols whose
    last bar isn't today.trade_date are ignored (stale/suspended)."""
    daily = {s: bars for s, bars in daily_by_symbol.items()
             if bars and bar_date(bars[-1]) == today.trade_date}
    if not daily:
        return ScreenResult(today.trade_date, [], [], [], 0)
    as_of = max(bars[-1].timestamp for bars in daily.values())
    inverted = {s: invert_bars(bars) for s, bars in daily.items()}

    out: dict[OptionType, list[Candidate]] = {OptionType.CALL: [], OptionType.PUT: []}
    skipped: list[Candidate] = []
    for side, bars_map in ((OptionType.CALL, daily), (OptionType.PUT, inverted)):
        for entry in build_shortlist(bars_map, as_of):
            rank = setup_rank(entry, cfg.max_out_sessions)
            if rank is None:
                continue
            base = analyse_symbol(entry.symbol, bars_map[entry.symbol])
            box_level = base.box_ceiling if base else None
            if side == OptionType.PUT and box_level:
                box_level = daily[entry.symbol][-1].close ** 2 / box_level
            contract, why = pick_contract(today, entry.symbol, side, cfg)
            cand = Candidate(
                symbol=entry.symbol, side=side, close=daily[entry.symbol][-1].close,
                setup_rank=rank, breakout_state=entry.breakout_state, days_out=entry.days_above_ceil,
                momentum_pct=entry.momentum_pct,
                box_level=round(box_level, 2) if box_level else None,
                box_width_pct=entry.box_width_pct,
                oi=oi_buildup(today, past, entry.symbol, cfg.oi_flat_pct),
                contract=contract, skip_reason=why,
            )
            (out[side] if contract else skipped).append(cand)

    for side in out:
        out[side].sort(key=lambda c: c.sort_key)
    skipped.sort(key=lambda c: c.sort_key)
    return ScreenResult(today.trade_date, out[OptionType.CALL][:cfg.top_n],
                        out[OptionType.PUT][:cfg.top_n], skipped, len(daily))


# ─── Telegram ────────────────────────────────────────────────────────────────

def _px(x: float) -> str:
    return f"{x:,.2f}" if x < 1000 else f"{x:,.1f}"


def _setup_text(c: Candidate) -> str:
    edge = "box top" if c.side == OptionType.CALL else "box floor"
    verb = "breakout above" if c.side == OptionType.CALL else "breakdown below"
    level = _px(c.box_level) if c.box_level else "?"
    width = f" (box {c.box_width_pct:g}% wide)" if c.box_width_pct else ""
    if c.breakout_state == "FRESH":
        return f"fresh {verb} {edge} {level}{width}"
    if c.breakout_state == "OUT":
        where = "above" if c.side == OptionType.CALL else "below"
        return f"{c.days_out} session(s) {where} {edge} {level}{width}"
    return f"near {edge} {level}{width}"


def _strength_text(c: Candidate) -> str:
    if c.side == OptionType.CALL:
        return f"{c.momentum_pct:.0f}% of 52w high"
    return f"{(100 / c.momentum_pct - 1) * 100:.0f}% above 52w low"


def _oi_text(c: Candidate, lookback: int) -> str:
    if not c.oi:
        return "OI n/a"
    return f"OI {lookback}d: {c.oi.label} (price {c.oi.price_chg_pct:+.1f}%, OI {c.oi.oi_chg_pct:+.0f}%)"


def _contract_lines(c: Candidate, rules: ExitRules) -> list[str]:
    k = c.contract
    q = k.quote
    name = k.fyers_symbol.removeprefix("NSE:") or f"{q.symbol} {q.expiry:%d %b} {q.strike:g} {q.option_type.value}"
    greeks = []
    if k.delta is not None:
        greeks.append(f"Δ{abs(k.delta):.2f}")
    if k.theta_pct is not None:
        greeks.append(f"θ {k.theta_pct:g}%/day")
    greeks.append(f"{k.dte}d left from next session" + (f", {k.note}" if k.note else ""))
    p = q.close
    lock = (f" · lock at {_px(p * (1 + rules.breakeven_at_pct / 100))} → "
            f"{_px(p * (1 + rules.breakeven_lock_pct / 100))}") if rules.breakeven_at_pct > 0 else ""
    return [
        f"   ➜ {name} @ {_px(p)} · lot {q.lot_size} = ₹{k.lot_cost:,.0f} · " + " · ".join(greeks),
        f"     OI {q.oi_lots:,} lots, {q.volume:,} traded · watcher: stop {_px(p * (1 - rules.initial_stop_pct / 100))}"
        f"{lock} · trail from {_px(p * (1 + rules.trail_after_pct / 100))}",
    ]


def format_telegram(result: ScreenResult, rules: ExitRules, cfg: ScreenerConfig,
                    spread_lines: Optional[dict[tuple[str, str], str]] = None) -> str:
    """`spread_lines` maps (side, symbol) -> one line from core/fno_screener/spreads.spread_line."""
    lines = [f"🎯 F&O option-buy candidates · close of {result.trade_date:%a %d %b}",
             f"Screening aid, not a signal. {result.scanned} F&O stocks scanned. "
             "Premiums are the bhavcopy close -- check the live bid/ask before buying."]
    for title, side, cands in (("📈 CALLS", OptionType.CALL, result.calls), ("📉 PUTS", OptionType.PUT, result.puts)):
        lines.append("")
        lines.append(title)
        if not cands:
            lines.append("   none today")
        for i, c in enumerate(cands, 1):
            if i > 1:
                lines.append("")
            lines.append(f"{i}. {c.symbol} {_px(c.close)} -- {_setup_text(c)} · {_strength_text(c)}")
            lines.append(f"   {_oi_text(c, cfg.oi_lookback_sessions)}")
            lines.extend(_contract_lines(c, rules))
            if spread_lines and (c.side.value, c.symbol) in spread_lines:
                lines.append(spread_lines[(c.side.value, c.symbol)])
            if c.box_level:
                below, above = ("below", "above") if side == OptionType.CALL else ("above", "below")
                if c.breakout_state == "NEAR":
                    lines.append(f"     not broken yet: wait for a close {above} {_px(c.box_level)}")
                else:
                    lines.append(f"     invalid if {c.symbol} closes back {below} {_px(c.box_level)}")
    if result.skipped:
        names = ", ".join(f"{c.symbol} {c.side.value}" for c in result.skipped[:8])
        more = f" +{len(result.skipped) - 8}" if len(result.skipped) > 8 else ""
        lines += ["", f"Setups with no liquid ITM contract ≤ ₹{cfg.max_lot_cost:,.0f}: {names}{more}"]
    lines += ["", "Hold 1-5 days; exit by day 5 if it hasn't moved. Check each name's results date "
                  "before buying -- an IV crush after results can sink a right call."]
    return "\n".join(lines)
