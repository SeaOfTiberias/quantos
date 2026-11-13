"""Diagnostic (no verdict): frozen rules R1-R4 on the live screener picks, 2026-10-09..11-13."""
import ast, json, sys
from pathlib import Path
from collections import defaultdict
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/step2_context_test.py; run on the VM (outcomes file lives there)
import step2_context_test as s2
from core.market_map.l1_store import default_root, Store
from core.market_map import context_rules as cr
s2.INDEX = Path.home() / ".quantos" / "index_bars"
raw = json.load(open(Path.home() / ".quantos" / "fno_screener_outcomes.json"))
picks = [v if isinstance(v, dict) else ast.literal_eval(v) for v in raw.values()]
root = str(default_root())
st = Store(Path(root))
by = defaultdict(set)
for p in picks:
    by[p["symbol"]].add(p["trade_date"])
cards = {}
for sym, ds in by.items():
    cards.update(dict(s2._cards_for((sym, sorted(ds), root))))
cards.update(dict(s2._index_cards(sorted({p["trade_date"] for p in picks}))))
rows = []
for p in picks:
    sym, d, side = p["symbol"], p["trade_date"], p["side"]
    ev = cr.evaluate(cards.get(f"{sym}|{d}"), cards.get(f"NIFTY|{d}"), side)
    adj, _ = st.adjusted(sym)
    f = adj[adj["date"] > str(d)].reset_index(drop=True)
    if ev is None or len(f) < 1:
        continue
    sg = 1 if side == "CE" else -1
    oc1 = sg * (f["c"].iat[0] / f["o"].iat[0] - 1) * 100
    oc5 = sg * (f["c"].iat[4] / f["o"].iat[0] - 1) * 100 if len(f) >= 5 else None
    rows.append(dict(d=d, sym=sym, side=side, oc1=oc1, oc5=oc5, **ev))
json.dump(rows, open("/tmp/diag179.json", "w"))
def show(rs, k):
    xs = [r[k] for r in rs if r[k] is not None]
    return f"n {len(xs):3d} mean {sum(xs)/len(xs):+6.2f}% right {sum(x>0 for x in xs)/len(xs)*100:4.0f}%" if xs else "n   0"
for side in ("CE", "PE", "ALL"):
    rs = [r for r in rows if side == "ALL" or r["side"] == side]
    for k in ("oc5", "oc1"):
        print(f"{side:3s} {k}  all: {show(rs,k)} | kept: {show([r for r in rs if r['keep']],k)} | dropped: {show([r for r in rs if not r['keep']],k)}")
    for rule in ("R1","R2","R3","R4"):
        print(f"     {rule} fails {sum(not r[rule] for r in rs)}/{len(rs)}  oc5 of fails: {show([r for r in rs if not r[rule]],'oc5')}")
