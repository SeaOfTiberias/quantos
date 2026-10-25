#!/usr/bin/env python3
"""
QuantOS — build_iv_history: seed ~/.quantos/atm_iv_history.csv for IV rank
───────────────────────────────────────────────────────────────────────────
One-off (or after a gap): reads the surge study's cached bhavcopy pass
(data_cache/surge/pc_pass1.pkl, from scripts/backtest_new_tracks.py --prepare),
turns each (symbol, day) ATM CE/PE pair into a Black-76 IV
(core/ideas/regime.py) and writes the last 320 sessions per symbol. After
that, regime.refresh() keeps it current from the daily bhavcopies.

    python scripts/build_iv_history.py                     # -> ~/.quantos/atm_iv_history.csv
    python scripts/build_iv_history.py --out some/file.csv
"""

from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ideas import regime  # noqa: E402
from core.mcp_tools.market import IV_HISTORY  # noqa: E402

PASS1 = Path("data_cache/surge/pc_pass1.pkl")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pass1", type=Path, default=PASS1)
    ap.add_argument("--out", type=Path, default=IV_HISTORY)
    a = ap.parse_args(argv)
    _, ivr = pickle.loads(a.pass1.read_bytes())
    last = sorted(set(ivr["date"]))[-regime.KEEP_ROWS - 5:]
    ivr = ivr[ivr["date"].isin(set(last))]
    hist: dict = {}
    for d, sym, iv in regime.rows_from_ivrows(ivr.itertuples(index=False, name=None)):
        hist.setdefault(sym, []).append((d, iv))
    for v in hist.values():
        v.sort()
    regime.save(a.out, hist)
    n = sum(len(v) for v in hist.values())
    print(f"{a.out}: {len(hist)} symbols, {n} rows, {min(last)} to {max(last)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
