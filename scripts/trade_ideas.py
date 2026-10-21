"""
QuantOS -- trade-idea log (core/ideas/log.py does the scoring)

Every trade idea gets written down with its levels before the outcome is
known, then scored daily against the market, including the ones passed on.

  add      python scripts/trade_ideas.py add --json '{"symbol": "NESTLEIND", "view": "bear",
             "action": "enter_if", "trigger": {"kind": "close_below", "level": 1238},
             "structure": {"kind": "bear_put", "expiry": "2026-11-23", "long_strike": 1250,
             "short_strike": 1200, "lot": 500}, "spot": 1236.6, "debit": 20.4, "note": "..."}'
  take     python scripts/trade_ideas.py take <id> --debit 20.5 [--lots 1] [--account icici-spouse]
  close    python scripts/trade_ideas.py close <id> --value 31.0
  list     python scripts/trade_ideas.py list
  evaluate python scripts/trade_ideas.py evaluate [--no-telegram]
           quotes every open idea's legs (one mark per day), re-scores all
           ideas from Fyers daily history, Telegrams any status change.
           Runs from quantos-trade-ideas.timer at 15:25 IST, while the
           option quotes are still live.

File: ~/.quantos/trade_ideas.json. Places NO orders.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ideas.log import (IST, IdeaError, evaluate, make_idea, option_symbol,  # noqa: E402
                            scoreboard)


def ideas_path() -> Path:
    override = os.getenv("QUANTOS_HOME_DIR")
    return (Path(override) if override else Path.home() / ".quantos") / "trade_ideas.json"


def load(path: Optional[Path] = None) -> list[dict]:
    try:
        return json.loads((path or ideas_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save(ideas: list[dict], path: Optional[Path] = None) -> None:
    path = path or ideas_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(ideas, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)


def _find(ideas: list[dict], idea_id: str) -> dict:
    hits = [i for i in ideas if i["id"] == idea_id] or [i for i in ideas if i["id"].startswith(idea_id)]
    if len(hits) != 1:
        raise SystemExit(f"no unique idea matches {idea_id!r}")
    return hits[0]


def add(raw: dict, path: Optional[Path] = None) -> dict:
    ideas = load(path)
    idea = make_idea(raw)
    if any(i["id"] == idea["id"] for i in ideas):
        n = sum(i["id"].startswith(idea["id"]) for i in ideas) + 1
        idea["id"] = f"{idea['id']}-{n}"
    ideas.append(idea)
    save(ideas, path)
    return idea


def _broker():
    from agent.main import load_config
    from core.brokers import get_broker
    b = get_broker(load_config("agent/config.yaml"))
    if not b.connect():
        raise SystemExit("Fyers connect failed -- check the token")
    return b._client


def _closes(client, symbol: str, since: str) -> list[tuple[str, float]]:
    start = date.fromisoformat(since)
    r = client.history({"symbol": f"NSE:{symbol}-EQ", "resolution": "D", "date_format": "1",
                        "range_from": str(start), "range_to": str(datetime.now(IST).date()), "cont_flag": "1"})
    # Fyers daily candles are stamped at 00:00 IST; read them in IST, not the VM's UTC.
    return [(datetime.fromtimestamp(c[0], IST).date().isoformat(), float(c[4])) for c in r.get("candles", [])]


def _mark(client, idea: dict, today: str) -> Optional[dict]:
    s = idea["structure"]
    right = "CE" if s["kind"].endswith("call") else "PE"
    legs = [option_symbol(idea["symbol"], s["expiry"], float(s["long_strike"]), right),
            option_symbol(idea["symbol"], s["expiry"], float(s["short_strike"]), right),
            f"NSE:{idea['symbol']}-EQ"]
    q = {x["n"]: x["v"] for x in client.quotes({"symbols": ",".join(legs)}).get("d", [])}
    lg, sh, eq = (q.get(n) or {} for n in legs)
    if not lg.get("ask") or not sh.get("bid"):
        return None
    return {"date": today, "at": datetime.now(IST).isoformat(timespec="seconds"), "spot": eq.get("lp"),
            "long_bid": lg.get("bid"), "long_ask": lg.get("ask"),
            "short_bid": sh.get("bid"), "short_ask": sh.get("ask")}


def _line(idea: dict, ev: dict) -> str:
    s = idea.get("structure")
    legs = f" {s['kind'].replace('_', ' ')} {s['long_strike']:g}/{s['short_strike']:g}" if s else ""
    pnl = f" | paper P&L ₹{ev['pnl']:+,.0f}" if ev.get("pnl") is not None else ""
    move = f" | spot {ev['spot_move_pct']:+.1f}% since idea" if ev.get("spot_move_pct") is not None else ""
    return f"{idea['symbol']}{legs} [{idea['action']}] -> {ev['status']}{move}{pnl}"


def run_evaluate(telegram: bool = True, path: Optional[Path] = None) -> list[str]:
    ideas = load(path)
    if not ideas:
        return []
    client = _broker()
    now = datetime.now(IST)
    today = now.date().isoformat()
    market_hours = now.weekday() < 5 and (9, 15) <= (now.hour, now.minute) <= (15, 30)
    changes = []
    history: dict[str, list] = {}
    for idea in ideas:
        if idea.get("closed"):
            continue
        s = idea.get("structure")
        prev = (idea.get("eval") or {}).get("status")
        if s and market_hours and date.fromisoformat(s["expiry"]) >= now.date():
            try:
                m = _mark(client, idea, today)
                if m:
                    idea["marks"] = [x for x in idea.get("marks", []) if x["date"] != today] + [m]
            except Exception as e:                       # a missing contract must not stop the run
                print(f"quote failed for {idea['id']}: {e}")
            time.sleep(0.3)
        sym = idea["symbol"]
        if sym not in history:
            first = min(i["created_at"][:10] for i in ideas if i["symbol"] == sym)
            history[sym] = _closes(client, sym, first)
            time.sleep(1)                               # Fyers rate-limits bursts
        closes = history[sym]
        # During market hours today's candle is still forming: score on the live price.
        ev = evaluate(idea, closes)
        idea["eval"] = ev
        idea["evaluated_at"] = now.isoformat(timespec="seconds")
        if ev["status"] != prev:
            changes.append(_line(idea, ev))
    save(ideas, path)
    if changes and telegram:
        from cloud.api.notifier import send_telegram
        text = "📒 Trade-idea log\n" + "\n".join(changes)
        try:
            asyncio.run(send_telegram(text))
        except Exception as e:
            print(f"telegram failed: {e}")
    return changes


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("--json", required=True)
    t = sub.add_parser("take"); t.add_argument("id"); t.add_argument("--debit", type=float, required=True)
    t.add_argument("--lots", type=int, default=1); t.add_argument("--account", default="icici-spouse")
    c = sub.add_parser("close"); c.add_argument("id"); c.add_argument("--value", type=float, required=True)
    sub.add_parser("list")
    e = sub.add_parser("evaluate"); e.add_argument("--no-telegram", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "add":
        try:
            idea = add(json.loads(args.json))
        except (IdeaError, ValueError, KeyError) as e:
            print(f"ERROR: {e}")
            return 1
        print(f"logged {idea['id']}")
    elif args.cmd in ("take", "close"):
        ideas = load()
        idea = _find(ideas, args.id)
        stamp = datetime.now(IST).isoformat(timespec="seconds")
        if args.cmd == "take":
            idea["taken"] = {"at": stamp, "debit": args.debit, "lots": args.lots, "account": args.account}
        else:
            if not idea.get("taken"):
                raise SystemExit("record `take` first")
            lot = float((idea.get("structure") or {}).get("lot") or 1)
            pnl = (args.value - idea["taken"]["debit"]) * lot * idea["taken"]["lots"]
            idea["closed"] = {"at": stamp, "value": args.value, "pnl": round(pnl, 0)}
        save(ideas)
        print(f"{args.cmd} recorded for {idea['id']}")
    elif args.cmd == "list":
        ideas = load()
        for i in ideas:
            ev = i.get("eval") or {"status": "not evaluated yet"}
            print(f"{i['id']:<48} {_line(i, ev)}")
        print(json.dumps(scoreboard([(i, i.get("eval") or {}) for i in ideas])))
    else:
        for line in run_evaluate(telegram=not args.no_telegram):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
