"""NIFTY 1H bullish SMC order block + session POC: the spot engine (docs/NIFTY_SMC_OB_1H_PREREG_2026-11-22.md §4).

Pure: bars in, trades out. The rules are the user's spec v3 defaults with the readings frozen in the
pre-registration (§4, items 1-10). No option is priced here (that is §5, a later step).

Bars: `Bar(start, o, h, l, c, subs)`. `start` is a naive IST datetime. `subs` are the bar's 5-minute bars
(start, o, h, l, c), used only to locate the first touch of a stop or target inside the hour.
`htf_bullish(d)`: the HTF filter for session date d, from the previous completed session (item 1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Callable, Optional

SWING = 5
ATR_LEN = 14
ATR_BUF = 0.3
MIN_RISK, MAX_RISK = 0.8, 1.8
RR = 2.0
BE_R, BE_PLUS = 1.0, 5.0
TRAIL_R, TRAIL_ATR = 1.4, 1.4
MAX_HOLD = 14
OB_SCAN = SWING + 3
TICK = 0.05
MIN_BARS_PER_DAY = 5          # special sessions (Muhurat, Budget-day half sessions): no signals


@dataclass(frozen=True)
class Bar:
    start: datetime
    o: float
    h: float
    l: float
    c: float
    subs: tuple = ()          # ((start, o, h, l, c), ...) 5-minute bars inside this bar


@dataclass
class Trade:
    signal_start: datetime    # start of signal bar t
    entry_time: datetime      # start of bar t+1 (filled at its open)
    entry: float
    risk: float
    atr: float
    ob_bot: float
    stop0: float
    target: float
    window: str               # "am" | "pm"
    exit_time: Optional[datetime] = None
    exit: Optional[float] = None
    reason: Optional[str] = None
    bars_held: int = 0
    stops: list = field(default_factory=list)   # (bar start, new stop) when the stop moved

    @property
    def points(self) -> Optional[float]:
        return None if self.exit is None else self.exit - self.entry


def wilder_atr(bars: list[Bar], n: int = ATR_LEN) -> list[Optional[float]]:
    out, prev, atr = [], None, None
    trs = []
    for b in bars:
        tr = b.h - b.l if prev is None else max(b.h - b.l, abs(b.h - prev), abs(b.l - prev))
        prev = b.c
        trs.append(tr)
        if atr is None:
            if len(trs) == n:
                atr = sum(trs) / n
        else:
            atr = (atr * (n - 1) + tr) / n
        out.append(atr)
    return out


def _window(start: datetime, signal_starts: dict) -> Optional[str]:
    return signal_starts.get(start.time())


def run(bars: list[Bar], htf_bullish: Callable[[date], bool], signal_starts: dict,
        allow_from: Optional[date] = None) -> list[Trade]:
    """`signal_starts`: {time of a signal bar's start: "am"|"pm"} (grid a: 10:15/14:15; grid b: 10:00/14:00).
    Entries are taken only on or after `allow_from` (the warm-up still builds state)."""
    atr = wilder_atr(bars)
    n = len(bars)
    per_day: dict = {}
    for b in bars:
        per_day[b.start.date()] = per_day.get(b.start.date(), 0) + 1

    sh = sl_ = None                     # last swing high / low
    sh_prev = sl_prev = None
    trend = 0
    ob_top = ob_bot = None
    ob_active = False
    pv_num = pv_den = 0.0
    trades: list[Trade] = []
    pos: Optional[Trade] = None
    pending: Optional[dict] = None      # a signal at bar t, filled at bar t+1's open

    for t, b in enumerate(bars):
        new_day = t == 0 or b.start.date() != bars[t - 1].start.date()

        # ── fill a pending entry at this bar's open ─────────────────────────
        if pending is not None:
            e = b.o
            a = pending["atr"]
            raw = e - (pending["ob_bot"] - ATR_BUF * a)
            risk = min(max(raw, MIN_RISK * a), MAX_RISK * a)
            pos = Trade(signal_start=pending["start"], entry_time=b.start, entry=e, risk=risk, atr=a,
                        ob_bot=pending["ob_bot"], stop0=e - risk, target=e + RR * risk, window=pending["window"])
            pos._stop = e - risk                                            # type: ignore[attr-defined]
            pending = None

        # ── exits inside this bar (5-minute path) ───────────────────────────
        if pos is not None:
            stop, tgt = pos._stop, pos.target                               # type: ignore[attr-defined]
            subs = b.subs or ((b.start, b.o, b.h, b.l, b.c),)
            for s in subs:
                st, so, shh, sll, _ = s
                if so <= stop:
                    pos.exit_time, pos.exit, pos.reason = st, so, "stop_gap"
                elif so >= tgt:
                    pos.exit_time, pos.exit, pos.reason = st, so, "target_gap"
                elif sll <= stop:
                    pos.exit_time, pos.exit, pos.reason = st, stop, "stop"
                elif shh >= tgt:
                    pos.exit_time, pos.exit, pos.reason = st, tgt, "target"
                if pos.exit is not None:
                    break
            if pos.exit is None:
                pos.bars_held += 1
                if pos.bars_held >= MAX_HOLD:
                    pos.exit_time, pos.exit, pos.reason = b.start, b.c, "time"
            else:
                pos.bars_held += 1
            if pos.exit is not None:
                if "stop" in pos.reason and stop > pos.stop0:
                    pos.reason += "_raised"
                trades.append(pos)
                pos = None

        # ── state at the close of bar t ─────────────────────────────────────
        if new_day:
            pv_num = pv_den = 0.0
        w = (b.h - b.l) + TICK
        pv_num += (b.h + b.l + b.c) / 3 * w
        pv_den += w
        poc = pv_num / pv_den

        k = t - SWING
        if k >= SWING:
            hk, lk = bars[k].h, bars[k].l
            if all(hk > bars[j].h for j in range(k - SWING, k)) and all(hk > bars[j].h for j in range(k + 1, t + 1)):
                sh = hk
            if all(lk < bars[j].l for j in range(k - SWING, k)) and all(lk < bars[j].l for j in range(k + 1, t + 1)):
                sl_ = lk

        bos = False
        prev_c = bars[t - 1].c if t else None
        if sh is not None and prev_c is not None and b.c > sh and prev_c <= (sh_prev if sh_prev is not None else sh):
            bos, trend = True, 1
            i = next((i for i in range(1, OB_SCAN + 1) if t - i >= 0 and bars[t - i].c < bars[t - i].o), 1)
            ob_top, ob_bot, ob_active = bars[t - i].h, bars[t - i].l, True
        if sl_ is not None and prev_c is not None and b.c < sl_ and prev_c >= (sl_prev if sl_prev is not None else sl_):
            trend = -1
        if ob_active and b.c < ob_bot:
            ob_active = False

        # ── stop management at the close (applies from the next bar) ────────
        if pos is not None:
            a = atr[t]
            new = pos._stop                                                 # type: ignore[attr-defined]
            if b.h - pos.entry >= BE_R * pos.risk:
                new = max(new, pos.entry + BE_PLUS)
            if a is not None and b.h - pos.entry >= TRAIL_R * pos.risk:
                new = max(new, b.c - TRAIL_ATR * a)
            if bos and a is not None and ob_bot > new:
                new = max(new, ob_bot - ATR_BUF * a)
            if new > pos._stop:                                             # type: ignore[attr-defined]
                pos._stop = new                                             # type: ignore[attr-defined]
                pos.stops.append((b.start, round(new, 2)))

        # ── signal at the close of bar t ────────────────────────────────────
        win = _window(b.start, signal_starts)
        if (pos is None and pending is None and win and atr[t] is not None and t + 1 < n
                and bars[t + 1].start.date() == b.start.date()
                and per_day[b.start.date()] >= MIN_BARS_PER_DAY
                and (allow_from is None or b.start.date() >= allow_from)
                and htf_bullish(b.start.date()) and trend == 1 and b.c > poc
                and ob_active and b.l <= ob_top and b.c >= ob_bot and b.c > b.o):
            pending = dict(start=b.start, atr=atr[t], ob_bot=ob_bot, window=win)
            ob_active = False                                               # consumed
        sh_prev, sl_prev = sh, sl_
    return trades


GRID_A = {time(10, 15): "am", time(14, 15): "pm"}     # Fyers 60m: entries 11:15 / 15:15
GRID_B = {time(10, 0): "am", time(14, 0): "pm"}       # hour-aligned: entries 11:00 / 15:00


# ─── shared exit management (step 3: the placebo uses it; the script asserts it reproduces run()) ──

def states(bars: list[Bar]) -> dict:
    """Per bar, after its close: ATR, whether a bullish BOS fired, and the OB bottom then in force.
    The same structure machine as run(); positions never change it (OB consumption only gates signals)."""
    atr = wilder_atr(bars)
    sh = sl_ = sh_prev = sl_prev = None
    ob_bot = None
    bos_l, ob_l = [], []
    for t, b in enumerate(bars):
        k = t - SWING
        if k >= SWING:
            hk, lk = bars[k].h, bars[k].l
            if all(hk > bars[j].h for j in range(k - SWING, k)) and all(hk > bars[j].h for j in range(k + 1, t + 1)):
                sh = hk
            if all(lk < bars[j].l for j in range(k - SWING, k)) and all(lk < bars[j].l for j in range(k + 1, t + 1)):
                sl_ = lk
        prev_c = bars[t - 1].c if t else None
        bos = bool(sh is not None and prev_c is not None and b.c > sh
                   and prev_c <= (sh_prev if sh_prev is not None else sh))
        if bos:
            i = next((i for i in range(1, OB_SCAN + 1) if t - i >= 0 and bars[t - i].c < bars[t - i].o), 1)
            ob_bot = bars[t - i].l
        bos_l.append(bos)
        ob_l.append(ob_bot)
        sh_prev, sl_prev = sh, sl_
    return dict(atr=atr, bos=bos_l, ob_bot=ob_l)


SUB_MIN = 5


def manage(bars: list[Bar], st: dict, k: int, risk: float) -> dict:
    """A long entered at bars[k].o with `risk`, managed exactly as run() manages it. Returns the exit:
    spot, reason, bars held, the exit bar index, and `end`: the end of the 5-minute bar the exit is priced
    at (a fill's own 5-minute bar; for the time stop, the hour bar's last 5-minute bar)."""
    e = bars[k].o
    stop, tgt, stop0 = e - risk, e + RR * risk, e - risk
    held = 0
    for t in range(k, len(bars)):
        b = bars[t]
        subs = b.subs or ((b.start, b.o, b.h, b.l, b.c),)
        out = None
        for s in subs:
            s0, so, shh, sll, _ = s
            if so <= stop:
                out = (so, "stop_gap", s0)
            elif so >= tgt:
                out = (so, "target_gap", s0)
            elif sll <= stop:
                out = (stop, "stop", s0)
            elif shh >= tgt:
                out = (tgt, "target", s0)
            if out:
                break
        held += 1
        if out is None and held >= MAX_HOLD:
            out = (b.c, "time", subs[-1][0])
        if out:
            px, reason, s0 = out
            if "stop" in reason and stop > stop0:
                reason += "_raised"
            return dict(exit=px, reason=reason, bars_held=held, t=t, end=s0 + timedelta(minutes=SUB_MIN),
                        entry=e, stop0=stop0, target=tgt)
        a = st["atr"][t]
        new = stop
        if b.h - e >= BE_R * risk:
            new = max(new, e + BE_PLUS)
        if a is not None and b.h - e >= TRAIL_R * risk:
            new = max(new, b.c - TRAIL_ATR * a)
        if st["bos"][t] and a is not None and st["ob_bot"][t] is not None and st["ob_bot"][t] > new:
            new = max(new, st["ob_bot"][t] - ATR_BUF * a)
        stop = max(stop, new)
    return dict(exit=None, reason="open", bars_held=held, t=len(bars) - 1, end=None, entry=e, stop0=stop0, target=tgt)
