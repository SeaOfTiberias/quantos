#!/usr/bin/env python3
"""NIFTY 1H SMC-OB, bull put credit spread (docs/NIFTY_SMC_OB_1H_BULLPUT_PREREG_2026-11-22.md).

    python scripts/research/smc_ob_1h_bullput.py calibrate   # step 1a: put skew from the bhavcopy -> frozen JSON
    python scripts/research/smc_ob_1h_bullput.py check       # step 1c: spread pricing vs bhavcopy closes, entry days
    python scripts/research/smc_ob_1h_bullput.py cases       # step 1d: 5 worked spreads on placebo-pool entries

    python scripts/research/smc_ob_1h_bullput.py discovery     # step 2 (user go-ahead 2026-11-23)
    python scripts/research/smc_ob_1h_bullput.py confirmation  # refuses until the discovery table is in the results doc
    python scripts/research/smc_ob_1h_bullput.py diagnostics   # §8, reported only
    python scripts/research/smc_ob_1h_bullput.py export        # per-trade CSV
Reuses scripts/research/smc_ob_1h_step3.py (World, expiry rule, frozen convention) unchanged.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics as stx
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.backtest import bull_put as bp  # noqa: E402
from core.backtest import smc_ob_1h as eng  # noqa: E402
from core.options.greeks import ImpliedVolatilityError, compute_greeks, implied_volatility  # noqa: E402
from core.options.models import OptionType  # noqa: E402
from core.orb_scalping.premium import effective_days_to_expiry  # noqa: E402
from scripts.research import smc_ob_1h_step3 as s3  # noqa: E402

BHAV = ROOT / "data_cache" / "nse_bhavcopy" / "parsed"
SKEW_JSON = ROOT / "docs" / "research" / "nifty_put_skew_2026-11-23.json"
CAL_FROM, CAL_TO = date(2019, 2, 11), date(2026, 10, 31)
DTE_LO, DTE_HI = 6, 10
MIN_VOL, MIN_CLOSE = 100, 0.5
Z_STEP, Z_MIN = 0.25, -3.0
CLOSE_1530 = time(15, 30)
CASE_SEED = 20261123
CASE_RISK_ATR = 1.2


def conv_frozen():
    fz = s3.frozen_convention()
    from core.orb_scalping.premium import TimeWeights
    return TimeWeights(fz["session"], fz["weeknight"], fz["weekend"]), fz["k_nifty"]


def dte(expiry: date, at_ist: datetime, w) -> float:
    return effective_days_to_expiry(expiry, s3.utc(at_ist), w)


_DAILY: dict = {}


def nse_close(d: date):
    """NSE's official NIFTY close (frozen daily file). Fills the bhavcopy's underlying_close, blank before 2023
    (amendment 1, 2026-11-23)."""
    if not _DAILY:
        with (s3.s2.DATA / "NIFTY_daily.csv").open() as fh:
            for row in csv.DictReader(fh):
                _DAILY[date.fromisoformat(row["date"][:10])] = float(row["c"])
    return _DAILY.get(d)


def bhav_rows(d: date) -> list[dict]:
    f = BHAV / f"{d:%Y%m%d}.csv"
    if not f.exists():
        return []
    with f.open() as fh:
        rows = [r for r in csv.DictReader(fh) if r["underlying"] == "NIFTY" and r["option_type"] in ("CE", "PE")]
    c = nse_close(d)
    for r in rows:
        if not r["underlying_close"] and c is not None:
            r["underlying_close"] = str(c)
    return rows


def underlying_agreement() -> tuple[int, float]:
    """Where the bhavcopy has underlying_close, its gap to the daily file's close (max abs, points)."""
    n, worst = 0, 0.0
    for f in sorted(BHAV.glob("*.csv")):
        d = datetime.strptime(f.stem, "%Y%m%d").date()
        with f.open() as fh:
            for r in csv.DictReader(fh):
                if r["underlying"] == "NIFTY" and r["underlying_close"]:
                    c = nse_close(d)
                    if c is not None:
                        n += 1
                        worst = max(worst, abs(float(r["underlying_close"]) - c))
                    break
    return n, worst


