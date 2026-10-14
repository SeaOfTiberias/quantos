#!/usr/bin/env python3
"""
QuantOS — "Straying Duckling" Residual Mean Reversion (Avellaneda-Lee)
──────────────────────────────────────────────────────────────────────
One driver, one pre-registered config per universe:

  niftybank  docs/STATARB_BANKNIFTY_METHODOLOGY.md  (primary M1)
  nifty50    docs/STATARB_NIFTY50_METHODOLOGY.md    (primary PCA5)

Data: cached NSE F&O bhavcopy zips (no Fyers token needed) + NSE results
dates for the blackout.

Usage:
    python scripts/statarb_residual.py --universe nifty50 scan
    python scripts/statarb_residual.py --universe nifty50 backtest
"""

import argparse
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.pairs.universe import fetch_sector_constituents  # noqa: E402
from core.statarb.backtest import (  # noqa: E402
    calibrate, compute_scores, concurrency, metrics, simulate, verdict,
)
from core.statarb.data import load_futures_panel, results_reaction_days  # noqa: E402
from core.statarb.residuals import PCA_WINDOW, build_panel, exclusion_reasons, score  # noqa: E402

RESULTS_BLACKOUT_DAYS = 5

# Sector priority + merges for MKT_SECTOR, docs/STATARB_NIFTY50_METHODOLOGY.md.
SECTOR_PRIORITY = [
    ("niftybank", "bank"), ("niftyit", "it"), ("niftypharma", "health"), ("niftyhealthcare", "health"),
    ("niftyauto", "auto"), ("niftyfmcg", "fmcg"), ("niftymetal", "metal"), ("niftyoilgas", "energy"),
    ("niftyenergy", "energy"), ("niftyfinance", "finance"), ("niftyrealty", "realty"),
    ("niftyconsumerdurables", "consumer_durables"), ("niftymedia", "media"),
]

UNIVERSES = {
    "niftybank": dict(
        title="BankNifty", index="niftybank", models=("M1", "M2"), primary="M1",
        recent_years=(2025,), use_filings=True, sectors=False,
        methodology="docs/STATARB_BANKNIFTY_METHODOLOGY.md", out="docs/STATARB_BANKNIFTY_RESULTS.md",
        limitations=[
            "- Hedge P&L uses the leave-one-out peer basket; a live hedge would be one BANKNIFTY future "
            "(tracking error not modelled). M2's 13-stock hedge is costed as one instrument (understated).",
            "- Results dates: NSE's filing-metadata API returns almost nothing after ~2025-02, which left the "
            "blackout mostly off for 2025-26 in the first run. Fixed (data, not rules) by merging NSE "
            "results board-meeting dates (date only; meeting day = reaction day). The first run's verdict "
            "was also FAIL (M1 PF 0.78, calibration t -0.40).",
        ],
    ),
    "nifty50": dict(
        title="Nifty 50", index="nifty50", models=("PCA5", "MKT_SECTOR"), primary="PCA5",
        recent_years=(2024, 2025), use_filings=False, sectors=True,
        methodology="docs/STATARB_NIFTY50_METHODOLOGY.md", out="docs/STATARB_NIFTY50_RESULTS.md",
        limitations=[
            "- PCA5's hedge spans up to 49 stocks; each trade is costed as ONE futures-equivalent leg of "
            "notional N x sum|h| (understates instrument count, ignores netting across the book).",
            "- Results dates from NSE board-meeting dates only (date, no time; meeting day = reaction day).",
            "- Recent listings / demergers (TMPV, BSE, JIOFIN, MAXHEALTH, ...) take part only after 252 "
            "days of their own futures history. ZOMATO->ETERNAL and TATAGLOBAL->TATACONSUM spliced as pure renames; SHRIRAMFIN (amalgamation) not spliced.",
        ],
    ),
}


