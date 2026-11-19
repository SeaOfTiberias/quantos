#!/usr/bin/env python3
"""
QuantOS — Darvas Bucket B: structural initial stop vs the ATR stop (E3 part 2)
──────────────────────────────────────────────────────────────────────────────
Pre-registration: docs/DARVAS_STRUCTURAL_STOP_PREREG_2026-11-19.md (29fe6aa, amendment 1 347ab6a),
committed before this code. Research only, no orders.

    python scripts/research/darvas_structural_stop.py worked     # the 5 worked cases (first 5 discovery trades)
    python scripts/research/darvas_structural_stop.py run        # every trade, resumable, then the verdict
    python scripts/research/darvas_structural_stop.py score      # the verdict from the saved rows

Everything frozen is imported, not re-written: analyse_symbol / WIDE_CFG / _stop_from_atr /
_simulate_exit_atr (the ATR-stop backtest), net_return (the OOS run), the v3 card and
call_plan.sweep_level (lesson 9).
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

Q = Path.home() / ".quantos"
STORE = Q / "l1_snap_20261113"
OUT = Q / "research_darvas_structural_stop_20261119"
DOC = ROOT / "docs" / "DARVAS_STRUCTURAL_STOP_RESULTS_2026-11-19.md"
PERIODS = {"discovery": ("darvas_atr_stop_oos_results.json", "2016-01-01", "2023-12-31"),
           "confirmation": ("darvas_atr_stop_results.json", "2024-01-01", "2099-12-31")}
LOOKBACK = 756
STOP_BUFFER_ATR = 0.1
GLAND_SESSIONS = 15
BOOT, SEED = 10_000, 20261119
UTC = timezone.utc


def bucket_b(w: float) -> bool:
    return 35.0 < w <= 50.0


def load_trades(period: str) -> tuple[list[dict], str]:
    fname, a, b = PERIODS[period]
    d = json.loads((Q / fname).read_text())
    tr = [dict(t, symbol=t.get("symbol") or s) for s, v in d.items() if isinstance(v, dict) and "trades" in v
          for t in v["trades"] if bucket_b(t["width_pct"]) and a <= t["entry_date"][:10] <= b]
    data_end = max(t["exit_date"][:10] for s, v in d.items() if isinstance(v, dict) and "trades" in v for t in v["trades"])
    return sorted(tr, key=lambda t: (t["entry_date"], t["symbol"])), data_end


# ─── one trade, both arms (worker) ───────────────────────────────────────────

_BARS: dict = {}


def _bars(sym: str, end: str):
    from core.market_map.l1_store import Store
    if (sym, end) not in _BARS:
        df, _ = Store(STORE).adjusted(sym)
        _BARS[(sym, end)] = df[df["date"] <= end].reset_index(drop=True) if len(df) else df
    return _BARS[(sym, end)]


def simulate(t: dict, data_end: str) -> dict:
    import scripts.backtest_darvas_atr_stop as atr
    from core.brokers.base import OHLCV
    from core.darvas.weekly_discovery import analyse_symbol as _orig
    from core.market_map import call_plan, card as cd, read as mr
    from scripts.backtest_darvas_atr_stop_oos import net_return
    from scripts.backtest_darvas_box_width import STRESSED_COST_MODEL, WIDE_CFG
    atr.analyse_symbol = lambda s, d, cfg=None: _orig(s, d[-LOOKBACK:], cfg)          # as both original runs
    sym, bo = t["symbol"], t["breakout_date"][:10]
    out = dict(symbol=sym, breakout=bo, entry_date=t["entry_date"][:10], width=t["width_pct"],
               cached_exit_date=t["exit_date"][:10], cached_exit_price=t["exit_price"], cached_reason=t["reason"])
    df = _bars(sym, data_end)
    if not len(df):
        return dict(out, status="not in store")
    ds = df["date"].dt.strftime("%Y-%m-%d").tolist()
    if bo not in ds or ds.index(bo) + 1 >= len(ds):
        return dict(out, status="no breakout bar")
    i = ds.index(bo)
    daily = [OHLCV(timestamp=datetime(d.year, d.month, d.day, tzinfo=UTC), open=float(o), high=float(h), low=float(lo),
                   close=float(c), volume=int(v or 0)) for d, o, h, lo, c, v in
             zip(df["date"], df["o"], df["h"], df["l"], df["c"], df["vol"])]
    res = atr.analyse_symbol(sym, daily[: i + 1], cfg=WIDE_CFG)
    if res is None or res.status != "FRESH BREAKOUT":
        return dict(out, status="breakout not reproduced", got=getattr(res, "status", None))
    e = i + 1
    entry = daily[e].open
    out.update(status="ok", entry_price=entry, cached_entry_price=t["entry_price"], ceiling=res.box_ceiling)

    def arm(stop: float) -> dict:
        if stop >= entry:                                                     # amendment 1: gap below the stop
            j, px, why = e, entry, "gap-at-entry"
        else:
            j, px, why = atr._simulate_exit_atr(sym, daily, e, stop, res.mm_target, res.box_ceiling)
        net = net_return(dict(entry_price=entry, exit_price=px), STRESSED_COST_MODEL)
        back = (why == "stop" and px < entry                                 # amendment 2: losing stops only
                and any(b.high > entry for b in daily[j + 1: j + 1 + GLAND_SESSIONS]))
        return dict(stop=round(stop, 2), risk_pct=(entry - stop) / entry, exit_date=ds[j], exit_price=px, reason=why,
                    net=net, net_r=((px - entry) / (entry - stop) if entry > stop else None), back_above_entry=back)

    out["atr"] = arm(atr._stop_from_atr(daily, i, res.box_ceiling))
    nxt = (date.fromisoformat(bo) + timedelta(days=1))
    from core.market_map.l1_store import Store
    l1 = mr.l1_for(sym, nxt, Store(STORE))
    if "error" in l1:
        return dict(out, structural=dict(out["atr"]), level=None, level_note=f"no read: {l1['error'][:80]}")
    c = cd.card(sym, l1, df[df["date"] <= bo])
    lvl = call_plan.sweep_level(c, df[df["date"] <= bo], "CE") if "error" not in c else None
    if not lvl or not c.get("atr_d"):
        out.update(structural=dict(out["atr"]), level=None, level_note="no level")
    else:
        out.update(structural=arm(lvl["level"] - STOP_BUFFER_ATR * c["atr_d"]), level=lvl["level"],
                   level_kinds=lvl["kinds"], atr_d=c["atr_d"], card_price=c["price"])
    return out


def _job(args):
    t, end = args
    try:
        return simulate(t, end)
    except Exception as ex:                                              # noqa: BLE001 -- one trade never kills the run
        return dict(symbol=t["symbol"], breakout=t["breakout_date"][:10], status=f"error {type(ex).__name__}: {ex}"[:200])


# ─── scoring ─────────────────────────────────────────────────────────────────

def reproduced(r: dict, ds_tol: int = 1) -> bool:
    if r.get("status") != "ok":
        return False
    a = r["atr"]
    d1, d2 = date.fromisoformat(a["exit_date"]), date.fromisoformat(r["cached_exit_date"])
    near = abs(((d1 - d2).days)) <= 3 if ds_tol else d1 == d2                       # one session ~ up to 3 days
    return near and abs(a["exit_price"] / r["cached_exit_price"] - 1) <= 0.01


def week_ci(rows: list[dict], diffs: list[float]) -> tuple[float, float]:
    g = defaultdict(list)
    for r, x in zip(rows, diffs):
        g[date.fromisoformat(r["entry_date"]).isocalendar()[:2]].append(x)
    groups, rng, ms = list(g.values()), random.Random(SEED), []
    for _ in range(BOOT):
        ms.append(statistics.mean([x for _ in groups for x in rng.choice(groups)]))
    ms.sort()
    return ms[int(.05 * BOOT)], ms[int(.95 * BOOT)]


def dd(xs: list[float]) -> float:
    run = peak = m = 0.0
    for x in xs:
        run += x
        peak = max(peak, run)
        m = max(m, peak - run)
    return m


def score() -> str:
    lines = ["# Darvas Bucket B: structural stop vs ATR stop -- results (2026-11-19)", "",
             "Pre-registered in `docs/DARVAS_STRUCTURAL_STOP_PREREG_2026-11-19.md` (29fe6aa, amendment 1 347ab6a) before "
             "any code or run. Runner `scripts/research/darvas_structural_stop.py`.", ""]
    verdict, gate_ok = {}, True
    for period in PERIODS:
        p = OUT / f"{period}.jsonl"
        rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []
        ok = [r for r in rows if r.get("status") == "ok"]
        rep = sum(reproduced(r) for r in ok) / len(ok) if ok else 0.0
        st = defaultdict(int)
        for r in rows:
            st[r.get("status", "?").split(":")[0][:30]] += 1
        lines += [f"## {period}", "", f"- trades {len(rows)}: " + ", ".join(f"{k} {v}" for k, v in sorted(st.items())),
                  f"- **reproduction gate:** the re-simulated ATR arm matches the cached trade on {rep:.1%} of the "
                  f"{len(ok)} simulated trades (need >= 90%)"]
        if rep < 0.90:
            gate_ok = False
            lines += ["- **GATE FAILS: no comparison is reported for this period.**", ""]
            continue
        diffs = [r["structural"]["net"] - r["atr"]["net"] for r in ok]
        lo, hi = week_ci(ok, diffs)
        halves = {}
        for lab, a, b in (("2016-19", "2016", "2019"), ("2020-23", "2020", "2023"), ("2024-26", "2024", "2026")):
            x = [d for r, d in zip(ok, diffs) if a <= r["entry_date"][:4] <= b]
            if x:
                halves[lab] = (len(x), statistics.mean(x))
        verdict[period] = dict(mean=statistics.mean(diffs), lo=lo, hi=hi, halves=halves)
        diff_stop = [r for r in ok if r.get("level") is not None and r["structural"]["stop"] != r["atr"]["stop"]]
        wider = sum(r["structural"]["stop"] < r["atr"]["stop"] for r in diff_stop)
        lines += [f"- **paired difference (structural - ATR), net per trade: {statistics.mean(diffs):+.2%}**, "
                  f"week-bootstrap 90% CI {lo:+.2%} .. {hi:+.2%}; "
                  + "; ".join(f"{k} {m:+.2%} (n {n})" for k, (n, m) in halves.items()), "",
                  "| | ATR arm | structural arm |", "|---|---|---|"]
        for lab, f in (("mean net", lambda a: f"{statistics.mean(a):+.2%}"),
                       ("win rate", lambda a: f"{sum(x > 0 for x in a) / len(a):.1%}"),
                       ("running-sum drawdown (exit order)", None)):
            if f is None:
                def by_exit(k):
                    return [r[k]["net"] for r in sorted(ok, key=lambda r: r[k]["exit_date"])]
                lines.append(f"| {lab} | {dd(by_exit('atr')):.0%} | {dd(by_exit('structural')):.0%} |")
            else:
                lines.append(f"| {lab} | {f([r['atr']['net'] for r in ok])} | {f([r['structural']['net'] for r in ok])} |")
        risk = lambda k: statistics.mean(r[k]["risk_pct"] for r in ok)                     # noqa: E731
        rr = lambda k: [r[k]["net_r"] for r in ok if r[k]["net_r"] is not None]            # noqa: E731
        stopped = lambda k: [r for r in ok if r[k]["reason"] == "stop" and r[k]["exit_price"] < r["entry_price"]]  # noqa: E731
        back = lambda k: sum(r[k]["back_above_entry"] for r in stopped(k)) / max(1, len(stopped(k)))  # noqa: E731
        lines += [f"| mean initial risk (% of entry) | {risk('atr'):.1%} | {risk('structural'):.1%} |",
                  f"| mean R (reported, not compared) | {statistics.mean(rr('atr')):+.2f} | {statistics.mean(rr('structural')):+.2f} |",
                  f"| losing stops back above entry within {GLAND_SESSIONS} sessions (GLAND pattern) | {back('atr'):.0%} of "
                  f"{len(stopped('atr'))} | {back('structural'):.0%} of {len(stopped('structural'))} |", "",
                  f"- initial stop differs on {len(diff_stop)} of {len(ok)} trades ({wider} wider, "
                  f"{len(diff_stop) - wider} tighter); no level {sum(r.get('level') is None for r in ok)}; "
                  f"gap at entry {sum(r['structural']['reason'] == 'gap-at-entry' for r in ok)}"]
        kinds = defaultdict(int)
        for r in diff_stop:
            for k in r.get("level_kinds") or []:
                kinds[k] += 1
        lines += ["- level kinds: " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items(), key=lambda x: -x[1])[:8]), ""]
    if gate_ok and "discovery" in verdict and "confirmation" in verdict:
        dv, cv = verdict["discovery"], verdict["confirmation"]
        c1 = dv["mean"] > 0 and dv["lo"] > 0
        c2 = all(dv["halves"].get(h, (0, -1))[1] > 0 for h in ("2016-19", "2020-23"))
        c3 = cv["mean"] > 0
        lines += ["## Verdict", "", f"1. discovery mean > 0 and CI lower > 0: {'holds' if c1 else '**FAILS**'}",
                  f"2. both discovery halves > 0: {'holds' if c2 else '**FAILS**'}",
                  f"3. confirmation mean > 0: {'holds' if c3 else '**FAILS**'}", "",
                  f"**{'PASS' if c1 and c2 and c3 else 'FAIL'}**"]
    else:
        lines += ["## Verdict", "", "**NO VERDICT: the reproduction gate failed or a period is missing.**"]
    return "\n".join(lines) + "\n"


def worked() -> None:
    tr, end = load_trades("discovery")
    for t in tr[:5]:
        r = simulate(t, end)
        print(json.dumps({k: r.get(k) for k in ("symbol", "breakout", "entry_date", "width", "status", "entry_price",
                                                "cached_entry_price", "ceiling", "level", "level_kinds", "atr_d",
                                                "cached_exit_date", "cached_exit_price", "cached_reason")}, default=str))
        for k in ("atr", "structural"):
            if k in r:
                print(f"   {k:10} stop {r[k]['stop']:>9} risk {r[k]['risk_pct']:.1%}  exit {r[k]['exit_date']} "
                      f"@ {r[k]['exit_price']:.2f} ({r[k]['reason']})  net {r[k]['net']:+.2%}  "
                      f"back-above-entry {r[k]['back_above_entry']}")
        print(f"   reproduces the cached trade: {reproduced(r)}")


def run(workers: int = 4) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for period in PERIODS:
        tr, end = load_trades(period)
        p = OUT / f"{period}.jsonl"
        done = {(json.loads(x)["symbol"], json.loads(x)["breakout"]) for x in p.read_text().splitlines() if x.strip()} \
            if p.exists() else set()
        todo = [t for t in tr if (t["symbol"], t["breakout_date"][:10]) not in done]
        print(f"{period}: {len(tr)} trades, data end {end}, {len(todo)} to do", flush=True)
        with ProcessPoolExecutor(max_workers=workers) as ex, p.open("a") as f:
            for n, r in enumerate(ex.map(_job, [(t, end) for t in todo], chunksize=4), 1):
                f.write(json.dumps(r, default=str) + "\n")
                f.flush()
                if n % 50 == 0:
                    print(f"  {period} {n}/{len(todo)}", flush=True)
    DOC.write_text(score(), encoding="utf-8")
    print(DOC.read_text(encoding="utf-8"))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "worked"
    {"worked": worked, "run": run, "score": lambda: print(score())}[cmd]()