def z_of(strike: float, spot: float, sigma: float, days: float) -> float:
    return math.log(strike / spot) / (sigma * math.sqrt(days / 365.0))


# ─── step 1a: skew calibration ───────────────────────────────────────────────

def calibrate() -> int:
    w, _k = conv_frozen()
    files = sorted(BHAV.glob("*.csv"))
    obs = []                                   # (year, z, ratio)
    days_used = skipped = 0
    for f in files:
        d = datetime.strptime(f.stem, "%Y%m%d").date()
        if not (CAL_FROM <= d <= CAL_TO):
            continue
        rows = bhav_rows(d)
        exps = sorted({date.fromisoformat(r["expiry"]) for r in rows})
        cand = [e for e in exps if DTE_LO <= (e - d).days <= DTE_HI]
        if not cand:
            skipped += 1
            continue
        e = cand[0]
        rs = [r for r in rows if r["expiry"] == e.isoformat() and r["close"] and r["underlying_close"]]
        if not rs:
            skipped += 1
            continue
        spot = float(rs[0]["underlying_close"])
        T = dte(e, datetime.combine(d, CLOSE_1530), w)
        a = bp.atm(spot)
        book = {(float(r["strike"]), r["option_type"]): r for r in rs}

        def iv(k, typ):
            r = book.get((float(k), typ))
            if r is None or float(r["close"]) < MIN_CLOSE:
                return None
            try:
                return implied_volatility(float(r["close"]), spot, k, T,
                                          OptionType.CALL if typ == "CE" else OptionType.PUT, strict=True)
            except ImpliedVolatilityError:
                return None
        ivc, ivp = iv(a, "CE"), iv(a, "PE")
        if ivc is None or ivp is None:
            skipped += 1
            continue
        sig = (ivc + ivp) / 2
        days_used += 1
        for j in range(0, 11):
            k = a - 50 * j
            r = book.get((float(k), "PE"))
            if r is None or float(r["volume"] or 0) < MIN_VOL:
                continue
            v = iv(k, "PE")
            if v is None:
                continue
            z = z_of(k, spot, sig, T)
            if Z_MIN <= z <= 0:
                obs.append((d.year, z, v / sig))

    def table(sel):
        b = defaultdict(list)
        for y, z, r in sel:
            i = min(int(-z / Z_STEP), int(-Z_MIN / Z_STEP) - 1)
            b[i].append(r)
        return {i: (stx.median(v), len(v)) for i, v in sorted(b.items())}
    pooled = table(obs)
    early = table([o for o in obs if o[0] <= 2022])
    late = table([o for o in obs if o[0] >= 2023])
    mids = [-(i + 0.5) * Z_STEP for i in pooled]
    z_asc = tuple(reversed(mids))
    s_asc = tuple(round(pooled[i][0], 4) for i in reversed(list(pooled)))
    out = dict(source="NSE bhavcopy closes, data_cache/nse_bhavcopy/parsed", span=[str(CAL_FROM), str(CAL_TO)],
               rule=f"nearest weekly with {DTE_LO}-{DTE_HI} calendar DTE; 15:30 frozen convention; sigma_ATM = mean IV "
                    f"of ATM CE and PE; puts ATM..ATM-500 step 50, volume >= {MIN_VOL}, close >= {MIN_CLOSE}; "
                    f"z = ln(K/S)/(sigma_ATM sqrt(T/365)); bucket {Z_STEP}; median IV_put/sigma_ATM",
               sessions_used=days_used, sessions_skipped=skipped, n_obs=len(obs), z=list(z_asc), s=list(s_asc))
    SKEW_JSON.write_text(json.dumps(out, indent=1), encoding="utf-8")
    na, worst = underlying_agreement()
    print(f"bhavcopy underlying_close vs NSE daily close where both exist: {na} sessions, max gap {worst:.2f} pts")
    print(f"sessions used {days_used}, skipped {skipped}, put observations {len(obs)}")
    print("| z bucket | s pooled | n | s 2019–22 | n | s 2023–26 | n |")
    print("|---|---|---|---|---|---|---|")
    for i in pooled:
        lo, hi = -i * Z_STEP, -(i + 1) * Z_STEP
        e_, l_ = early.get(i, (float("nan"), 0)), late.get(i, (float("nan"), 0))
        print(f"| {hi:.2f} .. {lo:.2f} | {pooled[i][0]:.3f} | {pooled[i][1]} | {e_[0]:.3f} | {e_[1]} | {l_[0]:.3f} | {l_[1]} |")
    print(f"wrote {SKEW_JSON}")
    return 0


