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
from typing import Optional

import pandas as pd
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ideas import events as results_cal  # noqa: E402
from core.market_map.index_bars import IndexBars  # noqa: E402
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
                        spot=float(p["entry_spot"]), src=p.get("src", "F&O")))
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


MAX_ENTRIES_PER_WEEK = 3  # main (sweep) entries per side per ISO week across every plan: the
                          # stocks' sweeps are mostly the market's (GLAND, ZYDUSLIFE, PERSISTENT all
                          # swept 16-26 Oct with the index), so one swing is one bet (the book job's
                          # max_fills groups, docs/TRADE_REASONING.md sweep-week grouping)


def week_entries(state: dict, side: str, day: str) -> int:
    """Main entries already made on `side` in `day`'s ISO week, across every plan."""
    wk = date.fromisoformat(day).isocalendar()[:2]
    return sum(1 for p in state.values() for t in p["tracks"]
               if t["kind"] in cp.SWEEP_KINDS and t["side"] == side and t.get("entry_date")
               and date.fromisoformat(t["entry_date"]).isocalendar()[:2] == wk)


class IndexState:
    """NIFTY's daily structure from its own card (core/market_map/index_bars.py + the stock map
    engine, as scripts/step2_context_test.py builds it). The guard (2026-11-16, user: use what is
    built; the book job's index guards): unfilled longs are cancelled when NIFTY CLOSES below its
    last daily low (the protected low in a D uptrend, the weak low in a downtrend: a close there
    extends the fall), shorts mirror. A close, not a low: NIFTY's own sweep that reclaims is the
    moment longs want (late Oct 2026: D down, held 22179.9, the stock sweeps paid)."""

    def __init__(self, df: Optional[pd.DataFrame] = None):
        if df is None:
            try:
                df = IndexBars().load("NIFTY")
            except Exception:                                              # noqa: BLE001
                df = None
        self.df = df if df is not None and len(df) else None
        self.cache: dict[str, Optional[dict]] = {}

    def summary(self, evening: str) -> Optional[dict]:
        if self.df is None:
            return None
        if evening not in self.cache:
            try:
                c = cd.card("NIFTY", structure.l1_read(self.df, next_weekday(date.fromisoformat(evening))), self.df)
                d, w = c["structure"].get("D") or {}, c["structure"].get("W") or {}
                px = lambda x: (x or {}).get("px")                                    # noqa: E731
                up = d.get("state") == "up"
                self.cache[evening] = dict(as_of=evening, D=d.get("state"), W=w.get("state"),
                                           low=px(d.get("protected") if up else d.get("weak")),
                                           high=px(d.get("weak") if up else d.get("protected")))
            except Exception:                                              # noqa: BLE001
                self.cache[evening] = None
        return self.cache[evening]

    def close(self, day: str) -> Optional[float]:
        if self.df is None:
            return None
        r = self.df[self.df["date"] == pd.Timestamp(day)]
        return float(r["c"].iat[0]) if len(r) else None

    def guard(self, ix: Optional[dict], day: str) -> dict:
        """{side: why} for the sides NIFTY's close on `day` cancels; {} if none or no data."""
        c = self.close(day)
        if not ix or c is None:
            return {}
        out = {}
        if ix.get("low") is not None and c < ix["low"]:
            out["CE"] = f"index guard: NIFTY closed {c:g} below its last D low {ix['low']:g}"
        if ix.get("high") is not None and c > ix["high"]:
            out["PE"] = f"index guard: NIFTY closed {c:g} above its last D high {ix['high']:g}"
        return out


PAGE_BARS = 120          # daily bars kept for each pick's page chart
PAGE_DAYS = 45           # calendar days after the call a closed plan's chart keeps updating


def page_file(root: Path, key: str) -> Path:
    """The page snapshot of one plan (cockpit #/plans/<key>, cloud/api/plans_routes.py)."""
    return root / "pages" / (key.replace("|", "_") + ".json")


def write_page(root: Path, key: str, p: dict, bars: "Bars", last: str, card: dict | None = None,
               card_as_of: str | None = None) -> None:
    """The card and the last PAGE_BARS daily bars through `last` for one plan, so the page never
    rebuilds a map. Without a new card the previous snapshot's card is kept."""
    f = page_file(root, key)
    f.parent.mkdir(parents=True, exist_ok=True)
    old = {}
    if f.exists():
        try:
            old = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            old = {}
    sym = p["call"]["sym"]
    a = bars.cache[sym][0] if sym in bars.cache else bars.st.adjusted(sym)[0]   # daily bars only
    rows = [] if a is None or a.empty else [
        [r["date"].date().isoformat(), round(float(r["o"]), 2), round(float(r["h"]), 2), round(float(r["l"]), 2),
         round(float(r["c"]), 2)] for _, r in a[a["date"] <= last].tail(PAGE_BARS).iterrows()]
    page = dict(key=key, updated=datetime.now(IST).isoformat(timespec="seconds"), through=last, bars=rows,
                card=card if card is not None else old.get("card"),
                card_as_of=card_as_of if card is not None else old.get("card_as_of"))
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(page, default=str), encoding="utf-8")
    tmp.replace(f)


