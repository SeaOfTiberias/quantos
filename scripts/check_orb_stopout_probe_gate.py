#!/usr/bin/env python3
"""
QuantOS — Candidate 18 Stop-Out Spread Probe: Pre-Registered Gate Check
──────────────────────────────────────────────────────────────────────
Reports whether docs/ORB_STOPOUT_SPREAD_PROBE_METHODOLOGY.md's stopping
rule has been satisfied for each index (NIFTY, BankNifty independently),
and ONLY reveals spread statistics once BOTH the minimum-sample (N>=20
exit events) and minimum-time (>=4 weeks since 2026-09-03) gates have
cleared for that index. Before that, it prints gate status only (N so
far, elapsed weeks, MET/WAITING) -- deliberately, so a curious mid-window
re-run cannot bias behavior the way the stop-when-favorable pattern in
this candidate's earlier cost-variant history did (Fable's 2026-07-31
review). Read-only, reads data_cache/orb_scalping_stopout_spread_
samples.csv (VM-only, gitignored) -- run this ON the VM, same as
scripts/analyze_orb_spread_samples.py.

Usage:
    python scripts/check_orb_stopout_probe_gate.py
"""

from __future__ import annotations

import csv
import statistics
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.probe_orb_scalping_stopout_spreads import LOG_PATH  # noqa: E402

MIN_SAMPLE_N = 20   # reuses core/risk/trade_history.py's Kelly-sizing 20-trade minimum, not a new arbitrary number
MIN_WEEKS = 4.0
PROBE_DEPLOYED_AT = date(2026, 9, 3)  # quantos-orb-stopout-probe.timer enabled on the VM -- fixed, not data-derived
UNDERLYINGS = ("NIFTY", "BANKNIFTY")


def elapsed_weeks(today: date, deployed_at: date = PROBE_DEPLOYED_AT) -> float:
    return (today - deployed_at).days / 7.0


def gate_status(n: int, weeks: float, min_n: int = MIN_SAMPLE_N, min_weeks: float = MIN_WEEKS) -> dict:
    """Pure, unit-testable -- the two gates from docs/ORB_STOPOUT_SPREAD_
    PROBE_METHODOLOGY.md. Both must hold before a conclusion is drawn."""
    n_met = n >= min_n
    time_met = weeks >= min_weeks
    return {"n": n, "n_met": n_met, "elapsed_weeks": round(weeks, 1),
            "time_met": time_met, "both_met": n_met and time_met}


def _load_exit_rows(underlying: str) -> list[dict]:
    if not LOG_PATH.exists():
        return []
    rows = csv.DictReader(LOG_PATH.open(newline="", encoding="utf-8"))
    return [r for r in rows if r["underlying"] == underlying and r["event"] == "exit"]


def format_report(underlying: str, rows: list[dict], status: dict) -> str:
    """Pure formatting, separated from I/O so the no-peek behavior (no
    spread numbers before both gates clear) is directly testable."""
    lines = [f"=== {underlying} ===",
             f"  N={status['n']} (need >= {MIN_SAMPLE_N}): {'MET' if status['n_met'] else 'WAITING'}",
             f"  elapsed={status['elapsed_weeks']} weeks (need >= {MIN_WEEKS}): "
             f"{'MET' if status['time_met'] else 'WAITING'}"]

    if not status["both_met"]:
        lines.append("  Gate NOT yet met -- per docs/ORB_STOPOUT_SPREAD_PROBE_METHODOLOGY.md, "
                      "no conclusion should be drawn yet. Re-check later; do not peek at spread numbers.")
        return "\n".join(lines)

    pcts = [float(r["spread_pct_of_mid"]) for r in rows if r["spread_pct_of_mid"]]
    if not pcts:
        lines.append("  Gate met but no rows have a usable spread_pct_of_mid -- check the log.")
        return "\n".join(lines)

    mean_pct, median_pct = statistics.mean(pcts), statistics.median(pcts)
    lines.append("  Gate MET -- reporting per the pre-registered methodology doc.")
    lines.append(f"  mean spread_pct_of_mid={mean_pct:.3f}%  (bps equiv: {mean_pct * 50:.1f})")
    lines.append(f"  median spread_pct_of_mid={median_pct:.3f}%  (bps equiv: {median_pct * 50:.1f})")

    by_reason: dict[str, list[float]] = {}
    for r in rows:
        if r["spread_pct_of_mid"]:
            by_reason.setdefault(r["trigger_reason"], []).append(float(r["spread_pct_of_mid"]))
    lines.append("  Informational only (not gating, see methodology doc) -- by trigger_reason:")
    for reason, vals in sorted(by_reason.items()):
        lines.append(f"    {reason}: n={len(vals)} mean={statistics.mean(vals):.3f}%")

    lines.append("  Next step: substitute the median bps-equivalent for this index's Stratified rate "
                  "in core/orb_scalping/costs.py and rerun scripts/backtest_orb_scalping.py -- "
                  "does PF/Sharpe still clear the pre-registered bar?")
    return "\n".join(lines)


def main() -> int:
    today = date.today()
    for underlying in UNDERLYINGS:
        rows = _load_exit_rows(underlying)
        status = gate_status(len(rows), elapsed_weeks(today))
        print(format_report(underlying, rows, status))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
