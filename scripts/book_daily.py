"""The daily book routine (docs/TRADE_REASONING.md): after the L1 refresh, every weekday.

  1. NIFTY/BANKNIFTY daily bars from NSE's index file (no broker login).
  2. Every open book walked forward: fills, cancels, exits, R (core/market_map/book.py), and
     scored against its baseline (the day's playbook setups taken mechanically).
  3. Reads: the index and every stock in an open book (the L1 map).
  4. Book day (the run after a Friday close, or --book-day): the top-500 scan and triage.
  5. The judgment (core/market_map/book_judge.py): index read, cancels of unfilled positions,
     index guards, and on a book day a new book. Code validates every decision.
  6. Save the books and a journal entry; Telegram the summary.

Paper only: places NO orders and touches no live job. No Fyers token needed (NSE files + the
L1 store). Needs ANTHROPIC_API_KEY for step 5 (skip with --no-model) and the Telegram env for 6.

    .venv/bin/python scripts/book_daily.py [--book-day] [--no-model] [--no-telegram]
        [--store DIR] [--books DIR] [--index DIR] [--as-of YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.market_map import book as bk  # noqa: E402
from core.market_map import book_judge as bj  # noqa: E402
from core.market_map import read as mr  # noqa: E402
from core.market_map import structure  # noqa: E402
from core.market_map.index_bars import INDICES, IndexBars  # noqa: E402
from core.market_map.l1_store import Store  # noqa: E402
from core.market_map.triage import latest_lots, pairs, triage  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
BOOKS = Path.home() / ".quantos" / "books"
VALID = 10


def next_weekday(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def load_books(root: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.glob("book_*.json"))]


def save_book(root: Path, b: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"book_{b['id']}.json").write_text(json.dumps(b, indent=1, default=str), encoding="utf-8")


def setup_rows(scan_rows: list[dict], tri: list[dict]) -> tuple[list[dict], dict]:
    """The setups the model may pick from (actionable only) and the full plan behind each id."""
    by_sym = {r["sym"]: r for r in scan_rows if "error" not in r}
    paired = set(pairs(scan_rows))
    shown, plans = [], {}
    for t in tri:
        if not t["actionable"]:
            continue
        r = by_sym[t["sym"]]
        sid = f"{t['sym']}:{t['track']}"
        plan = r[t["track"]]
        plans[sid] = dict(setup=plan, opp=r.get("opp") or [])
        shown.append(dict(id=sid, side=t["side"], setup=plan.get("setup"), band=t["band"], entry=t["entry"],
                          stop=t["stop"], target=t["target"], rr=t["rr"], price=t["price"], dist_atr=t["dist_atr"],
                          gap_pct=t["gap_pct"], risk_pct=t["risk_pct"], lot=t["lot"], lot_risk=t["lot_risk"],
                          half_risk=t["half_risk"], M=r.get("M"), W=r.get("W"), D=r.get("D"),
                          swept=plan.get("swept"), shift=plan.get("shift"), paired=t["sym"] in paired))
    return shown, plans


def fmt_pos(r: dict) -> str:
    s = r["status"]
    if s == "open":
        tail = f"open {r['res'].get('r'):+.2f}R"
    elif s == "closed":
        tail = f"closed {r['res'].get('r'):+.2f}R ({r['res'].get('reason')})"
    elif s == "pending":
        tail = f"resting {r['setup']['entry']:g}"
    else:
        tail = f"{s}: {r.get('reason')}"
    return f"{r['id']} {r['side']} - {tail}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", type=Path, default=None)
    ap.add_argument("--books", type=Path, default=BOOKS)
    ap.add_argument("--index", type=Path, default=None)
    ap.add_argument("--as-of", type=date.fromisoformat, default=None,
                    help="the session the reads are for (default: the one after the store's last session)")
    ap.add_argument("--book-day", action="store_true")
    ap.add_argument("--no-model", action="store_true")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--top", type=int, default=500)
    a = ap.parse_args(argv)

    store = Store(a.store)
    last = store.last_session()
    if last is None:
        print(f"ERROR: no L1 store at {store.root}")
        return 2
    as_of = a.as_of or next_weekday(last)
    run_ist = datetime.now(IST).isoformat(timespec="seconds")
    msgs = [f"QuantOS book routine, bars through {last} (reads for {as_of}). Paper only."]

    # 1. index bars
    ib = IndexBars(a.index)
    il = ib.last_session()
    got = ib.refresh((il + timedelta(days=1)) if il else last - timedelta(days=30), last, pause=0.2)
    idx = {s: ib.load(s) for s in INDICES.values()}
    closes = {s: (float(df["c"].iat[-1]) if len(df) else None) for s, df in idx.items()}
    if any(len(df) and df["date"].iat[-1].date() < last for df in idx.values()):
        msgs.append(f"WARNING: index bars end before {last} (NSE file late?); guards use what is there.")

    # 2. walk the books
    cache = {}

    def daily_for(sym):
        if sym not in cache:
            cache[sym] = store.adjusted(sym)[0]
        return cache[sym]

    books = [b for b in load_books(a.books) if not b.get("closed")]
    walked = {}
    for b in books:
        rows = bk.advance(b, daily_for, lambda s: idx.get(s))
        walked[b["id"]] = (rows, bk.score_book(b, rows, daily_for))

    # 3. reads
    index_reads = {s: bj.brief_read(structure.l1_read(df, as_of)) if len(df) > 300 else {"error": "too few bars"}
                   for s, df in idx.items()}
    syms = sorted({p["sym"] for b in books for p in b["positions"]})
    reads = {s: bj.brief_read(mr.l1_for(s, as_of, store)) for s in syms}

    # 4. book day: scan + triage
    book_day = a.book_day or as_of.weekday() == 0
    shown, plans, scan_summary = [], {}, None
    if book_day:
        from scripts.playbook_scan import scan
        lots, lots_day = latest_lots(last)
        scan_rows = scan(store, as_of, a.top)
        tri = triage(scan_rows, lots)
        shown, plans = setup_rows(scan_rows, tri)
        scan_summary = dict(reads=len(scan_rows), setups=len(tri), actionable=len(shown), lots_from=lots_day,
                            w_down=sum(r.get("W") == "down" for r in scan_rows),
                            w_up=sum(r.get("W") == "up" for r in scan_rows))
        shown = sorted(shown, key=lambda s: (s["dist_atr"], -(s["rr"] or 0)))

    # 5. judgment
    views = [bj.book_view(b, *walked[b["id"]], {s: reads.get(s) for s in syms}) for b in books]
    for v in views:
        v["positions"] = [dict(p, now=(p["now"] or {}).get("tf") and dict(price=p["now"]["price"],
                                                                         M=p["now"]["tf"]["M"]["state"],
                                                                         W=p["now"]["tf"]["W"]["state"],
                                                                         D=p["now"]["tf"]["D"]["state"],
                                                                         W_protected=p["now"]["tf"]["W"]["protected"]))
                          for p in v["positions"]]
    ctx = bj.build_context(as_of.isoformat(), index_reads, views, shown, book_day)
    if scan_summary:
        ctx["scan"] = scan_summary
    journal = dict(run_ist=run_ist, bars_through=last.isoformat(), as_of=as_of.isoformat(), book_day=book_day,
                   index_refresh=got, scan=scan_summary, n_setups_shown=len(ctx["setups"]))
    decided, errors, text = None, [], None
    if not a.no_model:
        try:
            import anthropic
            text, searches = bj.call_claude(anthropic.Anthropic(timeout=600.0), ctx)
            journal["searches"] = searches
            decided, errors = bj.validate(bj.parse_answer(text), ctx, closes)
        except Exception as e:
            errors = [f"model step failed: {e}"]
            traceback.print_exc()
    journal.update(answer=text, decided=decided, rejected=errors)

    # apply
    if decided:
        by_id = {b["id"]: b for b in books}
        for c in decided["cancels"]:
            by_id[c["book"]].setdefault("cancels", []).append(dict(id=c["id"], date=last.isoformat(), why=c["why"]))
        for g in decided["guards"]:
            b = by_id[g["book"]]
            g = {k: v for k, v in g.items() if k != "book"}
            b.setdefault("rules", {}).setdefault("guards", []).append(dict(g, since=as_of.isoformat()))
        nb = decided.get("new_book")
        if nb:
            new = dict(id=as_of.isoformat(), made=run_ist, first_session=as_of.isoformat(), by="book_judge",
                       why=nb["why"], passed_on=nb["passed_on"], index_read=decided["index_read"],
                       positions=[dict(id=p["id"], sym=p["id"].split(":")[0], track=p["id"].split(":")[1],
                                       setup=plans[p["id"]]["setup"], opp=plans[p["id"]]["opp"],
                                       group=p["group"], priority=p["priority"]) for p in nb["positions"]],
                       rules=dict(max_fills=nb["max_fills"],
                                  guards=[dict(g, since=as_of.isoformat()) for g in nb["guards"]]),
                       cancels=[], baseline=[dict(id=k, **v) for k, v in plans.items()])
            if (a.books / f"book_{new['id']}.json").exists():
                errors.append(f"new_book: a book {new['id']} already exists; not overwritten")
            else:
                books.append(new)
                walked[new["id"]] = (bk.advance(new, daily_for, lambda s: idx.get(s)), None)

    # re-walk, close resolved books, save
    for b in books:
        rows = bk.advance(b, daily_for, lambda s: idx.get(s))
        sc = bk.score_book(b, rows, daily_for)
        b["state"] = dict(as_of=last.isoformat(), positions=[dict(id=r["id"], status=r["status"], reason=r.get("reason"),
                                                                   fill=r["fill"], end=r.get("end"),
                                                                   r=r["res"].get("r")) for r in rows], score=sc)
        if sc["resolved"] and b["id"] != as_of.isoformat():
            b["closed"] = last.isoformat()
        save_book(a.books, b)
        walked[b["id"]] = (rows, sc)
    jdir = a.books / "journal"
    jdir.mkdir(parents=True, exist_ok=True)
    (jdir / f"{last.isoformat()}.json").write_text(json.dumps(dict(journal, rejected=errors), indent=1, default=str),
                                                    encoding="utf-8")

    # 6. summary
    if decided and decided["index_read"]:
        msgs.append(f"Index: {decided['index_read']}")
    for b in books:
        rows, sc = walked[b["id"]]
        head = f"\nBook {b['id']}" + (" (NEW)" if b["id"] == as_of.isoformat() else "") + (" CLOSED" if b.get("closed") else "")
        if sc:
            head += (f": book {sc['book']['net_r']:+.2f}R over {sc['book']['n']}, baseline "
                     f"{sc['baseline']['net_r_per_position'] if sc['baseline']['n'] else 'n/a'}R/position")
        msgs.append(head)
        msgs += ["  " + fmt_pos(r) for r in rows]
    if decided:
        msgs += [f"Cancelled {c['book']}/{c['id']}: {c['why']}" for c in decided["cancels"]]
        msgs += [f"Guard {g['book']}: {g['index']} {'below' if 'below' in g else 'above'} "
                 f"{g.get('below', g.get('above')):g} cancels unfilled {g['cancels']}s ({g['why']})" for g in decided["guards"]]
        if decided.get("new_book"):
            msgs.append(f"New book why: {decided['new_book']['why']}")
            if decided["new_book"]["passed_on"]:
                msgs.append(f"Passed on: {decided['new_book']['passed_on']}")
    if errors:
        msgs.append("Rejected: " + "; ".join(errors[:6]))
    out = "\n".join(msgs)
    print(out)
    if not a.no_telegram:
        try:
            from cloud.api.notifier import send_telegram
            for k in range(0, len(out), 3800):
                asyncio.run(send_telegram(out[k:k + 3800]))
        except Exception as e:
            print(f"telegram failed: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