def load_skew() -> bp.Skew:
    j = json.loads(SKEW_JSON.read_text(encoding="utf-8"))
    return bp.Skew(tuple(j["z"]), tuple(j["s"]))


# ─── pricing ─────────────────────────────────────────────────────────────────

def put_price(spot, strike, expiry, at_ist, vix, w, k, skew: bp.Skew) -> tuple[float, float]:
    days = dte(expiry, at_ist, w)
    sig = k * vix / 100.0
    if days <= 0:
        return max(0.0, strike - spot), sig
    iv = sig * skew.at(z_of(strike, spot, sig, days))
    return compute_greeks(spot=spot, strike=strike, days_to_expiry=days, implied_vol=iv,
                          option_type=OptionType.PUT).theoretical_price, iv


def spread_value(spot, ks, kl, expiry, at_ist, vix, w, k, skew):
    ps, ivs = put_price(spot, ks, expiry, at_ist, vix, w, k, skew)
    pl, ivl = put_price(spot, kl, expiry, at_ist, vix, w, k, skew)
    return ps, pl, ivs, ivl


# ─── step 1c: pricing check on entry days (no P&L) ───────────────────────────

def check() -> int:
    W = s3.World()
    w, k = conv_frozen()
    sk = load_skew()
    errs = {"skew": [], "flat": []}
    missing = listed_mismatch = 0
    n = 0
    for per in (s3.DISC, s3.CONF):
        for t in W.trades:
            d = t.entry_time.date()
            if not s3.in_period(d, per) or t.exit is None:
                continue
            n += 1
            e = W.expiry_for(d)
            ks, kl = bp.strikes(t.entry)
            rows = bhav_rows(d)
            if rows and e.isoformat() not in {r["expiry"] for r in rows}:
                listed_mismatch += 1
            book = {(float(r["strike"]), r["option_type"]): r for r in rows if r["expiry"] == e.isoformat()}
            rs_, rl_ = book.get((float(ks), "PE")), book.get((float(kl), "PE"))
            if not (rs_ and rl_ and rs_["close"] and rl_["close"] and rs_["underlying_close"]):
                missing += 1
                continue
            mkt = float(rs_["close"]) - float(rl_["close"])
            spot = float(rs_["underlying_close"])
            vix = W.vix_at(datetime.combine(d, time(15, 25)), "close")
            at = datetime.combine(d, CLOSE_1530)
            for name, s in (("skew", sk), ("flat", bp.FLAT)):
                ps, pl, _, _ = spread_value(spot, ks, kl, e, at, vix, w, k, s)
                model = ps - pl
                errs[name].append((model - mkt, abs(model - mkt) / mkt, mkt))
    print(f"scored trades {n}; both legs found in the bhavcopy {n - missing}; our expiry not listed that day {listed_mismatch}")
    print("| Pricing | n | Median signed error, pts (model − market) | Median abs error, pts | Median abs error, % of credit | 90th pct, % |")
    print("|---|---|---|---|---|---|")
    for name, v in errs.items():
        if not v:
            continue
        print(f"| {name} | {len(v)} | {stx.median(x[0] for x in v):+.1f} | {stx.median(abs(x[0]) for x in v):.1f} | "
              f"{stx.median(x[1] for x in v):.1%} | {sorted(x[1] for x in v)[int(0.9 * (len(v) - 1))]:.1%} |")
    print(f"median market credit {stx.median(x[2] for x in errs['skew']):.1f} pts")
    return 0


