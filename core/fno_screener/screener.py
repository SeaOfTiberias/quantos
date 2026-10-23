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

from dataclasses import dataclass, field, fields
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
    min_volume:           int = 150      # contracts traded on the bhavcopy day (20 let 80-lot books through)
    max_lot_cost:         float = 0.0    # premium x lot size, rupees; 0 = no cap (user 2026-10-23: budget is not a filter)
    max_itm_strikes:      int = 2        # how deep in the money to look (1 = nearest ITM strike only)
    max_delta:            float = 0.80   # deeper than this is mostly intrinsic, not "slightly ITM"
    oi_lookback_sessions: int = 5
    oi_flat_pct:          float = 2.0    # |OI change| below this % = no build-up either way
    max_out_sessions:     int = 5        # a breakout older than this is no longer a setup (see setup_rank)
    max_single_bid_ask_pct: float = 5.0  # (ask - bid) / mid of the single option; wider = don't buy it
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


WATCH_RANK = 2      # NEAR: listed with its trigger level, no contract -- not a buy yet


def setup_rank(entry: ShortlistEntry, max_out_sessions: int) -> Optional[int]:
    """0 fresh breakout, 1 broke out <= max_out_sessions ago, WATCH_RANK near
    the box edge; None = not a setup.

    A year of the screener's own signals (scripts/backtest_fno_screener.py,
    Sep 2025 - Oct 2026, ~2,000 breakouts per side) overturned the 77-pick
    reading that only day-1 breakouts work: 2-5 session old breakouts did
    slightly better (excess +0.24% over 5 sessions, t~2.2, both sides) and
    the day-1-only set lost under every exit rule tested. NEAR stays a
    watchlist: no edge as a buy (calls -0.09%)."""
    if not entry.trend_up or entry.momentum_tier == "LAGGARD":
        return None
    state, days = entry.breakout_state, entry.days_above_ceil
    if state == "FRESH":
        return 0
    if state == "OUT" and days is not None and days <= max_out_sessions:
        return 1
    if state == "NEAR":
        return WATCH_RANK
    return None


# Hook for excluding OI build-up labels per side. Empty: the 77-pick log had
# calls on short covering worst (n=5), but over the year the sign flipped
# between halves (+0.43% / -0.67%) -- noise, not a filter.
_EXCLUDED_OI: dict = {OptionType.CALL: set(), OptionType.PUT: set()}


# ─── Market regime (a label, not a filter) ───────────────────────────────────

@dataclass(frozen=True)
class MarketRegime:
    close: float
    ema:   float
    above: bool


def market_regime(daily: list[OHLCV], period: int = 20) -> Optional[MarketRegime]:
    """Nifty close vs its EMA(period). Shown and logged on every run but NOT
    used to suppress a side: on the 9-22 Oct picks a calls-above / puts-below
    gate kept the losers (near spread -9.6% at day 3) and dropped the winners
    (+9.1%). Revisit once the log is bigger."""
    if len(daily) < period:
        return None
    k, ema = 2 / (period + 1), daily[0].close
    for c in daily[1:]:
        ema += k * (c.close - ema)
    close = daily[-1].close
    return MarketRegime(round(close, 2), round(ema, 2), close >= ema)


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
    bid_ask_pct:  Optional[float] = None   # (ask - bid) / mid x 100 from the post-close quote; None = no quote


def bid_ask_pct(quote: Optional[tuple[float, float]]) -> Optional[float]:
    """(ask - bid) / mid in %, or None unless the quote is two-sided."""
    if not quote or quote[0] <= 0 or quote[1] < quote[0]:
        return None
    mid = (quote[0] + quote[1]) / 2
    return round((quote[1] - quote[0]) / mid * 100, 1)


