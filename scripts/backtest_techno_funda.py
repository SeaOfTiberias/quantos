#!/usr/bin/env python3
"""
QuantOS — Techno-Funda momentum (without Piotroski): the pre-registered backtest
────────────────────────────────────────────────────────────────────────────────
Rules, periods, costs, benchmark and pass criteria are frozen in
docs/TECHNO_FUNDA_PREREG_2026-11-01.md (+ amendment 1); the code is in
core/techno_funda/. Refuses to run unless scripts/techno_funda_gates.py passed
every data gate.

One continuous run from 2019-07-01 to 2026-10-23 (Rs 10L start). The held-out
test is the NAV path from the close of 2024-10-22 to 2026-10-23 -- positions
held at the split carry over, as they would in real trading.

Verdict (Base costs, held-out test, all must hold):
  P1 Sharpe > 0.80   P2 max drawdown < 20%   P3 CAGR > equal-weight universe
  P4 (capital-readiness) 90% week-block bootstrap CI of daily excess return
     over the benchmark has its lower end > 0; P1-P3 without P4 ->
     "PASS, not capital-ready".

--smoke runs the whole pipeline on whatever data exists and prints only counts
(signals, trades), never a return, for checking the code before the gates pass.

Usage: python scripts/backtest_techno_funda.py [--smoke]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.techno_funda import portfolio as pf  # noqa: E402
from core.techno_funda.panel import build  # noqa: E402

START, SPLIT, END = pd.Timestamp(2019, 7, 1), pd.Timestamp(2024, 10, 23), pd.Timestamp(2026, 10, 23)
GATES = Path("data_cache/techno_funda/gates.json")
OUT = Path("docs/TECHNO_FUNDA_RESULTS.md")
# context only, not a criterion: NSE price indices (TradingView daily closes, matched to
# NSE's own ind_close_all files on sample dates); a missing session carries the last close
INDICES = Path("data_cache/techno_funda/indices")
CONTEXT = [("Nifty 500", "NIFTY500"), ("Nifty MidSmallcap 400", "MIDSMALLCAP400"),
           ("Nifty Smallcap 250", "SMALLCAP250")]
LAYERS = [("price filters only", "price_sig"), ("price + profit growth", "sig_f1"),
          ("price + growth + OPM (the pre-registered rule)", "sig")]


def wide(p: pd.DataFrame, col: str, fill=np.nan) -> pd.DataFrame:
    w = p.pivot(index="date", columns="sym", values=col)
    if fill != fill:
        return w
    # fill BEFORE casting: bool(NaN) is True, which would invent signals
    return pd.DataFrame(np.where(w.isna(), fill, w), index=w.index, columns=w.columns).astype(type(fill))


def arrays(p: pd.DataFrame, last_bar: pd.Series):
    p = p[(p["date"] >= START) & (p["date"] <= END)]
    close = wide(p, "c")
    syms, dates = list(close.columns), close.index
    get = lambda col, fill=np.nan: wide(p, col, fill).reindex(index=dates, columns=syms)  # noqa: E731
    has_bar = close.notna().to_numpy()
    lb = last_bar.reindex(syms)
    last_idx = np.array([dates.get_indexer([d])[0] if d in dates else (len(dates) if d > dates[-1] else -1)
                         for d in lb])
    return dict(dates=dates, syms=syms, open=get("o").to_numpy(), close=close.to_numpy(),
                mult=get("mult").ffill().bfill().to_numpy(), has_bar=has_bar,
                rank=get("rank", 0.0).to_numpy(), exit=get("exit_sig", False).to_numpy().astype(bool),
                univ=get("univ", False).to_numpy().astype(bool), last=last_idx,
                sig={k: get(k, False).to_numpy().astype(bool) for _, k in LAYERS})


def benchmark(a) -> np.ndarray:
    """Equal-weight daily return of stocks eligible at the previous close."""
    c = a["close"]
    r = c[1:] / c[:-1] - 1
    ok = a["univ"][:-1] & a["has_bar"][1:] & a["has_bar"][:-1]
    return np.where(ok, r, 0).sum(axis=1) / np.maximum(ok.sum(axis=1), 1)


def index_nav(name: str, dates: pd.DatetimeIndex) -> np.ndarray | None:
    path = INDICES / f"{name}.csv"
    if not path.exists():
        return None
    c = pd.read_csv(path, parse_dates=["date"]).set_index("date")["c"]
    return c.reindex(c.index.union(dates)).ffill().reindex(dates).to_numpy()


def stats(nav: np.ndarray, dates: pd.DatetimeIndex) -> dict:
    r = pf.daily_returns(nav)
    years = (dates[-1] - dates[0]).days / 365.25
    return dict(cagr=pf.cagr(nav, years), sharpe=pf.sharpe(r), sortino=pf.sortino(r), mdd=pf.max_drawdown(nav))


def trade_stats(trades: list[pf.Trade], dates) -> dict:
    if not trades:
        return dict(n=0)
    ret = np.array([t.ret for t in trades])
    wins, losses = ret[ret > 0], ret[ret <= 0]
    return dict(n=len(trades), win_rate=float((ret > 0).mean()),
                win_loss=float(wins.mean() / -losses.mean()) if len(wins) and len(losses) and losses.mean() < 0 else float("nan"),
                avg_hold=float(np.mean([(dates[t.exit_day] - dates[t.entry_day]).days for t in trades])),
                reasons=pd.Series([t.reason for t in trades]).value_counts().to_dict())


def fmt(s: dict) -> str:
    return f"{s['cagr']:+.1%} | {s['sharpe']:.2f} | {s['sortino']:.2f} | {s['mdd']:.1%}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)
    if not args.smoke:
        g = json.loads(GATES.read_text()) if GATES.exists() else {}
        if not g.get("all_pass"):
            print(f"Data gates have not all passed ({GATES}): {g or 'not run'}. Not running.")
            return 2
    data = build()
    a = arrays(data["panel"], data["last_bar"])
    dates = a["dates"]
    runs = {k: pf.simulate(a["open"], a["close"], a["mult"], a["has_bar"], a["sig"][k], a["rank"], a["exit"],
                           a["last"], a["syms"]) for _, k in LAYERS}
    if args.smoke:
        for name, k in LAYERS:
            print(f"{name}: signal stock-days {int(a['sig'][k].sum())}, trades {len(runs[k].trades)}")
        print(f"days {len(dates)} ({dates[0].date()} .. {dates[-1].date()}), symbols {len(a['syms'])}")
        return 0

    bench_r = benchmark(a)
    bench = np.r_[1.0, np.cumprod(1 + bench_r)] * pf.NAV0
    split = dates.get_indexer([dates[dates >= SPLIT][0]])[0] - 1     # close of 2024-10-22
    per = {"test": slice(split, None), "dev": slice(0, split + 1), "full": slice(0, None)}

    lines = ["# Techno-Funda momentum (without Piotroski): results", "",
             f"Run {date.today()} by `scripts/backtest_techno_funda.py`. Rules frozen in "
             "`docs/TECHNO_FUNDA_PREREG_2026-11-01.md` (+ amendment 1); data gates in "
             "`docs/TECHNO_FUNDA_DATA_GATES.md`. Base costs. Price returns (no dividends) for the "
             "strategy and the benchmark; idle cash earns 0%.", ""]

    main_run = runs["sig"]
    t = per["test"]
    st, bt = stats(main_run.nav[t], dates[t]), stats(bench[t], dates[t])
    excess = pf.daily_returns(main_run.nav[t]) - bench_r[split:]
    weeks = dates[t][1:].isocalendar()
    lo, hi = pf.block_bootstrap_ci(excess, (weeks["year"] * 100 + weeks["week"]).to_numpy())
    p1, p2, p3, p4 = st["sharpe"] > 0.80, st["mdd"] < 0.20, st["cagr"] > bt["cagr"], lo > 0
    verdict = ("PASS" if p4 else "PASS, not capital-ready") if (p1 and p2 and p3) else "FAIL"
    lines += [f"## Verdict: **{verdict}**", "",
              f"Held-out test {dates[t][0].date()} .. {dates[t][-1].date()}:", "",
              "| criterion | result | needed | met |", "|---|---|---|---|",
              f"| P1 Sharpe | {st['sharpe']:.2f} | > 0.80 | {'yes' if p1 else 'no'} |",
              f"| P2 max drawdown | {st['mdd']:.1%} | < 20% | {'yes' if p2 else 'no'} |",
              f"| P3 CAGR vs equal-weight universe | {st['cagr']:+.1%} vs {bt['cagr']:+.1%} | above | {'yes' if p3 else 'no'} |",
              f"| P4 90% CI of daily excess return | {lo * 1e4:+.1f} .. {hi * 1e4:+.1f} bps/day | lower end > 0 | {'yes' if p4 else 'no'} |",
              "", "PASS means paper trading forward only. No capital without the user's explicit go-ahead.", "",
              "## All layers and periods (CAGR | Sharpe | Sortino | max drawdown)", "",
              "| layer | test | development | full |", "|---|---|---|---|"]
    for name, k in LAYERS:
        nav = runs[k].nav
        lines.append(f"| {name} | " + " | ".join(fmt(stats(nav[per[x]], dates[per[x]])) for x in ("test", "dev", "full")) + " |")
    lines.append("| equal-weight universe (benchmark, no costs) | "
                 + " | ".join(fmt(stats(bench[per[x]], dates[per[x]])) for x in ("test", "dev", "full")) + " |")
    missing = []
    for label, name in CONTEXT:
        nav = index_nav(name, dates)
        if nav is None or np.isnan(nav).any():
            missing.append(label)
            continue
        lines.append(f"| {label} (context, price index) | "
                     + " | ".join(fmt(stats(nav[per[x]], dates[per[x]])) for x in ("test", "dev", "full")) + " |")

    lines += ["", "## Trades (pre-registered rule, full period)", ""]
    ts = trade_stats(main_run.trades, dates)
    if ts["n"]:
        lines += [f"- Trades: {ts['n']}; win rate {ts['win_rate']:.1%}; average win / average loss {ts['win_loss']:.2f}; "
                  f"average hold {ts['avg_hold']:.0f} days; exits by reason {ts['reasons']}",
                  f"- Total costs paid: Rs {main_run.costs:,.0f}; average invested share of NAV "
                  f"{np.mean(main_run.invested / main_run.nav):.0%}"]
    else:
        lines.append("- No trades.")

    years = pd.Series(main_run.nav, index=dates).groupby(dates.year).agg(["first", "last"])
    byear = pd.Series(bench, index=dates).groupby(dates.year).agg(["first", "last"])
    lines += ["", "## Per year (rule vs benchmark, price return within the year)", "", "| year | rule | benchmark |", "|---|---|---|"]
    lines += [f"| {y} | {r['last'] / r['first'] - 1:+.1%} | {byear.loc[y, 'last'] / byear.loc[y, 'first'] - 1:+.1%} |"
              for y, r in years.iterrows()]
    lines += ["", "Index rows are context, not a pass criterion: NSE price indices (no dividends, like the "
              "strategy and benchmark rows), daily closes from TradingView, matched exactly to NSE's own "
              f"ind_close_all files on sample dates. {'Not on hand: ' + ', '.join(missing) + '.' if missing else ''}", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
