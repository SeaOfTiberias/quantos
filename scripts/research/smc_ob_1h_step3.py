#!/usr/bin/env python3
"""Step 3 of docs/NIFTY_SMC_OB_1H_PREREG_2026-11-22.md: options, placebo, verdict. Grid (b), chosen at step 2.

    python scripts/research/smc_ob_1h_step3.py discovery       # 2019-02-11..2022-12-31; write it to the results doc
    python scripts/research/smc_ob_1h_step3.py confirmation    # refuses until the discovery table is in the doc
    python scripts/research/smc_ob_1h_step3.py diagnostics     # §8, both periods (after confirmation)

Frozen pieces reused unchanged: core/orb_scalping/premium.py (effective_days_to_expiry, TimeWeights),
core/options/greeks.py (compute_greeks), core/orb_scalping/expiry.py, core/orb_scalping/costs.py, and the
convention JSON in docs/ORB_TIME_CONVENTION_CALIBRATION.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import statistics as stx
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.backtest import smc_ob_1h as eng  # noqa: E402
from core.options.greeks import compute_greeks  # noqa: E402
from core.options.models import OptionType  # noqa: E402
from core.orb_scalping import costs as oc  # noqa: E402
from core.orb_scalping.expiry import (is_nifty_weekly_expiry_day, next_nifty_weekly_expiry,  # noqa: E402
                                      nifty_weekly_expiry)
from core.orb_scalping.premium import TimeWeights, effective_days_to_expiry  # noqa: E402
from core.reference import calendar as cal  # noqa: E402
from scripts.research import smc_ob_1h as s2  # noqa: E402

RESULTS = ROOT / "docs" / "NIFTY_SMC_OB_1H_RESULTS.md"
CALIB = ROOT / "docs" / "ORB_TIME_CONVENTION_CALIBRATION.md"
IST = timezone(timedelta(hours=5, minutes=30))
WEEKLY_FROM = date(2019, 2, 11)
DISC = (date(2019, 2, 11), date(2022, 12, 31))
CONF = (date(2023, 1, 1), date(2026, 11, 20))
PRE = (date(2018, 1, 1), date(2019, 2, 8))
LOT = 75
MIN_DTE = 6
STRIKE_OFFSET = -100
FUT_COST = 0.0004          # Gate A: futures-equivalent round trip, share of entry spot
N_PLACEBO = 2000
SEED = 20261122
SIG_TIME = {"am": time(10, 0), "pm": time(14, 0)}
SHA_VIX = "8bf1861bff73d3ad226c9b9482f71a2c48b9f2f152b80ad3e3e8ae22c466d18a"


# ─── setup ───────────────────────────────────────────────────────────────────

def frozen_convention() -> dict:
    block = re.search(r"## Frozen convention.*?```json\n(.*?)```", CALIB.read_text(encoding="utf-8"), re.S)
    return json.loads(block.group(1))


class World:
    def __init__(self):
        s2.check_hashes()
        import hashlib
        if hashlib.sha256((s2.DATA / "INDIAVIX_5.csv").read_bytes()).hexdigest() != SHA_VIX:
            raise SystemExit("INDIAVIX_5.csv hash differs from the frozen one")
        self.bars = s2.grid_b(s2.load_rows("NIFTY_5.csv"))
        self.idx = {b.start: i for i, b in enumerate(self.bars)}
        self.htf = s2.htf_filter(s2.DATA / "NIFTY_daily.csv")
        self.trades = eng.run(self.bars, self.htf, eng.GRID_B, allow_from=date(2017, 11, 22))
        self.st = eng.states(self.bars)
        self.vix = {r[0]: (r[1], r[4]) for r in s2.load_rows("INDIAVIX_5.csv")}
        self.vix_keys = sorted(self.vix)
        fz = frozen_convention()
        self.conv = {"frozen": (TimeWeights(fz["session"], fz["weeknight"], fz["weekend"]), fz["k_nifty"]),
                     "calendar": (TimeWeights.calendar(), 1.0),
                     "252-day": (TimeWeights.trading_252(), 1.0)}
        self.tdays = set(cal.trading_days(date(2017, 11, 22), date(2026, 12, 31)))
        self.per_day = defaultdict(int)
        for b in self.bars:
            self.per_day[b.start.date()] += 1
        self._check_manage()

    def _check_manage(self):
        """eng.manage must reproduce every exit run() produced (the placebo relies on it)."""
        for t in self.trades:
            k = self.idx[t.entry_time]
            m = eng.manage(self.bars, self.st, k, t.risk)
            if t.exit is None:
                continue
            if abs(m["exit"] - t.exit) > 1e-6 or m["reason"] != t.reason or m["bars_held"] != t.bars_held:
                raise SystemExit(f"manage() differs from run() on {t.entry_time}: {m} vs {t.exit} {t.reason}")

    def vix_at(self, ts: datetime, which: str) -> float:
        """VIX at a 5-minute bar: its open (entry) or close (exit). Falls back to the latest bar before."""
        v = self.vix.get(ts)
        if v is None:
            from bisect import bisect_right
            i = bisect_right(self.vix_keys, ts) - 1
            v = self.vix[self.vix_keys[i]]
        return v[0] if which == "open" else v[1]

    def expiry_for(self, d: date) -> date:
        """The nearest (holiday-adjusted) weekly expiry at least MIN_DTE calendar days after d. Walks the
        search date forward rather than calling next_nifty_weekly_expiry, which loops forever on an expiry
        that was moved earlier for a holiday (expiry + 1 day is the holiday Thursday itself)."""
        j = MIN_DTE
        e = nifty_weekly_expiry(d + timedelta(days=j), self.tdays)
        while (e - d).days < MIN_DTE:
            j += 1
            e = nifty_weekly_expiry(d + timedelta(days=j), self.tdays)
        return e


def utc(ts: datetime) -> datetime:
    return ts.replace(tzinfo=IST).astimezone(timezone.utc)


def price(spot, strike, expiry, at_ist, vix, conv) -> float:
    w, k = conv
    dte = effective_days_to_expiry(expiry, utc(at_ist), w)
    return compute_greeks(spot=spot, strike=strike, days_to_expiry=dte, implied_vol=k * vix / 100.0,
                          option_type=OptionType.CALL).theoretical_price


def option_trade(W: World, k: int, risk: float, offset: int = STRIKE_OFFSET, conv: str = "frozen") -> dict:
    """One long call: entry at bars[k].o, managed by eng.manage, priced and costed."""
    b = W.bars[k]
    m = eng.manage(W.bars, W.st, k, risk)
    if m["exit"] is None:
        return dict(m, open=True)
    t_in = b.subs[0][0]                                     # entry at this bar's open = its first 5m bar
    d = t_in.date()
    e = W.expiry_for(d)
    strike = round(m["entry"] / 50) * 50 + offset
    c = W.conv[conv]
    v_in = W.vix_at(t_in, "open")
    v_out = W.vix_at(m["end"] - timedelta(minutes=eng.SUB_MIN), "close")
    p_in = price(m["entry"], strike, e, t_in, v_in, c)
    p_out = price(m["exit"], strike, e, m["end"], v_out, c)
    decay = price(m["entry"], strike, e, m["end"], v_in, c) - p_in      # at constant spot and VIX
    exp_day = is_nifty_weekly_expiry_day(d, W.tdays)
    cost = {name: fn(p_in, p_out, LOT, d).total / LOT for name, fn in
            (("clean", oc.clean_trade_cost), ("stressed", oc.stressed_trade_cost))}
    cost["stratified"] = oc.stratified_spread_trade_cost(p_in, p_out, LOT, d, "NIFTY", exp_day).total / LOT
    spot_pts = m["exit"] - m["entry"]
    return dict(m, open=False, entry_time=t_in, exit_end=m["end"], expiry=e, strike=strike, p_in=p_in, p_out=p_out,
                decay=decay, cost=cost, spot_pts=spot_pts, spot_net=spot_pts - FUT_COST * m["entry"],
                net=(p_out - p_in - cost["stratified"]) / p_in,
                net_clean=(p_out - p_in - cost["clean"]) / p_in,
                net_stressed=(p_out - p_in - cost["stressed"]) / p_in)


def in_period(d: date, p) -> bool:
    return p[0] <= d <= p[1]


def real_rows(W: World, period, **kw) -> list[dict]:
    rows = []
    for t in W.trades:
        if not in_period(t.entry_time.date(), period):
            continue
        r = option_trade(W, W.idx[t.entry_time], t.risk, **kw)
        if r["open"]:
            continue
        r.update(window=t.window, risk=t.risk, atr=t.atr, risk_atr=t.risk / t.atr)
        rows.append(r)
    return rows


# ─── statistics ──────────────────────────────────────────────────────────────

def tstat(xs: list[float]) -> float:
    if len(xs) < 2:
        return float("nan")
    sd = stx.stdev(xs)
    return stx.mean(xs) / (sd / math.sqrt(len(xs))) if sd > 0 else float("inf")


def placebo(W: World, period, rows: list[dict]) -> dict:
    """§7: each real trade gets an entry drawn among the period's same-window, HTF-bullish bars of the same
    calendar year (no structure/POC/OB condition), copying its Initial_Risk in ATR units."""
    pools = defaultdict(list)
    for t, b in enumerate(W.bars[:-1]):
        d = b.start.date()
        if not in_period(d, period) or W.per_day[d] < eng.MIN_BARS_PER_DAY or W.st["atr"][t] is None:
            continue
        for win, st_ in SIG_TIME.items():
            if b.start.time() == st_ and W.bars[t + 1].start.date() == d and W.htf(d):
                pools[(d.year, win)].append(t)
    cache = {}
    per_trade = []
    for i, r in enumerate(rows):
        key = (r["entry_time"].year, r["window"])
        outs = []
        for c in pools[key]:
            ck = (c, round(r["risk_atr"], 6))
            if ck not in cache:
                o = option_trade(W, c + 1, r["risk_atr"] * W.st["atr"][c])
                cache[ck] = None if o["open"] else (o["net"], o["spot_net"])
            if cache[ck] is not None:
                outs.append(cache[ck])
        per_trade.append(outs)
    rng = random.Random(SEED)
    real = stx.mean(r["net"] for r in rows)
    real_spot = stx.mean(r["spot_net"] for r in rows)
    means, means_spot = [], []
    for _ in range(N_PLACEBO):
        picks = [rng.choice(o) for o in per_trade]
        means.append(stx.mean(p[0] for p in picks))
        means_spot.append(stx.mean(p[1] for p in picks))
    return dict(p=sum(m >= real for m in means) / N_PLACEBO, mean=stx.mean(means),
                p5=sorted(means)[int(0.05 * N_PLACEBO)], p95=sorted(means)[int(0.95 * N_PLACEBO)],
                p_spot=sum(m >= real_spot for m in means_spot) / N_PLACEBO, mean_spot=stx.mean(means_spot),
                pool=sum(len(v) for v in pools.values()))


def summary(W: World, period, name: str, p_bar: float, need_t: bool) -> tuple[str, bool]:
    rows = real_rows(W, period)
    n = len(rows)
    sn = [r["spot_net"] for r in rows]
    on = [r["net"] for r in rows]
    gate_a = stx.mean(sn) > 0
    pl = placebo(W, period, rows)
    t = tstat(on)
    ok = stx.mean(on) > 0 and pl["p"] <= p_bar and (t >= 2.0 or not need_t)
    if need_t:
        ok = ok and gate_a
    L = [f"**{name}, {period[0]} to {period[1]}: n = {n}**", "",
         "| Measure | Value |", "|---|---|",
         f"| Gate A: spot net points per trade (after {FUT_COST:.2%} round trip) | {stx.mean(sn):+.1f} "
         f"(gross {stx.mean(r['spot_pts'] for r in rows):+.1f}; t {tstat(sn):.2f}){' — FAILS Gate A' if not gate_a else ''} |",
         f"| Options: mean net return on premium (Stratified) | {stx.mean(on):+.2%} (median {stx.median(on):+.2%}) |",
         f"| One-sided t | {t:.2f} |",
         f"| Winners (net > 0) | {sum(x > 0 for x in on)} of {n} |",
         f"| Mean entry premium / mean decay paid (points) | {stx.mean(r['p_in'] for r in rows):.1f} / "
         f"{stx.mean(r['decay'] for r in rows):+.1f} |",
         f"| Mean cost per round trip (points) | {stx.mean(r['cost']['stratified'] for r in rows):.2f} |",
         f"| Placebo ({N_PLACEBO} sets, pool {pl['pool']} bars): mean of set means | {pl['mean']:+.2%} "
         f"(5th–95th pct {pl['p5']:+.2%} .. {pl['p95']:+.2%}) |",
         f"| Placebo p (share of sets ≥ real) | {pl['p']:.3f} |",
         f"| Placebo, spot: mean {pl['mean_spot']:+.1f} pts, p | {pl['p_spot']:.3f} |",
         f"| Clean / Stressed mean net | {stx.mean(r['net_clean'] for r in rows):+.2%} / "
         f"{stx.mean(r['net_stressed'] for r in rows):+.2%} |"]
    return "\n".join(L), ok


# ─── diagnostics (§8) ────────────────────────────────────────────────────────

def hold_group(r: dict, W: World) -> str:
    d0, d1 = r["entry_time"].date(), r["exit_end"].date()
    if d0 == d1:
        return "intraday"
    days = sorted(x for x in W.tdays if d0 <= x <= d1)
    gaps = [(b - a).days for a, b in zip(days, days[1:])]
    return "weekend/holiday gap" if any(g > 1 for g in gaps) else "weeknight only"


def diagnostics(W: World) -> str:
    out = ["### Diagnostics (§8; reported, not scored)", ""]
    periods = (("discovery", DISC), ("confirmation", CONF))
    by_conv = {c: {p: real_rows(W, per, conv=c) for p, per in periods} for c in W.conv}

    # Friday and weekend holds
    out += ["**Holds by overnight gap, both periods together** (mean net return on premium, Stratified):", "",
            "| Group | n | Spot pts | Net (frozen) | Decay paid, pts (frozen) | Net (calendar) | Net (252-day) |",
            "|---|---|---|---|---|---|---|"]
    allc = {c: by_conv[c]["discovery"] + by_conv[c]["confirmation"] for c in W.conv}
    groups = defaultdict(lambda: defaultdict(list))
    for c, rows in allc.items():
        for r in rows:
            g = hold_group(r, W)
            groups[g][c].append(r)
            if r["entry_time"].weekday() == 4:
                groups["  of which Friday entries" if g == "weekend/holiday gap" else f"  Friday entries, {g}"][c].append(r)
    order = ["intraday", "weeknight only", "weekend/holiday gap", "  of which Friday entries"]
    for g in order + [k for k in groups if k not in order]:
        if g not in groups:
            continue
        fr = groups[g]["frozen"]
        m = lambda rs, k: stx.mean(x[k] for x in rs) if rs else float("nan")  # noqa: E731
        out.append(f"| {g} | {len(fr)} | {m(fr, 'spot_pts'):+.1f} | {m(fr, 'net'):+.2%} | {m(fr, 'decay'):+.1f} | "
                   f"{m(groups[g]['calendar'], 'net'):+.2%} | {m(groups[g]['252-day'], 'net'):+.2%} |")

    fz = {p: by_conv["frozen"][p] for p, _ in periods}

    def table(title, key_fn, rows_by_p):
        L = ["", f"**{title}:**", "", "| | Discovery n | Discovery net | Confirmation n | Confirmation net |", "|---|---|---|---|---|"]
        keys = sorted({key_fn(r) for p in rows_by_p for r in rows_by_p[p]})
        for k in keys:
            cells = []
            for p, _ in periods:
                rs = [r for r in rows_by_p[p] if key_fn(r) == k]
                cells += [str(len(rs)), f"{stx.mean(r['net'] for r in rs):+.2%}" if rs else "—"]
            L.append(f"| {k} | " + " | ".join(cells) + " |")
        return L
    out += table("By entry window", lambda r: "11:00" if r["window"] == "am" else "15:00", fz)
    out += table("By exit reason", lambda r: r["reason"], fz)
    out += table("By year", lambda r: str(r["entry_time"].year), fz)

    out += ["", "**Strike (frozen convention, Stratified):**", "", "| Strike | Discovery net | Confirmation net |", "|---|---|---|"]
    for name, off in (("ITM-2 (scored)", -100), ("ITM-1", -50), ("ATM", 0)):
        vals = [stx.mean(r["net"] for r in real_rows(W, per, offset=off)) for _, per in periods]
        out.append(f"| {name} | {vals[0]:+.2%} | {vals[1]:+.2%} |")

    pre = [t for t in W.trades if in_period(t.entry_time.date(), PRE) and t.exit is not None]
    pts = [t.exit - t.entry for t in pre]
    out += ["", f"**Pre-weekly stretch {PRE[0]} to {PRE[1]} (spot only, not scored):** n {len(pre)}, "
            f"mean gross {stx.mean(pts):+.1f} pts, net {stx.mean(p - FUT_COST * t.entry for p, t in zip(pts, pre)):+.1f} pts." if pre else ""]

    tv = {(e["ts"].date(), e["window"]): e for e in s2.tv_entries()}
    pairs = [(t, tv[(t.entry_time.date(), t.window)]) for t in W.trades
             if (t.entry_time.date(), t.window) in tv and t.exit is not None and t.entry_time.date() >= s2.REPRO_FROM]
    ours = sum(t.exit - t.entry for t, _ in pairs)
    theirs = sum(e["exit"]["price"] - e["price"] for _, e in pairs)
    out += ["", f"**Spot against the TradingView export, matched trades ({len(pairs)}):** this engine {ours:+.0f} pts, "
            f"TradingView {theirs:+.0f} pts."]
    out += [""] + pricing_check(W)
    rec = [r for p in fz for r in fz[p] if r["entry_time"].date() >= date(2026, 9, 30)]
    out += ["", f"**Real recorded quotes (option-chain recorder, since 2026-09-30):** {len(rec)} trades in that span"
            + ("." if rec else ": nothing to compare.")]
    return "\n".join(out)


def pricing_check(W: World) -> list[str]:
    """Model price of each trade's contract at 15:30 on its entry date vs the NSE bhavcopy close."""
    bdir = ROOT / "data_cache" / "nse_bhavcopy" / "parsed"
    errs = {"pre-registered span 2023-07..2026-07, 15:00 entries": [], "every entry 2019-02..2026-10": []}
    conv = W.conv["frozen"]
    for p in (DISC, CONF):
        for r in real_rows(W, p):
            d = r["entry_time"].date()
            f = bdir / f"{d:%Y%m%d}.csv"
            if not f.exists():
                continue
            close = spot = None
            with f.open() as fh:
                for row in csv.DictReader(fh):
                    if (row["underlying"] == "NIFTY" and row["option_type"] == "CE" and row["expiry"] == r["expiry"].isoformat()
                            and abs(float(row["strike"]) - r["strike"]) < 1e-6):
                        if row["close"] and row["underlying_close"]:
                            close, spot = float(row["close"]), float(row["underlying_close"])
                        break
            if not close:
                continue
            at = datetime.combine(d, time(15, 25))
            model = price(spot, r["strike"], r["expiry"], at + timedelta(minutes=5), W.vix_at(at, "close"), conv)
            e = abs(model - close) / close
            errs["every entry 2019-02..2026-10"].append(e)
            if r["window"] == "pm" and date(2023, 7, 1) <= d <= date(2026, 7, 31):
                errs["pre-registered span 2023-07..2026-07, 15:00 entries"].append(e)
    L = ["**Pricing check against NSE end-of-day option closes** (model at 15:30 spot and VIX vs the contract's "
         "bhavcopy close, entry day):", "", "| Span | n | Median abs error | 90th pct |", "|---|---|---|---|"]
    for k, v in errs.items():
        L.append(f"| {k} | {len(v)} | {stx.median(v):.1%} | {sorted(v)[int(0.9 * (len(v) - 1))]:.1%} |" if v else f"| {k} | 0 | — | — |")
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["discovery", "confirmation", "diagnostics"])
    a = ap.parse_args(argv)
    W = World()
    if a.step == "discovery":
        txt, ok = summary(W, DISC, "Discovery", 0.05, need_t=True)
        print(txt)
        print(f"\nDiscovery verdict: {'GOES ON to confirmation' if ok else 'FAIL (does not go on)'}")
    elif a.step == "confirmation":
        if "## Step 3a: discovery" not in RESULTS.read_text(encoding="utf-8"):
            raise SystemExit("Write the discovery table to the results doc first (pre-registration §6, step 3).")
        txt, ok = summary(W, CONF, "Confirmation", 0.10, need_t=False)
        print(txt)
        print(f"\nConfirmation: {'PASS' if ok else 'FAIL'}")
    else:
        print(diagnostics(W))
    return 0


if __name__ == "__main__":
    sys.exit(main())
