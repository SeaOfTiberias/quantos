#!/usr/bin/env python3
"""
Runs docs/CCI_CPR_SIGNAL_AND_FILTERS_PREREG_2026-11-07.md once: Part A (CCI(34)/SMA52 + monthly
CPR signal on the top-500 universe, 2013-2026) and Part B (scripts/backtest_cci_rsi_filters.py),
and writes the results document.

Reads data_cache/cci_cpr/bars.pkl: the adjusted bhavcopy panel (core/techno_funda/panel.py)
slimmed to sym, date, series, o, h, l, c, val, seg.

    python scripts/backtest_cci_cpr.py --out docs/CCI_CPR_SIGNAL_AND_FILTERS_RESULTS_2026-11-07.md
"""

from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.backtest import cci_cpr as m  # noqa: E402

BARS = Path("data_cache/cci_cpr/bars.pkl")
FNO_LIST = Path("agent/universe_fno_2026-10-19.txt")
START, END = pd.Timestamp("2013-01-01"), pd.Timestamp("2026-09-22")
TOP_N, MED_N = 500, 60
HORIZONS, PRIMARY = (5, 10, 20), 10
COST = 0.25                      # % round trip
SEED, N_BOOT = 20261107, 10_000
PASS_MEAN, PASS_GAP, PASS_N, ALPHA = 0.50, 0.30, 300, 0.05
SIDE_NAME = {1: "long", -1: "short"}


# ─── data ────────────────────────────────────────────────────────────────────

def load():
    t = time.time()
    df = pd.read_pickle(BARS)
    df["sym"] = df["sym"].astype(str)
    df["series"] = df["series"].astype(str)
    df = df.sort_values(["sym", "date"]).reset_index(drop=True)
    cal = np.array(sorted(df["date"].unique()))
    df["gi"] = np.searchsorted(cal, df["date"].to_numpy())
    syms = np.array(sorted(df["sym"].unique()))
    df["si"] = np.searchsorted(syms, df["sym"].to_numpy())
    # universe: top 500 EQ by median traded value over the 60 sessions BEFORE D
    df["med60"] = (df.groupby("sym", sort=False)["val"]
                   .transform(lambda s: s.rolling(MED_N, min_periods=MED_N).median().shift(1)))
    elig = df[(df["series"] == "EQ") & df["med60"].notna()].copy()
    elig["rk"] = elig.groupby("gi")["med60"].rank(ascending=False, method="first")
    U = np.zeros((len(cal), len(syms)), dtype=bool)
    u = elig[elig["rk"] <= TOP_N]
    U[u["gi"].to_numpy(), u["si"].to_numpy()] = True
    O = np.full((len(cal), len(syms)), np.nan)
    C = np.full((len(cal), len(syms)), np.nan)
    O[df["gi"].to_numpy(), df["si"].to_numpy()] = df["o"].to_numpy()
    C[df["gi"].to_numpy(), df["si"].to_numpy()] = df["c"].to_numpy()
    print(f"loaded {len(df):,} rows, {len(syms)} symbols, {len(cal)} sessions in {time.time() - t:.0f}s", flush=True)
    return df, cal, syms, U, O, C


def forward(O, C, h):
    """F[i, s] = close of session i+h-1 / open of session i - 1 (in %)."""
    Ch = np.full_like(C, np.nan)
    Ch[: len(C) - (h - 1)] = C[h - 1:]
    with np.errstate(invalid="ignore", divide="ignore"):
        return (Ch / O - 1) * 100


def bench(F, U):
    """B[s] = equal-weighted mean of F[s+1] over the universe of signal day s."""
    Fn = np.full_like(F, np.nan)
    Fn[:-1] = F[1:]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)       # an empty universe row -> NaN
        return np.nanmean(np.where(U, Fn, np.nan), axis=1)


# ─── signals ─────────────────────────────────────────────────────────────────

