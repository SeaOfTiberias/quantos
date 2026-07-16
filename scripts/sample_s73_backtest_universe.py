#!/usr/bin/env python3
"""
S7-3 — Pre-commit the backtest sample BEFORE any results exist.

The whole point of this script is that it must run and be committed
*before* a single symbol is backtested. If the sample were picked (or
adjusted) after seeing which names look good in TradingView, S7-3 stops
being a falsifier and becomes a demo reel.

Method (fixed, documented here — do not change after results arrive):
  1. Universe = agent/universe_nifty500.txt (the committed, semi-annual
     Nifty 500 list Stage A and regime breadth already use).
  2. Split into two cap tiers using NSE's own Smallcap 250 constituent list
     (Nifty 500 = Nifty 100 + Midcap 150 + Smallcap 250, so "in Smallcap
     250" vs "not" is a genuine large/mid vs small split, not a guess):
       - large_mid: in universe_nifty500 but NOT in Smallcap 250
       - small:     in universe_nifty500 AND in Smallcap 250
  3. random.Random(SEED).sample() draws N/2 from each tier. Fixed seed
     (not "random" random) so the draw is reproducible and auditable —
     anyone can re-run this script and get the identical list back.

Requires the raw NSE constituent CSV for Smallcap 250 (not committed to the
repo — same one used to build agent/universe_nifty500.txt originally).
"""

import argparse
import csv
import random
from pathlib import Path

SEED = 20260716  # date this was pre-committed, used as the fixed seed


def read_universe(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]


def read_smallcap250_symbols(csv_path: Path) -> set[str]:
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return {(r.get("Symbol") or "").strip().upper() for r in rows if r.get("Symbol")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("smallcap250_csv", type=Path, help="ind_niftysmallcap250list.csv")
    ap.add_argument("--universe", type=Path, default=Path("agent/universe_nifty500.txt"))
    ap.add_argument("--n", type=int, default=40, help="total sample size (split evenly)")
    ap.add_argument("--out", type=Path, default=Path("docs/S7_3_BACKTEST_SAMPLE.md"))
    args = ap.parse_args()

    universe = read_universe(args.universe)
    smallcap250 = read_smallcap250_symbols(args.smallcap250_csv)

    large_mid = sorted(s for s in universe if s not in smallcap250)
    small = sorted(s for s in universe if s in smallcap250)

    per_tier = args.n // 2
    rng = random.Random(SEED)
    sample_large_mid = sorted(rng.sample(large_mid, per_tier))
    rng2 = random.Random(SEED)  # independent draw per tier, same fixed seed
    sample_small = sorted(rng2.sample(small, per_tier))

    lines = [
        "# S7-3 Backtest Sample — pre-committed 2026-07-16, before any result exists",
        "",
        f"**Seed:** `{SEED}` · **N:** {args.n} ({per_tier} large/mid + {per_tier} small cap)",
        "",
        "Method: `scripts/sample_s73_backtest_universe.py` against "
        f"`{args.universe.as_posix()}` ({len(universe)} symbols), split by NSE Smallcap 250 "
        f"membership ({len(large_mid)} large/mid, {len(small)} small in the current "
        "universe). Re-running this script with the same inputs reproduces this "
        "list exactly. **Do not hand-edit this file or re-run with a different "
        "seed/N after seeing any backtest result** — that would be exactly the "
        "cherry-picking this pre-commit exists to prevent.",
        "",
        "## Large/mid cap tier",
        "",
        *[f"- {s}" for s in sample_large_mid],
        "",
        "## Small cap tier",
        "",
        *[f"- {s}" for s in sample_small],
        "",
    ]
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.n} symbols ({per_tier}+{per_tier}) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
