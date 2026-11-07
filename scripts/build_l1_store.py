#!/usr/bin/env python3
"""
One-off: build the L1 price store (core/market_map/l1_store.py) on the PC from the
bhavcopy cache the techno-funda panel was built from (2010-01-01 .. 2026-10-23), then copy
it to the VM. From there the VM's daily job (scripts/run_l1_refresh.py) keeps it current.

  bars      prices.load_bars: raw EQ/BE/BZ rows, ETFs dropped, symbols chained
  actions   the NSE API lists (2010-2026, deduplicated exactly as prices.load_actions does)
            plus the big drops the panel confirmed from filings (source "filings")

Check: --verify N compares the store's adjusted closes with the panel's for N symbols.

Usage:
  python scripts/build_l1_store.py --out data_cache/l1_store
  python scripts/build_l1_store.py --out data_cache/l1_store --verify 200
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.market_map.l1_store import Store  # noqa: E402
from core.techno_funda import prices as pr  # noqa: E402
from core.techno_funda.panel import CACHE as PANEL  # noqa: E402
from core.techno_funda.symbols import SymbolChain  # noqa: E402


def seed_actions(chain: SymbolChain) -> dict[str, list[dict]]:
    """Same rows as prices.load_actions (dedup on symbol, ex-date and subject), with the subject kept."""
    seen, out = set(), {}
    for path in pr.ACTION_FILES:
        for a in json.loads(path.read_text(encoding="utf-8")):
            f = pr.action_factor(a.get("subject", ""))
            if not f:
                continue
            ex = datetime.strptime(a["exDate"], "%d-%b-%Y").date()
            key = (a["symbol"].strip(), ex, a["subject"].strip().lower())
            if key in seen:
                continue
            seen.add(key)
            sym = chain.canonical(a["symbol"].strip(), ex)
            out.setdefault(sym, []).append(dict(ex=ex.isoformat(), factor=f, purpose=a["subject"].strip(),
                                                source="nse_api"))
    return out


def filings_actions(gaps: pd.DataFrame) -> dict[str, list[dict]]:
    out = {}
    for g in gaps[gaps["confirmed"]].itertuples(index=False):
        out.setdefault(g.sym, []).append(dict(ex=pd.Timestamp(g.date).date().isoformat(), factor=float(g.share_ratio),
                                              purpose=f"share count change {g.share_ratio:.4f} (filings)",
                                              source="filings"))
    return out


def build(out: Path) -> None:
    t = time.time()
    chain = SymbolChain.load()
    store = Store(out)
    acts = seed_actions(chain)
    with open(PANEL, "rb") as f:
        panel = pickle.load(f)
    for sym, lst in filings_actions(panel["gaps"]).items():
        acts.setdefault(sym, []).extend(lst)
    del panel
    store.write_actions(acts)
    print(f"actions: {sum(map(len, acts.values()))} for {len(acts)} symbols", flush=True)

    bars = pr.load_bars(chain)
    print(f"bars: {len(bars):,} rows, {bars['sym'].nunique()} symbols, loaded in {time.time() - t:.0f}s", flush=True)
    for sym, g in bars.groupby("sym", sort=True):
        store.write_symbol(sym, g)
    last = bars["date"].max().date()
    store.set_meta(last_session=last.isoformat(), built_from="PC bhavcopy cache", built=datetime.now().isoformat(timespec="seconds"),
                   actions_through="2026-06-24 (NSE API); PR bundles after that come from the VM job")
    print(f"store written to {out} (last session {last}) in {time.time() - t:.0f}s")


def verify(out: Path, n: int) -> int:
    store = Store(out)
    with open(PANEL, "rb") as f:
        panel = pickle.load(f)["panel"][["sym", "date", "c", "seg"]]
    syms = sorted(panel["sym"].unique())
    rng = np.random.default_rng(20261107)
    pick = sorted(rng.choice(syms, size=min(n, len(syms)), replace=False))
    acts = store.actions()
    worst, bad = 0.0, []
    for sym in pick:
        a, _ = store.adjusted(sym, acts)
        p = panel[panel["sym"] == sym]
        m = p.merge(a[["date", "c", "seg"]], on="date", suffixes=("_p", "_s"))
        if len(m) != len(p):
            bad.append((sym, "rows", len(p), len(m)))
            continue
        err = float(np.max(np.abs(m["c_s"] / m["c_p"] - 1))) if len(m) else 0.0
        worst = max(worst, err)
        if err > 1e-6 or (m["seg_p"] != m["seg_s"]).any():
            bad.append((sym, "values", round(err, 8), int((m["seg_p"] != m["seg_s"]).sum())))
    print(f"verify: {len(pick)} symbols, worst relative close difference {worst:.2e}, mismatches {len(bad)}")
    for b in bad[:20]:
        print("  ", b)
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data_cache/l1_store"))
    ap.add_argument("--verify", type=int, default=0, help="only compare N symbols against the panel")
    a = ap.parse_args(argv)
    if a.verify:
        return verify(a.out, a.verify)
    build(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
