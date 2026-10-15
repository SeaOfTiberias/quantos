#!/usr/bin/env python3
"""
QuantOS — Candidate 23b gate check (docs/SURGE_23B_METHODOLOGY.md).

Before 60 closed trades: counts and log health only -- no P&L, by design.
At 60+: the pre-registered verdict (real-quote fills, statutory costs).

Usage:
    python scripts/check_surge_23b.py
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.surge.live import MIN_CLOSED, evaluate, load_positions, store_dir  # noqa: E402


def main() -> int:
    positions = load_positions(store_dir() / "positions.jsonl")
    v = evaluate(positions)
    flags = Counter(p.exit_flag for p in positions if not p.open)
    print(f"Candidate 23b (L2W4): {len(positions)} logged, {v.open} open, {v.closed} closed and priced "
          f"(need {MIN_CLOSED}).")
    if flags:
        print("Exit quote flags: " + ", ".join(f"{k or 'two-sided'} {n}" for k, n in flags.items()))
    for line in v.lines:
        print(f"  {line}")
    if v.ready:
        print(f"PF {v.profit_factor:.2f}, Sharpe {v.sharpe:.2f}, mean return on risk {v.mean_ret:+.1%} "
              f"(t {v.t_stat:.2f}) -> {'PASS' if v.passed else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
