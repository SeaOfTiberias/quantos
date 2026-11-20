#!/usr/bin/env python3
"""The call ledger (docs/EXECUTION_PLAN_2026-11-19.md, E5): every call, from whatever source,
written down before its outcome and scored in R against two mechanical baselines.

  add    python scripts/ledger.py add --json '{"symbol": "SYN", "side": "long", "who": "claude",
           "entry": {"kind": "limit", "price": 98.5}, "stop": 95.2, "target": 106,
           "salvage": "...", "decision": "taken", "why": "..."}'
  list   python scripts/ledger.py list [--all]
  score  python scripts/ledger.py score [--no-telegram]   # the evening job: re-scores every call

Files (append-only calls, re-written scores):
  ~/.quantos/ledger/calls.jsonl    one call per line, never edited
  ~/.quantos/ledger/scores.json    {"as_of", "scores": {id: score}, "summary"}

Code computes, when a call is added: the frozen v3 map read (required: no read, no call), the
context card, the call-evening map plan (core/market_map/call_plan.make_plan) and the reference
close. The `as_of` session: the latest in the L1 store, or today once today's session has opened
(09:15 IST on a weekday), so a call never scores a bar its caller had already seen.

Records only: nothing here places an order. Scoring is core/ledger/score.py (unit-tested).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ledger import schema as sc  # noqa: E402
from core.ledger import score as sx  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
OPEN = time(9, 15)


def root() -> Path:
    override = os.getenv("QUANTOS_HOME_DIR")
    return (Path(override) if override else Path.home() / ".quantos") / "ledger"


def load_calls(r: Optional[Path] = None) -> list[dict]:
    p = (r or root()) / "calls.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                print(f"skipping a malformed ledger line: {line[:80]}")
    return out


def append_call(c: dict, r: Optional[Path] = None) -> None:
    p = (r or root()) / "calls.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(c, default=str) + "\n")


def cutoff(now: datetime, store_last: date) -> str:
    """The as_of session: bars after it are scored."""
    today = now.astimezone(IST).date()
    if today.weekday() < 5 and now.astimezone(IST).time() >= OPEN and today > store_last:
        return today.isoformat()
    return store_last.isoformat()


class Market:
    """Adjusted daily bars, the map read, card and map plan from the L1 store (or the index bars)."""

    def __init__(self, store=None, index_root: Optional[Path] = None):
        from core.market_map.l1_store import Store
        from core.market_map.read import L1_ROOT
        self.store = store if store is not None else Store(L1_ROOT)
        self.index_root = index_root
        self._cache: dict = {}

    def daily(self, sym: str):
        if sym not in self._cache:
            from core.market_map.read import INDEX_SYMBOLS
            if sym in INDEX_SYMBOLS:
                from core.market_map.index_bars import IndexBars
                df = IndexBars(self.index_root).load(sym)
            else:
                df, _ = self.store.adjusted(sym)
            self._cache[sym] = df
        return self._cache[sym]

    def bars_after(self, sym: str, as_of: str) -> list[dict]:
        df = self.daily(sym)
        if df is None or df.empty:
            return []
        d = df[df["date"] > as_of]
        return [dict(date=r.date.date().isoformat(), o=float(r.o), h=float(r.h), l=float(r.l), c=float(r.c))
                for r in d.itertuples()]

    def close_on(self, sym: str, day: str) -> Optional[float]:
        df = self.daily(sym)
        d = df[df["date"] <= day] if df is not None and len(df) else None
        return float(d["c"].iat[-1]) if d is not None and len(d) else None

    def context(self, raw: dict, now: datetime) -> dict:
        from core.market_map import call_plan as cp
        from core.market_map import card as cd
        from core.market_map.read import frozen, map_read
        sym = str(raw.get("symbol") or "").strip().upper()
        df = self.daily(sym)
        if df is None or df.empty:
            return dict(error=f"{sym}: no daily bars")
        last = df["date"].iat[-1].date()
        e = raw.get("entry") or {}
        entry = e.get("price") or float(df["c"].iat[-1])
        trade = None
        if raw.get("side") in ("long", "short"):
            trade = {"side": raw["side"], "entry": float(entry), "stop": raw.get("stop"), "target": raw.get("target")}
        rd = map_read(sym, trade, l1_store=self.store, index_root=self.index_root)
        l1 = rd.pop("l1", None) if isinstance(rd, dict) else None
        crd = cd.card(sym, l1, df) if l1 and "error" not in l1 else None
        plan = None
        if crd and not crd.get("error") and raw.get("side") in ("long", "short"):
            c2 = dict(crd, last_date=last.isoformat())
            plan = cp.make_plan(c2, df[df["date"] <= last.isoformat()], sx.CP_SIDE[raw["side"]])
            plan["as_of"] = last.isoformat()
        stored = frozen(rd) if "error" not in rd else rd
        if crd:
            stored["card"] = crd
        return dict(as_of=cutoff(now, last), ref_date=last.isoformat(), ref_close=float(df["c"].iat[-1]),
                    atr=(crd or {}).get("atr_d") or rd.get("atr"), map_read=stored, map_plan=plan)


def add(raw: dict, market: Optional[Market] = None, now: Optional[datetime] = None,
        r: Optional[Path] = None) -> dict:
    now = now or datetime.now(IST)
    m = market or Market()
    ctx = m.context(raw, now)
    if ctx.get("error"):
        raise sc.CallError(ctx["error"])
    calls = load_calls(r)
    sym = str(raw.get("symbol") or "").strip().upper()
    seq = 1 + sum(c["symbol"] == sym and c["as_of"] == ctx["as_of"] and c["who"] == raw.get("who") for c in calls)
    c = sc.make_call(raw, now=now, as_of=ctx["as_of"], ref_close=ctx["ref_close"], atr=ctx["atr"],
                     map_read=ctx["map_read"], map_plan=ctx["map_plan"], seq=seq)
    c["ref_date"] = ctx["ref_date"]
    if raw.get("source_ref") and any(x.get("source_ref") == raw["source_ref"] for x in calls):
        raise sc.CallError(f"already in the ledger: {raw['source_ref']}")
    append_call(c, r)
    return c


def score_all(market: Optional[Market] = None, r: Optional[Path] = None) -> dict:
    m = market or Market()
    calls = load_calls(r)
    scores = {}
    for c in calls:
        try:
            now_ref = m.close_on(c["symbol"], c["ref_date"])
            scale = (now_ref / c["ref_close"]) if now_ref and c.get("ref_close") else 1.0
            scores[c["id"]] = sx.score(c, m.bars_after(c["symbol"], c["as_of"]), scale)
        except Exception as e:                                  # noqa: BLE001 -- one call never stops the rest
            scores[c["id"]] = dict(id=c["id"], error=f"{type(e).__name__}: {e}"[:200], final=False,
                                   r_call=0.0, r_if_taken=0.0, r_as_sent=0.0, r_map_plan=0.0)
    out = dict(as_of=datetime.now(IST).isoformat(timespec="seconds"), scores=scores,
               summary=sx.summary(calls, scores))
    p = (r or root()) / "scores.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    tmp.replace(p)
    return out


def summary_text(out: dict, calls: list[dict]) -> str:
    def g(name, s):
        if not s.get("n"):
            return f"{name}: none yet"
        av = f"; avoided {s['avoided']} (if taken {s['avoided_if_taken']:+.2f}R)" if s.get("avoided") else ""
        return (f"{name}: n {s['n']} ({s['final']} final), mean {s['mean_r']:+.2f}R vs as sent "
                f"{s['as_sent']:+.2f}R, map plan {s['map_plan']:+.2f}R{av}")
    s = out["summary"]
    lines = ["Call ledger (E5), scored in R; untraded = 0R. Paper records, not orders.",
             g("Discretionary", s["discretionary"]), "  " + g("user", s["user"]), "  " + g("Claude", s["claude"]),
             g("Mechanical", s["mechanical"])]
    return "\n".join(lines)


def send(msg: str) -> bool:
    from cloud.api.notifier import send_telegram
    try:
        return bool(asyncio.run(send_telegram(msg)))
    except Exception as e:                                      # noqa: BLE001
        print(f"telegram error ({type(e).__name__})")
        return False


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a_add = sub.add_parser("add")
    a_add.add_argument("--json", required=True)
    a_list = sub.add_parser("list")
    a_list.add_argument("--all", action="store_true")
    a_sc = sub.add_parser("score")
    a_sc.add_argument("--no-telegram", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "add":
        try:
            c = add(json.loads(a.json))
        except (sc.CallError, ValueError) as e:
            print(f"REFUSED: {e}")
            return 2
        mp = c.get("map_plan") or {}
        sw = mp.get("sweep") or {}
        print(f"logged {c['id']}: {c['side']} {c['symbol']} {c['entry']} stop {c['stop']} target {c['target']} "
              f"({c['decision']}); scored from the session after {c['as_of']}")
        print(f"  map plan baseline: " + (f"sweep {sw['level']} ({', '.join(sw.get('kinds') or [])}), "
                                         f"target {(sw.get('target') or {}).get('level')}" if sw else
                                         f"none ({mp.get('error') or 'no sweep level'})"))
        return 0
    if a.cmd == "list":
        calls = load_calls()
        sp = root() / "scores.json"
        scores = json.loads(sp.read_text()).get("scores", {}) if sp.exists() else {}
        for c in calls:
            s = scores.get(c["id"], {})
            if not a.all and s.get("final"):
                continue
            print(f"{c['id']:<36} {c['side']:<5} {c['decision']:<7} call {s.get('call', {}).get('state', '-'):<9} "
                  f"R {s.get('r_call', 0):+.2f} | as sent {s.get('r_as_sent', 0):+.2f} | map {s.get('r_map_plan', 0):+.2f}")
        return 0
    out = score_all()
    text = summary_text(out, load_calls())
    print(text)
    if not a.no_telegram and out["summary"]["discretionary"].get("n"):
        send(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
