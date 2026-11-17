"""Darvas second chance: map re-entry after a losing stop-out.

Pre-registration: docs/DARVAS_REENTRY_PREREG_2026-11-17.md. Research only, no orders.

    python scripts/research/darvas_reentry.py build OUT_DIR      # calls_<chunk>.json per chunk
    (then per chunk) python scripts/call_plans.py --store STORE --no-telegram --root OUT_DIR/root_<chunk>
        --calls OUT_DIR/calls_<chunk>.json --darvas NONEXISTENT --start <first> --replay-from <first>
    python scripts/research/darvas_reentry.py score OUT_DIR
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.market_map.l1_store import Store  # noqa: E402

Q = Path.home() / ".quantos"
STORE = Q / "l1_snap_20261113"
COST = 0.0025
CHUNKS = (("2016_19", "2016", "2019"), ("2020_23", "2020", "2023"), ("2024_26", "2024", "2026"))
SRC = {"2016_19": "darvas_atr_stop_oos_results.json", "2020_23": "darvas_atr_stop_oos_results.json",
       "2024_26": "darvas_atr_stop_results.json"}


def bucket_b(w: float) -> bool:
    return 35.0 < w <= 50.0


def trades(fname: str) -> list[dict]:
    d = json.loads((Q / fname).read_text())
    return [t for v in d.values() if isinstance(v, dict) and "trades" in v for t in v["trades"]
            if bucket_b(t["width_pct"])]


def build(out: Path) -> None:
    st = Store(STORE)
    syms = set(st.symbols())
    out.mkdir(parents=True, exist_ok=True)
    for name, a, b in CHUNKS:
        calls, dropped, n_all = {}, 0, 0
        for t in trades(SRC[name]):
            y = t["entry_date"][:4]
            ex = t["exit_date"][:10]
            if not (a <= ex[:4] <= b):
                continue
            if a <= y <= b:
                n_all += 1
            if not (t["reason"] == "stop" and t["exit_price"] < t["entry_price"]):
                continue
            s = t["symbol"]
            if s not in syms:
                dropped += 1
                continue
            bars, _ = st.adjusted(s)
            row = bars[bars["date"].dt.strftime("%Y-%m-%d") == ex]
            if row.empty:
                dropped += 1
                continue
            k = f"{ex}|CE|{s}"
            calls[k] = dict(key=k, trade_date=ex, symbol=s, side="CE", entry_spot=float(row["c"].iat[0]),
                            src="Darvas re-entry", darvas_entry=t["entry_date"][:10],
                            darvas_entry_price=t["entry_price"], darvas_exit_price=t["exit_price"])
        (out / f"calls_{name}.json").write_text(json.dumps(calls, indent=1))
        first = min((c["trade_date"] for c in calls.values()), default="-")
        print(f"{name}: {len(calls)} picks (losing stop-outs), {dropped} dropped (not in store), "
              f"{n_all} Bucket B trades entered in the chunk, first pick {first}")


def plain_reentry(st: Store, sym: str, d: str) -> float | None:
    bars, _ = st.adjusted(sym)
    ds = bars["date"].dt.strftime("%Y-%m-%d").tolist()
    if d not in ds:
        return None
    i = ds.index(d)
    if i + 15 >= len(bars):
        return None
    return float(bars["c"].iat[i + 15] / bars["o"].iat[i + 1] - 1 - COST)


def tstat(x: list[float]) -> float:
    if len(x) < 2:
        return float("nan")
    m = sum(x) / len(x)
    sd = math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))
    return m / (sd / math.sqrt(len(x))) if sd else float("nan")


def score(out: Path) -> None:
    st = Store(STORE)
    rows = []
    for name, _, _ in CHUNKS:
        sp = out / f"root_{name}" / "state.json"
        if not sp.exists():
            print(f"{name}: no state yet")
            continue
        state = json.loads(sp.read_text(encoding="utf-8"))
        for k, p in state.items():
            c = p["call"]
            ents = [t for t in p["tracks"] if t["kind"] in ("sweep", "re-sweep")]
            closed = [t for t in ents if t["state"] in ("target", "stopped", "time")]
            open_ = [t for t in ents if t.get("entry") and t["state"] not in ("target", "stopped", "time")]
            for t in closed:
                risk = t["entry"] - t["stop"] if t.get("stop") is not None else t["risk"]
                rows.append(dict(chunk=name, key=k, sym=c["sym"], d=c["date"], kind=t["kind"], exit=t["state"],
                                 level=(t.get("kinds") or ["?"])[0], r_gross=t["r"],
                                 r_net=(t["exit"] - t["entry"] - COST * t["entry"]) / t["risk"],
                                 pct_net=t["exit"] / t["entry"] - 1 - COST))
            if open_:
                print(f"  still open: {k} {[t['state'] for t in open_]}")
    e = pd.DataFrame(rows)
    print("\n== main entries, net R (0.25% round trip inside R)")
    verdict = {}
    for lab, chunks in (("2016-19", ["2016_19"]), ("2020-23", ["2020_23"]), ("2016-23 (discovery)", ["2016_19", "2020_23"]),
                        ("2024-26 (confirmation)", ["2024_26"])):
        x = e[e.chunk.isin(chunks)] if len(e) else e
        r = x.r_net.tolist() if len(x) else []
        m = sum(r) / len(r) if r else float("nan")
        verdict[lab] = (len(r), m, tstat(r))
        print(f"  {lab:<24} n {len(r):>4}  net R {m:+.2f}  t {tstat(r):+.2f}  gross R "
              f"{(x.r_gross.mean() if len(x) else float('nan')):+.2f}  net % {(x.pct_net.mean() if len(x) else float('nan')):+.2%}")
    n, m, t = verdict["2016-23 (discovery)"]
    d_ok = n >= 60 and m >= 0.20 and t >= 2 and verdict["2016-19"][1] > 0 and verdict["2020-23"][1] > 0
    nc, mc, _ = verdict["2024-26 (confirmation)"]
    c_ok = nc >= 20 and mc > 0
    print(f"\n== VERDICT: discovery {'PASS' if d_ok else 'FAIL'}; confirmation {'PASS' if c_ok else 'FAIL'} "
          f"-> {'PASS' if d_ok and c_ok else 'FAIL'}")

    print("\n== REPORTED, not scored")
    if len(e):
        print(e.groupby(["chunk", "exit"]).r_net.agg(["size", "mean"]).round(2).to_string())
        print(e.groupby("level").r_net.agg(["size", "mean"]).round(2).sort_values("size", ascending=False).head(10).to_string())
    for name, a, b in CHUNKS:
        cp = out / f"calls_{name}.json"
        if not cp.exists():
            continue
        calls = json.loads(cp.read_text())
        pl = [plain_reentry(st, c["symbol"], c["trade_date"]) for c in calls.values()]
        pl = [x for x in pl if x is not None]
        ent = e[e.chunk == name] if len(e) else e
        n_all = sum(1 for t in trades(SRC[name]) if a <= t["entry_date"][:4] <= b)
        add = ent.pct_net.sum() / n_all if n_all and len(ent) else float("nan")
        print(f"  {name}: picks {len(calls)}, entered {ent.key.nunique() if len(ent) else 0}; plain re-entry "
              f"(next open, 15 sessions, net) {sum(pl)/len(pl):+.2%} t {tstat(pl):+.2f} n {len(pl)}; "
              f"map re-entry adds {add:+.2%} per Bucket B trade ({n_all})")
    e.to_csv(out / "reentry_entries.csv", index=False)


if __name__ == "__main__":
    cmd, out = sys.argv[1], Path(sys.argv[2])
    {"build": build, "score": score}[cmd](out)
