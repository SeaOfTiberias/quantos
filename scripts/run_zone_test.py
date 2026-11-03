#!/usr/bin/env python3
"""
QuantOS — run the price-map zone test, as frozen (Market Map sprint S3)
───────────────────────────────────────────────────────────────────────
docs/PRICE_MAP_ZONES_PREREG_2026-10-28.md + amendment 1. Reads the bars that
scripts/fetch_zone_test_bars.py cached on the VM (copied to
data_cache/zone_test/bars/), rebuilds every stock's map for every session D
from bars before D only (core/price_map/build.build_map, unchanged), scores
strong, weak and placebo events (core/market_map/zone_test.py), and reports
criteria 1-5 plus the reported-only tables.

    python scripts/run_zone_test.py [--bars data_cache/zone_test/bars] [--workers 4] [--limit N]

Writes data_cache/zone_test/events.csv and data_cache/zone_test/summary.json,
and prints the results block for the pre-registration's Results section.
No re-tuning: every constant comes from the pre-registration.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

IST = timezone(timedelta(hours=5, minutes=30))
START, END = date(2025, 11, 3), date(2026, 10, 27)
DAILY_DAYS, INTRADAY_DAYS = 365, 99
OUTCOME_SESSIONS = 5                    # D and the next 4
BOOT, SEED = 10_000, 20261104
OUT = Path("data_cache/zone_test")


def _bars(rows):
    from core.brokers.base import OHLCV
    return [OHLCV(timestamp=datetime.fromtimestamp(r[0], timezone.utc), open=r[1], high=r[2], low=r[3], close=r[4],
                  volume=int(r[5])) for r in rows]


def run_symbol(path: str) -> list[dict]:
    """Every event of one stock over the test period."""
    from core.market_map.zone_test import Seen, day_events, htf_label
    from core.orb_scalping.conditions import load_weinstein_clauses
    from core.price_map.build import build_map
    from core.vault.facts import MarketFacts
    from core.vault.stages import classify

    with gzip.open(path, "rt") as f:
        raw = json.load(f)
    sym = raw["symbol"]
    daily, intra = _bars(raw["daily"]), _bars(raw["intraday"])
    ddates = [b.timestamp.astimezone(IST).date() for b in daily]
    idates = [b.timestamp.astimezone(IST).date() for b in intra]
    sessions = sorted(set(idates))
    by_day: dict[date, list] = defaultdict(list)
    for b, d in zip(intra, idates):
        by_day[d].append(b)
    clauses = load_weinstein_clauses()
    seen, out = Seen(), []
    for k, d in enumerate(sessions):
        if not (START <= d <= END):
            continue
        lo = bisect.bisect_left(ddates, d - timedelta(days=DAILY_DAYS))
        hi = bisect.bisect_left(ddates, d)                       # bars before D only
        ilo = bisect.bisect_left(idates, d - timedelta(days=INTRADAY_DAYS))
        ihi = bisect.bisect_left(idates, d)
        m = build_map(sym, daily[lo:hi], intra[ilo:ihi], d)
        if "error" in m:
            continue
        window_days = sessions[k:k + OUTCOME_SESSIONS]
        window = [b for wd in window_days for b in by_day[wd]]
        complete = len(window_days) == OUTCOME_SESSIONS
        evs = day_events(k, m["zones"], m["close"], m["atr"], by_day[d], window, complete, seen)
        if not evs:
            continue
        st = classify(clauses, MarketFacts(sym, daily[:hi])).stage
        stage = int(st) if st is not None else None
        for e in evs:
            e.update(symbol=sym, date=d.isoformat(), atr=m["atr"], atr_pct=m["atr_pct"], stage=stage,
                     htf=htf_label(stage, e["side"]))
            out.append(e)
    return out


# ─── statistics ──────────────────────────────────────────────────────────────

def rate(evs) -> tuple[float, int, int]:
    rej = sum(e["outcome"] == "rejected" for e in evs)
    n = sum(e["outcome"] in ("rejected", "broken") for e in evs)
    return (rej / n if n else float("nan")), rej, n


def boot_diff(strong, placebo, seed=SEED, draws=BOOT):
    """95% interval of strong rate - placebo rate, resampling sessions with replacement."""
    import numpy as np
    days = sorted({e["date"] for e in strong} | {e["date"] for e in placebo})
    ix = {d: i for i, d in enumerate(days)}
    agg = np.zeros((len(days), 4))
    for col, evs in ((0, strong), (2, placebo)):
        for e in evs:
            if e["outcome"] in ("rejected", "broken"):
                agg[ix[e["date"]], col] += e["outcome"] == "rejected"
                agg[ix[e["date"]], col + 1] += 1
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(days), size=(draws, len(days)))
    s = agg[pick].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        d = s[:, 0] / s[:, 1] - s[:, 2] / s[:, 3]
    d = d[~np.isnan(d)]
    return float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def verdict(events: list[dict]) -> dict:
    strong = [e for e in events if e["kind"] == "strong"]
    weak = [e for e in events if e["kind"] == "weak"]
    plac = [e for e in events if e["kind"] == "placebo"]
    rs, rp, rw = rate(strong), rate(plac), rate(weak)
    diff = rs[0] - rp[0]
    ci = boot_diff(strong, plac)
    scored = sorted(e["date"] for e in strong if e["outcome"] != "timeout")
    med = scored[len(scored) // 2] if scored else None
    halves = []
    for name, f in (("first", lambda e: e["date"] < med), ("second", lambda e: e["date"] >= med)):
        a, b = rate([e for e in strong if f(e)]), rate([e for e in plac if f(e)])
        halves.append({"half": name, "strong": a, "placebo": b, "diff": a[0] - b[0]})
    crit = {
        "1 strong - placebo >= 5pp": diff >= 0.05,
        "2 95% CI excludes 0": ci[0] > 0 or ci[1] < 0,
        "3 diff > 0 in both halves": all(h["diff"] > 0 for h in halves),
        "4 strong rate > weak rate": rs[0] > rw[0],
        "5 >= 300 strong events": rs[2] >= 300,
    }
    return {"strong": rs, "placebo": rp, "weak": rw, "diff": diff, "ci95": ci, "median_date": med,
            "halves": halves, "criteria": crit, "pass": all(crit.values()),
            "timeouts": {k: sum(e["outcome"] == "timeout" for e in evs) for k, evs in
                         (("strong", strong), ("placebo", plac), ("weak", weak))},
            "events": {"strong": len(strong), "placebo": len(plac), "weak": len(weak)}}


def pct(x) -> str:
    return "n/a" if x != x else f"{x * 100:.1f}%"


def report(events: list[dict], v: dict, n_symbols: int) -> str:
    strong = [e for e in events if e["kind"] == "strong"]
    plac = [e for e in events if e["kind"] == "placebo"]
    L = [f"**Verdict: {'PASS' if v['pass'] else 'FAIL'}**", "",
         f"Run {datetime.now(IST):%Y-%m-%d %H:%M} IST by `scripts/run_zone_test.py` on {n_symbols} F&O stocks, "
         f"sessions {START}..{END}. Events with an outcome (rejected + broken); timeouts reported separately.", "",
         "| | rejection rate | rejected / scored | events (incl. timeouts) | timeouts |", "|---|---|---|---|---|"]
    for k in ("strong", "placebo", "weak"):
        r = v[k]
        L.append(f"| {k} | {pct(r[0])} | {r[1]} / {r[2]} | {v['events'][k]} | {v['timeouts'][k]} |")
    L += ["", f"Difference strong - placebo: **{v['diff'] * 100:+.1f} pp**, 95% session-bootstrap CI "
              f"[{v['ci95'][0] * 100:+.1f}, {v['ci95'][1] * 100:+.1f}] pp ({BOOT:,} draws, seed {SEED}).", "",
          f"Halves, split at the median strong-event date {v['median_date']}:", ""]
    L += [f"- {h['half']}: strong {pct(h['strong'][0])} (n={h['strong'][2]}), placebo {pct(h['placebo'][0])} "
          f"(n={h['placebo'][2]}), diff {h['diff'] * 100:+.1f} pp" for h in v["halves"]]
    L += ["", "| Criterion | Result |", "|---|---|"]
    L += [f"| {k} | {'pass' if ok else '**FAIL**'} |" for k, ok in v["criteria"].items()]

    L += ["", "### Reported only (not part of pass or fail)", "", "**Support and resistance:**", "",
          "| side | strong | placebo | diff |", "|---|---|---|---|"]
    for sd in ("support", "resistance"):
        a = rate([e for e in strong if e["side"] == sd])
        b = rate([e for e in plac if e["side"] == sd])
        L.append(f"| {sd} | {pct(a[0])} (n={a[2]}) | {pct(b[0])} (n={b[2]}) | {(a[0] - b[0]) * 100:+.1f} pp |")
    L += ["", "**Family combinations (strong zones):**", "", "| families | rate | n |", "|---|---|---|"]
    for fam, _ in Counter(e["families"] for e in strong).most_common():
        r = rate([e for e in strong if e["families"] == fam])
        L.append(f"| {fam} | {pct(r[0])} | {r[2]} |")
    atrs = sorted(e["atr_pct"] for e in strong)
    if atrs:
        t1, t2 = atrs[len(atrs) // 3], atrs[2 * len(atrs) // 3]
        L += ["", f"**ATR% terciles** (cuts {t1:g}%, {t2:g}% from strong events):", "",
              "| tercile | strong | placebo | diff |", "|---|---|---|---|"]
        for name, f in (("low", lambda x: x < t1), ("mid", lambda x: t1 <= x < t2), ("high", lambda x: x >= t2)):
            a = rate([e for e in strong if f(e["atr_pct"])])
            b = rate([e for e in plac if f(e["atr_pct"])])
            L.append(f"| {name} | {pct(a[0])} (n={a[2]}) | {pct(b[0])} (n={b[2]}) | {(a[0] - b[0]) * 100:+.1f} pp |")

    L += ["", "**Amendment 1 A: HTF stage split** (stage on D from daily bars to D−1):", "",
          "| stage | side | HTF | strong | placebo | diff |", "|---|---|---|---|---|---|"]
    for stg in (1, 2, 3, 4, None):
        for sd in ("support", "resistance"):
            a = rate([e for e in strong if e["stage"] == stg and e["side"] == sd])
            b = rate([e for e in plac if e["stage"] == stg and e["side"] == sd])
            from core.market_map.zone_test import htf_label
            L.append(f"| {stg if stg is not None else 'unclassified'} | {sd} | {htf_label(stg, sd)} | "
                     f"{pct(a[0])} (n={a[2]}) | {pct(b[0])} (n={b[2]}) | "
                     + (f"{(a[0] - b[0]) * 100:+.1f} pp |" if a[2] and b[2] else "n/a |"))
    L += ["", "| HTF | strong | placebo | diff | 95% CI |", "|---|---|---|---|---|"]
    for lab in ("with", "against", "none"):
        s_ = [e for e in strong if e["htf"] == lab]
        p_ = [e for e in plac if e["htf"] == lab]
        a, b = rate(s_), rate(p_)
        ci = boot_diff(s_, p_) if a[2] and b[2] else (float("nan"), float("nan"))
        L.append(f"| {lab} | {pct(a[0])} (n={a[2]}) | {pct(b[0])} (n={b[2]}) | {(a[0] - b[0]) * 100:+.1f} pp | "
                 f"[{ci[0] * 100:+.1f}, {ci[1] * 100:+.1f}] |")
    L += ["", "Note: a placebo's HTF label follows its own test side (a stage-2 placebo tested as resistance "
              "is 'against'), so the with/against placebo groups are not the mirrors of the zone groups."]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bars", default=str(OUT / "bars"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="first N stocks only (a smoke run, not the test)")
    a = ap.parse_args(argv)
    files = sorted(str(p) for p in Path(a.bars).glob("*.json.gz"))
    if a.limit:
        files = files[:a.limit]
    if not files:
        print(f"no bars in {a.bars}")
        return 1
    events: list[dict] = []
    with ProcessPoolExecutor(a.workers) as ex:
        for i, evs in enumerate(ex.map(run_symbol, files, chunksize=1), 1):
            events += evs
            if i % 20 == 0 or i == len(files):
                print(f"{i}/{len(files)} stocks, {len(events)} events", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    keys = ["symbol", "date", "kind", "side", "low", "high", "outcome", "families", "atr", "atr_pct", "stage", "htf"]
    with (OUT / ("events_smoke.csv" if a.limit else "events.csv")).open("w", newline="") as f:
        w = csv.DictWriter(f, keys)
        w.writeheader()
        w.writerows({k: e.get(k) for k in keys} for e in events)
    v = verdict(events)
    text = report(events, v, len(files))
    if not a.limit:
        (OUT / "summary.json").write_text(json.dumps(v, indent=1, default=str))
        (OUT / "results.md").write_text(text, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
