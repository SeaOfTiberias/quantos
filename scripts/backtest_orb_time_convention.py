#!/usr/bin/env python3
"""
QuantOS — Candidate 18 under the calibrated time convention
─────────────────────────────────────────────────────────────
Written 2026-09-30, BEFORE the calibration or this backtest was run.

Reads the FROZEN convention (time weights + per-index VIX scale) from the JSON
block in docs/ORB_TIME_CONVENTION_CALIBRATION.md, which
scripts/calibrate_orb_time_convention.py writes and which is committed before
this script runs, then reruns candidate 18 (Stratified costs, 1 lot, BANKNIFTY
expiry day skipped per the fix-2 decision) under:
  - frozen    the calibrated convention            <- the verdict
  - calendar  fix-2's intraday calendar time, k=1   (sensitivity)
  - 252-day   sessions only, k=1                    (sensitivity)

PRE-REGISTERED verdict rule (same as the calibration script's rule 3):
  candidate 18 "passes" only if BOTH NIFTY and BANKNIFTY clear PF > 1.0 AND
  Sharpe > 0.5 under the frozen convention. If the calibration doc says the
  fitted convention was NOT validated on its holdout, no single verdict is
  claimed: frozen and calendar are both reported as bounds.
A fail is a recommendation to close candidate 18, which the user decides.

Offline: uses the candles cached by scripts/backtest_orb_fix2.py
(data_cache/orb_fix2_candles.pkl). Usage:
    python scripts/backtest_orb_time_convention.py [--out docs/ORB_TIME_CONVENTION_RESULTS.md]
"""
from __future__ import annotations

import argparse
import json
import pickle
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.backtest.parser import _compute_metrics  # noqa: E402
from core.orb_scalping.backtest import run_index_backtest  # noqa: E402
from core.orb_scalping.premium import TimeWeights  # noqa: E402

CALIBRATION_DOC = Path("docs/ORB_TIME_CONVENTION_CALIBRATION.md")
CANDLES = Path("data_cache/orb_fix2_candles.pkl")


def load_frozen(doc_text: str) -> tuple[dict, bool]:
    """The frozen JSON block and whether the calibration was validated."""
    block = re.search(r"## Frozen convention.*?```json\n(.*?)```", doc_text, re.S)
    if not block:
        raise SystemExit(f"No frozen convention JSON block in {CALIBRATION_DOC}.")
    validated = "on the holdout: **YES**" in doc_text
    return json.loads(block.group(1)), validated


def _row(label, trades):
    m = _compute_metrics(trades)
    net = sum(t.profit - t.costs for t in trades)
    ok = m.has_positive_edge
    return ok, (f"| {label} | {m.total_trades} | {m.win_rate:.0%} | {m.profit_factor:.2f} | "
                f"{m.sharpe_ratio:.2f} | {net:,.0f} | {'PASS' if ok else 'FAIL'} |")


def run(data: dict, frozen: dict, validated: bool) -> str:
    fw = TimeWeights(frozen["session"], frozen["weeknight"], frozen["weekend"])
    conventions = {
        "frozen (calibrated)": dict(time_weights=fw),
        "calendar (fix-2 B/D)": dict(time_weights=TimeWeights.calendar()),
        "252 trading days": dict(time_weights=TimeWeights.trading_252()),
    }
    scale = {"NIFTY": frozen["k_nifty"], "BANKNIFTY": frozen["k_banknifty"]}
    header = "| Convention | N | Win | PF | Sharpe | Net Rs (1 lot) | Bar |\n|---|---|---|---|---|---|---|"
    out = ["# Candidate 18 under the calibrated time convention", "",
           f"Frozen convention from `{CALIBRATION_DOC}`: session {fw.session}, weeknight {fw.weeknight}, "
           f"weekend {fw.weekend} (calendar-day-equivalents); VIX scale NIFTY {scale['NIFTY']}, "
           f"BANKNIFTY {scale['BANKNIFTY']}. Holdout-validated: **{'YES' if validated else 'NO'}**. "
           f"Stratified costs, 1 lot, BANKNIFTY expiry day skipped. Method and rule: "
           f"`scripts/backtest_orb_time_convention.py` docstring (committed before this run).", ""]
    verdict = {}
    for underlying, key in (("NIFTY", "nifty"), ("BANKNIFTY", "banknifty")):
        out += [f"## {underlying}", "", header]
        for label, kw in conventions.items():
            vol = scale[underlying] if label.startswith("frozen") else 1.0
            trades = run_index_backtest(data[key], data["vix"], underlying=underlying,
                                        banknifty_expiry_policy="skip", vol_scale=vol, **kw)[5]
            ok, row = _row(label, trades)
            out.append(row)
            if label.startswith("frozen"):
                verdict[underlying] = ok
        out.append("")
    if not validated:
        out += ["## Verdict", "", "**No single verdict**: the calibrated convention did not beat calendar "
                "time on its holdout, so frozen and calendar are reported as bounds (pre-registered).", ""]
    else:
        passed = all(verdict.values())
        out += ["## Verdict (pre-registered rule)", "",
                f"NIFTY {'PASS' if verdict['NIFTY'] else 'FAIL'}, BANKNIFTY "
                f"{'PASS' if verdict['BANKNIFTY'] else 'FAIL'} under the frozen convention -> "
                f"candidate 18 **{'PASSES' if passed else 'FAILS'}**."
                + ("" if passed else " Recommendation: close candidate 18 (the user decides)."), ""]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="docs/ORB_TIME_CONVENTION_RESULTS.md")
    args = ap.parse_args(argv)
    frozen, validated = load_frozen(CALIBRATION_DOC.read_text(encoding="utf-8"))
    report = run(pickle.loads(CANDLES.read_bytes()), frozen, validated)
    Path(args.out).write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
