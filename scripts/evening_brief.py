"""The evening brief (docs/EXECUTION_PLAN_2026-11-19.md, E6), every weekday at 20:15 IST after the
call plans (20:00 IST). Code-only: no model, no orders, no broker login.

  1. Index: NIFTY and BANKNIFTY v3 cards (W and D structure, protected / weak levels, nearest strong zones).
  2. Breadth: W and D structure state over the top-500 universe and the day's D (and closed-week W)
     sweeps. Structure only, so it takes minutes (the full playbook scan takes 80).
  3. Candidates: tonight's F&O screener and Darvas calls from the call plans' state, each with its
     card, the Darvas plan (stop, target) where there is one and the call-day map plan.
  4. Vetoes flagged by code (core/ops/evening_brief.py, V1-V4). Markers, never orders.

Writes ~/.quantos/brief/brief_<session>.json and brief_latest.json (GET /reports/brief, #/brief) and
Telegrams the text. The user, or Claude in a Claude Code session, turns it into ledger calls
(scripts/ledger.py add, docs/TRADE_REASONING.md).

    .venv/bin/python scripts/evening_brief.py [--no-telegram] [--top 500] [--store DIR]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import traceback
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ideas import events as results_cal  # noqa: E402
from core.market_map import card as cd  # noqa: E402
from core.market_map import structure  # noqa: E402
from core.market_map.index_bars import IndexBars  # noqa: E402
from core.market_map.l1_store import Store, default_root  # noqa: E402
from core.ops import evening_brief as eb  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
QUANTOS = Path.home() / ".quantos"
OUT = QUANTOS / "brief"
CALL_PLANS = QUANTOS / "call_plans" / "state.json"
DARVAS = QUANTOS / "darvas_atr_stop_plan.json"


def next_weekday(d: date) -> date:
    from scripts.call_plans import next_weekday as nw
    return nw(d)


def index_cards(as_of: date, ib: IndexBars | None = None) -> dict:
    ib = ib or IndexBars()
    out = {}
    for sym in ("NIFTY", "BANKNIFTY"):
        try:
            df = ib.load(sym)
            rd = structure.l1_read(df, as_of)
            rd["last_date"] = df[df["date"] < pd.Timestamp(as_of)]["date"].iat[-1].date().isoformat()
            out[sym] = cd.card(sym, rd, df)
        except Exception as e:                                             # noqa: BLE001
            out[sym] = dict(sym=sym, error=f"{type(e).__name__}: {str(e)[:120]}")
    return out


def breadth_rows(st: Store, last: date, as_of: date, top: int) -> list[dict]:
    rows = []
    for u in st.universe(last)[:top]:
        sym = u["sym"]
        try:
            a, _ = st.adjusted(sym)
            seg = structure.latest_segment(a)
            sm = {}
            for tf in ("W", "D"):
                bars = structure.completed(seg, tf, as_of)
                sm[tf] = structure.summary(bars, structure.run(bars, structure.TF_K[tf]), tf) if len(bars) else {}
            rows.append(eb.breadth_row(sym, sm, last.isoformat()))
        except Exception as e:                                             # noqa: BLE001
            rows.append(dict(sym=sym, error=f"{type(e).__name__}: {str(e)[:80]}"))
    return rows


def tonight_calls(last: str, state_path: Path = CALL_PLANS, darvas_path: Path = DARVAS) -> tuple[list[dict], list[str]]:
    """Tonight's calls from the call plans' state, with the Darvas plan's stop and target joined in."""
    warn = []
    if not state_path.exists():
        return [], ["call plans state missing: no candidates"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state and max(p.get("through", "") for p in state.values()) < last:
        warn.append(f"call plans have not walked {last} yet (the 20:00 IST job may not have run)")
    dv = {}
    try:
        plan = json.loads(darvas_path.read_text(encoding="utf-8"))
        if (plan.get("bars_as_of") or plan.get("through")) == last:
            dv = {e["symbol"]: e for e in plan.get("entries") or []}
    except (OSError, ValueError):
        pass
    out = []
    for key, p in sorted(state.items()):
        c = p["call"]
        if c["date"] != last:
            continue
        d = dv.get(c["sym"]) if c.get("src") == "Darvas" else None
        out.append(dict(key=key, sym=c["sym"], side=c["side"], spot=c["spot"], src=c.get("src", "F&O"),
                        stop=(d or {}).get("initial_stop"), target=(d or {}).get("target"),
                        version=(p.get("versions") or [{}])[0]))
    return out, warn


def candidate(c: dict, st: Store, as_of: date, last: date, cal: dict) -> dict:
    from core.market_map.m5_store import M5Store
    out = {k: c[k] for k in ("key", "sym", "side", "spot", "src")}
    try:
        a, _ = st.adjusted(c["sym"])
        m5 = M5Store(st.root).adjusted(c["sym"], a, st.actions().get(c["sym"], [])) if len(a) else []
        rd = structure.l1_read(a, as_of, m5 if len(m5) else None)
        rd["last_date"] = last.isoformat()
        card = cd.card(c["sym"], rd, a)
    except Exception as e:                                                 # noqa: BLE001
        return dict(out, error=f"no map read: {type(e).__name__}: {str(e)[:100]}")
    nr = results_cal.next_results(cal, c["sym"], last) if cal.get("results") else None
    n_res = results_cal.trading_days_until(last, nr) if nr else None
    zones = (rd.get("htf") or {}).get("zones") or []
    tr = eb.trades(c, c.get("version") or {})
    for t in tr:
        t["vetoes"] = eb.vetoes(t, c["side"], card, zones, n_res)
    mp = (c.get("version") or {}).get("sweep")
    return dict(out, card=card, trades=tr, results=nr.isoformat() if nr else None, results_in=n_res,
                map_plan=dict(level=mp["level"], kinds=mp.get("kinds"), target=(mp.get("target") or {}).get("level"))
                if mp else None)


def build(st: Store, top: int, now: datetime, state_path: Path = CALL_PLANS, darvas_path: Path = DARVAS,
          results_path: Path | None = results_cal.DEFAULT_PATH, ib: IndexBars | None = None) -> dict:
    last = st.last_session()
    as_of = next_weekday(last)
    warn = []
    if now.weekday() < 5 and last < now.date() and now.hour >= 20:
        warn.append(f"L1 store's last session is {last}: tonight's refresh may not have run")
    t0 = time.time()
    rows = breadth_rows(st, last, as_of, top)
    calls, w = tonight_calls(last.isoformat(), state_path, darvas_path)
    warn += w
    cal = {}
    if results_path is not None:
        cal = results_cal.refresh(results_path)
        if cal.get("error"):
            warn.append(f"results calendar: {cal['error']}")
    return dict(session=last.isoformat(), made_at=now.isoformat(timespec="seconds"),
                index=index_cards(as_of, ib), breadth=eb.breadth(rows),
                candidates=[candidate(c, st, as_of, last, cal) for c in calls],
                warnings=warn, seconds=round(time.time() - t0), status="map v3 UNTESTED: markers, never signals")


def save(b: dict, root: Path = OUT) -> None:
    root.mkdir(parents=True, exist_ok=True)
    s = json.dumps(b, default=str)
    for name in (f"brief_{b['session']}.json", "brief_latest.json"):
        tmp = root / (name + ".tmp")
        tmp.write_text(s, encoding="utf-8")
        tmp.replace(root / name)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--top", type=int, default=500)
    ap.add_argument("--store", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    st = Store(a.store or default_root())
    b = build(st, a.top, datetime.now(IST))
    save(b, a.out)
    msg = eb.text(b)
    print(msg)
    if not a.no_telegram:
        try:
            from cloud.api.notifier import send_telegram
            for k in range(0, len(msg), 3800):
                asyncio.run(send_telegram(msg[k:k + 3800]))
        except Exception:                                                  # noqa: BLE001
            traceback.print_exc()
    return 0


if __name__ == "__main__":
    sys.exit(main())
