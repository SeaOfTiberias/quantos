#!/usr/bin/env python3
"""
QuantOS — blind LLM context review of the put H1 retest
───────────────────────────────────────────────────────
Runs docs/PUT_RETEST_CONTEXT_REVIEW_PREREG_2026-10-26.md in three steps:

  build   trades (one per breakdown episode, scripts/backtest_fno_indicator_filter.py's
          H1 logic) + the context known at entry -> ~/.quantos/bt_fno/put_retest_context.jsonl
  review  first half only, symbols and dates removed -> Claude (model_for("context_review"))
          -> at most 3 skip rules, saved with the response under docs/
  test    the saved rules on the second half -> results doc

Reads ~/.quantos/bt_fno/{bars.pkl, outcomes.jsonl, m15/*.npy, results_dates.json, sectors.json};
build also fetches India VIX daily bars from Fyers (needs today's token).

Usage:
    python scripts/review_put_retest_context.py build
    python scripts/review_put_retest_context.py review
    python scripts/review_put_retest_context.py test
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import re
import sys
import time
from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, stdev
from typing import Optional

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.backtest_fno_entries import BT, IST, Sym, atr_at, trade  # noqa: E402

TAG = "2026-10-26"
CONTEXT = BT / "put_retest_context.jsonl"
VIX = BT / "vix.json"
RULES = ROOT / "docs" / f"put_retest_context_rules_{TAG}.json"
REVIEW_DOC = ROOT / "docs" / f"PUT_RETEST_CONTEXT_REVIEW_LLM_{TAG}.md"
RESULTS_DOC = ROOT / "docs" / f"PUT_RETEST_CONTEXT_REVIEW_RESULTS_{TAG}.md"
FEATURE = "context_review"
MIN_REMOVED, MIN_KEPT_FRAC, T_PASS = 30, 0.5, 2.0

# specific sectors first: a stock in both NIFTY BANK and NIFTY FINANCIAL SERVICES is "bank"
SECTOR_ORDER = ["niftybank", "niftypsubank", "niftyit", "niftypharma", "niftyhealthcare", "niftyrealty",
                "niftymetal", "niftyfmcg", "niftyauto", "niftyoilgas", "niftyenergy", "niftymedia",
                "niftyconsumerdurables", "niftychemicals", "niftycapitalmarkets", "niftyindiadefence",
                "niftyfinancialservices", "niftyinfrastructure", "niftycommodities", "niftyconsumption", "niftycpse"]

FEATURES = {
    "days_to_results": "trading days from the signal to the stock's next results board meeting (99 = none known)",
    "days_since_results": "trading days since its last results board meeting (99 = none known)",
    "nifty_above_ema20": "NIFTY closed above its 20-day EMA on the signal day",
    "nifty_ret5": "NIFTY % change over the 5 sessions to the signal",
    "nifty_ret20": "NIFTY % change over the 20 sessions to the signal",
    "vix": "India VIX close on the signal day",
    "vix_chg5": "India VIX % change over 5 sessions",
    "sector": "NSE sectoral index the stock belongs to ('other' if none)",
    "sector_ret20": "mean 20-session % change of the other backtest stocks in that sector",
    "ret5": "stock % change over 5 sessions to the signal",
    "ret20": "stock % change over 20 sessions to the signal",
    "atr_pct": "ATR(14) as % of the close",
    "dist_52w_low_atr": "close minus the 52-week low, in ATR",
    "depth_below_floor_atr": "how far the close is below the broken box floor, in ATR",
    "box_width_pct": "height of the broken box as % of the floor",
    "vol_ratio": "signal-day volume vs its average",
    "days_out": "sessions since the breakdown (0 = breakdown day)",
    "tier": "screener tier",
    "bucket": "screener bucket",
    "momentum_pct": "screener momentum percentile (inverted for puts: high = weak stock)",
    "oi": "5-session futures OI build-up label",
    "iv": "implied vol of the screener's chosen put contract",
    "fill_session": "session of the fill after the signal (1-3)",
    "fill_gap_atr": "fill day's open vs the previous close, in ATR (+ = gapped up toward the limit)",
    "filled_at_open": "the open was already at or above the limit, so it filled at the open",
    "weekday": "weekday of the fill",
    "days_to_expiry": "trading days from the fill to the monthly expiry",
}


# ── build ────────────────────────────────────────────────────────────────────

def _daily() -> dict[str, dict[date, tuple]]:
    raw = pickle.loads((BT / "bars.pkl").read_bytes())
    return {s: {(t.astimezone(IST).date() if t.tzinfo else t.date()): (o, h, l, c) for t, o, h, l, c, v in rows}
            for s, rows in raw.items()}


def fetch_vix(first: date, last: date) -> dict[str, float]:
    if VIX.exists():
        return json.loads(VIX.read_text())
    from agent.main import load_config
    from core.brokers import get_broker
    b = get_broker(load_config(str(ROOT / "agent" / "config.yaml")))
    if not b.connect():
        raise SystemExit("Fyers connect failed -- refresh the token")
    out: dict[str, float] = {}
    frm = datetime.combine(first, datetime.min.time(), timezone.utc)
    while frm.date() <= last:
        to = min(frm + timedelta(days=360), datetime.combine(last, datetime.min.time(), timezone.utc))
        for c in b.get_historical_data("INDIA VIX", "1d", frm, to):
            out[c.timestamp.astimezone(IST).date().isoformat()] = c.close
        frm = to + timedelta(days=1)
        time.sleep(1.0)
    VIX.write_text(json.dumps(out))
    return out


def _pct(series: list[float], i: int, n: int) -> Optional[float]:
    return (series[i] / series[i - n] - 1) * 100 if i >= n and series[i - n] else None


def monthly_expiry(d: date, cal: list[date]) -> date:
    """Last Tuesday of d's month (NSE stock expiry from Sep 2025), moved back to a trading day;
    the next month's once it has passed."""
    for k in range(2):
        y, m = d.year + (d.month + k - 1) // 12, (d.month + k - 1) % 12 + 1
        last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
        e = last - timedelta(days=(last.weekday() - 1) % 7)
        i = bisect_right(cal, e) - 1
        if i >= 0 and cal[i] >= d:
            return cal[i]
    return d