# ─── step 1d: worked spreads on placebo-pool entries ─────────────────────────

def cases() -> int:
    W = s3.World()
    w, k = conv_frozen()
    sk = load_skew()
    pool = []
    for t, b in enumerate(W.bars[:-1]):
        d = b.start.date()
        if not (s3.in_period(d, s3.DISC) or s3.in_period(d, s3.CONF)):
            continue
        if W.per_day[d] < eng.MIN_BARS_PER_DAY or W.st["atr"][t] is None:
            continue
        if b.start.time() in s3.SIG_TIME.values() and W.bars[t + 1].start.date() == d and W.htf(d):
            pool.append(t)
    rng = random.Random(CASE_SEED)
    picks = sorted(rng.sample(pool, 5))
    real = {W.idx[t.entry_time] for t in W.trades}
    for c in picks:
        kx = c + 1
        b = W.bars[kx]
        atr = W.st["atr"][c]
        m = eng.manage(W.bars, W.st, kx, CASE_RISK_ATR * atr)
        t_in = b.subs[0][0]
        t_out = m["end"]
        e = W.expiry_for(t_in.date())
        ks, kl = bp.strikes(m["entry"])
        v_in, v_out = W.vix_at(t_in, "open"), W.vix_at(t_out - timedelta(minutes=eng.SUB_MIN), "close")
        si, li, ivs_i, ivl_i = spread_value(m["entry"], ks, kl, e, t_in, v_in, w, k, sk)
        so, lo, ivs_o, ivl_o = spread_value(m["exit"], ks, kl, e, t_out, v_out, w, k, sk)
        r = bp.spread_result(si, li, so, lo)
        lot = bp.nifty_lot(e, monthly=s3.nifty_weekly_expiry(e + timedelta(days=7), W.tdays).month != e.month)
        print()
        print(f"placebo-pool entry {t_in:%a %Y-%m-%d %H:%M} (real signal too: {'yes' if kx in real else 'no'}); "
              f"spot {m['entry']:.2f}, ATR {atr:.1f}, risk {CASE_RISK_ATR}×ATR = {CASE_RISK_ATR * atr:.1f}")
        print(f"  expiry {e} ({dte(e, t_in, w):.2f} effective days), short {ks} PE, long {kl} PE; VIX {v_in:.2f}")
        print(f"  entry: short {si:.2f} (IV {ivs_i:.1%}), long {li:.2f} (IV {ivl_i:.1%}) -> credit {r.credit:.2f}, "
              f"max risk {r.max_risk:.2f}")
        print(f"  spot exit {t_out:%a %m-%d %H:%M} {m['exit']:.2f} ({m['reason']}, {m['bars_held']} bars); VIX {v_out:.2f}")
        print(f"  exit: short {so:.2f} (IV {ivs_o:.1%}), long {lo:.2f} (IV {ivl_o:.1%}) -> debit {r.debit:.2f}")
        print(f"  net {r.credit:.2f} − {r.debit:.2f} − {r.cost:.1f} = {r.net:+.2f} pts; R = {r.r:+.1%}; "
              f"lot {lot} -> ₹{r.net * lot:+,.0f}")
    return 0


# ─── step 2: the spread on each entry ────────────────────────────────────────

RESULTS = ROOT / "docs" / "NIFTY_SMC_OB_1H_BULLPUT_RESULTS.md"
EXPORT = ROOT / "backtest_results" / "SMC-OB-1H_BULLPUT_QUANTOS_NSE_NIFTY_2026-11-23.csv"
CALL_EXPORT = ROOT / "backtest_results" / "SMC-OB-1H_QUANTOS_NSE_NIFTY_2026-11-22.csv"


def is_monthly(W, e: date) -> bool:
    return s3.nifty_weekly_expiry(e + timedelta(days=7), W.tdays).month != e.month


