#!/usr/bin/env python3
"""
QuantOS — Techno-Funda momentum: signal-count feasibility (2026-11-01)
────────────────────────────────────────────────────────────────────────
Step 1 of the Upasani-style techno-funda candidate (spec: fundamental quality
-- Piotroski >= 8, YoY profit growth > 15%, OPM > 15%, Rs 100-20,000 Cr -- plus
four daily price filters). Written BEFORE it was run. It computes NO returns:
it only counts how many stocks pass the price filters, to answer whether the
strategy can ever fill its 10-15 slots before we spend days fetching ~50,000
XBRL filings for the fundamental layer.

Price filters, on each daily close t (adjusted bars):
  T1  close > 0.85 * ATH          ATH = running max of adjusted high since the
                                  data starts (2016-01), so for older listings it
                                  is "high since 2016" -- a known limitation.
  T2  50 < RSI14 < 65             Wilder RSI on adjusted closes.
  T3  close > previous close
  T4  volume > SMA5(volume)       the 5-day mean includes day t, as the spec says.
  L   SMA50(traded value) > Rs 50 lakh   the spec's liquidity filter.

Data: NSE's daily equity bhavcopies (raw cache of core/fundamentals/pead/
eq_bhavcopy.py), EQ series, ETFs dropped. Every stock traded that day is listed,
including later delistings -- no survivorship from the source. Split/bonus
adjustment reuses the Darvas OOS adjuster (NSE corporate-action lists 2016-2026
plus its missing-split heuristic).

Market cap is NOT on hand yet (needs share counts from the XBRL filings), so
the Rs 20,000 Cr cap is bracketed: "all liquid" is the upper bound on counts;
"ex-top-200" drops the 200 largest names by median traded value over the prior
126 sessions (re-ranked each 1 Jan / 1 Jul) as a rough large-cap proxy. The
fundamental filters will cut counts further; this is a ceiling.

Counted from 2018-01-01 so every ATH has at least two years of history.

Usage: python scripts/count_techno_funda_signals.py
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.fundamentals.pead.eq_bhavcopy import CUTOVER_DATE, DEFAULT_RAW_CACHE_DIR  # noqa: E402
from scripts.backtest_darvas_atr_stop_oos import STD_FRACTIONS, action_factor  # noqa: E402

COUNT_FROM = date(2018, 1, 1)
ACTION_FILES = (Path("data_cache/nse_corporate_actions_2016_2023.json"),
                Path("data_cache/nse_corporate_actions_2024_2026.json"))
ATH_FRAC, RSI_LO, RSI_HI, RSI_N = 0.85, 50.0, 65.0, 14
LIQ_RS, LIQ_N = 5_000_000.0, 50
LARGE_N, LARGE_WINDOW = 200, 126
OUT = Path("docs/TECHNO_FUNDA_SIGNAL_COUNT.md")


# ─── Data ─────────────────────────────────────────────────────────────────────

def _read_day(p: Path, d: date) -> pd.DataFrame:
    with zipfile.ZipFile(p) as zf:
        df = pd.read_csv(io.BytesIO(zf.read(zf.namelist()[0])), dtype=str)
    if d >= CUTOVER_DATE:
        df = df[(df["FinInstrmTp"] == "STK") & (df["SctySrs"] == "EQ")]
        cols = {"TckrSymb": "sym", "OpnPric": "o", "HghPric": "h", "LwPric": "l",
                "ClsPric": "c", "TtlTradgVol": "vol", "TtlTrfVal": "val"}
    else:
        df = df[df["SERIES"].str.strip() == "EQ"]
        cols = {"SYMBOL": "sym", "OPEN": "o", "HIGH": "h", "LOW": "l",
                "CLOSE": "c", "TOTTRDQTY": "vol", "TOTTRDVAL": "val"}
    df = df[list(cols)].rename(columns=cols)
    df["sym"] = df["sym"].str.strip()
    df = df[~(df["sym"].str.endswith("BEES") | df["sym"].str.contains("ETF"))]
    for k in ("o", "h", "l", "c", "vol", "val"):
        df[k] = pd.to_numeric(df[k], errors="coerce")
    df = df.dropna()
    df = df[(df["c"] > 0) & (df["o"] > 0)]
    df["date"] = pd.Timestamp(d)
    return df


def load_bars() -> pd.DataFrame:
    frames = []
    for p in sorted(DEFAULT_RAW_CACHE_DIR.glob("*.zip")):
        d = datetime.strptime(p.stem, "%Y%m%d").date()
        frames.append(_read_day(p, d))
    return pd.concat(frames, ignore_index=True).sort_values(["sym", "date"], ignore_index=True)


def load_actions() -> dict[str, list[tuple[pd.Timestamp, float]]]:
    out: dict[str, list[tuple[pd.Timestamp, float]]] = defaultdict(list)
    for path in ACTION_FILES:
        for a in json.loads(path.read_text()):
            f = action_factor(a["subject"])
            if f:
                out[a["symbol"].strip()].append((pd.Timestamp(datetime.strptime(a["exDate"], "%d-%b-%Y")), f))
    return out


def adjust(g: pd.DataFrame, actions: list[tuple[pd.Timestamp, float]]) -> pd.DataFrame:
    """Same rule as backtest_darvas_atr_stop_oos.adjust, vectorised: bars before an
    ex-date scale by its factor; then standard-fraction gaps NSE's list missed."""
    dates = g["date"].to_numpy()
    mult = np.ones(len(g))
    for ex, f in actions:
        mult[dates < np.datetime64(ex)] *= f
    o, c = g["o"].to_numpy() * mult, g["c"].to_numpy() * mult
    gap_days = np.diff(dates).astype("timedelta64[D]").astype(int)
    ratio = o[1:] / c[:-1]
    extra = np.ones(len(g))
    for i in np.nonzero((ratio < 0.65) & (gap_days <= 6))[0]:
        f = next((x for x in STD_FRACTIONS if abs(ratio[i] / x - 1) < 0.04), None)
        if f:
            extra[: i + 1] *= f
    mult *= extra
    g = g.copy()
    for k in ("o", "h", "l", "c"):
        g[k] = g[k].to_numpy() * mult
    g["vol"] = g["vol"].to_numpy() / mult
    return g


