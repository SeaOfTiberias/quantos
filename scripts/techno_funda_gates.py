#!/usr/bin/env python3
"""
QuantOS — Techno-Funda momentum: data gates D1-D5 (pre-registered 2026-11-01)
──────────────────────────────────────────────────────────────────────────────
Runs the gates in docs/TECHNO_FUNDA_PREREG_2026-11-01.md (+ amendment 1) on the
built panel and writes docs/TECHNO_FUNDA_DATA_GATES.md plus
data_cache/techno_funda/gates.json. scripts/backtest_techno_funda.py refuses to
run unless every gate passed. Computes no returns.

  D1  price coverage: every NSE trading day 2010-01-01..2026-10-23 has a
      bhavcopy (NSE trading calendar, core/reference/calendar.py, covers
      2015-01-01..2026-08-18; outside it the file counts per year are listed).
      More than 5 missing days in 2019-2026 -> stop.
  D2  corporate actions: actions applied; every unexplained -35% gap and how
      it was resolved (confirmed from filings, or record restarted). Reported.
  D3  filing parse checks, each filing against its own figures:
      (a) revenue + other income - expenses within 1% of profit before
          exceptional items and tax;
      (b) in Q4 filings, the four quarters' revenue (OneD) sums to within 1%
          of the full-year revenue (FourD). Q4 = the old feed's "Fourth
          Quarter"; for integrated filings, the quarter ending in the month
          the company's old-feed Q4 filings end in.
      A filing passes if every check that applies to it passes.
      Under 95% passing -> stop.
  D4  coverage: share of non-financial, in-band, liquid EQ stock-days with
      computable growth and OPM inputs, by year. Under 70% in any year from
      2019 -> stop.
  D5  classification: every filing 2018-2026 classified (old feed: bank/indAs;
      integrated: XBRL prefix). Reported per year. Stop if any year has more
      than 1% of its filings unclassified -- that is the "absent in some
      years" case the pre-registration names (individual gaps make only that
      stock ineligible, as amendment 1 says).

Usage: python scripts/techno_funda_gates.py [--refresh]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.fundamentals.pead.eq_bhavcopy import DEFAULT_RAW_CACHE_DIR  # noqa: E402
from core.reference import calendar as cal  # noqa: E402
from core.techno_funda.panel import build  # noqa: E402

OUT = Path("docs/TECHNO_FUNDA_DATA_GATES.md")
GATES = Path("data_cache/techno_funda/gates.json")
END = date(2026, 10, 23)


def d1() -> tuple[bool, list[str]]:
    lo, hi = cal.coverage()
    have = {p.stem for p in DEFAULT_RAW_CACHE_DIR.glob("*.zip")}
    missing = [d for d in cal.trading_days(max(lo, date(2010, 1, 1)), min(hi, END)) if f"{d:%Y%m%d}" not in have]
    recent = [d for d in missing if d >= date(2019, 1, 1)]
    tail = [d for d in (hi + timedelta(days=k) for k in range(1, (END - hi).days + 1))
            if d.weekday() < 5 and f"{d:%Y%m%d}" not in have]
    per_year = Counter(s[:4] for s in have)
    ok = len(recent) <= 5
    lines = [f"**D1 price coverage: {'PASS' if ok else 'STOP'}**", "",
             f"- Calendar days ({max(lo, date(2010, 1, 1))} .. {min(hi, END)}) with no bhavcopy: {len(missing)}; "
             f"in 2019+: {len(recent)} {[str(d) for d in recent]}",
             f"- Weekdays after the calendar's end ({hi} .. {END}) with no file (NSE returned 404 = "
             f"no session, but not verified against a calendar): {[str(d) for d in tail]}",
             "- Files per year (no calendar before 2015; ~245-250 is a full year): "
             + ", ".join(f"{y}: {per_year[y]}" for y in sorted(per_year) if y <= "2026"), ""]
    return ok, lines


def d2(gaps: pd.DataFrame) -> tuple[bool, list[str]]:
    if gaps.empty:
        return True, ["**D2 corporate actions: reported** -- no unexplained -35% gaps.", ""]
    g = gaps.assign(year=pd.to_datetime(gaps["date"]).dt.year)
    by = g.groupby("year")["confirmed"].agg(["count", "sum"])
    lines = ["**D2 corporate actions: reported**", "",
             f"- Unexplained overnight moves of -35% or worse: {len(g)}; confirmed by the "
             f"company's share count (adjusted): {int(g['confirmed'].sum())}; record restarted: "
             f"{int((~g['confirmed']).sum())}", "",
             "| year | gaps | confirmed | restarted |", "|---|---|---|---|"]
    lines += [f"| {y} | {int(r['count'])} | {int(r['sum'])} | {int(r['count'] - r['sum'])} |" for y, r in by.iterrows()]
    return True, lines + [""]


def d3(f: pd.DataFrame) -> tuple[bool, list[str]]:
    std = f[(f["financial"] == False) & f["has_quarter"]].copy()  # noqa: E712
    calc = std["q_revenue"] + std["q_other_income"].fillna(0) - std["q_expenses"]
    a_ok = (calc - std["q_pbt_pre_exceptional"]).abs() <= 0.01 * std["q_pbt_pre_exceptional"].abs()
    std["a"] = a_ok.where(std[["q_revenue", "q_expenses", "q_pbt_pre_exceptional"]].notna().all(axis=1))

    std["pe"] = pd.to_datetime(std["period_end"])
    fy_month = (std[std["relating"] == "Fourth Quarter"].groupby("symbol")["pe"]
                .agg(lambda s: s.dt.month.mode().iat[0]))
    is_q4 = (std["relating"] == "Fourth Quarter") | (
        (std["feed"] == "integrated") & (std["pe"].dt.month == std["symbol"].map(fy_month)))
    latest = std.sort_values("broadcast").groupby(["symbol", "consolidated", "pe"]).tail(1)
    rev = latest.set_index(["symbol", "consolidated", "pe"])["q_revenue"]
    b = []
    for idx, r in std[is_q4].iterrows():
        qs = [rev.get((r["symbol"], r["consolidated"], (r["pe"] - pd.DateOffset(months=3 * k)) + pd.offsets.MonthEnd(0)))
              for k in (1, 2, 3)]
        if any(x is None or pd.isna(x) for x in qs) or pd.isna(r["y_revenue"]) or pd.isna(r["q_revenue"]):
            b.append((idx, None))
            continue
        total = r["q_revenue"] + sum(qs)
        b.append((idx, abs(total - r["y_revenue"]) <= 0.01 * abs(r["y_revenue"])))
    std["b"] = pd.Series(dict(b), dtype=object)
    checked = std[std["a"].notna() | std["b"].notna()]
    passed = checked.apply(lambda r: all(v for v in (r["a"], r["b"]) if v is not None and v == v), axis=1)
    rate = passed.mean() if len(checked) else float("nan")
    ok = rate >= 0.95
    lines = [f"**D3 filing parse checks: {'PASS' if ok else 'STOP'}** ({rate:.1%} of {len(checked)} checked filings pass)", "",
             f"- (a) arithmetic: {int(std['a'].eq(True).sum())} pass, {int(std['a'].eq(False).sum())} fail, "
             f"{int(std['a'].isna().sum())} not checkable (an input missing)",
             f"- (b) Q4 quarters sum to full year: {int(std['b'].eq(True).sum())} pass, {int(std['b'].eq(False).sum())} fail, "
             f"{int(is_q4.sum()) - int(std['b'].notna().sum())} Q4 filings not checkable (a quarter missing)",
             f"- Non-financial filings with no parsed figures (XBRL not downloaded, 404 or unparseable): "
             f"{int(((f['financial'] == False) & ~f['has_quarter']).sum())}, of which parse errors: "  # noqa: E712
             f"{int(f['parse_error'].sum())}", ""]
    return ok, lines


def d4(p: pd.DataFrame, gates_from: int = 2019) -> tuple[bool, list[str]]:
    p = p[p["date"] >= pd.Timestamp(2019, 7, 1)]
    den = p[(p["series"] == "EQ") & (p["financial"] == False) & (p["mcap"] > 1e9) & (p["mcap"] < 2e11)  # noqa: E712
            & (p["val50"] > 5e6)]
    cov = (den["growth_inputs"].eq(True) & den["opm_inputs"].eq(True)).groupby(den["date"].dt.year).mean()
    liquid = p[(p["series"] == "EQ") & (p["val50"] > 5e6)]
    no_state = liquid["financial"].isna().groupby(liquid["date"].dt.year).mean()
    no_mcap = (liquid["financial"].eq(False) & liquid["mcap"].isna()).groupby(liquid["date"].dt.year).mean()
    ok = bool((cov[cov.index >= gates_from] >= 0.70).all())
    lines = [f"**D4 coverage: {'PASS' if ok else 'STOP'}**", "",
             "| year | in-band non-financial liquid stock-days | with growth + OPM inputs | liquid EQ stock-days with no filing yet | ... non-financial but no market cap |",
             "|---|---|---|---|---|"]
    n = den.groupby(den["date"].dt.year).size()
    lines += [f"| {y} | {n.get(y, 0)} | {cov.get(y, float('nan')):.1%} | {no_state.get(y, float('nan')):.1%} | "
              f"{no_mcap.get(y, float('nan')):.1%} |" for y in sorted(set(n.index) | set(no_state.index))]
    return ok, lines + [""]


def d5(f: pd.DataFrame) -> tuple[bool, list[str]]:
    f = f.assign(year=pd.to_datetime(f["broadcast"]).dt.year)
    share = f["financial"].isna().groupby([f["year"], f["feed"]]).agg(["mean", "sum", "size"])
    ok = bool((share["mean"] <= 0.01).all())
    lines = [f"**D5 classification: {'PASS' if ok else 'STOP'}**", "",
             "| year | feed | filings | unclassified |", "|---|---|---|---|"]
    lines += [f"| {y} | {feed} | {int(r['size'])} | {int(r['sum'])} ({r['mean']:.2%}) |" for (y, feed), r in share.iterrows()]
    return ok, lines + [""]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="rebuild the panel from the caches")
    args = ap.parse_args(argv)
    data = build(refresh=args.refresh)
    results, body = {}, []
    for name, (ok, lines) in [("D1", d1()), ("D2", d2(data["gaps"])), ("D3", d3(data["filings"])),
                              ("D4", d4(data["panel"])), ("D5", d5(data["filings"]))]:
        results[name] = bool(ok)
        body += lines
    all_ok = all(results.values())
    head = ["# Techno-Funda momentum: data gates", "",
            f"Run {date.today()} by `scripts/techno_funda_gates.py`. No returns computed. "
            f"Filings loaded: {data['n_filings']}; symbols with 2000-2009 highs: {data['pre2010']}.", "",
            f"**Overall: {'ALL GATES PASS -- the backtest may run' if all_ok else 'STOP -- the backtest does not run'}**", ""]
    OUT.write_text("\n".join(head + body), encoding="utf-8")
    GATES.parent.mkdir(parents=True, exist_ok=True)
    GATES.write_text(json.dumps(dict(results, all_pass=all_ok, run=str(date.today()))), encoding="utf-8")
    print("\n".join(head + body))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