def run(store: Store, start: str, root: Path = ROOT, calls_path: Path = CALLS,
        last: str | None = None, darvas_path: Path | None = DARVAS,
        results_path: Path | None = results_cal.DEFAULT_PATH, pages: bool = True,
        index: Optional["IndexState"] = None) -> tuple[list[str], list[str]]:
    """One evening (`last`: the session it runs after; default the store's last session).
    `results_path`: NSE's upcoming-results calendar (None in replays: there is no history of it).
    Returns (new-plan lines, event lines)."""
    root.mkdir(parents=True, exist_ok=True)
    cal = results_cal.load(results_path) if results_path and results_path.exists() else {}
    idx = index if index is not None else IndexState()
    state_p, journal_p = root / "state.json", root / "journal.jsonl"
    state = json.loads(state_p.read_text(encoding="utf-8")) if state_p.exists() else {}
    last = last or store.last_session().isoformat()
    stamp = datetime.now(IST).isoformat(timespec="seconds")
    bars = Bars(store)
    journal, new_lines, ev_lines = [], [], []
    cards: dict[str, tuple[dict, str]] = {}                                # key -> (card, as of) made tonight
    touched: set[str] = set()                                              # plans whose page changes tonight

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
        tracks = [cp.new_track("sweep", c["side"])] if v.get("sweep") else []
        if c.get("src") == "Darvas" and upto is not None and len(upto):   # starter on a follow-through close
            tracks.append(cp.confirm_track(c["side"], _bar(upto.iloc[-1])))
        state[c["key"]] = dict(call=c, versions=[v], tracks=tracks, through=c["date"])
        cards[c["key"]] = (card, c["date"])
        touched.add(c["key"])
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
        if cal.get("results"):                                             # tonight's results date
            nr = results_cal.next_results(cal, p["call"]["sym"], date.fromisoformat(p["through"]))
            for t in p["tracks"]:
                t["next_results"] = nr.isoformat() if nr else None
        for _, row in new.iterrows():
            b = _bar(row)
            ix = idx.summary(p["through"])                                 # NIFTY as of the evening before b
            for i, t in enumerate(p["tracks"]):
                if t["state"] not in cp.OPEN_STATES:
                    continue
                n0 = len(t["events"])
                if t["state"] == "trigger_pending" and t["kind"] in cp.SWEEP_KINDS \
                        and week_entries(state, t["side"], b["date"]) >= MAX_ENTRIES_PER_WEEK:
                    p["tracks"][i] = t = dict(t, state="skipped", events=t["events"] + [dict(
                        date=b["date"], what=f"week full: {MAX_ENTRIES_PER_WEEK} entries this week (one market swing, one bet)")])
                else:
                    p["tracks"][i] = t = cp.step(t, _version_for(p, b["date"]), b)
                if t["state"] == "triggered" and "index_at_entry" not in t:
                    t["index_at_entry"] = ix
                for e in t["events"][n0:]:
                    journal.append(dict(at=stamp, key=key, kind=t["kind"], what="event", event=e))
                    ev_lines.append(cp.event_line(p["call"]["sym"], p["call"]["side"], t["kind"], e,
                                                  p["call"].get("src", "F&O")))
                if t["state"] not in cp.OPEN_STATES and not any(x["kind"] == "re-sweep" for x in p["tracks"]):
                    r = cp.re_sweep(t)                     # one more try at the same level; the loop
                    if r is not None:                      # steps it on this same bar (the stop-out bar
                        p["tracks"].append(r)              # is its sweep)
                        journal.append(dict(at=stamp, key=key, kind="re-sweep", what="event",
                                            event=dict(date=b["date"], what="re-armed: one more sweep of the same level")))
            why = idx.guard(ix, b["date"])                                 # NIFTY closed through its last D low/high
            for i, t in enumerate(p["tracks"]):
                if t["state"] in ("waiting", "swept", "trigger_pending") and why.get(t["side"]):
                    p["tracks"][i] = t = dict(t, state="cancelled", events=t["events"] + [dict(date=b["date"], what=why[t["side"]])])
                    journal.append(dict(at=stamp, key=key, kind=t["kind"], what="event", event=t["events"][-1]))
                    ev_lines.append(cp.event_line(p["call"]["sym"], p["call"]["side"], t["kind"], t["events"][-1],
                                                  p["call"].get("src", "F&O")))
            p["through"] = b["date"]
            touched.add(key)
        if p["through"] == last and any(t["state"] == "waiting" for t in p["tracks"]) \
                and p["versions"][-1]["as_of"] < last:
            card, upto = bars.card(p["call"]["sym"], last)
            if upto is not None:
                v = cp.make_plan(card, upto, p["call"]["side"])
                v["as_of"] = last
                p["versions"].append(v)
                cards[key] = (card, last)
                journal.append(dict(at=stamp, key=key, what="replan", version=v))

    with journal_p.open("a", encoding="utf-8") as f:                       # journal first, then state
        for j in journal:
            f.write(json.dumps(j, default=str) + "\n")
    state_p.write_text(json.dumps(state, indent=1, default=str), encoding="utf-8")
    if not pages:                                                          # replays: pages on the last night only
        return new_lines, ev_lines
    for key in sorted(touched):                                            # pages last: a failure here
        p = state[key]                                                     # never loses the journal
        try:
            card, as_of = cards.get(key) or (None, None)
            if card is None and any(t["state"] in cp.OPEN_STATES for t in p["tracks"]):
                card, as_of = bars.card(p["call"]["sym"], last)[0], last   # open trades: tonight's map
            write_page(root, key, p, bars, last, card, as_of)
        except Exception:                                                  # noqa: BLE001
            traceback.print_exc()
    # closed plans keep their chart running for PAGE_DAYS after the call, so the page shows what
    # price did after the exit (GLAND: the deeper sweep came after the stop)
    since = (date.fromisoformat(last) - timedelta(days=PAGE_DAYS)).isoformat()
    for key, p in state.items():
        if key not in touched and p["call"]["date"] >= since:
            try:
                write_page(root, key, p, bars, last)
            except Exception:                                              # noqa: BLE001
                traceback.print_exc()
    return new_lines, ev_lines


