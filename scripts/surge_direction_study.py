#!/usr/bin/env python3
"""
QuantOS — Candidate 23 Stage 1: does a +5% stock surge continue or fade?
──────────────────────────────────────────────────────────────────────────
docs/SURGE_DIRECTION_METHODOLOGY.md, pre-registered before this ran.

Data: data_cache/statarb/futures_panel_all.csv (cached F&O bhavcopy) and
NSE results board-meeting dates (cached). No Fyers token needed.

Usage:
    python scripts/surge_direction_study.py
    python scripts/surge_direction_study.py --out docs/SURGE_DIRECTION_RESULTS.md
"""

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from core.statarb.data import (  # noqa: E402
    DEFAULT_CACHE_DIR, SYMBOL_RENAMES, fetch_results_board_meetings, load_futures_panel,
)
from core.statarb.residuals import build_panel  # noqa: E402
from core.surge.events import (  # noqa: E402
    CONDITIONS, HORIZONS, baseline, find_events, judge, results_rows, split, stats, subsets,
)


def _pct(x, signed=True):
    return f"{x:+.2%}" if signed else f"{x:.1%}"


def _row(name, s):
    if s is None:
        return f"| {name} | 0 | | | | | | | |"
    return (f"| {name} | {s.n} | {s.n_dates} | {_pct(s.clustered_mean)} | {s.t:.2f} | {_pct(s.median)} | "
            f"{_pct(s.probs['p_ge_4'], False)} | {_pct(s.probs['p_ge_7'], False)} | {_pct(s.probs['p_le_0'], False)} |")


