#!/usr/bin/env python3
"""Step 2 context test (docs/STEP2_CONTEXT_TEST_PREREG_2026-11-13.md): does map context keep
better screener signals than it drops?

    python scripts/step2_context_test.py --stage cards   # context cards for every signal (cached)
    python scripts/step2_context_test.py --stage a1      # frozen rules R1-R4, stats, verdicts
    python scripts/step2_context_test.py --stage a2-build   # anonymised daily prompts (no calls)

Signals: FRESH or OUT <= 5 sessions from ~/.quantos/bt_fno/outcomes.jsonl. A signal on day t
is read with bars through t (card as of the next weekday) and acted on at t+1's open.
Research only: no orders, no capital.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from multiprocessing import Pool
from pathlib import Path
from statistics import mean, stdev
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.market_map import card as cd  # noqa: E402
from core.market_map import context_rules as cr  # noqa: E402

HOME = Path.home() / ".quantos"
OUTCOMES = HOME / "bt_fno" / "outcomes.jsonl"
STORE = HOME / "l1_snap_20261113"
INDEX = HOME / "index_bars"
OUT = HOME / "step2"
COST = 0.10            # % round trip, futures
T_PASS = 2.7
MIN_KEPT = {"A1": 150, "A2": 100}
HORIZONS = {"swing": "oc5", "intraday": "oc1"}
A2_FROM = "2026-07-01"


def next_weekday(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def signals() -> list[dict]:
    rows = [json.loads(line) for line in OUTCOMES.read_text().splitlines()]
    return [r for r in rows if r["state"] == "FRESH" or (r["state"] == "OUT" and (r.get("days_out") or 0) <= 5)]


# ─── cards ───────────────────────────────────────────────────────────────────

def _cards_for(args) -> list[tuple[str, dict]]:
    sym, dates, store_root = args
    from core.market_map import structure
    from core.market_map.l1_store import Store
    from core.market_map.m5_store import M5Store
    st = Store(Path(store_root))
    out = []
    try:
        adj, _ = st.adjusted(sym)
    except Exception as e:                                        # noqa: BLE001
        return [(f"{sym}|{d}", dict(sym=sym, error=f"store: {e}")) for d in dates]
    if adj.empty:
        return [(f"{sym}|{d}", dict(sym=sym, error="not in the L1 store")) for d in dates]
    m5 = M5Store(st.root).adjusted(sym, adj, st.actions().get(sym, []))
    m5 = m5 if len(m5) else None
    for d in dates:
        as_of = next_weekday(date.fromisoformat(d))
        try:
            rd = structure.l1_read(adj, as_of, m5)
            rd["last_date"] = adj["date"][adj["date"] < str(as_of)].iat[-1].date().isoformat()
            out.append((f"{sym}|{d}", cd.card(sym, rd, adj)))
        except Exception as e:                                    # noqa: BLE001
            out.append((f"{sym}|{d}", dict(sym=sym, error=f"{type(e).__name__}: {str(e)[:120]}")))
    return out


def _index_cards(dates: list[str]) -> list[tuple[str, dict]]:
    from core.market_map import structure
    from core.market_map.index_bars import IndexBars
    df = IndexBars(INDEX).load("NIFTY")
    out = []
    for d in dates:
        as_of = next_weekday(date.fromisoformat(d))
        out.append((f"NIFTY|{d}", cd.card("NIFTY", structure.l1_read(df, as_of), df)))
    return out


def stage_cards(workers: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "cards.jsonl"
    done = set()
    if path.exists():
        done = {json.loads(line)["key"] for line in path.read_text().splitlines()}
    sig = signals()
    by_sym = defaultdict(set)
    for r in sig:
        if f"{r['symbol']}|{r['date']}" not in done:
            by_sym[r["symbol"]].add(r["date"])
    idx_dates = sorted({r["date"] for r in sig if f"NIFTY|{r['date']}" not in done})
    with path.open("a") as f:
        for k, c in _index_cards(idx_dates):
            f.write(json.dumps(dict(key=k, card=c), default=str) + "\n")
        print(f"index cards: {len(idx_dates)}", flush=True)
        jobs = [(s, sorted(ds), str(STORE)) for s, ds in sorted(by_sym.items())]
        with Pool(workers) as pool:
            for i, res in enumerate(pool.imap_unordered(_cards_for, jobs), 1):
                for k, c in res:
                    f.write(json.dumps(dict(key=k, card=c), default=str) + "\n")
                f.flush()
                if i % 10 == 0:
                    print(f"  {i}/{len(jobs)} symbols", flush=True)
    print(f"cards -> {path}")


def load_cards() -> dict:
    return {d["key"]: d["card"] for d in map(json.loads, (OUT / "cards.jsonl").read_text().splitlines())}


# ─── stats ───────────────────────────────────────────────────────────────────

def option_returns(r: dict) -> dict:
    """Single contract and debit verticals (sell 1/2/3 strikes further OTM), close day 0 -> day 5."""
    k, ch = r.get("contract"), r.get("chain")
    if not k or not ch:
        return {}
    strikes = sorted(float(s) for s in ch["strikes"])
    px = {float(s): v for s, v in ch["strikes"].items()}
    K = float(k["strike"])
    if K not in px:
        return {}
    c0, c5 = px[K][0], px[K][3]
    out = {}
    if c0 and c5 is not None and c0 > 0:
        out["single"] = round((c5 / c0 - 1) * 100, 2)
    otm = [s for s in strikes if s > K] if r["side"] == "CE" else sorted((s for s in strikes if s < K), reverse=True)
    for n in (1, 2, 3):
        if len(otm) < n:
            break
        s = otm[n - 1]
        a0, a5 = px[s][0], px[s][3]
        if None in (c0, c5, a0, a5):
            continue
        debit = c0 - a0
        if debit > 0:
            out[f"vert{n}"] = round(((c5 - a5) / debit - 1) * 100, 2)
    return out


def _t(xs: list[float]) -> Optional[float]:
    if len(xs) < 3:
        return None
    s = stdev(xs)
    return round(mean(xs) / (s / math.sqrt(len(xs))), 2) if s > 0 else None


def split_stats(rows: list[dict], key: str, mid: str, arm: str) -> dict:
    """kept vs dropped on outcome `key` (signed %), the per-day difference t, halves after cost."""
    rows = [r for r in rows if r.get(key) is not None]
    kept = [r for r in rows if r["keep"]]
    drop = [r for r in rows if not r["keep"]]
    by_day = defaultdict(lambda: ([], []))
    for r in rows:
        by_day[r["date"]][0 if r["keep"] else 1].append(r[key])
    diffs = [mean(k) - mean(d) for k, d in by_day.values() if k and d]
    h1 = [r[key] - COST for r in kept if r["date"] < mid]
    h2 = [r[key] - COST for r in kept if r["date"] >= mid]
    out = dict(n=len(rows), kept=len(kept), dropped=len(drop),
               kept_mean=round(mean(r[key] for r in kept), 3) if kept else None,
               dropped_mean=round(mean(r[key] for r in drop), 3) if drop else None,
               kept_win=round(sum(r[key] > 0 for r in kept) / len(kept) * 100, 1) if kept else None,
               days_both=len(diffs), diff_mean=round(mean(diffs), 3) if diffs else None, t=_t(diffs),
               kept_net_h1=round(mean(h1), 3) if h1 else None, kept_net_h2=round(mean(h2), 3) if h2 else None)
    checks = [out["diff_mean"] is not None and out["diff_mean"] > 0 and out["t"] is not None and out["t"] >= T_PASS,
              bool(h1) and bool(h2) and mean(h1) > 0 and mean(h2) > 0,
              len(kept) >= MIN_KEPT[arm]]
    out["checks"] = checks
    out["verdict"] = "PASS" if all(checks) else "FAIL"
    return out


def median_date(rows: list[dict]) -> str:
    ds = sorted(r["date"] for r in rows)
    return ds[len(ds) // 2]


def stage_a1() -> None:
    cards = load_cards()
    sig = signals()
    rows, missing = [], 0
    for r in sig:
        c = cards.get(f"{r['symbol']}|{r['date']}")
        ev = cr.evaluate(c, cards.get(f"NIFTY|{r['date']}"), r["side"]) if c else None
        if ev is None:
            missing += 1
            continue
        rows.append(dict(date=r["date"], sym=r["symbol"], side=r["side"], state=r["state"],
                         oc1=r.get("oc1"), oc5=r.get("oc5"), ex5=r.get("ex5"), **ev, **option_returns(r)))
    mid = "2026-03-12"
    res = dict(prereg="docs/STEP2_CONTEXT_TEST_PREREG_2026-11-13.md", signals=len(sig), no_card=missing,
               scored=len(rows), halves_split=mid, tests={}, diagnostics={})
    for side in ("CE", "PE"):
        sr = [r for r in rows if r["side"] == side]
        for h, key in HORIZONS.items():
            res["tests"][f"A1 {h} {side}"] = split_stats(sr, key, mid, "A1")
        d = res["diagnostics"][side] = {}
        d["keep_rate"] = round(sum(r["keep"] for r in sr) / len(sr) * 100, 1) if sr else None
        for rule in ("R1", "R2", "R3", "R4"):
            alt = [dict(r, keep=r[rule]) for r in sr]
            d[rule] = {h: {k: v for k, v in split_stats(alt, key, mid, "A1").items() if k != "checks"}
                       for h, key in HORIZONS.items()}
        alt = list(sr)
        d["ex5"] = {k: v for k, v in split_stats(alt, "ex5", mid, "A1").items() if k != "checks"}
        for o in ("single", "vert1", "vert2", "vert3"):
            k = [r[o] for r in sr if r["keep"] and r.get(o) is not None]
            x = [r[o] for r in sr if not r["keep"] and r.get(o) is not None]
            d[o] = dict(kept_n=len(k), kept_mean=round(mean(k), 2) if k else None,
                        dropped_n=len(x), dropped_mean=round(mean(x), 2) if x else None)
        post = [r for r in sr if r["date"] >= A2_FROM]
        pm = median_date(post) if post else A2_FROM
        d["post_cutoff"] = {h: {k: v for k, v in split_stats(post, key, pm, "A2").items() if k != "checks"}
                            for h, key in HORIZONS.items()}
    (OUT / "a1_rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (OUT / "a1_results.json").write_text(json.dumps(res, indent=1))
    for k, v in res["tests"].items():
        print(f"{k:22s} n {v['n']:5d} kept {v['kept']:5d} kept {v['kept_mean']} dropped {v['dropped_mean']} "
              f"diff {v['diff_mean']} t {v['t']} halves {v['kept_net_h1']}/{v['kept_net_h2']} -> {v['verdict']}")
    print(f"-> {OUT / 'a1_results.json'}")


# ─── A2: anonymised prompts (built and checked before any call) ──────────────

def anonymise(c: dict, label: str, factor: float) -> str:
    """The card's text with the symbol relabelled, prices scaled and calendar dates removed."""
    import re
    t = cd.text(c).replace(f"## {c['sym']} ", f"## {label} ")

    def scale(m):
        s = m.group(0)
        v = float(s) * factor
        return f"{v:.2f}".rstrip("0").rstrip(".")
    # dates first (they would otherwise be scaled as numbers)
    t = re.sub(r"\bon \d{4}-\d{2}-\d{2}(?:, )?", "", t)
    t = re.sub(r"\(from \d{4}-\d{2}-\d{2}\)", "", t)
    t = re.sub(r"\b\d{4}-(?:\d{2}|W\d{2}|Q\d)(?:-\d{2})?\b", "<period>", t)
    t = re.sub(r"\bvalue \d{4}:", "value <period>:", t)                 # Y profile: a bare year
    # prices: numbers that are not %, ATR multiples, ages, look-backs (1d, 52w) or labels (x3, R1)
    t = re.sub(r"(?<![\w.])(\d+\.?\d*)(?![\d.]*(?:%|ATR|d\b|w\b|\s*sessions|\s*bars|\s*periods))", scale, t)
    return t


