#!/usr/bin/env python3
"""
QuantOS — Trend-day filter (candidate 21), stage 1: index points (2026-10-01)
──────────────────────────────────────────────────────────────────────────────
Written BEFORE it was run. Motivation: in candidate 18 (ORB) and in the user's
EMA 9/20 TradingView runs, the few trades that stayed open into the close made
large moves (NIFTY EMA put: 35 session_flatten exits averaged +46 pts) while the
bulk bled on choppy days. Hypothesis: a trend day can be recognised by 10:30 IST
with information available at that time, and trading only those days with a wide
trail earns enough index points to clear costs.

PRIMARY RULE (the only one the verdict is based on; no parameter is tuned):
  Decision at 10:30 IST, using only the 5-min bars that close by 10:30.
  Trend day = BOTH
    (A) the 10:25 bar's close is beyond the opening range (09:15-09:30 high/low),
    (B) the 09:15-10:30 range >= 1.25 x the median of the same window over the
        prior 20 trading days.
  Direction = the side of the opening range the 10:25 close is on.
  Entry: at the open of the first bar from 10:30 on where EMA 9 vs EMA 20 (5-min
    closes, continuous across days, as TradingView computes them) agrees with the
    direction; no entry from 14:30 on. One trade per day.
  Exit: a trailing stop 2 x ATR(14, 5-min) behind the best close since entry,
    set on each bar close and live from the next bar (a gap through it fills at
    the bar's open), or at the open of the 15:20 bar.
  Cost: 1 lot of index futures (scripts/backtest_orb_exits.futures_cost:
    brokerage, STT, exchange, SEBI, stamp, GST, 1 pt slippage each way).

PRE-REGISTERED BAR, per index, never pooled:
  futures net PF > 1 AND per-trade net t > 3 over the full sample
  AND mean net > 0 in the holdout (entries from 2025-01-01).
  Only a pass goes on to stage 2 (option pricing on the calibrated convention
  and real recorded chains). A fail closes the primary rule.

Reported DESCRIPTIVELY only (cannot rescue a fail; multiple-testing):
  - the same entry/exit on ALL days (no trend filter), to show what the filter adds;
  - the primary rule with a hold-to-15:20 exit instead of the trail;
  - the primary rule plus "India VIX at 10:30 above its 09:15 open";
  - the primary rule plus "gap > 0.3% from the prior close, unfilled by 10:30".

Offline (data_cache/orb_fix2_candles.pkl). Usage:
    python scripts/backtest_trend_day_filter.py [--out docs/TREND_DAY_FILTER_RESULTS.md]
"""
from __future__ import annotations

import argparse
import math
import pickle
import statistics
import sys
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.orb_scalping.backtest import BANKNIFTY_LOT_SIZE, NIFTY_LOT_SIZE  # noqa: E402
from scripts.backtest_orb_exits import futures_cost, t_stat  # noqa: E402

CANDLES = Path("data_cache/orb_fix2_candles.pkl")

# IST times expressed in UTC (IST = UTC+5:30); bar times are bar OPEN times.
OR_END = time(4, 0)           # 09:30 IST: opening range = bars opening before this
DECISION = time(5, 0)         # 10:30 IST: bars opening before this are known
LAST_ENTRY = time(9, 0)       # 14:30 IST
FLATTEN = time(9, 50)         # 15:20 IST
GAP_PCT = 0.003
RANGE_MULT = 1.25
RANGE_LOOKBACK = 20
ATR_LEN = 14
TRAIL_ATR = 2.0
HOLDOUT_FROM = date(2025, 1, 1)


@dataclass
class Trade:
    day: date
    direction: int        # +1 long / -1 short
    entry: float
    exit: float
    reason: str
    trend: bool
    vix_up: bool
    gap_unfilled: bool

    @property
    def pts(self) -> float:
        return (self.exit - self.entry) * self.direction


def ema(values: list[float], n: int) -> list[float]:
    k, out = 2 / (n + 1), []
    for v in values:
        out.append(v if not out else out[-1] + k * (v - out[-1]))
    return out


def atr(candles, n: int) -> list[float]:
    """Wilder ATR, as TradingView's ta.atr."""
    out, prev_close = [], None
    for c in candles:
        tr = c.high - c.low if prev_close is None else max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
        out.append(tr if not out else out[-1] + (tr - out[-1]) / n)
        prev_close = c.close
    return out


