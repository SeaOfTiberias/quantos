#!/usr/bin/env python3
"""
QuantOS desk edge E1, phase 1: is the stock-option straddle overpriced across a results announcement?
Pre-registration: docs/E1_RESULTS_VOL_PREREG_2026-11-27.md.

    python scripts/measure_results_straddle.py --check     # event and data counts only, no P&L
    python scripts/measure_results_straddle.py --worked    # 5 events + their controls by hand
    python scripts/measure_results_straddle.py             # the full measurement (after sign-off + spread calibration)

Per event (core/fno/results_events.py): P = last session closed before the broadcast, R = the next
session. At P's close: the stock's near-month future (nearest expiry after R) gives the spot; the
straddle is the strike nearest that spot where both legs traded on the nearest option expiry after R.
Sold at P's close, bought back at R's close (same strike, both legs traded at R). Control: the same
stock and structure on the session SESSIONS_BACK before P, if no results event of that stock falls
within CONTROL_GAP sessions of it.
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.fno import bhavcopy_futures as bf      # noqa: E402
from core.fno import bhavcopy_options as bo      # noqa: E402
from core.fno import results_events as rev       # noqa: E402

START, END = date(2019, 2, 11), date(2026, 10, 31)       # broadcast window
HALF_SPLIT = date(2023, 1, 1)
SESSIONS_BACK, CONTROL_GAP = 10, 5
COST_DATE = date(2026, 4, 1)                             # verdict costs: today's rates
SPREAD_HALF = None                                       # half-spread per leg per side, fraction of premium: set from the calibration
T_PASS = 2.0
RAW = Path("data_cache/nse_bhavcopy/raw")
STAMP_BUY = 0.00003                                      # stamp duty on option buys, 0.003% of premium
# Amendment 1: Muhurat sessions (one-hour Diwali sessions) are in the bhavcopy-derived calendar as
# ordinary days; weekday ones are dropped from the session list like the weekend specials.
MUHURAT = {date(2019, 10, 27), date(2020, 11, 14), date(2021, 11, 4), date(2022, 10, 24), date(2023, 11, 12),
           date(2024, 11, 1), date(2025, 10, 21), date(2026, 11, 8)}


@dataclass(frozen=True)
class Trade:
    symbol: str
    p: date
    r: date
    expiry: date
    spot: float
    spot_r: float
    strike: float
    s_p: float                     # straddle at P (call + put closes)
    s_r: float                     # same straddle at R
    broadcast: Optional[str] = None

    @property
    def gross_bps(self) -> float:             # short straddle P&L, bps of spot
        return (self.s_p - self.s_r) / self.spot * 1e4

    @property
    def implied_move(self) -> float:          # straddle / spot (whole remaining tenor)
        return self.s_p / self.spot

    @property
    def realized_move(self) -> float:
        return abs(self.spot_r / self.spot - 1)


def cost_bps(t: Trade, spread_half: float) -> float:
    """Round trip at 2026 rates: sell both legs at P (STT on premium), buy both back at R (no STT,
    stamp duty), plus the spread haircut on both sides; bps of spot."""
    from core.options.vrp.costs import entry_leg_cost
    sell = entry_leg_cost(t.s_p, COST_DATE).total
    buy_c = entry_leg_cost(t.s_r, COST_DATE)
    buy = buy_c.total - buy_c.stt + STAMP_BUY * t.s_r
    spread = spread_half * (t.s_p + t.s_r)
    return (sell + buy + spread) / t.spot * 1e4


def build_trade(sym: str, p: date, r: date, day: dict, broadcast: Optional[str] = None) -> tuple[Optional[Trade], str]:
    """day: date -> (futures rows, option rows). Returns (trade, reason) where reason names the
    first missing piece."""
    if p not in day or r not in day:
        return None, "no file"
    futs_p, opts_p = day[p]
    futs_r, opts_r = day[r]
    fut = bf.contract_after(futs_p, sym, r)                       # expiry strictly after R
    if fut is None or fut.close <= 0:
        return None, "not in F&O"
    fr = [x for x in futs_r if x.symbol == sym and x.expiry == fut.expiry]
    if not fr:
        return None, "no future at R"
    exps = sorted({o.expiry for o in opts_p if o.symbol == sym and o.expiry > r})
    if not exps:
        return None, "no option expiry after R"
    st = bo.atm_straddle(opts_p, sym, exps[0], fut.close)
    if st is None:
        return None, "no traded ATM straddle at P"
    k, c, pu = st
    at_r = {o.opt: o for o in opts_r if o.symbol == sym and o.expiry == exps[0] and o.strike == k
            and o.volume > 0 and o.close > 0}
    if "CE" not in at_r or "PE" not in at_r:
        return None, "straddle not traded at R"
    return Trade(sym, p, r, exps[0], fut.close, fr[0].close, k, c.close + pu.close,
                 at_r["CE"].close + at_r["PE"].close, broadcast), "ok"


def plan(events: list, sessions: list[date]) -> tuple[list, dict[date, set]]:
    """[(event, (P, R), control (P', R') or None)], and date -> symbols needed."""
    idx = {d: i for i, d in enumerate(sessions)}
    by_sym = defaultdict(list)
    rows = []
    for e in events:
        pr = rev.pre_and_reaction(e.broadcast, sessions)
        if pr:
            by_sym[e.symbol].append(idx[pr[0]])
            rows.append((e, pr))
    out, need = [], defaultdict(set)
    for e, (p, r) in rows:
        ip = idx[p] - SESSIONS_BACK
        ctl = None
        if ip >= 0 and all(abs(ip - j) > CONTROL_GAP and abs(ip + 1 - j) > CONTROL_GAP for j in by_sym[e.symbol]):
            ctl = (sessions[ip], sessions[ip + 1])
        out.append((e, (p, r), ctl))
        for d in (p, r) + (ctl or ()):
            need[d].add(e.symbol)
    return out, need


def load_days(need: dict[date, set]) -> dict:
    day = {}
    for d in sorted(need):
        f = RAW / f"{d:%Y%m%d}.zip"
        if not f.exists():
            continue
        text = bo.read_zip_text(f.read_bytes())
        day[d] = (bf.parse_csv(text, d, need[d], kind="stock"), bo.parse_csv(text, d, need[d]))
    return day


def t_monthly(xs: list[tuple[date, float]]) -> tuple[float, int]:
    """t-statistic over calendar-month means (results cluster in seasons), months with >= 5 events."""
    m = defaultdict(list)
    for d, x in xs:
        m[(d.year, d.month)].append(x)
    means = [statistics.mean(v) for v in m.values() if len(v) >= 5]
    if len(means) < 3:
        return float("nan"), len(means)
    sd = statistics.stdev(means)
    return (statistics.mean(means) / (sd / math.sqrt(len(means))) if sd else float("nan")), len(means)


def paired_t(a: list[float], b: list[float]) -> float:
    d = [x - y for x, y in zip(a, b)]
    sd = statistics.stdev(d) if len(d) > 2 else 0
    return statistics.mean(d) / (sd / math.sqrt(len(d))) if sd else float("nan")


def verdict(trades: list[Trade], pairs: list[tuple[Trade, Trade]], spread_half: float) -> dict:
    net = [(t.p, t.gross_bps - cost_bps(t, spread_half)) for t in trades]
    t_all, months = t_monthly(net)
    h1 = [x for d, x in net if d < HALF_SPLIT]
    h2 = [x for d, x in net if d >= HALF_SPLIT]
    mean = statistics.mean(x for _, x in net)
    ev = [a.gross_bps for a, _ in pairs]
    cl = [b.gross_bps for _, b in pairs]
    pt = paired_t(ev, cl)
    checks = {
        "1 net mean > 0, monthly-cluster t >= 2.0": mean > 0 and t_all >= T_PASS,
        "2 net mean > 0 in both halves": statistics.mean(h1) > 0 and statistics.mean(h2) > 0,
        "3 event gross beats its control, paired t >= 2.0": statistics.mean(ev) > statistics.mean(cl) and pt >= T_PASS,
    }
    return dict(n=len(net), mean=mean, t=t_all, months=months, h1=statistics.mean(h1), h2=statistics.mean(h2),
                ev=statistics.mean(ev), cl=statistics.mean(cl), pt=pt, npairs=len(pairs),
                checks=checks, alive=all(checks.values()))


def main(argv=None) -> int:
    from core.reference.calendar import trading_days
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--worked", action="store_true")
    a = ap.parse_args(argv)
    sessions = [d for d in trading_days(date(2019, 1, 1), date(2026, 11, 27)) if d.weekday() < 5 and d not in MUHURAT]
    events = [e for e in rev.load_events() if START <= e.broadcast.date() <= END]
    rows, need = plan(events, sessions)
    print(f"{len(events)} results events {START}..{END}; {len(need)} session files needed", flush=True)
    day = load_days(need)
    trades, reasons, pairs, ctl_reasons = [], Counter(), [], Counter()
    for e, (p, r), ctl in rows:
        t, why = build_trade(e.symbol, p, r, day, e.broadcast.isoformat(sep=" "))
        reasons[why] += 1
        if t is None:
            continue
        trades.append(t)
        if ctl:
            c, cw = build_trade(e.symbol, ctl[0], ctl[1], day)
            ctl_reasons[cw] += 1
            if c:
                pairs.append((t, c))
        else:
            ctl_reasons["no clean control session"] += 1
    out = [f"## Data check", "", f"Events {len(rows)} (with P/R sessions). Outcome per event:", ""]
    out += [f"- {k}: {v}" for k, v in reasons.most_common()]
    out += ["", "Controls for usable events:", ""] + [f"- {k}: {v}" for k, v in ctl_reasons.most_common()]
    by_year = Counter(t.p.year for t in trades)
    out += ["", "Usable events by year: " + ", ".join(f"{y} {n}" for y, n in sorted(by_year.items())),
            f"Distinct stocks: {len({t.symbol for t in trades})}; paired with a control: {len(pairs)}.",
            "Days from P to option expiry (quartiles): "
            + (", ".join(str(int(q)) for q in statistics.quantiles([(t.expiry - t.p).days for t in trades], n=4)) if len(trades) > 4 else "n/a"),
            ""]
    if a.check:
        sys.stdout.buffer.write("\n".join(out).encode("utf-8"))
        return 0
    if a.worked:
        picks = [trades[i * len(trades) // 5] for i in range(5)]
        ctl_of = {id(x): c for x, c in pairs}
        w = ["## Worked events", "", "| Stock | Broadcast | P | R | Expiry | Spot P | Spot R | Strike | Straddle P | Straddle R | Gross bps | Control P | Control gross bps |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for t in picks:
            c = ctl_of.get(id(t))
            w.append(f"| {t.symbol} | {t.broadcast} | {t.p} | {t.r} | {t.expiry} | {t.spot:.2f} | {t.spot_r:.2f} | {t.strike:g} | "
                     f"{t.s_p:.2f} | {t.s_r:.2f} | {t.gross_bps:+.1f} | {c.p if c else '-'} | {f'{c.gross_bps:+.1f}' if c else '-'} |")
        sys.stdout.buffer.write("\n".join(out + w).encode("utf-8"))
        return 0
    if SPREAD_HALF is None:
        raise SystemExit("SPREAD_HALF not set: run the pre-registered spread calibration first")
    v = verdict(trades, pairs, SPREAD_HALF)
    sys.stdout.buffer.write(("\n".join(out) + "\n" + repr(v)).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