def leg_cost(fn, p_in, p_out, lot, d, *extra) -> float:
    return fn(p_in, p_out, lot, d, *extra).total / lot


def spread_trade(W, k: int, risk: float, *, width: int = bp.WIDTH, conv: str = "frozen",
                 skew: bp.Skew = None, pt: bool = False):
    """A bull put spread opened at bars[k].o and closed at the frozen spot exit (or, with pt, at the first
    5-minute close where 70% of the credit is captured). None if the spot trade is still open."""
    m = eng.manage(W.bars, W.st, k, risk)
    if m["exit"] is None:
        return None
    b = W.bars[k]
    t_in = b.subs[0][0]
    d = t_in.date()
    e = W.expiry_for(d)
    w, kk = W.conv[conv]
    ks, kl = bp.strikes(m["entry"], width)
    v_in = W.vix_at(t_in, "open")
    si, li, ivs, ivl = spread_value(m["entry"], ks, kl, e, t_in, v_in, w, kk, skew)
    t_out, spot_out, reason = m["end"], m["exit"], m["reason"]
    if t_out.date() >= e:
        raise SystemExit(f"hold reaches expiry: entry {t_in}, exit {t_out}, expiry {e}")
    v_out = W.vix_at(t_out - timedelta(minutes=eng.SUB_MIN), "close")
    credit = si - li
    if pt:
        last = t_out - timedelta(minutes=eng.SUB_MIN)            # the spot exit's own 5-minute bar
        done = False
        for t in range(k, m["t"] + 1):
            for sub in W.bars[t].subs:
                if sub[0] >= last:
                    done = True
                    break
                at = sub[0] + timedelta(minutes=eng.SUB_MIN)
                vx = W.vix_at(sub[0], "close")
                ps, pl, _, _ = spread_value(sub[4], ks, kl, e, at, vx, w, kk, skew)
                if bp.profit_take_hit(ps - pl, credit):
                    t_out, spot_out, reason, v_out, done = at, sub[4], "profit_take", vx, True
                    break
            if done:
                break
    so, lo, _, _ = spread_value(spot_out, ks, kl, e, t_out, v_out, w, kk, skew)
    r = bp.spread_result(si, li, so, lo, width)
    lot = bp.nifty_lot(e, is_monthly(W, e))
    exp_day = s3.is_nifty_weekly_expiry_day(d, W.tdays)
    strat = (leg_cost(s3.oc.stratified_spread_trade_cost, si, so, lot, d, "NIFTY", exp_day)
             + leg_cost(s3.oc.stratified_spread_trade_cost, li, lo, lot, d, "NIFTY", exp_day))
    stress = leg_cost(s3.oc.stressed_trade_cost, si, so, lot, d) + leg_cost(s3.oc.stressed_trade_cost, li, lo, lot, d)
    gross = r.credit - r.debit
    return dict(entry_time=t_in, exit_end=t_out, reason=reason, bars_held=m["bars_held"], entry=m["entry"],
                exit_spot=spot_out, spot_reason=m["reason"], stop0=m["stop0"], target=m["target"], expiry=e,
                ks=ks, kl=kl, ivs=ivs, ivl=ivl, si=si, li=li, so=so, lo=lo, vix_in=v_in, vix_out=v_out,
                credit=r.credit, debit=r.debit, net=r.net, max_risk=r.max_risk, r=r.r, lot=lot,
                rs=r.net * lot, r_strat=(gross - strat) / r.max_risk, r_stress=(gross - stress) / r.max_risk,
                cost_strat=strat, cost_stress=stress)


def real_rows(W, period, **kw) -> list[dict]:
    rows = []
    for t in W.trades:
        if not s3.in_period(t.entry_time.date(), period):
            continue
        r = spread_trade(W, W.idx[t.entry_time], t.risk, **kw)
        if r is None:
            continue
        r.update(window=t.window, risk=t.risk, atr=t.atr, risk_atr=t.risk / t.atr, stops=t.stops)
        rows.append(r)
    return rows