def build() -> int:
    daily = _daily()
    cal = sorted(daily["NIFTY"])
    pos = {d: i for i, d in enumerate(cal)}
    nxt = {d: cal[i + 1] for i, d in enumerate(cal[:-1])}
    nclose = [daily["NIFTY"][d][3] for d in cal]
    nema, a = [], 2 / 21
    for c in nclose:
        nema.append(c if not nema else nema[-1] + a * (c - nema[-1]))
    vix = fetch_vix(cal[0], cal[-1])
    vix_days = sorted(date.fromisoformat(x) for x in vix)
    results = {s: sorted(date.fromisoformat(x) for x in v)
               for s, v in json.loads((BT / "results_dates.json").read_text()).items()}
    sectors = json.loads((BT / "sectors.json").read_text())
    sector_of = {}
    for name in SECTOR_ORDER:
        for s in sectors.get(name, []):
            sector_of.setdefault(s, name.replace("nifty", ""))

    closes = {s: {d: v[3] for d, v in dd.items()} for s, dd in daily.items()}
    sdays = {s: sorted(dd) for s, dd in daily.items()}

    def ret_at(s: str, d: date, n: int) -> Optional[float]:
        ds = sdays[s]
        i = bisect_right(ds, d) - 1
        return (closes[s][ds[i]] / closes[s][ds[i - n]] - 1) * 100 if i >= n else None

    def tdays(a: date, b: date) -> int:
        return abs(bisect_left(cal, b) - bisect_left(cal, a))

    sigs = [json.loads(l) for l in (BT / "outcomes.jsonl").read_text().splitlines() if l.strip()]
    sigs = sorted((r for r in sigs if r["state"] in ("FRESH", "OUT") and r.get("box_level") and r["side"] == "PE"),
                  key=lambda r: r["date"])
    syms: dict[str, Optional[Sym]] = {}

    def sym(s: str) -> Optional[Sym]:
        if s not in syms:
            f = BT / "m15" / f"{s}.npy"
            arr = np.load(f) if f.exists() else None
            syms[s] = Sym(arr) if arr is not None and arr.size else None
        return syms[s]

    done, rows = set(), []
    for r in sigs:
        s, t = r["symbol"], date.fromisoformat(r["date"])
        ep = (s, round(r["box_level"], 2))
        if ep in done:
            continue
        S, d1 = sym(s), nxt.get(t)
        if S is None or d1 is None or d1 not in daily[s]:
            continue
        i1, atr = S.day_index(d1), atr_at(daily[s], t)
        if i1 is None or not atr:
            continue
        p = r["box_level"] - 0.25 * atr
        sess, day, fill = 0, None, None
        for i in range(i1, len(S.a)):
            if S.days[i] != day:
                day, sess = S.days[i], sess + 1
                if sess > 3:
                    break
                day_open, first_bar = S.a[i, 1], True
            else:
                first_bar = False
            if S.a[i, 2] >= p:
                ret = trade(S, i, max(S.a[i, 1], p), -1, atr, False)
                if ret is not None:
                    fill = (i, sess, day, day_open, first_bar and S.a[i, 1] >= p, ret)
                break
        if fill is None:
            continue
        done.add(ep)
        i, fsess, fday, fopen, at_open, ret = fill
        prev_d = cal[pos[fday] - 1] if fday in pos and pos[fday] > 0 else None
        prev_c = daily[s].get(prev_d, (None,) * 4)[3] if prev_d else None
        close = daily[s][t][3]
        lows = [daily[s][d][2] for d in sdays[s] if t - timedelta(days=365) < d <= t]
        nx = [d for d in results.get(s, []) if d >= t]
        pv = [d for d in results.get(s, []) if d < t]
        vi = bisect_right(vix_days, t) - 1
        v_now = vix[vix_days[vi].isoformat()] if vi >= 0 else None
        v_old = vix[vix_days[vi - 5].isoformat()] if vi >= 5 else None
        sec = sector_of.get(s, "other")
        peers = [x for x in (ret_at(o, t, 20) for o, n in sector_of.items() if n == sec and o != s and o in daily)
                 if x is not None] if sec != "other" else []
        k = pos[t]
        rows.append({
            "symbol": s, "signal_date": t.isoformat(), "ret": round(float(ret), 3), "win": bool(ret > 0),
            "days_to_results": tdays(t, nx[0]) if nx else 99,
            "days_since_results": tdays(pv[-1], t) if pv else 99,
            "nifty_above_ema20": bool(nclose[k] > nema[k]),
            "nifty_ret5": _pct(nclose, k, 5), "nifty_ret20": _pct(nclose, k, 20),
            "vix": v_now, "vix_chg5": (v_now / v_old - 1) * 100 if v_now and v_old else None,
            "sector": sec, "sector_ret20": mean(peers) if peers else None,
            "ret5": ret_at(s, t, 5), "ret20": ret_at(s, t, 20),
            "atr_pct": atr / close * 100,
            "dist_52w_low_atr": (close - min(lows)) / atr,
            "depth_below_floor_atr": (r["box_level"] - close) / atr,
            "box_width_pct": r.get("box_width_pct"), "vol_ratio": r.get("vol_ratio"),
            "days_out": r.get("days_out") or 0, "tier": r.get("tier"), "bucket": r.get("bucket"),
            "momentum_pct": r.get("momentum_pct"), "oi": r.get("oi"),
            "iv": (r.get("contract") or {}).get("iv"),
            "fill_session": fsess,
            "fill_gap_atr": (fopen - prev_c) / atr if prev_c else None,
            "filled_at_open": bool(at_open),
            "weekday": fday.strftime("%a"),
            "days_to_expiry": tdays(fday, monthly_expiry(fday, cal)),
        })
    with CONTEXT.open("w") as f:
        for row in rows:
            f.write(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items()}) + "\n")
    print(f"{len(rows)} trades -> {CONTEXT}  (win {mean(r['win'] for r in rows):.0%}, mean {mean(r['ret'] for r in rows):+.2f}%)")
    return 0