HDR = ["| Subset | Events | Dates | Mean X(5), date-clustered | t | Median X(5) | P(R8 ≥ 4%) | P(R8 ≥ 7%) | P(R8 ≤ 0) |",
       "|---|---|---|---|---|---|---|---|---|"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="docs/SURGE_DIRECTION_RESULTS.md")
    args = ap.parse_args()

    raw_syms = pd.read_csv(DEFAULT_CACHE_DIR / "futures_panel_all.csv", usecols=["symbol"]).symbol.unique()
    symbols = sorted({SYMBOL_RENAMES.get(s, s) for s in raw_syms})
    series = load_futures_panel(symbols, date.today(), allow_network=False)
    panel = build_panel(series)
    print(f"panel {panel.dates[0]} -> {panel.dates[-1]}, {len(panel.dates)} days, {len(panel.symbols)} symbols")

    meetings = fetch_results_board_meetings(panel.symbols, 2019, panel.dates[-1].year, refresh_current=False)
    no_meet = sorted(s for s, v in meetings.items() if not v)
    res_rows = results_rows(panel, meetings)

    events, excl = find_events(panel, res_rows)
    mining, holdout, cut = split(events)
    print(f"{len(events)} events; cutoff {cut}; mining {len(mining)}, holdout {len(holdout)}")

    overall = judge("ALL", mining, holdout)
    branches = []
    sub_all = subsets(events)
    sub_m, sub_h = subsets(mining), subsets(holdout)
    for name in sub_all:
        branches.append(judge(name, sub_m[name], sub_h[name]))
    passed = [b for b in branches if b.passed]
    base = baseline(panel)

    if passed:
        verdict = "PASS"
    elif overall.passed:
        verdict = "FAIL (unconditional drift only)"
    else:
        verdict = "FAIL"
    print(f"verdict: {verdict}; branches: {[b.subset for b in passed]}")

    L = [
        "# Candidate 23 Stage 1 — +5% Surge Direction — Results", "",
        f"Methodology: docs/SURGE_DIRECTION_METHODOLOGY.md (pre-registered 2026-10-15). Data "
        f"{panel.dates[0]} to {panel.dates[-1]}, {len(panel.symbols)} F&O symbols (near-month futures, "
        "roll-adjusted). X(h) = forward return minus the equal-weighted F&O universe over the same days; "
        "t-stats cluster by event date. No costs, no option prices.", "",
        f"## Verdict: **{verdict}**", "",
    ]
    if passed:
        for b in passed:
            L.append(f"- **{b.subset}** → {b.direction} → "
                     f"{'bull call spread' if b.direction == 'continuation' else 'bear call spread'} candidate "
                     f"(mining {_pct(b.mining.clustered_mean)}, t {b.mining.t:.2f}; "
                     f"holdout {_pct(b.holdout.clustered_mean)}, t {b.holdout.t:.2f}).")
    else:
        L.append("- No subset cleared mining |t| ≥ 2.0 with a same-sign holdout t ≥ 1.5.")
    L += ["", f"Events: {len(events)} (mining {len(mining)} before {cut}, holdout {len(holdout)} from {cut}).",
          f"Excluded: history {excl.history}, forward data {excl.forward}, corporate-action jump "
          f"{excl.corp_action}, 10-day cooldown {excl.cooldown}.", ""]

    L += ["## Q1 — all surges", ""] + HDR
    L += [_row("All — mining", overall.mining), _row("All — holdout", overall.holdout),
          _row("All — full", stats(events))]
    L += ["", f"Baseline, all stock-days (n={int(base['n'])}): P(R8 ≥ 4%) {_pct(base['p_ge_4'], False)}, "
              f"P(R8 ≥ 7%) {_pct(base['p_ge_7'], False)}, P(R8 ≤ 0) {_pct(base['p_le_0'], False)}.", ""]
    full = stats(events)
    L += ["Drift profile, all events (event-mean X(h)): " +
          ", ".join(f"h={h}: {_pct(full.drift[h])}" for h in HORIZONS) + ".", ""]
    by_year = Counter(e.day.year for e in events)
    L += ["Events per year: " + ", ".join(f"{y}: {n}" for y, n in sorted(by_year.items())) + ".", ""]
    L.append("Mean X(5) by year: " + ", ".join(
        f"{y}: {_pct(stats([e for e in events if e.day.year == y]).event_mean)}" for y in sorted(by_year)) + ".")
    L.append("")

    L += ["## Q2 — selector (mining → holdout)", "",
          "| Subset | Mining n | Mining mean X(5) | Mining t | Holdout n | Holdout mean X(5) | Holdout t | Result |",
          "|---|---|---|---|---|---|---|---|"]
    for b in branches:
        m, h = b.mining, b.holdout
        L.append(f"| {b.subset} | {m.n if m else 0} | {_pct(m.clustered_mean) if m else ''} | "
                 f"{f'{m.t:.2f}' if m else ''} | {h.n if h else 0} | {_pct(h.clustered_mean) if h else ''} | "
                 f"{f'{h.t:.2f}' if h else ''} | {'**BRANCH (' + b.direction + ')**' if b.passed else b.reason} |")
    L.append("")

    L += ["## Every subset, full sample (descriptive)", ""] + HDR
    for name, evs in sub_all.items():
        L.append(_row(name, stats(evs)))
    L.append("")
    L += ["Drift profile by subset (event-mean X(h)):", "",
          "| Subset | " + " | ".join(f"h={h}" for h in HORIZONS) + " |",
          "|---|" + "---|" * len(HORIZONS)]
    for name, evs in sub_all.items():
        s = stats(evs)
        if s:
            L.append(f"| {name} | " + " | ".join(_pct(s.drift[h]) for h in HORIZONS) + " |")
    L.append("")

    L += ["## Results × 52-week breakout (descriptive)", ""] + HDR
    for r in (True, False):
        for b in (True, False):
            evs = [e for e in events if e.cond["results"] == r and e.cond["breakout52"] == b]
            L.append(_row(f"results={r}, breakout52={b}", stats(evs)))
    L.append("")

    L += ["## Disclosures", "",
          f"- {len(no_meet)} of {len(panel.symbols)} symbols returned no results meetings from NSE "
          "(mostly names that left the F&O list or were delisted); their surges count as results=FALSE.",
          "- Futures stand in for spot; basis changes are included in every return.",
          "- 10 subsets are tested; about one false mining pass is expected by chance at |t| ≥ 2. "
          "The holdout requirement is the guard.", ""]
    Path(args.out).write_text("\n".join(L), encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