def sector_map(symbols: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for index, sector in SECTOR_PRIORITY:
        for s in fetch_sector_constituents(index):
            if s in symbols:
                out.setdefault(s, sector)
    return out


def _load(cfg):
    symbols = fetch_sector_constituents(cfg["index"])
    print(f"{cfg['index']} constituents ({len(symbols)}): {', '.join(symbols)}")
    series = load_futures_panel(symbols, date.today())
    missing = sorted(set(symbols) - set(series))
    if missing:
        print(f"  no futures data: {', '.join(missing)}")
    panel = build_panel(series)
    print(f"  panel {panel.dates[0]} -> {panel.dates[-1]}, {len(panel.dates)} days, {len(panel.symbols)} symbols")
    results_days, upcoming = results_reaction_days(panel.symbols, panel.dates, use_filings=cfg["use_filings"])
    for year in range(panel.dates[0].year + 1, panel.dates[-1].year):
        thin = [s for s in panel.symbols
                if sum(1 for i in results_days[s] if panel.dates[i].year == year) < 4]
        if thin:
            print(f"  note: <4 results days in {year} for {', '.join(thin)}")
    sectors = sector_map(panel.symbols) if cfg["sectors"] else None
    return panel, results_days, upcoming, sectors


# ─── scan ───────────────────────────────────────────────────────────────────

def cmd_scan(cfg, args) -> int:
    panel, results_days, upcoming, sectors = _load(cfg)
    t = len(panel.dates) - 1
    soon = panel.dates[t] + timedelta(days=RESULTS_BLACKOUT_DAYS * 7 // 5 + 1)
    primary, other = cfg["models"]
    print(f"\n{cfg['title']} residual scan as of {panel.dates[t]}  "
          f"(UNVALIDATED unless {cfg['out']} says PASS)\n")
    hdr = (f"{'symbol':<12}{'s ' + primary:>8}{'s ' + other:>14}{'hl(d)':>7}{'speed':>7}"
           f"  {'results':<8} note")
    print(hdr)
    print("-" * len(hdr))
    reasons = exclusion_reasons(panel, t)
    rows = []
    for j, sym in enumerate(panel.symbols):
        a = score(panel, t, j, primary, reasons, sectors)
        b = score(panel, t, j, other, reasons, sectors)
        near = (any(abs(t - r) <= RESULTS_BLACKOUT_DAYS for r in results_days[sym])
                or any(m <= soon for m in upcoming[sym]))
        cand = a.tradeable and abs(a.s) >= 1.25 and not near
        note = a.excluded or ("CANDIDATE " + ("long" if a.s < 0 else "short") if cand else "")
        rows.append((abs(a.s) if a.s is not None else -1, sym, a, b, near, note))
    rows.sort(reverse=True, key=lambda r: r[0])
    shown = rows if args.all else [r for r in rows if r[0] >= 1.0 or r[5]]
    for _, sym, a, b, near, note in shown:
        f = lambda x, w: f"{x:{w}.2f}" if x is not None else f"{'-':>{w}}"  # noqa: E731
        hl = f"{a.fit.half_life_days:7.1f}" if a.fit else f"{'-':>7}"
        speed = f"{'ok' if a.speed_ok else 'slow':>7}" if a.fit else f"{'-':>7}"
        print(f"{sym:<12}{f(a.s, 8)}{f(b.s, 14)}{hl}{speed}  {'YES' if near else '':<8} {note}")
    if not args.all:
        print(f"({len(rows) - len(shown)} names with |s| < 1.0 hidden; --all to show)")
    print("\ns < 0: stock lagging its family (long candidate); s > 0: running ahead (short candidate).")
    nxt = sorted((m, sym) for sym in panel.symbols for m in upcoming[sym] if m <= panel.dates[t] + timedelta(days=21))
    if nxt:
        print("Results board meetings next 3 weeks: " + ", ".join(f"{sym} {m:%d-%b}" for m, sym in nxt))
    return 0


# ─── backtest ───────────────────────────────────────────────────────────────

def _fmt_metrics(m) -> str:
    return (f"{m.total_trades} | {m.win_rate:.1%} | {m.profit_factor:.2f} | {m.sharpe_ratio:.2f} | "
            f"{m.net_profit_pct:+.1f}% | {m.max_drawdown_pct:.1f}% | {m.avg_bars_held:.1f} |")


def cmd_backtest(cfg, args) -> int:
    panel, results_days, _, sectors = _load(cfg)
    start_idx = PCA_WINDOW + 1
    print(f"  evaluation from {panel.dates[start_idx]} to {panel.dates[-1]}")

    results = {}
    for model in cfg["models"]:
        print(f"\n[{model}] scoring ...")
        scores = compute_scores(panel, model, start_idx, sectors)
        trades = simulate(panel, scores, start_idx, results_days)
        cal = calibrate(panel, scores, start_idx)
        checks = verdict(trades, cal, cfg["recent_years"])
        m = metrics(trades)
        print(f"  {len(trades)} trades, PF {m.profit_factor:.2f}, Sharpe {m.sharpe_ratio:.2f}, "
              f"calibration t {cal.t_stat:.2f}")
        excl = Counter(s.excluded for row in scores[start_idx:] for s in row if s and s.excluded)
        results[model] = (trades, cal, checks, m, excl, concurrency(trades, panel, start_idx))

    out = args.out or cfg["out"]
    Path(out).write_text(_build_report(cfg, panel, start_idx, results, sectors), encoding="utf-8")
    print(f"\nWrote {out}")
    return 0


def _build_report(cfg, panel, start_idx, results, sectors) -> str:
    primary, other = cfg["models"]
    L = [
        f"# {cfg['title']} Residual Mean Reversion — Results",
        "",
        f"Methodology: {cfg['methodology']} (pre-registered). "
        f"Universe ({len(panel.symbols)}): {', '.join(panel.symbols)}. "
        f"Evaluation {panel.dates[start_idx]} to {panel.dates[-1]}. "
        "All figures net of the futures cost model + 2 bps/side slippage; % basis = ₹5L stock-leg notional.",
        "",
    ]
    checks = results[primary][2]
    L += [f"## Verdict ({primary}, primary)", "", f"**{'PASS' if all(checks.values()) else 'FAIL'}**", "",
          f"| Check | {primary} | {other} (info only) |", "|---|---|---|"]
    for k in checks:
        L.append(f"| {k} | {'pass' if checks[k] else 'FAIL'} | {'pass' if results[other][2][k] else 'FAIL'} |")
    L.append("")

    hdr = ["| Slice | Trades | Win rate | PF | Sharpe | Net % (sum) | Max DD | Avg days |",
           "|---|---|---|---|---|---|---|---|"]
    for model, (trades, cal, _, m, excl, (avg_open, max_open)) in results.items():
        L += [f"## {model}", "", "### Trade summary", ""] + hdr
        L.append(f"| All | {_fmt_metrics(m)}")
        ordered = sorted(trades, key=lambda x: x.exit_date)
        mid = len(ordered) // 2
        if mid:
            L.append(f"| First half | {_fmt_metrics(metrics(ordered[:mid]))}")
            L.append(f"| Second half | {_fmt_metrics(metrics(ordered[mid:]))}")
        for side in ("LONG", "SHORT"):
            sub = [t for t in trades if t.side == side]
            if sub:
                L.append(f"| {side.title()} only | {_fmt_metrics(metrics(sub))}")
        for year in sorted({t.exit_date.year for t in trades}):
            sub = [t for t in trades if t.exit_date.year == year]
            L.append(f"| {year} | {_fmt_metrics(metrics(sub))}")
        gross = sum(t.gross_pnl for t in trades)
        cost = sum(t.cost for t in trades)
        L += ["", f"Gross P&L ₹{gross:,.0f}, costs ₹{cost:,.0f}, net ₹{gross - cost:,.0f}. "
                  f"Open positions: average {avg_open:.1f}, max {max_open}.", ""]

        L += ["### Exit reasons", "", "| Reason | Trades | Net P&L |", "|---|---|---|"]
        for reason, n in Counter(t.exit_reason for t in trades).most_common():
            L.append(f"| {reason} | {n} | ₹{sum(t.net_pnl for t in trades if t.exit_reason == reason):,.0f} |")
        L.append("")
        if sectors:
            L += ["### Per sector (info only)", "", "| Sector | Trades | Net P&L | PF |", "|---|---|---|---|"]
            for sec in sorted({sectors.get(t.symbol, "unassigned") for t in trades}):
                sub = [t for t in trades if sectors.get(t.symbol, "unassigned") == sec]
                L.append(f"| {sec} | {len(sub)} | ₹{sum(t.net_pnl for t in sub):,.0f} | "
                         f"{metrics(sub).profit_factor:.2f} |")
            L.append("")
        L += ["### Per symbol", "", "| Symbol | Trades | Net P&L | PF |", "|---|---|---|---|"]
        for sym in panel.symbols:
            sub = [t for t in trades if t.symbol == sym]
            if sub:
                L.append(f"| {sym} | {len(sub)} | ₹{sum(t.net_pnl for t in sub):,.0f} | "
                         f"{metrics(sub).profit_factor:.2f} |")
        L += ["", "### Calibration (10-day forward residual return, non-overlapping, tradeable days)", "",
              "| s bucket | Samples | Mean fwd residual |", "|---|---|---|"]
        for label, (n, mean) in cal.buckets.items():
            L.append(f"| {label} | {n} | {mean:+.2%} |" if n else f"| {label} | 0 | - |")
        L += ["", f"Long bucket (s ≤ −1.25): n={cal.long_n}, mean {cal.long_mean:+.2%}. "
                  f"Short bucket (s ≥ +1.25): n={cal.short_n}, mean {cal.short_mean:+.2%}. "
                  f"Welch t = {cal.t_stat:.2f}.", ""]
        L += ["### Stock-days with no s-score (exclusions)", "", "| Reason | Stock-days |", "|---|---|"]
        for reason, n in excl.most_common():
            L.append(f"| {reason} | {n} |")
        L.append("")

    L += ["## Disclosed limitations", "",
          "- Current constituent list applied to the whole history (no point-in-time membership).",
          "- Results blackout uses actual results dates as if known in advance (board-meeting notice "
          "is normally given days ahead).",
          "- Every signal taken with no capital limit: this measures the signal, not a portfolio.",
          *cfg["limitations"],
          "- The paper's speed filter (1/(-ln b) < 30 days on 60 observations) is weak: the AR(1) slope is "
          "biased down on short samples, and about 65% of simulated pure random walks pass it "
          "(tests/unit/test_statarb.py). Kept as pre-registered.", ""]
    return "\n".join(L)


def main(default_universe: str = "nifty50") -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", choices=sorted(UNIVERSES), default=default_universe)
    sub = p.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan", help="today's candidates")
    sc.add_argument("--all", action="store_true", help="show every name, not just |s| >= 1")
    bt = sub.add_parser("backtest", help="pre-registered validation run")
    bt.add_argument("--out", default=None)
    args = p.parse_args()
    cfg = UNIVERSES[args.universe]
    return cmd_scan(cfg, args) if args.cmd == "scan" else cmd_backtest(cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