def signals(df, cal, U):
    rows = []
    t = time.time()
    for (sym, seg), g in df.groupby(["sym", "seg"], sort=False):
        if len(g) < m.CCI_N + m.CCI_AVG_N + 2:
            continue
        h, l, c = g["h"].to_numpy(), g["l"].to_numpy(), g["c"].to_numpy()
        dates, gi, si = g["date"].to_numpy(), g["gi"].to_numpy(), int(g["si"].iat[0])
        cand = m.candidate_days(h, l, c, dates)
        top, bot = m.monthly_cpr(dates, h, l, c)
        sma150 = m.sma(c, 150)
        atr = m.wilder_atr(h, l, c)
        for (arm, side), days in cand.items():
            for d in days:
                rows.append((sym, si, int(gi[d]), dates[d], arm, side,
                             _stage(c, sma150, d), atr[d] / c[d] * 100 if c[d] else np.nan,
                             _cpr_pos(c, top, bot, d)))
    sig = pd.DataFrame(rows, columns=["sym", "si", "gi", "date", "arm", "side", "stage", "atrp", "cpr_pos"])
    sig = sig[(sig["date"] >= START) & (sig["date"] <= END)]
    sig = sig[U[sig["gi"].to_numpy(), sig["si"].to_numpy()]]
    # skip rule: per stock, arm and side, on kept signals, in market sessions
    keep = []
    for _, g in sig.sort_values("gi").groupby(["sym", "arm", "side"], sort=False):
        kept = set(m.apply_skip(g["gi"].tolist()))
        keep.append(g[g["gi"].isin(kept)].drop_duplicates("gi"))
    sig = pd.concat(keep, ignore_index=True)
    print(f"signals: {len(sig):,} in {time.time() - t:.0f}s", flush=True)
    return sig


def _stage(c, sma150, d):
    """Weinstein stage proxy: price vs its 150-day (30-week) SMA and that SMA's 20-session slope."""
    if d < 20 or np.isnan(sma150[d]) or np.isnan(sma150[d - 20]):
        return "n/a"
    up = sma150[d] > sma150[d - 20]
    if c[d] > sma150[d] and up:
        return "2 (above, rising)"
    if c[d] < sma150[d] and not up:
        return "4 (below, falling)"
    return "1/3 (mixed)"


def _cpr_pos(c, top, bot, d):
    """Where the PREVIOUS close sat against the monthly CPR in force that day."""
    if d < 1 or np.isnan(top[d - 1]):
        return "n/a"
    x = c[d - 1]
    return "above" if x > top[d - 1] else "below" if x < bot[d - 1] else "inside"


# ─── statistics ──────────────────────────────────────────────────────────────

def weeks(dates):
    iso = pd.DatetimeIndex(dates).isocalendar()
    return (iso["year"].astype(int) * 100 + iso["week"].astype(int)).to_numpy()


def week_sums(x, wk, universe):
    pos = {w: i for i, w in enumerate(universe)}
    S, N = np.zeros(len(universe)), np.zeros(len(universe))
    for v, w in zip(x, wk):
        S[pos[w]] += v
        N[pos[w]] += 1
    return S, N


def boot_mean(x, dates):
    """(lo, hi, p) of the mean, resampling calendar weeks."""
    wk = weeks(dates)
    uw = np.unique(wk)
    S, N = week_sums(x, wk, uw)
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(uw), size=(N_BOOT, len(uw)))
    with np.errstate(invalid="ignore"):
        b = S[idx].sum(1) / N[idx].sum(1)
    b = b[~np.isnan(b)]
    p = min(1.0, 2 * min((b <= 0).mean(), (b >= 0).mean()))
    return np.percentile(b, 2.5), np.percentile(b, 97.5), p


