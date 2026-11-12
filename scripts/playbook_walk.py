#!/usr/bin/env python3
"""
Playbook v1 walk-through (docs/MARKET_PLAYBOOK_V1.md): each read's plan (P1, P2) from the L1
store, and every SETUP walked forward on the daily bars that followed. A walk-through, not a
test: no P&L verdict comes from it (playbook "Testing").

    PYTHONPATH=~/quantos ~/quantos/.venv/bin/python scripts/playbook_walk.py \
        --sample docs/review_round1/v3/sample.json --extra HDFCBANK:2026-10-28 --out walk.json

--extra SYM:YYYY-MM-DD adds discussion cases (labelled; excluded from any scoring).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.market_map import playbook as pb  # noqa: E402
from core.market_map import read as mr  # noqa: E402
from core.market_map.l1_store import Store  # noqa: E402


def walk(store, rid: str, sym: str, as_of: date, case: str) -> dict:
    l1 = mr.l1_for(sym, as_of, store)
    if "error" in l1:
        return dict(id=rid, sym=sym, as_of=as_of.isoformat(), case=case, error=l1["error"])
    daily, _ = store.adjusted(sym)
    p = pb.plan(l1, daily, as_of)
    out = dict(id=rid, sym=sym, as_of=as_of.isoformat(), case=case, price=l1["price"],
               alignment=l1["alignment"]["text"], plan=p, lines=pb.lines(p), results={})
    for key in ("p1", "p2"):
        s = p[key]
        if s["status"] == "SETUP":
            r = pb.simulate(s, daily, as_of, pb.opposing_strong(l1, s["side"] == "long"))
            out["results"][key] = r
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=Path, help="a review sample.json (its `picked` list)")
    ap.add_argument("--extra", action="append", default=[], help="SYM:YYYY-MM-DD discussion case")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    store = Store()
    rows = []
    if a.sample:
        for p in json.loads(a.sample.read_text())["picked"]:
            rows.append(walk(store, p["id"], p["sym"], date.fromisoformat(p["as_of"]), "round 1 read"))
            print(rows[-1]["id"], rows[-1]["sym"], *rows[-1].get("lines", [rows[-1].get("error")])[1:], sep="\n  ")
    for x in a.extra:
        sym, d = x.split(":")
        rows.append(walk(store, f"X-{sym}-{d}", sym, date.fromisoformat(d), "discussion case (not scored)"))
        print(rows[-1]["id"], *rows[-1].get("lines", [rows[-1].get("error")])[1:], sep="\n  ")
    a.out.write_text(json.dumps(rows, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