def simulate(candles, vix_by_day: dict, hold_to_close: bool = False, use_filter: bool = True) -> list[Trade]:
    closes = [c.close for c in candles]
    e9, e20, a14 = ema(closes, 9), ema(closes, 20), atr(candles, ATR_LEN)
    days: dict[date, list[int]] = {}
    for i, c in enumerate(candles):
        days.setdefault(c.timestamp.date(), []).append(i)
    trades, ranges, prev_close = [], [], None
    for day in sorted(days):
        idx = days[day]
        early = [i for i in idx if candles[i].timestamp.time() < DECISION]
        orng = [i for i in idx if candles[i].timestamp.time() < OR_END]
        if len(orng) < 3 or len(early) < 15:
            prev_close = candles[idx[-1]].close
            continue
        or_hi, or_lo = max(candles[i].high for i in orng), min(candles[i].low for i in orng)
        win_rng = max(candles[i].high for i in early) - min(candles[i].low for i in early)
        last = candles[early[-1]].close
        direction = 1 if last > or_hi else -1 if last < or_lo else 0
        expanded = len(ranges) >= RANGE_LOOKBACK and win_rng >= RANGE_MULT * statistics.median(ranges[-RANGE_LOOKBACK:])
        ranges.append(win_rng)
        trend = direction != 0 and expanded
        open_ = candles[idx[0]].open
        gap_unfilled = False
        if prev_close:
            g = (open_ - prev_close) / prev_close
            if abs(g) > GAP_PCT:
                lo, hi = min(candles[i].low for i in early), max(candles[i].high for i in early)
                gap_unfilled = (g > 0 and lo > prev_close) or (g < 0 and hi < prev_close)
        vx = vix_by_day.get(day, [])
        vx_early = [v for v in vx if v.timestamp.time() < DECISION]
        vix_up = bool(vx_early) and vx_early[-1].close > vx_early[0].open
        prev_close = candles[idx[-1]].close
        if use_filter and not trend:
            continue
        if direction == 0:
            continue
        # Entry: first bar from 10:30 whose PRIOR bar's EMA alignment agrees.
        after = [i for i in idx if candles[i].timestamp.time() >= DECISION]
        entry_i = next((i for i in after if candles[i].timestamp.time() < LAST_ENTRY
                        and (e9[i - 1] - e20[i - 1]) * direction > 0), None)
        if entry_i is None:
            continue
        entry = candles[entry_i].open
        best, stop, exit_px, reason = entry, None, None, None
        for i in [j for j in after if j >= entry_i]:
            c = candles[i]
            if c.timestamp.time() >= FLATTEN:
                exit_px, reason = c.open, "session_flatten"
                break
            if stop is not None:
                if direction == 1 and c.low <= stop:
                    exit_px, reason = min(stop, c.open), "trailing_stop"
                    break
                if direction == -1 and c.high >= stop:
                    exit_px, reason = max(stop, c.open), "trailing_stop"
                    break
            best = max(best, c.close) if direction == 1 else min(best, c.close)
            if not hold_to_close:
                lvl = best - direction * TRAIL_ATR * a14[i]
                stop = lvl if stop is None else (max(stop, lvl) if direction == 1 else min(stop, lvl))
        if exit_px is None:          # session ended early (special/half day)
            exit_px, reason = candles[idx[-1]].close, "day_end"
        trades.append(Trade(day, direction, entry, exit_px, reason, trend, vix_up, gap_unfilled))
    return trades


def stats_row(label: str, trades: list[Trade], lot: int) -> tuple[str, dict]:
    if len(trades) < 2:
        return f"| {label} | {len(trades)} | — | — | — | — | — | — | — |", {}
    pts = [t.pts for t in trades]
    net = [t.pts * lot - futures_cost(t.entry, t.exit, lot) for t in trades]
    w, l = sum(x for x in net if x > 0), -sum(x for x in net if x <= 0)
    pf = w / l if l else float("inf")
    ho = [n for t, n in zip(trades, net) if t.day >= HOLDOUT_FROM]
    ho_mean = statistics.mean(ho) if ho else float("nan")
    t = t_stat(net)
    row = (f"| {label} | {len(trades)} | {statistics.mean(pts):+.1f} | {t_stat(pts):.2f} | "
           f"{sum(1 for x in net if x > 0) / len(net):.0%} | {pf:.2f} | {statistics.mean(net):+,.0f} | {t:.2f} | "
           f"{ho_mean:+,.0f} (n={len(ho)}) |")
    return row, dict(pf=pf, t=t, ho_mean=ho_mean)


def run(data: dict) -> str:
    vix_by_day: dict[date, list] = {}
    for v in data["vix"]:
        vix_by_day.setdefault(v.timestamp.date(), []).append(v)
    head = ("| Rule | N | Gross pts/trade | t (pts) | Win (net) | PF (net) | Net Rs/trade | t (net) | Holdout net Rs/trade |\n"
            "|---|---|---|---|---|---|---|---|---|")
    out = ["# Trend-day filter (candidate 21) — stage 1, index points", "",
           "Rules and the pre-registered bar: `scripts/backtest_trend_day_filter.py` docstring, committed before "
           "this run. 1 lot of index futures; costs = scripts/backtest_orb_exits.futures_cost. "
           f"Holdout = entries from {HOLDOUT_FROM}.", ""]
    for und, key, lot in (("NIFTY", "nifty", NIFTY_LOT_SIZE), ("BANKNIFTY", "banknifty", BANKNIFTY_LOT_SIZE)):
        prim = simulate(data[key], vix_by_day)
        r, m = stats_row("**PRIMARY** trend day, 2xATR trail", prim, lot)
        ok = bool(m) and m["pf"] > 1 and m["t"] > 3 and m["ho_mean"] > 0
        rows = [r]
        rows.append(stats_row("all days (no filter), 2xATR trail", simulate(data[key], vix_by_day, use_filter=False), lot)[0])
        hold = simulate(data[key], vix_by_day, hold_to_close=True)
        rows.append(stats_row("trend day, hold to 15:20", hold, lot)[0])
        rows.append(stats_row("trend day + VIX rising", [t for t in prim if t.vix_up], lot)[0])
        rows.append(stats_row("trend day + unfilled gap", [t for t in prim if t.gap_unfilled], lot)[0])
        from collections import Counter
        reasons = ", ".join(f"{k} {v}" for k, v in Counter(t.reason for t in prim).most_common())
        years = Counter(t.day.year for t in prim)
        by_year = ", ".join(f"{y}: {statistics.mean([t.pts for t in prim if t.day.year == y]):+.1f} pts (n={n})"
                            for y, n in sorted(years.items()))
        out += [f"## {und} — verdict: **{'PASS -> stage 2' if ok else 'FAIL'}**", "", head, *rows, "",
                f"Primary exits: {reasons}", "", f"Primary by year: {by_year}", ""]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="docs/TREND_DAY_FILTER_RESULTS.md")
    args = ap.parse_args(argv)
    report = run(pickle.loads(CANDLES.read_bytes()))
    Path(args.out).write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