def write_all_pages(store: Store, root: Path = ROOT) -> int:
    """(Re)write every plan's page from its current state: tonight's card for open plans, the card
    of the plan's last version day for closed ones."""
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    bars, last = Bars(store), store.last_session().isoformat()
    for key, p in state.items():
        open_ = any(t["state"] in cp.OPEN_STATES for t in p["tracks"])
        day = p["through"] if open_ else p["versions"][-1]["as_of"]
        write_page(root, key, p, bars, last, bars.card(p["call"]["sym"], day)[0], day)
    return len(state)


SPAN = cp.EXPIRY + cp.MAX_HOLD   # sessions after the call over which plan and as-sent are paired


def _main(t: dict) -> bool:
    return t["kind"] in cp.SWEEP_KINDS


def pair(p: dict, a) -> dict:
    """One pick, plan vs as sent over the same span: the call's close to the close SPAN sessions
    later (or the last close, marked incomplete). Plan = the main (sweep) trades' % at their exit,
    or marked at the span's end close if still open, 0 with no entry; starters reported apart."""
    c = p["call"]
    sg = 1 if c["side"] == "CE" else -1
    after = a[a["date"] > c["date"]]
    complete = len(after) >= SPAN
    end = after.iloc[SPAN - 1] if complete else (after.iloc[-1] if len(after) else None)
    if end is None:
        return dict(complete=False, as_sent=0.0, plan=0.0, starter=None, entered=False)
    end_c, end_d = float(end["c"]), end["date"].date().isoformat()

    def pct(t):
        if t.get("entry") is None or t.get("entry_date", "9") > end_d:
            return None
        if t.get("exit") is not None and t.get("exit_date", "9") <= end_d:
            return t["pct"]
        return round(sg * (end_c / t["entry"] - 1) * 100, 2)
    mains = [x for x in (pct(t) for t in p["tracks"] if _main(t)) if x is not None]
    st = [x for x in (pct(t) for t in p["tracks"] if t["kind"] == "confirm") if x is not None]
    return dict(complete=complete, as_sent=round(sg * (end_c / c["spot"] - 1) * 100, 2),
                plan=round(sum(mains), 2), starter=(round(sum(st), 2) if st else None), entered=bool(mains))


def _later_target(t: dict, a, side: str, sessions: int = cp.MAX_HOLD) -> Optional[bool]:
    """A stopped trade: did price reach its target within `sessions` after the stop (the stop was
    too tight) or not (the stop did its job)? None for anything else."""
    if t.get("state") != "stopped" or t.get("target") is None:
        return None
    after = a[a["date"] > t["exit_date"]].head(sessions)
    if after.empty:
        return None
    return bool(after["h"].max() >= t["target"]) if side == "CE" else bool(after["l"].min() <= t["target"])