LEAK = re.compile(r"\d{4}-\d{2}|\d{4}-W\d|\d{4}-Q\d|value \d{4}:")


def leaks(text: str, syms: set[str], c: dict) -> list[str]:
    """Anything in an anonymised prompt that could identify the stock or the date."""
    out = [m.group(0) for m in LEAK.finditer(text)]
    out += [s for s in syms if len(s) >= 3 and re.search(rf"\b{re.escape(s)}\b", text)]
    p = f"{c['price']:g}"
    if len(p.replace(".", "")) >= 3 and re.search(rf"(?<![\d.]){re.escape(p)}(?![\d])", text):
        out.append(f"raw price {p}")
    return out


def stage_a2_build() -> None:
    cards = load_cards()
    sig = [r for r in signals() if r["date"] >= A2_FROM]
    by_day = defaultdict(list)
    for r in sig:
        by_day[r["date"]].append(r)
    all_syms = {r["symbol"] for r in signals()} | {"NIFTY", "BANKNIFTY"}
    out = []
    for d, rs in sorted(by_day.items()):
        rng = random.Random(f"step2|{d}")
        idx = cards.get(f"NIFTY|{d}")
        parts = [anonymise(idx, "INDEX", rng.uniform(0.5, 2.0))] if idx and "error" not in idx else []
        key = []
        for i, r in enumerate(sorted(rs, key=lambda r: r["symbol"]), 1):
            c = cards.get(f"{r['symbol']}|{r['date']}")
            if not c or "error" in c:
                continue
            f = random.Random(f"{r['symbol']}|{d}").uniform(0.5, 2.0)
            lab = f"S{i:02d}"
            body = anonymise(c, lab, f)
            bad = leaks(body, all_syms, c)
            if bad:
                raise SystemExit(f"anonymisation leak for {r['symbol']} {d}: {bad[:5]}")
            parts.append(f"signal {lab}: {'long (CE)' if r['side'] == 'CE' else 'short (PE)'}\n" + body)
            key.append(dict(label=lab, sym=r["symbol"], side=r["side"]))
        out.append(dict(day=d, prompt="\n\n".join(parts), key=key))
    p = OUT / "a2_prompts.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in out) + "\n")
    print(f"{len(out)} days, {sum(len(x['key']) for x in out)} signals -> {p}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["cards", "a1", "a2-build"], required=True)
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args(argv)
    {"cards": lambda: stage_cards(a.workers), "a1": stage_a1, "a2-build": stage_a2_build}[a.stage]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