def single_ok(k: "Contract", cfg: ScreenerConfig) -> bool:
    """The single option passes the bid-ask gate. No quote = judged on
    OI/volume alone (min_volume), so it passes."""
    return k.bid_ask_pct is None or k.bid_ask_pct <= cfg.max_single_bid_ask_pct


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
            if cfg.max_lot_cost and lot_cost > cfg.max_lot_cost:
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
    atr:           Optional[float] = None   # ATR(14) on real daily bars, rupees

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
    watch:      list[Candidate] = field(default_factory=list)    # NEAR: trigger level only, no contract
    dropped:    list[Candidate] = field(default_factory=list)    # a setup, excluded by OI (skip_reason says why)
    market:     Optional[MarketRegime] = None


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
    watch: list[Candidate] = []
    dropped: list[Candidate] = []
    for side, bars_map in ((OptionType.CALL, daily), (OptionType.PUT, inverted)):
        for entry in build_shortlist(bars_map, as_of):
            rank = setup_rank(entry, cfg.max_out_sessions)
            if rank is None:
                continue
            base = analyse_symbol(entry.symbol, bars_map[entry.symbol])
            box_level = base.box_ceiling if base else None
            if side == OptionType.PUT and box_level:
                box_level = daily[entry.symbol][-1].close ** 2 / box_level
            oi = oi_buildup(today, past, entry.symbol, cfg.oi_flat_pct)
            excluded = oi is not None and oi.label in _EXCLUDED_OI[side]
            if rank == WATCH_RANK or excluded:
                contract, why = None, (oi.label if excluded else "")
            else:
                contract, why = pick_contract(today, entry.symbol, side, cfg)
            cand = Candidate(
                symbol=entry.symbol, side=side, close=daily[entry.symbol][-1].close,
                setup_rank=rank, breakout_state=entry.breakout_state, days_out=entry.days_above_ceil,
                momentum_pct=entry.momentum_pct,
                box_level=round(box_level, 2) if box_level else None,
                box_width_pct=entry.box_width_pct,
                oi=oi, contract=contract, skip_reason=why, atr=daily_atr(daily[entry.symbol]),
            )
            if excluded:
                dropped.append(cand)
            elif rank == WATCH_RANK:
                watch.append(cand)
            else:
                (out[side] if contract else skipped).append(cand)

    for side in out:
        out[side].sort(key=lambda c: c.sort_key)
    for xs in (skipped, watch, dropped):
        xs.sort(key=lambda c: c.sort_key)
    return ScreenResult(today.trade_date, out[OptionType.CALL][:cfg.top_n],
                        out[OptionType.PUT][:cfg.top_n], skipped, len(daily),
                        watch=watch, dropped=dropped)


# ─── Telegram ────────────────────────────────────────────────────────────────

# What a year of the screener's own signals says per side (scripts/backtest_fno_exits.py,
# Sep 2025 - Oct 2026, as futures, 0.1% round trip). Calls are still sent, marked; the
# user tunes them out later rather than the screener hiding them.
SIDE_EDGE = {
    OptionType.CALL: "no measured edge -- lost after costs under every exit and entry rule tested (1y backtest)",
    OptionType.PUT:  "measured edge with the retest plan: +0.31%/trade, 69% won, both halves (1y backtest, futures)",
}
PLAN_ENTRY_ATR = 0.25      # limit this far from the broken box level, toward the trade (H1 retest)
PLAN_ENTRY_SESSIONS = 3
PLAN_STOP_ATR = 0.75       # stop this many ATRs from entry, judged on the DAILY close
PLAN_TARGET_R = 1.0        # resting take-profit at 1R
PLAN_MAX_SESSIONS = 10


def daily_atr(bars: list[OHLCV], n: int = 14) -> Optional[float]:
    if len(bars) < n + 1:
        return None
    trs = [max(b.high - b.low, abs(b.high - a.close), abs(b.low - a.close)) for a, b in zip(bars[-n - 1:], bars[-n:])]
    return round(sum(trs) / n, 2)


def _plan_text(c: Candidate) -> Optional[str]:
    """The pre-registered H1 retest entry and the fixed exit
    (docs/FNO_ENTRY_SEARCH_PREREG_2026-10-23.md, scripts/backtest_fno_entries.py):
    a limit just inside the broken level, valid PLAN_ENTRY_SESSIONS sessions;
    stop on a daily close 0.75 ATR beyond the fill; resting 1R target."""
    if not c.atr or not c.box_level:
        return None
    sign = 1 if c.side == OptionType.CALL else -1
    entry = c.box_level + sign * PLAN_ENTRY_ATR * c.atr
    stop = entry - sign * PLAN_STOP_ATR * c.atr
    target = entry + sign * PLAN_TARGET_R * PLAN_STOP_ATR * c.atr
    verb, beyond = ("buy", "below") if sign > 0 else ("sell", "above")
    return (f"   plan (futures): {verb} limit {_px(entry)} (retest, valid {PLAN_ENTRY_SESSIONS} sessions) · "
            f"stop daily close {beyond} {_px(stop)} · target {_px(target)} (1R, resting) · "
            f"out by session {PLAN_MAX_SESSIONS}")


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


