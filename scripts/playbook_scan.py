"""Playbook v1 over the top-N universe on one date, then triage (docs/TRADE_REASONING.md,
steps 2-3). Read-only: places no orders, writes two JSON files.

    python scripts/playbook_scan.py --as-of 2026-11-13 --out scan.json
        [--store ~/.quantos/l1_store] [--top 500] [--lots fno_lots.txt]

--lots: one line "SYM:LOT,SYM:LOT,..." (futures lot sizes, e.g. from the F&O bhavcopy). Without
it every short counts as "no futures". Writes <out> (one row per stock) and <out>.triage.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.market_map import playbook as pb  # noqa: E402
from core.market_map import read as mr  # noqa: E402
from core.market_map.l1_store import Store  # noqa: E402
from core.market_map.triage import pairs, triage  # noqa: E402


def scan(st: Store, as_of: date, top: int) -> list[dict]:
    last = st.last_session()
    uni = st.universe(min(as_of - timedelta(days=1), last) if last else as_of - timedelta(days=1))[:top]
    rows, t = [], time.time()
    for i, u in enumerate(uni):
        sym = u["sym"]
        l1 = mr.l1_for(sym, as_of, st)
        if "error" in l1:
            rows.append(dict(sym=sym, rank=u["rank"], error=l1["error"]))
            continue
        daily, _ = st.adjusted(sym)
        p = pb.plan(l1, daily, as_of)
        tf = l1["tf"]
        rows.append(dict(sym=sym, rank=u["rank"], price=l1["price"], atr_d=tf["D"].get("atr"),
                         atr_w=l1["htf"]["atr_w"], M=tf["M"]["state"], W=tf["W"]["state"], D=tf["D"]["state"],
                         w_prot=(tf["W"].get("protected") or {}).get("price"),
                         w_weak=(tf["W"].get("weak") or {}).get("price"),
                         d_event=tf["D"].get("last_event"), p1=p["p1"], p2=p["p2"],
                         opp=pb.opposing_strong(l1, p["p1"].get("side", "long") == "long")))
        if i % 25 == 0:
            print(i, sym, round(time.time() - t), flush=True)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", required=True, type=date.fromisoformat)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--store", type=Path, default=Path.home() / ".quantos" / "l1_store")
    ap.add_argument("--top", type=int, default=500)
    ap.add_argument("--lots", type=Path)
    a = ap.parse_args()
    lots = {}
    if a.lots:
        for kv in a.lots.read_text().replace("\n", ",").split(","):
            if ":" in kv:
                k, v = kv.rsplit(":", 1)
                lots[k.strip()] = int(v)
    rows = scan(Store(a.store), a.as_of, a.top)
    a.out.write_text(json.dumps(rows, default=str))
    tri = triage(rows, lots)
    summary = dict(as_of=str(a.as_of), reads=len(rows), setups=len(tri),
                   actionable=sum(t["actionable"] for t in tri), pairs=pairs(rows),
                   w_down=sum(r.get("W") == "down" for r in rows), w_up=sum(r.get("W") == "up" for r in rows))
    a.out.with_suffix(".triage.json").write_text(json.dumps(dict(summary=summary, rows=tri), indent=1, default=str))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