# ─── Filters ──────────────────────────────────────────────────────────────────

def wilder_rsi(close: pd.Series, n: int = RSI_N) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + gain / loss)


def flags(g: pd.DataFrame) -> pd.DataFrame:
    c = g["c"]
    rsi = wilder_rsi(c)
    out = pd.DataFrame({"date": g["date"].to_numpy(), "sym": g["sym"].to_numpy()})
    out["t1"] = (c > ATH_FRAC * g["h"].cummax()).to_numpy()
    out["t2"] = ((rsi > RSI_LO) & (rsi < RSI_HI)).to_numpy()
    out["t3"] = (c > c.shift(1)).to_numpy()
    out["t4"] = (g["vol"] > g["vol"].rolling(5).mean()).to_numpy()
    out["liq"] = (g["val"].rolling(LIQ_N).mean() > LIQ_RS).to_numpy()
    return out


def large_cap_proxy(bars: pd.DataFrame) -> dict[pd.Timestamp, frozenset]:
    """Each 1 Jan / 1 Jul: the LARGE_N names with the highest median traded value
    over the prior LARGE_WINDOW sessions."""
    days = np.sort(bars["date"].unique())
    piv = bars.pivot_table(index="date", columns="sym", values="val")
    out = {}
    for y in range(COUNT_FROM.year, 2027):
        for m in (1, 7):
            rd = pd.Timestamp(y, m, 1)
            i = np.searchsorted(days, np.datetime64(rd))
            if i == 0 or i >= len(days):
                continue
            med = piv.loc[days[max(0, i - LARGE_WINDOW)]:days[i - 1]].median()
            out[rd] = frozenset(med.nlargest(LARGE_N).index)
    return out


# ─── Report ───────────────────────────────────────────────────────────────────