def report(store: Store, root: Path = ROOT) -> str:
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    bars, rows, pairs = Bars(store), [], []
    for key, p in sorted(state.items()):
        c = p["call"]
        a = bars.adj(c["sym"])[0]
        lc = float(a["c"].iat[-1])
        pairs.append(dict(pair(p, a), src=c.get("src", "F&O")))
        for t in p["tracks"] or [dict(kind="-", state="no plan")]:
            m = cp.mark(t, lc) if t.get("state") == "triggered" else {}
            rows.append(dict(key=key, src=c.get("src", "F&O"), kind=t["kind"], state=t["state"],
                             closed=t.get("r") is not None, r=t.get("r", m.get("r")), pct=t.get("pct", m.get("pct")),
                             later_target=_later_target(t, a, c["side"]), side=t.get("side"),
                             index_d=(t.get("index_at_entry") or {}).get("D") or "?",
                             level=((t.get("kinds") or ["?"])[0].split(" ")[0] + " " + " ".join((t.get("kinds") or ["?"])[0].split(" ")[1:2])).strip()))
    lines = [f"{r['key']:32s} {r['kind']:9s} {r['state']:16s} R {r['r']!s:>6} plan% {r['pct']!s:>6}" for r in rows]
    for src in sorted({r["src"] for r in rows}):
        lines.append(f"\n== {src}")
        for name, kinds in (("main (sweep + re-sweep)", cp.SWEEP_KINDS), ("starter (confirm)", ("confirm",))):
            closed = [r for r in rows if r["src"] == src and r["kind"] in kinds and r["closed"]]
            open_ = [r for r in rows if r["src"] == src and r["kind"] in kinds and r["state"] == "triggered"]
            if not closed and not open_:
                continue
            ex = {k: sum(r["state"] == k for r in closed) for k in ("target", "stopped", "time")}
            lines.append(f"{name}: {len(closed)} closed, mean R {mean(r['r'] for r in closed):.2f} "
                         f"(target {ex['target']}, stopped {ex['stopped']}, time {ex['time']})" if closed
                         else f"{name}: 0 closed")
            if open_:
                lines.append(f"   {len(open_)} open, marked mean R {mean(r['r'] for r in open_):.2f}")
            lt = [r["later_target"] for r in closed if r["later_target"] is not None]
            if lt:
                lines.append(f"   stopped, then the target within {cp.MAX_HOLD} sessions: {sum(lt)} of {len(lt)} "
                             "(high = the stop is too tight)")
            if kinds == cp.SWEEP_KINDS and closed:
                for lv in sorted({r["level"] for r in closed}):
                    g = [r["r"] for r in closed if r["level"] == lv]
                    lines.append(f"   level {lv:18s} {len(g):3d} closed, mean R {mean(g):.2f}")
                for sd in ("CE", "PE"):
                    for st in sorted({r["index_d"] for r in closed if r["side"] == sd}):
                        g = [r["r"] for r in closed if r["side"] == sd and r["index_d"] == st]
                        lines.append(f"   {sd} with NIFTY D {st:5s} at entry {len(g):3d} closed, mean R {mean(g):.2f}")
            gone = [r for r in rows if r["src"] == src and r["kind"] in kinds and r["state"] in ("cancelled", "skipped")]
            if gone and kinds == cp.SWEEP_KINDS:
                lines.append(f"   not entered: {sum(r['state'] == 'cancelled' for r in gone)} cancelled by the NIFTY guard, "
                             f"{sum(r['state'] == 'skipped' for r in gone)} skipped (R:R, week full, results, gap)")
        for done, label in ((True, f"complete {SPAN}-session span"), (False, "span not complete yet")):
            g = [x for x in pairs if x["src"] == src and x["complete"] == done]
            if g:
                lines.append(f"paired, every pick ({label}): {len(g)} picks, {sum(x['entered'] for x in g)} entered; "
                             f"plan mean {mean(x['plan'] for x in g):.2f}% vs as sent {mean(x['as_sent'] for x in g):.2f}%; "
                             f"plan beat as-sent on {sum(x['plan'] > x['as_sent'] for x in g)}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", type=Path, default=None)
    ap.add_argument("--start", default=None, help="plan calls from this date on (default: the store's last session)")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--pages", action="store_true", help="(re)write every plan's page snapshot and exit")
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
    if a.pages:
        print(f"{write_all_pages(store, a.root)} pages written to {a.root / 'pages'}")
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
            n, e = run(store, start, a.root, a.calls, last=d, darvas_path=a.darvas, results_path=None,
                       pages=(d == days[-1]))
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
