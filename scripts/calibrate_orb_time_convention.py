#!/usr/bin/env python3
"""
QuantOS — Calibrate the ORB option-pricing time convention to real quotes
───────────────────────────────────────────────────────────────────────────
Written 2026-09-30, BEFORE it was run, after Fable's review of fix 2 found
candidate 18's backtest verdict hinges on how option time decay is spread over
the week: calendar time (repo fix 2) passes, a trading-time fit to bhavcopy
fails. This settles the convention on data neither model saw: the ORB spread
probe's real intraday MID quotes (bid/ask) on near-ATM NIFTY and BANKNIFTY
options at 09:35 / 12:00 / 15:15 IST daily since 2026-07-29
(data_cache/orb_scalping_spread_samples.csv, copied from the VM), with India
VIX from the cached 5m candles (data_cache/orb_fix2_candles.pkl).

Model (what the backtest uses):
    premium = BlackScholes(spot, strike, T = D_eff / 365, vol = k_index x VIX)
    D_eff   = w_session x sessions_left + w_weeknight x weeknights_left
              + w_weekend x weekends_left     (core/orb_scalping/premium.py
              TimeWeights / effective_days_to_expiry; linear in the weights)
    k_index: one VIX scale per index -- BANKNIFTY trades at a higher IV than
             India VIX (a NIFTY measure), and without it the time weights
             would bend to absorb that level gap.

Fit: grid search minimizing mean squared log error (log model - log mid).
Rows: bid > 0 and ask > 0, sampled inside the session. Split by date: the
first 70% of sample dates fit, the last 30% are a holdout the fit never sees.

PRE-REGISTERED (fixed before running):
  1. The frozen convention is the FULL-SAMPLE fit (weights + both k), written
     to docs/ORB_TIME_CONVENTION_CALIBRATION.md and committed BEFORE any
     backtest uses it.
  2. It counts as validated only if its HOLDOUT error beats calendar time
     (w = 0.26/0.74/2.74, k fitted the same way) on the train-fitted
     parameters. If not, the doc says so, and calendar and fitted are both
     reported as bounds with no single verdict.
  3. Candidate 18's backtest verdict (scripts/backtest_orb_time_convention.py)
     then uses the frozen convention: 18 "passes" only if BOTH NIFTY and
     BANKNIFTY (expiry day skipped) clear PF > 1.0 AND Sharpe > 0.5 under it.
     Calendar and 252-trading-day results are reported as sensitivity only.
Known limitation, stated up front: few quotes at 0-3 days to expiry (NIFTY
samples are 4-8 DTE, BANKNIFTY 18-27). NIFTY trades never hold < 2 DTE, and
BANKNIFTY's own expiry day is now skipped, but 1-3 DTE BANKNIFTY trades at
month end are extrapolated.

Offline -- no broker calls. Usage:
    python scripts/calibrate_orb_time_convention.py [--out docs/ORB_TIME_CONVENTION_CALIBRATION.md]
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import pickle
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
from scipy.special import ndtr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.options.greeks import DEFAULT_RISK_FREE_RATE  # noqa: E402
from core.orb_scalping.premium import TimeWeights, effective_days_to_expiry  # noqa: E402

SAMPLES = Path("data_cache/orb_scalping_spread_samples.csv")
CANDLES = Path("data_cache/orb_fix2_candles.pkl")
SESSION = (time(3, 45), time(10, 0))
TRAIN_FRACTION = 0.7

GRID_SESSION = np.round(np.arange(0.10, 2.01, 0.05), 3)
GRID_WEEKNIGHT = np.round(np.arange(0.00, 1.01, 0.05), 3)
GRID_WEEKEND = np.round(np.arange(0.00, 3.01, 0.10), 3)
GRID_K = np.round(np.arange(0.70, 1.81, 0.01), 3)

CALENDAR = TimeWeights.calendar()
UNIT = (TimeWeights(1, 0, 0), TimeWeights(0, 1, 0), TimeWeights(0, 0, 1))


def bs_price(spot, strike, days, vol, is_call):
    t = np.maximum(days, 1e-9) / 365.0
    sq = vol * np.sqrt(t)
    d1 = (np.log(spot / strike) + (DEFAULT_RISK_FREE_RATE + 0.5 * vol ** 2) * t) / sq
    d2 = d1 - sq
    disc = strike * np.exp(-DEFAULT_RISK_FREE_RATE * t)
    call = spot * ndtr(d1) - disc * ndtr(d2)
    put = disc * ndtr(-d2) - spot * ndtr(-d1)
    return np.where(is_call, call, put)


def load_rows() -> dict:
    vix = sorted(pickle.loads(CANDLES.read_bytes())["vix"], key=lambda c: c.timestamp)
    vix_ts = [c.timestamp for c in vix]
    rows = []
    for r in csv.DictReader(SAMPLES.open(encoding="utf-8")):
        ts = datetime.fromisoformat(r["sampled_at_utc"])
        bid, ask = float(r["bid"] or 0), float(r["ask"] or 0)
        if bid <= 0 or ask <= 0 or not (SESSION[0] <= ts.time() < SESSION[1]) or ts.weekday() >= 5:
            continue
        i = bisect.bisect_right(vix_ts, ts) - 1
        if i < 0 or vix_ts[i].date() != ts.date():
            continue
        expiry = ts.date() + timedelta(days=int(r["dte"]))
        units = [effective_days_to_expiry(expiry, ts, u) for u in UNIT]
        if effective_days_to_expiry(expiry, ts, CALENDAR) <= 0:
            continue
        rows.append(dict(ts=ts, underlying=r["underlying"], is_call=r["option_type"] == "CE",
                         spot=float(r["spot"]), strike=float(r["strike"]), mid=(bid + ask) / 2,
                         vix=vix[i].open / 100.0, units=units, dte=int(r["dte"])))
    return rows


def _arrays(rows):
    return {k: np.array([r[k] for r in rows]) for k in ("spot", "strike", "mid", "vix", "is_call", "dte")} | {
        "units": np.array([r["units"] for r in rows]),
        "bn": np.array([r["underlying"] == "BANKNIFTY" for r in rows]),
        "hour": np.array([r["ts"].hour * 60 + r["ts"].minute for r in rows])}


def _best_k(a, days, mask):
    """Best VIX scale for the rows in `mask` at these effective days, over the
    whole k grid at once (broadcast); returns (k, sse)."""
    if not mask.any():
        return 1.0, 0.0
    k = GRID_K[:, None]
    p = bs_price(a["spot"][mask], a["strike"][mask], days[mask], a["vix"][mask] * k, a["is_call"][mask])
    sse = np.sum((np.log(np.maximum(p, 1e-6)) - np.log(a["mid"][mask])) ** 2, axis=1)
    i = int(np.argmin(sse))
    return float(GRID_K[i]), float(sse[i])


def fit(a, weights_grid=None):
    """Grid search over (session, weeknight, weekend); k per index fitted inside."""
    n = len(a["mid"])
    best = None
    grid = weights_grid or [(s, w, e) for s in GRID_SESSION for w in GRID_WEEKNIGHT for e in GRID_WEEKEND]
    for s, w, e in grid:
        days = a["units"] @ np.array([s, w, e])
        if np.any(days <= 0):
            continue
        k_n, sse_n = _best_k(a, days, ~a["bn"])
        k_b, sse_b = _best_k(a, days, a["bn"])
        mse = (sse_n + sse_b) / n
        if best is None or mse < best["mse"]:
            best = dict(session=s, weeknight=w, weekend=e, k_nifty=k_n, k_banknifty=k_b, mse=mse)
    return best


def error(a, p) -> float:
    days = a["units"] @ np.array([p["session"], p["weeknight"], p["weekend"]])
    k = np.where(a["bn"], p["k_banknifty"], p["k_nifty"])
    model = bs_price(a["spot"], a["strike"], days, a["vix"] * k, a["is_call"])
    return float(np.mean((np.log(np.maximum(model, 1e-6)) - np.log(a["mid"])) ** 2))


def residual_table(a, p) -> list[str]:
    days = a["units"] @ np.array([p["session"], p["weeknight"], p["weekend"]])
    k = np.where(a["bn"], p["k_banknifty"], p["k_nifty"])
    res = np.log(np.maximum(bs_price(a["spot"], a["strike"], days, a["vix"] * k, a["is_call"]), 1e-6)) - np.log(a["mid"])
    out = ["| Slice | N | Mean log error (model - market) |", "|---|---|---|"]
    for label, m in (("09:35 IST", a["hour"] < 5 * 60), ("12:00 IST", (a["hour"] >= 5 * 60) & (a["hour"] < 8 * 60)),
                     ("15:15 IST", a["hour"] >= 8 * 60), ("NIFTY", ~a["bn"]), ("BANKNIFTY", a["bn"])):
        if m.any():
            out.append(f"| {label} | {int(m.sum())} | {res[m].mean():+.3f} |")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="docs/ORB_TIME_CONVENTION_CALIBRATION.md")
    args = ap.parse_args(argv)

    rows = load_rows()
    dates = sorted({r["ts"].date() for r in rows})
    cut = dates[int(len(dates) * TRAIN_FRACTION)]
    train = _arrays([r for r in rows if r["ts"].date() < cut])
    hold = _arrays([r for r in rows if r["ts"].date() >= cut])
    full = _arrays(rows)
    print(f"{len(rows)} usable quotes, {len(dates)} days; train < {cut} <= holdout")

    cal_grid = [(CALENDAR.session, CALENDAR.weeknight, CALENDAR.weekend)]
    t252 = TimeWeights.trading_252()
    fable_w = (0.8, 0.29, 0.6)

    fitted_train = fit(train)
    fitted_full = fit(full)
    compare = {
        "fitted": fitted_train,
        "calendar": fit(train, cal_grid),
        "trading_252": fit(train, [(t252.session, t252.weeknight, t252.weekend)]),
        "fable_bhavcopy_fit": fit(train, [fable_w]),
    }
    validated = error(hold, compare["fitted"]) < error(hold, compare["calendar"])

    lines = ["# ORB option-pricing time convention — calibration", "",
             f"Method and pre-registered rule: `scripts/calibrate_orb_time_convention.py` docstring "
             f"(committed before this run). {len(rows)} real intraday mid quotes over {len(dates)} days "
             f"({dates[0]} to {dates[-1]}); train < {cut}, holdout from {cut}.", "",
             "Weights are calendar-day-equivalents of decay per session / weeknight / weekend; "
             "k scales India VIX per index.", "",
             "## Train-fitted conventions, scored on the untouched holdout", "",
             "| Convention | session | weeknight | weekend | k NIFTY | k BANKNIFTY | Train MSE | Holdout MSE |",
             "|---|---|---|---|---|---|---|---|"]
    for name, p in compare.items():
        lines.append(f"| {name} | {p['session']:.2f} | {p['weeknight']:.2f} | {p['weekend']:.2f} | "
                     f"{p['k_nifty']:.2f} | {p['k_banknifty']:.2f} | {error(train, p):.4f} | {error(hold, p):.4f} |")
    lines += ["", f"Fitted beats calendar on the holdout: **{'YES' if validated else 'NO'}** "
              f"(pre-registered validation condition).", "",
              "## Frozen convention (full-sample fit) — used by the backtest", "",
              "```json", json.dumps({k: round(v, 4) for k, v in fitted_full.items()}, indent=2), "```", "",
              "Residuals of the frozen convention (negative = model too cheap):", ""]
    lines += residual_table(full, fitted_full)
    lines += ["", "Limitation (stated before running): few quotes under 4 days to expiry; "
              "BANKNIFTY month-end 1-3 DTE trades are extrapolated."]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
