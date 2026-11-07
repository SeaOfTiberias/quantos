#!/usr/bin/env python3
"""
Daily L1 data refresh on the VM, after the close (sprint plan S5, slice 1; design §7).
Data only: no orders, no alerts, no change to any live job.

  1. NSE's symbol-change file -> move rows of renamed symbols.
  2. Every weekday after the store's last session, up to today: the CM bhavcopy, appended.
     A 404 is a holiday or not yet published; a later run picks a late file up.
  3. The PR bundle for the same days -> new splits and bonuses (corporate actions).
  4. The top-500 list for the next session (universe.json).
  5. A report (reports/<session>.json): new actions, renames, and every unexplained drop
     of 35% or more in the last 10 sessions among the top 500 (each starts a new segment
     until an action explains it).
  6. On Fridays (or with --fyers-check): Fyers' adjusted daily closes against the store's,
     over the last year, for the top 500. A missed or wrong split shows as a step in the
     ratio between the two.

Usage (VM):
  .venv/bin/python scripts/run_l1_refresh.py
  .venv/bin/python scripts/run_l1_refresh.py --pr-since 2026-06-01   # first run: fill the action gap
  .venv/bin/python scripts/run_l1_refresh.py --fyers-check
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.market_map import nse_daily as nd  # noqa: E402
from core.market_map.l1_store import Store  # noqa: E402
from core.techno_funda.symbols import SymbolChain  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
GAP_LOOKBACK = 10
CHECK_DAYS, CHECK_TOL = 365, 0.02


def weekdays_after(last: date, today: date) -> list[date]:
    out, d = [], last + timedelta(days=1)
    while d <= today:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def ratio_check(ours: pd.DataFrame, theirs: list[tuple[date, float]], tol: float = CHECK_TOL):
    """Fyers close / store close over the common dates. Both are split-adjusted, so the
    ratio should be flat. Returns None if it is (spread within `tol`), else the spread and
    the date of the largest one-day step in the ratio."""
    t = pd.DataFrame(theirs, columns=["date", "fc"])
    t["date"] = pd.to_datetime(t["date"])
    m = ours[["date", "c"]].merge(t, on="date")
    if len(m) < 20:
        return dict(status="too_few_dates", n=len(m))
    r = (m["fc"] / m["c"]).to_numpy()
    spread = float(r.max() / r.min() - 1)
    if spread <= tol:
        return None
    steps = np.abs(np.diff(np.log(r)))
    i = int(np.argmax(steps)) + 1
    return dict(status="mismatch", spread=round(spread, 4), n=len(m),
                step_date=m["date"].iat[i].date().isoformat(), step=round(float(np.exp(steps[i - 1]) - 1), 4))


def recent_gaps(store: Store, syms: list[str], acts: dict, since: pd.Timestamp) -> list[dict]:
    out = []
    for s in syms:
        _, gaps = store.adjusted(s, acts)
        out += [dict(sym=g["sym"], date=str(g["date"]), move=g["move"]) for g in gaps
                if pd.Timestamp(g["date"]) >= since]
    return out


def fyers_check(store: Store, syms: list[str], acts: dict, config_path: str) -> list[dict]:
    from agent.main import load_config
    from core.brokers import get_broker
    b = get_broker(load_config(config_path))
    if not b.connect():
        raise RuntimeError("Fyers connect() failed -- refresh the token")
    now = datetime.now(timezone.utc)
    out = []
    for s in syms:
        ours, _ = store.adjusted(s, acts)
        try:
            bars = b.get_historical_data(f"NSE:{s}-EQ", "1d", now - timedelta(days=CHECK_DAYS), now) or []
        except Exception as e:                       # one bad symbol mustn't stop the check
            out.append(dict(sym=s, status="error", error=str(e)[:120]))
            continue
        theirs = [(c.timestamp.astimezone(IST).date(), c.close) for c in bars]
        res = ratio_check(ours, theirs)
        if res:
            out.append(dict(sym=s, **res))
        time.sleep(0.12)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--today", type=date.fromisoformat, default=None)
    ap.add_argument("--pr-since", type=date.fromisoformat, default=None,
                    help="re-read PR bundles from this date (the first run fills the gap after 2026-06-24)")
    ap.add_argument("--fyers-check", action="store_true")
    ap.add_argument("--config", default="agent/config.yaml")
    a = ap.parse_args(argv)

    store = Store(a.root)
    today = a.today or datetime.now(IST).date()
    last = store.last_session()
    if last is None:
        print(f"ERROR: no store at {store.root} -- build it first (scripts/build_l1_store.py)")
        return 2

    # 1. renames
    sc = store.raw / "symbolchange.csv"
    try:
        body = nd.fetch(nd.SYMBOLCHANGE_URL)
        if body:
            sc.parent.mkdir(parents=True, exist_ok=True)
            sc.write_bytes(body)
    except Exception as e:
        print(f"symbolchange.csv not refreshed ({e}); using the last copy")
    chain = SymbolChain.load(sc) if sc.exists() else SymbolChain.load()
    renames = store.apply_renames(chain)

    # 2. prices
    added_days, missing = [], []
    for d in weekdays_after(last, today):
        day = nd.bhavcopy_day(store.raw, d, chain)
        if day is None:
            missing.append(d.isoformat())
            continue
        store.append_day(day, d)
        store.set_meta(last_session=d.isoformat())
        added_days.append(d.isoformat())
        print(f"{d}: {len(day)} rows appended", flush=True)
    last = store.last_session()

    # 3. corporate actions
    pr_from = a.pr_since or (date.fromisoformat(store.meta()["pr_through"]) + timedelta(days=1)
                             if store.meta().get("pr_through") else last)
    new_actions = []
    for d in [x for x in weekdays_after(pr_from - timedelta(days=1), today)]:
        got = nd.pr_day(store.raw, d, chain)
        if got is None:
            continue
        rows, etfs = got
        new_actions += store.add_actions(rows)
        store.add_etfs(etfs)
        store.set_meta(pr_through=d.isoformat())
    for x in new_actions:
        print(f"action: {x['sym']} ex {x['ex']} x{x['factor']:.4g} ({x['purpose']})")

    # 4. universe for the next session
    uni = store.universe(last)
    store.root.mkdir(parents=True, exist_ok=True)
    store.universe_path.write_text(json.dumps(dict(
        as_of=last.isoformat(), for_session="the session after as_of",
        rule="not on NSE's ETF list; EQ on as_of; median traded value of the last 60 sessions; top 500",
        n=len(uni), rows=uni), indent=0), encoding="utf-8")

    # 5. report
    acts = store.actions()
    syms = [u["sym"] for u in uni]
    since = pd.Timestamp(last) - pd.tseries.offsets.BDay(GAP_LOOKBACK)
    gaps = recent_gaps(store, syms, acts, since)
    report = dict(session=last.isoformat(), run_ist=datetime.now(IST).isoformat(timespec="seconds"),
                  days_added=added_days, days_without_file=missing, renames=renames,
                  new_actions=new_actions, universe_n=len(uni), unexplained_drops=gaps)

    # 6. Fyers cross-check
    if a.fyers_check or today.weekday() == 4:
        try:
            report["fyers_check"] = fyers_check(store, syms, acts, a.config)
        except Exception as e:
            report["fyers_check"] = [dict(status="not_run", error=str(e)[:200])]
    rp = store.root / "reports" / f"{last.isoformat()}.json"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")

    print(f"store: last session {last}, {len(added_days)} day(s) added, {len(new_actions)} new action(s), "
          f"{len(renames)} rename(s), universe {len(uni)}, unexplained drops {len(gaps)}")
    for g in gaps:
        print(f"  unexplained drop: {g['sym']} {g['date']} {g['move']:+.1%}")
    for c in report.get("fyers_check", []):
        print(f"  fyers check: {c}")
    print(f"report -> {rp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
