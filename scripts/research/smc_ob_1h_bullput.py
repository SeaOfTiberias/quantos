#!/usr/bin/env python3
"""NIFTY 1H SMC-OB, bull put credit spread (docs/NIFTY_SMC_OB_1H_BULLPUT_PREREG_2026-11-22.md).

    python scripts/research/smc_ob_1h_bullput.py calibrate   # step 1a: put skew from the bhavcopy -> frozen JSON
    python scripts/research/smc_ob_1h_bullput.py check       # step 1c: spread pricing vs bhavcopy closes, entry days
    python scripts/research/smc_ob_1h_bullput.py cases       # step 1d: 5 worked spreads on placebo-pool entries

Step 2 (discovery, confirmation, diagnostics) is not in this file until the user's go-ahead after step 1.
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["calibrate", "check", "cases"])
    a = ap.parse_args(argv)
    return {"calibrate": calibrate, "check": check, "cases": cases}[a.step]()


if __name__ == "__main__":
    sys.exit(main())