def placebo(W, period, rows, key="r", **kw) -> dict:
    """Pre-registration §4: the call test's placebo (same pools, draws and seed), priced as the same spread."""
    pools = defaultdict(list)
    for t, b in enumerate(W.bars[:-1]):
        d = b.start.date()
        if not s3.in_period(d, period) or W.per_day[d] < eng.MIN_BARS_PER_DAY or W.st["atr"][t] is None:
            continue
        for win, st_ in s3.SIG_TIME.items():
            if b.start.time() == st_ and W.bars[t + 1].start.date() == d and W.htf(d):
                pools[(d.year, win)].append(t)
    cache, per_trade = {}, []
    for r in rows:
        outs = []
        for c in pools[(r["entry_time"].year, r["window"])]:
            ck = (c, round(r["risk_atr"], 6))
            if ck not in cache:
                o = spread_trade(W, c + 1, r["risk_atr"] * W.st["atr"][c], **kw)
                cache[ck] = None if o is None else o[key]
            if cache[ck] is not None:
                outs.append(cache[ck])
        per_trade.append(outs)
    rng = random.Random(s3.SEED)
    real = stx.mean(r[key] for r in rows)
    means = [stx.mean(rng.choice(o) for o in per_trade) for _ in range(s3.N_PLACEBO)]
    ms = sorted(means)
    return dict(p=sum(m >= real for m in means) / s3.N_PLACEBO, mean=stx.mean(means),
                p5=ms[int(0.05 * s3.N_PLACEBO)], p95=ms[int(0.95 * s3.N_PLACEBO)],
                pool=sum(len(v) for v in pools.values()))


def summary(W, period, name, p_bar, need_t):
    sk = load_skew()
    rows = real_rows(W, period, skew=sk)
    pl = placebo(W, period, rows, skew=sk)
    R = [r["r"] for r in rows]
    t = s3.tstat(R)
    ok = stx.mean(R) > 0 and pl["p"] <= p_bar and (t >= 2.0 or not need_t)
    L = [f"**{name}, {period[0]} to {period[1]}: n = {len(rows)}**", "",
         "| Measure | Value |", "|---|---|",
         f"| **Mean net return on maximum risk, R (3.0-pt costs)** | **{stx.mean(R):+.2%}** (median {stx.median(R):+.2%}) |",
         f"| One-sided t | {t:.2f} |",
         f"| Winners (net > 0) | {sum(x > 0 for x in R)} of {len(R)} |",
         f"| Mean credit / maximum risk / net (points) | {stx.mean(r['credit'] for r in rows):.1f} / "
         f"{stx.mean(r['max_risk'] for r in rows):.1f} / {stx.mean(r['net'] for r in rows):+.2f} |",
         f"| Placebo ({s3.N_PLACEBO} sets, pool {pl['pool']} bars): mean of set means | {pl['mean']:+.2%} "
         f"(5th–95th pct {pl['p5']:+.2%} .. {pl['p95']:+.2%}) |",
         f"| **Placebo p (share of sets ≥ real)** | **{pl['p']:.3f}** |",
         f"| R with Stratified / Stressed costs, both legs | {stx.mean(r['r_strat'] for r in rows):+.2%} / "
         f"{stx.mean(r['r_stress'] for r in rows):+.2%} |",
         f"| Net ₹ total at historical lots | {sum(r['rs'] for r in rows):+,.0f} |"]
    return "\n".join(L), ok


def check_spot_matches_export(W) -> None:
    """§7: the spot trades must be the ones in the call test's export."""
    with CALL_EXPORT.open(encoding="utf-8") as f:
        ex = {r["entry_time"]: r for r in csv.DictReader(f) if r["period"] in ("discovery", "confirmation")}
    rows = real_rows(W, s3.DISC, skew=bp.FLAT) + real_rows(W, s3.CONF, skew=bp.FLAT)
    if len(rows) != len(ex):
        raise SystemExit(f"{len(rows)} spot trades vs {len(ex)} in the export")
    for r in rows:
        x = ex[f"{r['entry_time']:%Y-%m-%d %H:%M}"]
        if abs(float(x["exit_spot"]) - r["exit_spot"]) > 0.006 or abs(float(x["entry_spot"]) - r["entry"]) > 0.006:
            raise SystemExit(f"spot trade differs from the export at {r['entry_time']}")