def describe(counts: pd.Series, label: str) -> list[str]:
    rows = [f"| {label} | median | p10 | p90 | days >=1 | days >=10 | days >=15 |",
            "|---|---|---|---|---|---|---|"]
    for y, s in counts.groupby(counts.index.year):
        rows.append(f"| {y} | {s.median():.0f} | {s.quantile(.1):.0f} | {s.quantile(.9):.0f} | "
                    f"{(s >= 1).mean():.0%} | {(s >= 10).mean():.0%} | {(s >= 15).mean():.0%} |")
    s = counts
    rows.append(f"| **all** | {s.median():.0f} | {s.quantile(.1):.0f} | {s.quantile(.9):.0f} | "
                f"{(s >= 1).mean():.0%} | {(s >= 10).mean():.0%} | {(s >= 15).mean():.0%} |")
    return rows


def main() -> int:
    bars = load_bars()
    actions = load_actions()
    bars = pd.concat([adjust(g, actions.get(s, [])) for s, g in bars.groupby("sym", sort=False)],
                     ignore_index=True)
    f = pd.concat([flags(g) for _, g in bars.groupby("sym", sort=False)], ignore_index=True)

    large = large_cap_proxy(bars)
    keys = sorted(large)
    period = pd.Series(pd.cut(f["date"], bins=keys + [pd.Timestamp(2100, 1, 1)], labels=keys, right=False))
    f["large"] = [s in large[p] if not pd.isna(p) else False for s, p in zip(f["sym"], period)]

    f = f[f["date"] >= pd.Timestamp(COUNT_FROM)]
    f["all4"] = f["t1"] & f["t2"] & f["t3"] & f["t4"] & f["liq"]
    f["all4_small"] = f["all4"] & ~f["large"]
    liq = f[f["liq"]]

    daily = f.groupby("date")[["all4", "all4_small"]].sum()
    wk = f.assign(week=f["date"].dt.to_period("W-FRI"))
    weekly = wk[wk["all4"]].groupby("week")["sym"].nunique().reindex(wk["week"].unique(), fill_value=0)
    weekly_small = wk[wk["all4_small"]].groupby("week")["sym"].nunique().reindex(wk["week"].unique(), fill_value=0)

    pass_rate = {k: liq[k].mean() for k in ("t1", "t2", "t3", "t4")}
    t12 = (liq["t1"] & liq["t2"]).mean()
    liq_daily = f.groupby("date")["liq"].sum()

    lines = [
        "# Techno-Funda momentum: signal-count feasibility",
        "",
        f"Run {date.today()} by `scripts/count_techno_funda_signals.py` (read its docstring for the "
        "rules, written before the run). Counts only, no returns. Window: "
        f"{f['date'].min():%Y-%m-%d} .. {f['date'].max():%Y-%m-%d}.",
        "",
        "These are CEILINGS: the fundamental filters (Piotroski >= 8, profit growth > 15%, "
        "OPM > 15%) and the true Rs 20,000 Cr cap are not applied yet.",
        "",
        f"Liquid universe (50-day mean traded value > Rs 50 lakh): median "
        f"{liq_daily.median():.0f} stocks a day.",
        "",
        "## How often each price filter passes (liquid stock-days)",
        "",
        "| filter | pass rate |",
        "|---|---|",
        f"| T1 close > 0.85 x ATH | {pass_rate['t1']:.1%} |",
        f"| T2 50 < RSI14 < 65 | {pass_rate['t2']:.1%} |",
        f"| T3 green day | {pass_rate['t3']:.1%} |",
        f"| T4 volume > SMA5 | {pass_rate['t4']:.1%} |",
        f"| T1 and T2 | {t12:.1%} |",
        f"| all four | {liq['all4'].mean():.2%} |",
        "",
        "## Stocks passing all four filters on a day: all liquid stocks",
        "",
        *describe(daily["all4"], "year"),
        "",
        "## Same, excluding the top 200 by traded value (rough large-cap proxy)",
        "",
        *describe(daily["all4_small"], "year"),
        "",
        "## Distinct stocks passing on at least one day of the week",
        "",
        "| universe | median | p10 | weeks >=10 | weeks >=15 |",
        "|---|---|---|---|---|",
        f"| all liquid | {weekly.median():.0f} | {weekly.quantile(.1):.0f} | "
        f"{(weekly >= 10).mean():.0%} | {(weekly >= 15).mean():.0%} |",
        f"| ex-top-200 | {weekly_small.median():.0f} | {weekly_small.quantile(.1):.0f} | "
        f"{(weekly_small >= 10).mean():.0%} | {(weekly_small >= 15).mean():.0%} |",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
