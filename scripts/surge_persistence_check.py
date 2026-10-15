#!/usr/bin/env python3
"""
QuantOS — Candidate 23b Part C: does surge follow-through persist month to month?
───────────────────────────────────────────────────────────────────────────────────
docs/SURGE_23B_METHODOLOGY.md "Part C", pre-registered before this ran.
Mining period only (2020-05 .. 2024-12), Stage 1 events with breakout52=FALSE.

Usage:
    python scripts/surge_persistence_check.py
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

from scripts.surge_spread_stage2 import load_events  # noqa: E402

START, END = date(2020, 5, 1), date(2024, 12, 31)
MIN_TRAILING = 15


def month_key(d: date) -> tuple[int, int]:
    return d.year, d.month


def prev_months(ym: tuple[int, int], n: int) -> list[tuple[int, int]]:
    y, m = ym
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append((y, m))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="docs/SURGE_23B_PERSISTENCE_RESULTS.md")
    args = ap.parse_args()

    panel, branch = load_events()
    events = [e for e in branch if START <= e.day <= END or e.day < START]   # earlier months feed the first predictors
    by_month: dict[tuple[int, int], list] = {}
    for e in events:
        by_month.setdefault(month_key(e.day), []).append(e)

    rows = []
    months = sorted(k for k in by_month if START <= date(k[0], k[1], 1) <= END)
    for ym in months:
        first_day = min(d for d in panel.dates if month_key(d) == ym)
        first_idx = panel.dates.index(first_day)
        trailing = [e for pm in prev_months(ym, 3) for e in by_month.get(pm, []) if e.t + 5 < first_idx]
        if len(trailing) < MIN_TRAILING:
            continue
        pred = float(np.mean([e.excess[5] for e in trailing]))
        out = float(np.mean([e.excess[5] for e in by_month[ym]]))
        rows.append((ym, pred, out, len(trailing), len(by_month[ym])))

    pred = np.array([r[1] for r in rows])
    out = np.array([r[2] for r in rows])
    rho, p = spearmanr(pred, out, alternative="greater")
    pos, neg = out[pred > 0], out[pred <= 0]
    c1 = rho > 0 and p < 0.05
    c2 = len(pos) > 0 and len(neg) > 0 and pos.mean() > neg.mean()
    verdict = "PASS" if (c1 and c2) else "FAIL"
    print(f"{len(rows)} months; Spearman {rho:.3f} (one-sided p {p:.3f}); "
          f"mean next-month X(5) when trailing>0: {pos.mean():+.2%} (n={len(pos)}), "
          f"<=0: {neg.mean():+.2%} (n={len(neg)}); verdict {verdict}")

    L = ["# Candidate 23b Part C — Surge Follow-Through Persistence — Results", "",
         "Methodology: docs/SURGE_23B_METHODOLOGY.md, Part C (pre-registered 2026-10-15). Stage 1 events with "
         "breakout52=FALSE, months 2020-05 to 2024-12. Predictor = mean 5-day excess return of the previous 3 "
         "months' events whose outcome was known before the month began (≥ 15 events); outcome = that "
         "month's events' mean 5-day excess return.", "",
         f"## Verdict: **{verdict}**", "",
         f"- Spearman correlation {rho:.3f}, one-sided p {p:.3f} → {'pass' if c1 else 'FAIL'} (needs > 0, p < 0.05)",
         f"- Mean outcome when the predictor > 0: {pos.mean():+.2%} ({len(pos)} months); when ≤ 0: "
         f"{neg.mean():+.2%} ({len(neg)} months) → {'pass' if c2 else 'FAIL'}", "",
         ("Consequence: Part A adds the pre-registered secondary arm (trailing follow-through gate, logged "
          "at entry, reported beside the ungated primary)." if verdict == "PASS" else
          "Consequence: no gate. Market state stays descriptive only (Part B). With about "
          f"{len(rows)} monthly points the test has low power: this is no evidence of persistence, not proof "
          "of none."), "",
         "## Monthly series", "",
         "| Month | Predictor (trailing 3-mo X(5)) | Outcome (month X(5)) | Trailing events | Month events |",
         "|---|---|---|---|---|"]
    for ym, pr, ou, nt, nm in rows:
        L.append(f"| {ym[0]}-{ym[1]:02d} | {pr:+.2%} | {ou:+.2%} | {nt} | {nm} |")
    L.append("")
    Path(args.out).write_text("\n".join(L), encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
