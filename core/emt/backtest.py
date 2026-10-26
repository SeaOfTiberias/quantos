"""
QuantOS — EMT (exhaustion mean theory) backtest on NIFTY 5-minute bars
──────────────────────────────────────────────────────────────────────
Rules are fixed in docs/EMT_VWAP_METHODOLOGY.md. Pure functions over OHLCV
lists; scripts/backtest_emt_vwap.py does the fetching and the report.

Stretch away from the mean (k x ATR), then the first bar that closes back
toward it is the signal; enter at the next open, target the mean, stop beyond
the stretch extreme, flat at 15:15. Results are in index points.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from core.brokers.base import OHLCV

IST = timezone(timedelta(hours=5, minutes=30))
FIRST_ENTRY, LAST_ENTRY, FLAT_AT = time(9, 30), time(14, 30), time(15, 15)
MODES = ("vwap_ema", "vwap", "ema")


@dataclass
class Bar:
    t: datetime          # bar start, IST
    o: float
    h: float
    l: float
    c: float
    vwap: Optional[float]
    ema9: float
    atr: float


@dataclass
class Trade:
    day: date
    side: int            # +1 long, -1 short
    entry_t: datetime
    entry: float
    stop: float
    exit_t: datetime
    exit: float
    reason: str          # target | stop | eod

    @property
    def points(self) -> float:
        return self.side * (self.exit - self.entry)

    @property
    def risk(self) -> float:
        return abs(self.stop - self.entry)


def build_bars(index: list[OHLCV], fut: list[OHLCV], ema_n: int = 9, atr_n: int = 14) -> list[Bar]:
    """Index prices, session VWAP of (O+H+L+C)/4 weighted by futures volume, EMA9, Wilder ATR."""
    vol = {c.timestamp: c.volume for c in fut}
    bars: list[Bar] = []
    alpha = 2.0 / (ema_n + 1)
    ema = atr = None
    prev_close = None
    day = None
    pv = v = 0.0
    for c in sorted(index, key=lambda x: x.timestamp):
        t = c.timestamp.astimezone(IST)
        if t.date() != day:
            day, pv, v = t.date(), 0.0, 0.0
        w = float(vol.get(c.timestamp, 0) or 0)
        pv += (c.open + c.high + c.low + c.close) / 4.0 * w
        v += w
        tr = c.high - c.low if prev_close is None else max(c.high, prev_close) - min(c.low, prev_close)
        atr = tr if atr is None else atr + (tr - atr) / atr_n
        ema = c.close if ema is None else ema + alpha * (c.close - ema)
        prev_close = c.close
        bars.append(Bar(t, c.open, c.high, c.low, c.close, pv / v if v else None, ema, atr))
    return bars


def _mean(b: Bar, mode: str) -> Optional[float]:
    return b.ema9 if mode == "ema" else b.vwap


def _stretched(b: Bar, k: float, mode: str) -> int:
    m = _mean(b, mode)
    if m is None or b.atr <= 0:
        return 0
    d = b.c - m
    if d >= k * b.atr and (mode != "vwap_ema" or b.c > b.ema9):
        return 1
    if d <= -k * b.atr and (mode != "vwap_ema" or b.c < b.ema9):
        return -1
    return 0


def run_day(bars: list[Bar], k: float, mode: str = "vwap_ema", side: int = 0) -> list[Trade]:
    """side 0 takes both; +1 longs only, -1 shorts only (the other side's signals leave it flat)."""
    trades: list[Trade] = []
    armed, extreme = 0, 0.0
    pos: Optional[dict] = None
    pending: Optional[dict] = None       # signal at a close -> entry at the next open
    for i, b in enumerate(bars):
        tm = b.t.time()
        if pending is not None:
            if FIRST_ENTRY <= tm <= LAST_ENTRY:
                pos = {**pending, "entry": b.o, "entry_t": b.t}
            pending = None
        if pos is not None:
            side, stop, entry = pos["side"], pos["stop"], pos["entry"]
            target = _mean(bars[i - 1], mode)
            exit_px = reason = None
            if tm >= FLAT_AT:
                exit_px, reason = b.o, "eod"
            elif side < 0:
                if b.o > stop:
                    exit_px, reason = b.o, "stop"
                elif target is not None and b.o <= target:
                    exit_px, reason = b.o, "target"
                elif b.h > stop:
                    exit_px, reason = stop, "stop"
                elif target is not None and b.l <= target:
                    exit_px, reason = target, "target"
            else:
                if b.o < stop:
                    exit_px, reason = b.o, "stop"
                elif target is not None and b.o >= target:
                    exit_px, reason = b.o, "target"
                elif b.l < stop:
                    exit_px, reason = stop, "stop"
                elif target is not None and b.h >= target:
                    exit_px, reason = target, "target"
            if exit_px is not None:
                trades.append(Trade(b.t.date(), side, pos["entry_t"], entry, stop, b.t, exit_px, reason))
                pos = None
            continue                      # no new setups while in a trade (or on its exit bar)
        if i == 0:
            armed = 0
            s = _stretched(b, k, mode)
            if s:
                armed, extreme = s, (b.h if s > 0 else b.l)
            continue
        prev, m = bars[i - 1], _mean(b, mode)
        if armed:
            extreme = max(extreme, b.h) if armed > 0 else min(extreme, b.l)
            turned = b.c < prev.c if armed > 0 else b.c > prev.c
            if turned:
                still_out = m is not None and (b.c > m if armed > 0 else b.c < m)
                if still_out and side in (0, -armed):
                    pending = {"side": -armed, "stop": extreme}
                armed = 0
            continue
        s = _stretched(b, k, mode)
        if s:
            armed, extreme = s, (b.h if s > 0 else b.l)
    return trades


def by_day(bars: list[Bar]) -> dict[date, list[Bar]]:
    out: dict[date, list[Bar]] = {}
    for b in bars:
        out.setdefault(b.t.date(), []).append(b)
    return out


def run(bars: list[Bar], k: float, mode: str = "vwap_ema", days: Optional[set] = None,
        side: int = 0) -> list[Trade]:
    trades: list[Trade] = []
    for d, day_bars in sorted(by_day(bars).items()):
        if days is None or d in days:
            trades.extend(run_day(day_bars, k, mode, side))
    return trades


def metrics(trades: list[Trade], cost: float) -> dict:
    net = [t.points - cost for t in trades]
    n = len(net)
    if not n:
        return {"n": 0}
    mean = sum(net) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in net) / (n - 1)) if n > 1 else 0.0
    wins, losses = sum(x for x in net if x > 0), -sum(x for x in net if x < 0)
    eq = peak = dd = 0.0
    for x in net:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    reasons: dict[str, int] = {}
    for t in trades:
        reasons[t.reason] = reasons.get(t.reason, 0) + 1
    return {
        "n": n, "win": sum(1 for x in net if x > 0) / n, "mean_gross": sum(t.points for t in trades) / n,
        "mean_net": mean, "total_net": sum(net), "pf": wins / losses if losses else float("inf"),
        "t": mean / (sd / math.sqrt(n)) if sd else 0.0, "max_dd": dd,
        "avg_risk": sum(t.risk for t in trades) / n, "reasons": reasons,
    }