# ── review ───────────────────────────────────────────────────────────────────

def load_rows() -> tuple[list[dict], str]:
    rows = [json.loads(l) for l in CONTEXT.read_text().splitlines() if l.strip()]
    sigs = sorted({json.loads(l)["date"] for l in (BT / "outcomes.jsonl").read_text().splitlines() if l.strip()})
    return rows, sigs[len(sigs) // 2]


def _summ(rs: list[dict]) -> str:
    if not rs:
        return "n=0"
    return f"n={len(rs)}, win {mean(r['win'] for r in rs):.0%}, mean {mean(r['ret'] for r in rs):+.2f}%"


def bucket_tables(rows: list[dict]) -> str:
    out = []
    for f in FEATURES:
        vals = [r[f] for r in rows if r.get(f) is not None]
        if not vals:
            continue
        out.append(f"\n{f}:")
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            qs = np.quantile(vals, [0.2, 0.4, 0.6, 0.8])
            edges = [-math.inf, *qs, math.inf]
            for lo, hi in zip(edges, edges[1:]):
                rs = [r for r in rows if r.get(f) is not None and lo < r[f] <= hi]
                out.append(f"  ({lo:.2f}, {hi:.2f}]: {_summ(rs)}")
        else:
            for v in sorted({str(x) for x in vals}):
                rs = [r for r in rows if str(r.get(f)) == v]
                if len(rs) >= 10:
                    out.append(f"  {v}: {_summ(rs)}")
    return "\n".join(out)


def review() -> int:
    from scripts.review_structure import load_env_file
    load_env_file(ROOT / ".env.cloud-api")
    import anthropic
    from core import prompts
    from core.llm.calllog import log_call
    from core.llm.registry import model_for

    rows, mid = load_rows()
    first = [r for r in rows if r["signal_date"] < mid]
    cols = list(FEATURES)
    csv_lines = [",".join(cols + ["ret_pct", "win"])]
    for r in first:
        csv_lines.append(",".join("" if r.get(c) is None else str(r[c]) for c in cols) + f",{r['ret']},{int(r['win'])}")
    user = "\n".join([
        "Strategy: after a stock breaks down below a multi-week range (box) floor, sell its futures with a "
        "limit 0.25 ATR under the broken floor (a retest from below), valid 3 sessions. Stop on a daily close "
        "0.75 ATR above the fill, emergency stop 1 ATR further on touch, take profit at 1R (0.75 ATR below the "
        "fill), exit after 10 sessions. 0.1% round-trip cost. One trade per breakdown, F&O stocks, NSE.",
        f"This half: {_summ(first)}. Winners are mostly 1R targets; losers mostly stops.",
        "", "Feature definitions:", *[f"- {k}: {v}" for k, v in FEATURES.items()],
        "", "Win rate and mean return by feature bucket (quintiles for numbers), this half only:",
        bucket_tables(first),
        "", f"All {len(first)} trades of this half (CSV, ret_pct after cost):", "```csv", *csv_lines, "```",
        "", "Propose at most 3 skip rules as instructed.",
    ])
    model = model_for(FEATURE)
    client = anthropic.Anthropic(timeout=900.0)
    started, response = time.perf_counter(), None
    try:
        response = client.beta.messages.create(
            model=model, max_tokens=16000, system=prompts.load("context_review_system"),
            output_config={"effort": "high"}, messages=[{"role": "user", "content": user}],
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
    finally:
        log_call(FEATURE, model, response, started)
    if response.stop_reason == "refusal":
        raise SystemExit(f"refused: {response.stop_details}")
    text = "\n".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()
    m = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if not m:
        raise SystemExit("no json block in the response:\n" + text)
    rules = json.loads(m[-1])["rules"][:3]
    RULES.write_text(json.dumps({"model": response.model, "mid": mid, "rules": rules}, indent=1) + "\n")
    REVIEW_DOC.write_text("\n".join([
        f"# Put retest context review — {response.model}, {TAG}", "",
        "Protocol: docs/PUT_RETEST_CONTEXT_REVIEW_PREREG_2026-10-26.md. The model saw the first half only "
        f"(signals before {mid}, {len(first)} trades), with symbols and dates removed. "
        f"Tokens: {response.usage.input_tokens} in, {response.usage.output_tokens} out.", "",
        "## Model response", "", text, "",
        "## Tables it was given (first half)", "", "```", bucket_tables(first).strip(), "```", "",
    ]))
    print(text)
    print(f"\nrules -> {RULES}\nreview -> {REVIEW_DOC}")
    return 0


# ── test ─────────────────────────────────────────────────────────────────────

def matches(rule: dict, row: dict) -> bool:
    ops = {"<": lambda a, b: a < b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
           "==": lambda a, b: a == b, "!=": lambda a, b: a != b, "in": lambda a, b: a in b}
    for c in rule["conditions"]:
        v = row.get(c["feature"])
        if v is None:
            return False
        try:
            if not ops[c["op"]](v, c["value"]):
                return False
        except TypeError:
            return False
    return True


def stats(rs: list[dict]) -> dict:
    if not rs:
        return {"n": 0}
    x = [r["ret"] for r in rs]
    pos_, neg = sum(v for v in x if v > 0), -sum(v for v in x if v < 0)
    return {"n": len(x), "win": mean(r["win"] for r in rs), "mean": mean(x), "pf": pos_ / neg if neg else math.inf,
            "sd": stdev(x) if len(x) > 1 else 0.0}


def welch_t(a: dict, b: dict) -> float:
    if a["n"] < 2 or b["n"] < 2:
        return 0.0
    se = math.sqrt(a["sd"] ** 2 / a["n"] + b["sd"] ** 2 / b["n"])
    return (a["mean"] - b["mean"]) / se if se else 0.0


def _cell(s: dict) -> str:
    if not s["n"]:
        return "0 | | | "
    pf = "inf" if s["pf"] == math.inf else f"{s['pf']:.2f}"
    return f"{s['n']} | {s['win']:.0%} | {s['mean']:+.2f}% | {pf}"


def test() -> int:
    rows, mid = load_rows()
    spec = json.loads(RULES.read_text())
    halves = {"first (seen)": [r for r in rows if r["signal_date"] < mid],
              "second (held out)": [r for r in rows if r["signal_date"] >= mid]}
    rules = spec["rules"] + ([{"name": "ALL rules (skip if any)", "any": spec["rules"]}] if len(spec["rules"]) > 1 else [])
    out = [f"# Put retest context review — results ({TAG})", "",
           f"Rules from {spec['model']} (docs/PUT_RETEST_CONTEXT_REVIEW_LLM_{TAG}.md), judged on the second half "
           f"(signals from {mid}) per docs/PUT_RETEST_CONTEXT_REVIEW_PREREG_2026-10-26.md. Returns % per trade "
           "after cost.", ""]
    verdicts = []
    for name, rs in halves.items():
        base = stats(rs)
        out += [f"## {name} half — unfiltered: {_cell(base)}", "",
                "| rule | kept n | kept win | kept mean | kept PF | skipped n | skipped win | skipped mean | skipped PF | t (kept − skipped) | verdict |",
                "|---|---|---|---|---|---|---|---|---|---|---|"]
        for rule in rules:
            fire = (lambda r, rule=rule: any(matches(x, r) for x in rule["any"])) if "any" in rule else \
                   (lambda r, rule=rule: matches(rule, r))
            kept, skipped = stats([r for r in rs if not fire(r)]), stats([r for r in rs if fire(r)])
            t = welch_t(kept, skipped) if kept["n"] and skipped["n"] else 0.0
            v = ""
            if name.startswith("second"):
                ok = (skipped["n"] >= MIN_REMOVED and kept["n"] >= MIN_KEPT_FRAC * base["n"]
                      and kept["mean"] > base["mean"] and t >= T_PASS)
                v = "PASS" if ok else "FAIL"
                verdicts.append(f"{rule['name']}: {v}")
            out.append(f"| {rule['name']} | {_cell(kept)} | {_cell(skipped)} | {t:+.2f} | {v} |")
        out.append("")
    out[4:4] = ["**Verdicts (held-out half):** " + ("; ".join(verdicts) if verdicts else "no rules proposed"), ""]
    out += ["## Rules", "", *[f"- **{r['name']}**: {r['reason']} Conditions: `{json.dumps(r['conditions'])}`"
                              for r in spec["rules"]]]
    RESULTS_DOC.write_text("\n".join(out) + "\n")
    print("\n".join(out))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["build", "review", "test"])
    return {"build": build, "review": review, "test": test}[ap.parse_args().step]()


if __name__ == "__main__":
    raise SystemExit(main())