def _contract_lines(c: Candidate, rules: ExitRules, cfg: ScreenerConfig) -> list[str]:
    """The single option: secondary to the spread, and only if its bid-ask passes."""
    k = c.contract
    q = k.quote
    name = k.fyers_symbol.removeprefix("NSE:") or f"{q.symbol} {q.expiry:%d %b} {q.strike:g} {q.option_type.value}"
    spread = "bid-ask n/a" if k.bid_ask_pct is None else f"bid-ask {k.bid_ask_pct:g}%"
    if not single_ok(k, cfg):
        return [f"     single: {name} -- {spread} > {cfg.max_single_bid_ask_pct:g}%, don't buy it outright"]
    greeks = []
    if k.delta is not None:
        greeks.append(f"Δ{abs(k.delta):.2f}")
    if k.theta_pct is not None:
        greeks.append(f"θ {k.theta_pct:g}%/day")
    greeks.append(f"{k.dte}d left" + (f", {k.note}" if k.note else ""))
    p = q.close
    lock = (f" · lock at {_px(p * (1 + rules.breakeven_at_pct / 100))} → "
            f"{_px(p * (1 + rules.breakeven_lock_pct / 100))}") if rules.breakeven_at_pct > 0 else ""
    return [
        f"     single: {name} @ {_px(p)} · lot {q.lot_size} = ₹{k.lot_cost:,.0f} · {spread} · " + " · ".join(greeks),
        f"     OI {q.oi_lots:,} lots, {q.volume:,} traded · watcher: stop {_px(p * (1 - rules.initial_stop_pct / 100))}"
        f"{lock} · trail from {_px(p * (1 + rules.trail_after_pct / 100))}",
    ]


def _market_text(m: Optional[MarketRegime]) -> str:
    if m is None:
        return "Nifty vs EMA20: n/a"
    return (f"Nifty {m.close:,.0f} {'above' if m.above else 'below'} EMA20 {m.ema:,.0f} "
            "(label only -- not used to filter)")


def _names(cands: list[Candidate], limit: int = 8) -> str:
    names = ", ".join(f"{c.symbol} {c.side.value}" for c in cands[:limit])
    return names + (f" +{len(cands) - limit}" if len(cands) > limit else "")


def format_telegram(result: ScreenResult, rules: ExitRules, cfg: ScreenerConfig,
                    spread_lines: Optional[dict[tuple[str, str], str]] = None) -> str:
    """`spread_lines` maps (side, symbol) -> the primary line from core/fno_screener/spreads.spread_line."""
    lines = [f"🎯 F&O candidates · close of {result.trade_date:%a %d %b}",
             f"Screening aid, not a signal. {result.scanned} F&O stocks scanned. Breakouts up to 5 sessions old. "
             "Prices are the close -- check the live bid/ask before entering.",
             _market_text(result.market)]
    for title, side, cands in (("📈 CALLS", OptionType.CALL, result.calls), ("📉 PUTS", OptionType.PUT, result.puts)):
        lines.append("")
        lines.append(f"{title} -- {SIDE_EDGE[side]}")
        if not cands:
            lines.append("   none today")
        for i, c in enumerate(cands, 1):
            if i > 1:
                lines.append("")
            lines.append(f"{i}. {c.symbol} {_px(c.close)} -- {_setup_text(c)} · {_strength_text(c)}")
            lines.append(f"   {_oi_text(c, cfg.oi_lookback_sessions)}")
            if plan := _plan_text(c):
                lines.append(plan)
            if spread_lines and (c.side.value, c.symbol) in spread_lines:
                lines.append(spread_lines[(c.side.value, c.symbol)])
            lines.extend(_contract_lines(c, rules, cfg))
            if c.box_level:
                below = "below" if side == OptionType.CALL else "above"
                lines.append(f"     invalid if {c.symbol} closes back {below} {_px(c.box_level)}")
    if result.watch:
        lines += ["", "👀 WATCH -- not broken yet, no trade until a close beyond the level"]
        for c in result.watch[:2 * cfg.top_n]:
            beyond = "above" if c.side == OptionType.CALL else "below"
            gap = f" ({abs(c.box_level / c.close - 1) * 100:.1f}% away)" if c.box_level else ""
            level = _px(c.box_level) if c.box_level else "?"
            lines.append(f"   {c.symbol} {c.side.value} {_px(c.close)}: close {beyond} {level}{gap}")
    if result.dropped:
        lines += ["", f"Dropped on OI build-up: {_names(result.dropped)}"]
    if result.skipped:
        cap = f" ≤ ₹{cfg.max_lot_cost:,.0f}" if cfg.max_lot_cost else ""
        lines += ["", f"No liquid ITM option{cap} (futures? run pick_structure): "
                      f"{_names(result.skipped)}"]
    lines += ["", "Hold 1-5 days; exit by day 5 if it hasn't moved. Check each name's results date "
                  "before buying -- an IV crush after results can sink a right call."]
    return "\n".join(lines)