def hold_group(r, W):
    return s3.hold_group(r, W)


def diagnostics(W) -> str:
    sk = load_skew()
    periods = (("discovery", s3.DISC), ("confirmation", s3.CONF))
    out = ["### Diagnostics (§8; reported, not scored)", ""]

    def line(title, kw, with_placebo=True, key="r"):
        cells = []
        for _, per in periods:
            rows = real_rows(W, per, **kw)
            R = [r[key] for r in rows]
            pp = placebo(W, per, rows, key=key, **kw)["p"] if with_placebo else float("nan")
            extra = f", fired {sum(r['reason'] == 'profit_take' for r in rows)}" if kw.get("pt") else ""
            cells.append(f"{stx.mean(R):+.2%} (t {s3.tstat(R):.2f}, p {pp:.3f}{extra})")
        return f"| {title} | " + " | ".join(cells) + " |"
    out += ["**Variants** (mean R, one-sided t, placebo p with the same variant):", "",
            "| Variant | Discovery | Confirmation |", "|---|---|---|",
            line("Scored: 250 wing, skew, frozen, 3.0 pts", dict(skew=sk)),
            line("Profit-take at 70% of credit", dict(skew=sk, pt=True)),
            line("300-point wing", dict(skew=sk, width=bp.WIDTH_ALT)),
            line("Stratified costs, both legs", dict(skew=sk), key="r_strat"),
            line("Stressed costs, both legs", dict(skew=sk), key="r_stress"),
            line("Flat IV (no skew)", dict(skew=bp.FLAT)),
            line("Calendar time convention", dict(skew=sk, conv="calendar")),
            line("252-day time convention", dict(skew=sk, conv="252-day"))]

    by_conv = {c: [r for _, per in periods for r in real_rows(W, per, skew=sk, conv=c)] for c in W.conv}
    groups = defaultdict(lambda: defaultdict(list))
    for c, rows in by_conv.items():
        for r in rows:
            g = hold_group(r, W)
            groups[g][c].append(r)
            if r["entry_time"].weekday() == 4 and g == "weekend/holiday gap":
                groups["  of which Friday entries"][c].append(r)
    mean = lambda rs, k: stx.mean(x[k] for x in rs) if rs else float("nan")  # noqa: E731
    out += ["", "**Holds by overnight gap, both periods** (mean R):", "",
            "| Group | n | Spot pts | R (frozen) | R (calendar) | R (252-day) |", "|---|---|---|---|---|---|"]
    for g in ("intraday", "weeknight only", "weekend/holiday gap", "  of which Friday entries"):
        fr = groups[g]["frozen"]
        out.append(f"| {g} | {len(fr)} | {mean(fr, 'exit_spot') - mean(fr, 'entry'):+.1f} | {mean(fr, 'r'):+.2%} | "
                   f"{mean(groups[g]['calendar'], 'r'):+.2%} | {mean(groups[g]['252-day'], 'r'):+.2%} |")

    fz = {p: real_rows(W, per, skew=sk) for p, per in periods}

    def table(title, key_fn):
        L = ["", f"**{title}** (mean R):", "", "| | Discovery n | Discovery R | Confirmation n | Confirmation R |",
             "|---|---|---|---|---|"]
        for kx in sorted({key_fn(r) for p in fz for r in fz[p]}):
            cells = []
            for p, _ in periods:
                rs = [r for r in fz[p] if key_fn(r) == kx]
                cells += [str(len(rs)), f"{stx.mean(r['r'] for r in rs):+.2%}" if rs else "—"]
            L.append(f"| {kx} | " + " | ".join(cells) + " |")
        return L
    out += table("By entry window", lambda r: "11:00" if r["window"] == "am" else "15:00")
    out += table("By spot exit reason", lambda r: r["spot_reason"])
    out += table("By year", lambda r: str(r["entry_time"].year))
    out += ["", "**Rupees at historical lot sizes** (3.0-pt costs): " + "; ".join(
        f"{p} {sum(r['rs'] for r in fz[p]):+,.0f} over {len(fz[p])} trades" for p, _ in periods) + "."]
    return "\n".join(out)


