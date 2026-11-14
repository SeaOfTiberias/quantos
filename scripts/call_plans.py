"""Map plans for the F&O screener's Telegram calls and the Darvas scan's breakouts (core/market_map/call_plan.py), every weekday
after the L1 refresh (20:00 IST).

  1. New calls (the screener's picks in ~/.quantos/fno_screener_outcomes.json not yet planned,
     from --start on): the card as of the call's close -> a plan version (sweep / breakout,
     target, expiry), tracks opened.
  2. Open plans: each new daily bar is walked with the version made the evening before it
     (no lookahead): swept, triggered, entered at the next open, stopped / target / time,
     lapsed, broke.
  3. Plans still waiting are re-planned from tonight's card (new liquidity counts).
  4. Every version and event goes to an append-only journal BEFORE the outcome; the state file
     holds the tracks. Telegram: the new plans and tonight's events.
  5. --report: every call, the plan's result vs the call as sent (close to the last close).

Paper only: places NO orders, needs no broker login and no API key (L1 store + Telegram env).

    .venv/bin/python scripts/call_plans.py [--no-telegram] [--start YYYY-MM-DD] [--report]
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import json
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.market_map import call_plan as cp  # noqa: E402
from core.market_map import card as cd  # noqa: E402
from core.market_map import structure  # noqa: E402
from core.market_map.l1_store import Store, default_root  # noqa: E402
from core.market_map.m5_store import M5Store  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
QUANTOS = Path.home() / ".quantos"
CALLS = QUANTOS / "fno_screener_outcomes.json"
DARVAS = QUANTOS / "darvas_atr_stop_plan.json"     # the 18:00 IST scan's plan, rewritten nightly
ROOT = QUANTOS / "call_plans"


def next_weekday(d: date, n: int = 1) -> date:
    for _ in range(n):
        d += timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
    return d


def load_calls(path: Path = CALLS) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for v in raw.values():
        p = v if isinstance(v, dict) else ast.literal_eval(v)
        out.append(dict(key=p["key"], date=p["trade_date"], sym=p["symbol"], side=p["side"],
                        spot=float(p["entry_spot"])))
    return sorted(out, key=lambda p: (p["date"], p["sym"], p["side"]))


def load_darvas(path: Path = DARVAS) -> list[dict]:
    """Tonight's Darvas breakouts (2026-11-14, user: the map picks the entry for Darvas too).
    The scan rewrites its plan file every evening, so each run picks up that evening's entries;
    the Darvas paper executor still enters them at the open, unchanged, for the comparison."""
    if not path.exists():
        return []
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    d = plan.get("bars_as_of") or plan.get("through")
    return [dict(key=f"{d}|DARVAS|{e['symbol']}", date=d, sym=e["symbol"], side="CE",
                 spot=float(e["last_close"]), src="Darvas") for e in plan.get("entries") or []
            if d and e.get("symbol") and e.get("last_close")]


class Bars:
    """Adjusted daily bars and cards from the L1 store, cached per symbol."""

    def __init__(self, store: Store):
        self.st, self.cache = store, {}

    def adj(self, sym: str):
        if sym not in self.cache:
            a, _ = self.st.adjusted(sym)
            m5 = M5Store(self.st.root).adjusted(sym, a, self.st.actions().get(sym, [])) if len(a) else []
            self.cache[sym] = (a, m5 if len(m5) else None)
        return self.cache[sym]

    def card(self, sym: str, through: str) -> tuple[dict, object]:
        """The card from bars through `through` (inclusive), and those bars."""
        a, m5 = self.adj(sym)
        if a is None or a.empty:
            return dict(sym=sym, error="not in the L1 store"), None
        upto = a[a["date"] <= through]
        if upto.empty:
            return dict(sym=sym, error=f"no bars through {through}"), None
        as_of = next_weekday(date.fromisoformat(through))
        try:
            rd = structure.l1_read(a, as_of, m5)
            rd["last_date"] = upto["date"].iat[-1].date().isoformat()
            return cd.card(sym, rd, a), upto
        except Exception as e:                                             # noqa: BLE001
            return dict(sym=sym, error=f"{type(e).__name__}: {str(e)[:120]}"), upto


def _bar(row) -> dict:
    return dict(date=row["date"].date().isoformat(), o=float(row["o"]), h=float(row["h"]),
                l=float(row["l"]), c=float(row["c"]))


def _version_for(plan: dict, day: str) -> dict:
    """The version made on the last evening before `day`."""
    vs = [v for v in plan["versions"] if v["as_of"] < day]
    return vs[-1] if vs else {}


def run(store: Store, start: str, root: Path = ROOT, calls_path: Path = CALLS,
        last: str | None = None, darvas_path: Path | None = DARVAS) -> tuple[list[str], list[str]]:
    """One evening (`last`: the session it runs after; default the store's last session).
    Returns (new-plan lines, event lines)."""
    root.mkdir(parents=True, exist_ok=True)
    state_p, journal_p = root / "state.json", root / "journal.jsonl"
    state = json.loads(state_p.read_text(encoding="utf-8")) if state_p.exists() else {}
    last = last or store.last_session().isoformat()
    stamp = datetime.now(IST).isoformat(timespec="seconds")
    bars = Bars(store)
    journal, new_lines, ev_lines = [], [], []

    # 1. new calls
    calls = load_calls(calls_path) + (load_darvas(darvas_path) if darvas_path else [])
    for c in calls:
        if c["key"] in state or c["date"] < start or c["date"] > last:
            continue
        card, _ = bars.card(c["sym"], c["date"])
        upto = bars.adj(c["sym"])[0]
        upto = upto[upto["date"] <= c["date"]] if upto is not None and len(upto) else upto
        v = cp.make_plan(card, upto, c["side"]) if upto is not None and len(upto) else dict(error=card.get("error"))
        v["as_of"] = c["date"]
        tracks = [cp.new_track(k, c["side"]) for k in ("sweep", "breakout") if v.get(k)]
        state[c["key"]] = dict(call=c, versions=[v], tracks=tracks, through=c["date"])
        journal.append(dict(at=stamp, key=c["key"], what="plan", version=v))
        expires = next_weekday(date.fromisoformat(c["date"]), cp.EXPIRY).isoformat()
        new_lines += cp.plan_lines(c["sym"], c["side"], c["spot"], v, expires, c.get("src", "F&O")) + [""]

    # 2. walk open plans over the new bars, 3. re-plan the ones still waiting
    for key, p in state.items():
        if not any(t["state"] in cp.OPEN_STATES for t in p["tracks"]):
            continue
        a = bars.adj(p["call"]["sym"])[0]
        if a is None or a.empty:
            continue
        new = a[(a["date"] > p["through"]) & (a["date"] <= last)]
        for _, row in new.iterrows():
            b = _bar(row)
            for i, t in enumerate(p["tracks"]):
                if t["state"] not in cp.OPEN_STATES:
                    continue
                n0 = len(t["events"])
                p["tracks"][i] = t = cp.step(t, _version_for(p, b["date"]), b)
                for e in t["events"][n0:]:
                    journal.append(dict(at=stamp, key=key, kind=t["kind"], what="event", event=e))
                    ev_lines.append(cp.event_line(p["call"]["sym"], p["call"]["side"], t["kind"], e,
                                                  p["call"].get("src", "F&O")))
            p["through"] = b["date"]
        if p["through"] == last and any(t["state"] == "waiting" for t in p["tracks"]) \
                and p["versions"][-1]["as_of"] < last:
            card, upto = bars.card(p["call"]["sym"], last)
            if upto is not None:
                v = cp.make_plan(card, upto, p["call"]["side"])
                v["as_of"] = last
                p["versions"].append(v)
                journal.append(dict(at=stamp, key=key, what="replan", version=v))

    with journal_p.open("a", encoding="utf-8") as f:                       # journal first, then state
        for j in journal:
            f.write(json.dumps(j, default=str) + "\n")
    state_p.write_text(json.dumps(state, indent=1, default=str), encoding="utf-8")
    return new_lines, ev_lines


def report(store: Store, root: Path = ROOT) -> str:
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    bars, rows = Bars(store), []
    for key, p in sorted(state.items()):
        c = p["call"]
        a = bars.adj(c["sym"])[0]
        lc = float(a["c"].iat[-1])
        sg = 1 if c["side"] == "CE" else -1
        as_sent = round(sg * (lc / c["spot"] - 1) * 100, 2)
        for t in p["tracks"] or [dict(kind="-", state="no plan")]:
            m = cp.mark(t, lc) if t.get("state") == "triggered" else {}
            rows.append(dict(key=key, src=c.get("src", "F&O"), kind=t["kind"], state=t["state"], r=t.get("r", m.get("r")),
                             pct=t.get("pct", m.get("pct")), as_sent=as_sent))
    lines = [f"{r['key']:32s} {r['kind']:9s} {r['state']:16s} R {r['r']!s:>6} plan% {r['pct']!s:>6}  as-sent% {r['as_sent']}"
             for r in rows]
    for src in sorted({r["src"] for r in rows}):
        done = [r for r in rows if r["r"] is not None and r["src"] == src]
        if done:
            lines.append(f"\n{src}: {len(done)} entered: mean R {mean(r['r'] for r in done):.2f}, mean plan% "
                         f"{mean(r['pct'] for r in done):.2f}; as sent on the same calls "
                         f"{mean(r['as_sent'] for r in done):.2f}%")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", type=Path, default=None)
    ap.add_argument("--start", default=None, help="plan calls from this date on (default: the store's last session)")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--root", type=Path, default=ROOT, help="state + journal folder (default ~/.quantos/call_plans)")
    ap.add_argument("--calls", type=Path, default=CALLS)
    ap.add_argument("--darvas", type=Path, default=DARVAS, help="the Darvas scan's plan file")
    ap.add_argument("--replay-from", default=None,
                    help="replay every evening from this session to the store's last (testing; use a scratch --root)")
    a = ap.parse_args(argv)
    store = Store(a.store or default_root())
    if a.report:
        print(report(store, a.root))
        return 0
    start_p = a.root / "start.txt"
    start = a.start or (start_p.read_text().strip() if start_p.exists() else store.last_session().isoformat())
    a.root.mkdir(parents=True, exist_ok=True)
    if not start_p.exists():
        start_p.write_text(start)
    if a.replay_from:
        a2 = store.adjusted("NIFTYBEES" if "NIFTYBEES" in store.symbols() else store.symbols()[0])[0]
        days = [d.date().isoformat() for d in a2["date"] if a.replay_from <= d.date().isoformat() <= store.last_session().isoformat()]
        for d in days:
            n, e = run(store, start, a.root, a.calls, last=d, darvas_path=a.darvas)
            print(f"== {d}: {sum(1 for x in n if x.startswith('🗺'))} new, {len(e)} events")
        print(report(store, a.root))
        return 0
    try:
        new_lines, ev_lines = run(store, start, a.root, a.calls, darvas_path=a.darvas)
    except Exception:                                                      # noqa: BLE001
        traceback.print_exc()
        return 1
    last = store.last_session()
    msg = [f"🗺 Map plans for the F&O calls and Darvas breakouts · close of {last:%a %d %b}",
           "Wait for the level; enter on the reclaim; stop beyond the sweep; bank at the target. "
           "Paper plans (UNTESTED rule, scored vs the calls as sent), not orders.", ""]
    msg += new_lines or ["No new calls tonight.", ""]
    if ev_lines:
        msg += ["Tonight's events on open plans:"] + ev_lines
    text = "\n".join(msg)
    print(text)
    if not a.no_telegram and (new_lines or ev_lines):
        from cloud.api.notifier import send_telegram
        parts, cur = [], ""
        for line in text.split("\n"):
            if len(cur) + len(line) + 1 > 3900:
                parts.append(cur); cur = ""
            cur += line + "\n"
        parts.append(cur)
        if not all(asyncio.run(send_telegram(x)) for x in parts if x.strip()):
            print("ERROR: Telegram send failed")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