def boot_diff(x1, d1, x2, d2):
    """(lo, hi) of mean(x1) - mean(x2), resampling the same calendar weeks for both."""
    w1, w2 = weeks(d1), weeks(d2)
    uw = np.unique(np.concatenate([w1, w2]))
    S1, N1 = week_sums(x1, w1, uw)
    S2, N2 = week_sums(x2, w2, uw)
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(uw), size=(N_BOOT, len(uw)))
    with np.errstate(invalid="ignore"):
        b = S1[idx].sum(1) / N1[idx].sum(1) - S2[idx].sum(1) / N2[idx].sum(1)
    b = b[~np.isnan(b)]
    return np.percentile(b, 2.5), np.percentile(b, 97.5)


def summary(t: pd.DataFrame, col: str) -> dict:
    x = t[col].dropna()
    if not len(x):
        return {"n": 0}
    d = t.loc[x.index, "date"]
    med = d.sort_values().iloc[len(d) // 2]
    return {"n": len(x), "mean": x.mean(), "win": (x > 0).mean(),
            "h1": x[d < med].mean(), "h2": x[d >= med].mean(), "split": med}


def holm(ps: dict) -> dict:
    order = sorted(ps, key=ps.get)
    out, ok = {}, True
    for k, key in enumerate(order):
        ok = ok and ps[key] <= ALPHA / (len(order) - k)
        out[key] = ok
    return out


def fmt(s):
    if not s["n"]:
        return "| 0 | | | | |"
    return f"| {s['n']:,} | {s['mean']:+.2f}% | {s['win']:.0%} | {s['h1']:+.2f}% | {s['h2']:+.2f}% |"


# ─── run ─────────────────────────────────────────────────────────────────────

def part_a():
    df, cal, syms, U, O, C = load()
    sig = signals(df, cal, U)
    del df
    for h in HORIZONS:
        F = forward(O, C, h)
        B = bench(F, U)
        gi, si = sig["gi"].to_numpy(), sig["si"].to_numpy()
        nxt = np.minimum(gi + 1, len(cal) - 1)
        r = np.where(gi + 1 < len(cal), F[nxt, si], np.nan)
        exc = (r - B[gi]) * sig["side"].to_numpy()
        sig[f"net{h}"] = exc - COST
        del F
    fno = set(FNO_LIST.read_text().split()) if FNO_LIST.exists() else set()
    sig["fno_now"] = sig["sym"].isin(fno)

    col = f"net{PRIMARY}"
    lines = ["## Part A: CCI(34)/SMA52 + monthly CPR signal", "",
             f"Top-{TOP_N} universe by 60-session median traded value, signals {START.date()} to {END.date()}, "
             f"entry at the next open. Returns are % per trade, minus the equal-weighted universe over the same "
             f"window (sign flipped for shorts), after {COST}% cost.", ""]
    res, ps = {}, {}
    for side in (1, -1):
        full = sig[(sig["arm"] == "full") & (sig["side"] == side)].dropna(subset=[col])
        arm1 = sig[(sig["arm"] == "cci_only") & (sig["side"] == side)].dropna(subset=[col])
        s = summary(full, col)
        lo, hi, p = boot_mean(full[col].to_numpy(), full["date"]) if s["n"] else (np.nan, np.nan, 1.0)
        dlo, dhi = boot_diff(full[col].to_numpy(), full["date"], arm1[col].to_numpy(), arm1["date"]) \
            if s["n"] and len(arm1) else (np.nan, np.nan)
        gap = s["mean"] - arm1[col].mean() if s["n"] else np.nan
        res[side] = dict(s=s, lo=lo, hi=hi, p=p, gap=gap, dlo=dlo, dhi=dhi, arm1=summary(arm1, col))
        ps[side] = p
    hp = holm(ps)
    verdicts = []
    lines += ["| side | n | mean | 95% CI | p | Holm | H1 | H2 | vs CCI alone | its 95% CI | verdict |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for side in (1, -1):
        r = res[side]
        s = r["s"]
        checks = {
            f"mean >= +{PASS_MEAN:.2f}%": s["n"] and s["mean"] >= PASS_MEAN,
            "Holm": hp[side],
            "both halves > 0": s["n"] and s["h1"] > 0 and s["h2"] > 0,
            f"beats CCI alone by >= {PASS_GAP:.2f} pp, CI > 0": r["gap"] >= PASS_GAP and r["dlo"] > 0,
            f"n >= {PASS_N}": s["n"] >= PASS_N,
        }
        v = "PASS" if all(checks.values()) else "FAIL"
        r["failed"] = [k for k, ok in checks.items() if not ok]
        verdicts.append(f"A-{SIDE_NAME[side]}: {v}")
        if s["n"]:
            lines.append(f"| {SIDE_NAME[side]} | {s['n']:,} | {s['mean']:+.2f}% | {r['lo']:+.2f} to {r['hi']:+.2f} | "
                         f"{r['p']:.3f} | {'pass' if hp[side] else 'fail'} | {s['h1']:+.2f}% | {s['h2']:+.2f}% | "
                         f"{r['gap']:+.2f} pp | {r['dlo']:+.2f} to {r['dhi']:+.2f} | {v} |")
        else:
            lines.append(f"| {SIDE_NAME[side]} | 0 | | | | | | | | | FAIL |")
    lines.append("")
    for side in (1, -1):
        if res[side]["failed"]:
            lines.append(f"- **{SIDE_NAME[side]}** failed: {', '.join(res[side]['failed'])}.")
    lines += ["", "### Comparison arms and horizons (reported only)", "",
              "| arm | side | horizon | n | mean | win | H1 | H2 |", "|---|---|---|---|---|---|---|---|"]
    for arm in m.ARMS:
        for side in (1, -1):
            t = sig[(sig["arm"] == arm) & (sig["side"] == side)]
            for h in HORIZONS:
                lines.append(f"| {arm} | {SIDE_NAME[side]} | {h} " + fmt(summary(t, f"net{h}")))
    full = sig[sig["arm"] == "full"]
    for title, key in (("By year", "year"), ("By Weinstein stage (proxy: 150-day SMA and its slope)", "stage"),
                       ("By where the previous close sat against the monthly CPR", "cpr_pos"),
                       ("By ATR% tercile", "atr_t"), ("Shorts: stocks on the current F&O list (survivorship-biased)", "fno_now")):
        f2 = full.copy()
        f2["year"] = f2["date"].dt.year
        f2["atr_t"] = pd.qcut(f2["atrp"], 3, labels=["low", "mid", "high"])
        if key == "fno_now":
            f2 = f2[f2["side"] == -1]
        lines += ["", f"### {title} (full rule, {PRIMARY} sessions)", "",
                  "| group | side | n | mean | win | H1 | H2 |", "|---|---|---|---|---|---|---|"]
        for gk, g in f2.groupby(key, observed=True):
            for side in (1, -1):
                t = g[g["side"] == side]
                if len(t):
                    lines.append(f"| {gk} | {SIDE_NAME[side]} " + fmt(summary(t, col)))
    dropped = sig[col].isna().sum()
    lines += ["", f"{dropped:,} signals had no {PRIMARY}-session outcome (no bar on the entry or exit day) and are left out."]
    return "\n".join(lines), verdicts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/CCI_CPR_SIGNAL_AND_FILTERS_RESULTS_2026-11-07.md")
    ap.add_argument("--skip-b", action="store_true")
    a = ap.parse_args()
    text_a, va = part_a()
    text_b, vb = ("", [])
    if not a.skip_b:
        from scripts.backtest_cci_rsi_filters import report
        text_b, vb = report()
    head = ["# CCI + monthly CPR signal, and CCI / RSI entry filters: results", "",
            "Rules: docs/CCI_CPR_SIGNAL_AND_FILTERS_PREREG_2026-11-07.md (approved 2026-11-07). Run once.", "",
            "**Verdicts:** " + "; ".join(va + vb), ""]
    doc = "\n".join(head + [text_a, "", text_b]) + "\n"
    Path(a.out).write_text(doc, encoding="utf-8")
    print(doc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