def export(W) -> int:
    sk = load_skew()
    cols = ["n", "period", "window", "entry_time", "entry_spot", "stop0", "target", "stop_moves", "exit_time",
            "exit_spot", "exit_reason", "bars_held", "spot_pts", "expiry", "lot", "short_strike", "long_strike",
            "vix_in", "vix_out", "short_iv_in", "long_iv_in", "short_in", "long_in", "credit", "max_risk",
            "short_out", "long_out", "debit", "cost_pts", "net_pts", "r_pct", "net_rs", "r_pct_stratified",
            "r_pct_stressed"]
    with EXPORT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        n = 0
        for name, per in (("discovery", s3.DISC), ("confirmation", s3.CONF)):
            for r in real_rows(W, per, skew=sk):
                n += 1
                w.writerow([n, name, r["window"], f"{r['entry_time']:%Y-%m-%d %H:%M}", f"{r['entry']:.2f}",
                            f"{r['stop0']:.2f}", f"{r['target']:.2f}",
                            "; ".join(f"{a:%m-%d %H:%M}->{b:.2f}" for a, b in r["stops"]),
                            f"{r['exit_end'] - timedelta(minutes=eng.SUB_MIN):%Y-%m-%d %H:%M}", f"{r['exit_spot']:.2f}",
                            r["reason"], r["bars_held"], f"{r['exit_spot'] - r['entry']:.2f}", r["expiry"], r["lot"],
                            r["ks"], r["kl"], f"{r['vix_in']:.2f}", f"{r['vix_out']:.2f}", f"{r['ivs']:.4f}",
                            f"{r['ivl']:.4f}", f"{r['si']:.2f}", f"{r['li']:.2f}", f"{r['credit']:.2f}",
                            f"{r['max_risk']:.2f}", f"{r['so']:.2f}", f"{r['lo']:.2f}", f"{r['debit']:.2f}",
                            f"{bp.COST_PTS:.1f}", f"{r['net']:.2f}", f"{r['r'] * 100:.2f}", f"{r['rs']:.0f}",
                            f"{r['r_strat'] * 100:.2f}", f"{r['r_stress'] * 100:.2f}"])
    print(f"wrote {n} trades to {EXPORT}")
    return 0


def run_step(step: str) -> int:
    W = s3.World()
    check_spot_matches_export(W)
    if step == "discovery":
        txt, ok = summary(W, s3.DISC, "Discovery", 0.05, need_t=True)
        print(txt)
        print(f"\nDiscovery verdict: {'GOES ON to confirmation' if ok else 'FAIL (does not go on)'}")
    elif step == "confirmation":
        if "## Step 2a: discovery" not in RESULTS.read_text(encoding="utf-8"):
            raise SystemExit("Write the discovery table to the results doc first (pre-registration §6, step 2).")
        txt, ok = summary(W, s3.CONF, "Confirmation", 0.10, need_t=False)
        print(txt)
        print(f"\nConfirmation: {'PASS' if ok else 'FAIL'}")
    elif step == "diagnostics":
        print(diagnostics(W))
    else:
        return export(W)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["calibrate", "check", "cases", "discovery", "confirmation", "diagnostics",
                                     "export"])
    a = ap.parse_args(argv)
    if a.step in ("calibrate", "check", "cases"):
        return {"calibrate": calibrate, "check": check, "cases": cases}[a.step]()
    return run_step(a.step)


if __name__ == "__main__":
    sys.exit(main())
