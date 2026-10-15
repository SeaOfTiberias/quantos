"""
QuantOS — Candidate 23 Stage 2: results report (markdown).
"""

from __future__ import annotations

from collections import Counter

import numpy as np

from core.surge.spreads import GATING, SCENARIOS, STRUCTURES, Stage2Result, _metrics


def _m(m) -> str:
    if m.total_trades == 0:
        return "0 | | | |"
    return f"{m.total_trades} | {m.win_rate:.0%} | {m.profit_factor:.2f} | {m.sharpe_ratio:.2f} |"


def build_report(r: Stage2Result) -> str:
    L = [
        "# Candidate 23 Stage 2 — Bull Call Spreads on Non-52-Week-High Surges — Results", "",
        "Methodology: docs/SURGE_SPREAD_STAGE2_METHODOLOGY.md (pre-registered 2026-10-15). Entry at the "
        "surge-day close, exit at the close of min(t+8, the day before expiry), bhavcopy closing prices. "
        "Returns are on risk (net P&L / debit), so every trade carries equal weight. Statutory costs "
        "are in every scenario; Clean has no bid-ask, Base 1% and Stressed 2% of each leg price per side "
        f"(₹0.05 minimum). Mining before {r.cutoff}, holdout from {r.cutoff}.", "",
        f"## Verdict: **{r.verdict}**", "",
    ]
    if r.chosen:
        L.append(f"Structure picked on mining (highest Stressed Sharpe, ≥ 100 trades, PF > 1): **{r.chosen}** "
                 f"(long leg {r.chosen[1]} strike(s) above ATM, short leg {r.chosen[3]} strike(s) above that).")
    for reason in r.reasons:
        L.append(f"- {reason}")
    L.append("")

    if r.chosen:
        L += ["## Chosen structure", "",
              "| Split | Scenario | Trades | Win | PF | Sharpe | Median return on risk | Mean return on risk |",
              "|---|---|---|---|---|---|---|---|"]
        for split_name, flag in (("mining", False), ("holdout", True)):
            sub = [t for t in r.trades if t.structure == r.chosen and t.holdout == flag]
            for sc in SCENARIOS:
                rets = [t.ret(sc) for t in sub]
                med = f"{np.median(rets):+.1%}" if rets else ""
                mean = f"{np.mean(rets):+.1%}" if rets else ""
                L.append(f"| {split_name} | {sc} | {_m(r.metrics[(r.chosen, split_name, sc)])} {med} | {mean} |")
        sub = [t for t in r.trades if t.structure == r.chosen]
        if sub:
            L += ["", f"Average debit: {np.mean([t.debit / t.width for t in sub]):.0%} of the strike width. "
                      f"Average hold: {np.mean([t.days for t in sub]):.1f} trading days. Exit fallbacks: "
                      + ", ".join(f"{k or 'close'} {v}" for k, v in Counter(t.exit_fallback for t in sub).items())
                      + "."]
            L += ["", "Per year (Stressed, chosen structure):", "",
                  "| Year | Trades | Win | PF | Sharpe |", "|---|---|---|---|---|"]
            for y in sorted({t.entry.year for t in sub}):
                L.append(f"| {y} | {_m(_metrics([t for t in sub if t.entry.year == y], GATING))}")
            L += ["", "Results day vs not (Stressed, chosen structure, full sample, descriptive):", "",
                  "| Subset | Trades | Win | PF | Sharpe |", "|---|---|---|---|---|"]
            for flag in (True, False):
                L.append(f"| results={flag} | {_m(_metrics([t for t in sub if t.results == flag], GATING))}")
        L.append("")

    for split_name in ("mining", "holdout"):
        L += [f"## All 16 structures — {split_name}"
              + (" (information only; cannot replace the chosen structure)" if split_name == "holdout" else ""),
              "",
              "| Structure | Clean: n, win, PF, Sharpe | Base: n, win, PF, Sharpe | Stressed: n, win, PF, Sharpe |",
              "|---|---|---|---|"]
        for s in STRUCTURES:
            cells = []
            for sc in SCENARIOS:
                m = r.metrics[(s, split_name, sc)]
                cells.append(f"{m.total_trades}, {m.win_rate:.0%}, {m.profit_factor:.2f}, {m.sharpe_ratio:.2f}"
                             if m.total_trades else "0")
            L.append(f"| {s}{' ◀' if s == r.chosen else ''} | " + " | ".join(cells) + " |")
        L.append("")

    L += ["## Coverage", "",
          f"{r.n_events} branch events; {len({(t.symbol, t.entry) for t in r.trades})} produced at least one "
          f"valid structure; {len(r.trades)} structure-trades in total.", "",
          "| Skip reason | Count |", "|---|---|"]
    for k, v in sorted(r.skips.items(), key=lambda kv: -kv[1]):
        L.append(f"| {k} | {v} |")
    L.append("")
    return "\n".join(L)
