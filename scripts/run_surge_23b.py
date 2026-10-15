#!/usr/bin/env python3
"""
QuantOS — Candidate 23b: daily 15:15 paper log of L2W4 bull call spreads on surges
───────────────────────────────────────────────────────────────────────────────────
docs/SURGE_23B_METHODOLOGY.md, pre-registered before the first forward trade.
Fired once per weekday at 15:15 IST by quantos-surge-23b.timer.

Each run:
  1. Prices the exit of any open paper spread that is due (8 sessions held, or
     the last session before expiry) at the live bid/ask.
  2. Finds F&O stocks up >= 5% at 15:15 that are not at a fresh 52-week high,
     and paper-enters an L2W4 bull call spread at the live ask/bid.
  3. Logs one market-state row (NIFTY change, India VIX, F&O breadth, surges).

READ-ONLY: no order code. P&L is never printed before 60 closed trades
(check with scripts/check_surge_23b.py).

Usage:
    python scripts/run_surge_23b.py
    python scripts/run_surge_23b.py --dry-run     # fetch and print, write nothing
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers import get_broker  # noqa: E402
from core.brokers.fyers import _fyers_symbol  # noqa: E402
from core.fno_screener.bhavcopy import parse_fno_day  # noqa: E402
from core.fno_screener.screener import IST, bar_date  # noqa: E402
from core.marketdata.option_chain_recorder import parse_expiries  # noqa: E402
from core.options.vrp.bhavcopy import BhavcopyNotAvailable, fetch_raw  # noqa: E402
from core.surge.live import (  # noqa: E402
    SURGE_PCT, Leg, Position, append_jsonl, choose_expiry, exit_due, exit_value, in_cooldown,
    is_fresh_52w_high, load_positions, pick_legs, save_positions, store_dir,
)

REFERENCE_SYMBOL = "NIFTY 50"
BHAVCOPY_DIR = Path.home() / ".quantos" / "nse_fo_bhavcopy"
STRIKE_COUNT = 12
SPACING = 0.4


def _chain(client, symbol: str, epoch: str = "") -> dict:
    resp = client.optionchain(data={"symbol": _fyers_symbol(symbol), "strikecount": STRIKE_COUNT,
                                    "timestamp": epoch})
    time.sleep(SPACING)
    if resp.get("code") != 200:
        raise RuntimeError(f"optionchain {symbol}: {resp.get('message')}")
    return resp.get("data", {}) or {}


def _calls(data: dict) -> tuple[list[Leg], float, float | None]:
    rows = data.get("optionsChain", []) or []
    under = next((r for r in rows if not r.get("option_type")), {})
    legs = [Leg(symbol=r.get("symbol", ""), strike=float(r.get("strike_price") or 0),
                bid=float(r.get("bid") or 0), ask=float(r.get("ask") or 0), ltp=float(r.get("ltp") or 0),
                volume=float(r.get("volume") or 0), oi=float(r.get("oi") or 0))
            for r in rows if r.get("option_type") == "CE"]
    vix = (data.get("indiavixData") or {}).get("ltp")
    return legs, float(under.get("ltp") or 0), vix


def _sessions(broker) -> list:
    bars = broker.get_historical_data(REFERENCE_SYMBOL, "1d", datetime.now(timezone.utc) - timedelta(days=90),
                                      datetime.now(timezone.utc))
    return sorted({bar_date(c) for c in bars or []})


def _universe(prev_session) -> tuple[list[str], dict[str, int]]:
    BHAVCOPY_DIR.mkdir(parents=True, exist_ok=True)
    day = parse_fno_day(fetch_raw(prev_session, BHAVCOPY_DIR), prev_session)
    lots = {s: q[0].lot_size for s, q in day.options.items() if q}
    return day.symbols, lots


def _prior_closes(broker, symbol: str, today) -> list[float]:
    """Daily closes before `today`, about 400 calendar days back, in two
    requests (Fyers caps a daily-history request at 366 days)."""
    end = datetime.now(timezone.utc)
    mid = end - timedelta(days=200)
    by_date = {}
    for start, stop in ((end - timedelta(days=400), mid), (mid, end)):
        for c in broker.get_historical_data(symbol, "1d", start, stop) or []:
            if bar_date(c) < today:
                by_date[bar_date(c)] = c.close
        time.sleep(SPACING)
    return [by_date[d] for d in sorted(by_date)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="agent/config.yaml")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ignore-session", action="store_true",
                    help="dry-run only: treat the latest session as today (plumbing test outside hours)")
    args = ap.parse_args()
    if args.ignore_session and not args.dry_run:
        ap.error("--ignore-session is only allowed with --dry-run")

    broker = get_broker(load_config(args.config))
    if not broker.connect():
        print("ERROR: broker connect() failed -- check the Fyers token.")
        return 1
    client = broker._client
    now = datetime.now(IST)
    today = now.date()
    sessions = _sessions(broker)
    if args.ignore_session and sessions:
        today = sessions[-1]
    if not sessions or sessions[-1] != today:
        print(f"{today}: not a trading session (latest {REFERENCE_SYMBOL} bar {sessions[-1] if sessions else None}).")
        return 0

    base = store_dir()
    pos_path = base / "positions.jsonl"
    positions = load_positions(pos_path)
    sessions_since = {d.isoformat(): sum(1 for s in sessions if s > d) for d in sessions}
    log = {"run_at": now.isoformat(timespec="seconds"), "session": today.isoformat(),
           "exits": [], "entries": [], "skips": []}

    # 1. Exits due today
    for p in positions:
        if not p.open or p.last_session == today.isoformat():
            continue
        entry = datetime.fromisoformat(p.entry_date).date()
        p.sessions_held = sum(1 for s in sessions if entry < s <= today)
        p.last_session = today.isoformat()
        if not exit_due(p, today):
            continue
        try:
            legs, spot, _ = _calls(_chain(client, p.symbol, p.expiry_epoch))
        except Exception as e:
            log["exits"].append({"symbol": p.symbol, "error": str(e)})
            continue
        by_k = {l.strike: l for l in legs}
        vl, fl = exit_value(by_k.get(p.long["strike"]), "long")
        vs, fs = exit_value(by_k.get(p.short["strike"]), "short")
        p.exit_date, p.spot_exit = today.isoformat(), spot
        p.long_exit = {**(asdict(by_k[p.long["strike"]]) if p.long["strike"] in by_k else {}), "value": vl}
        p.short_exit = {**(asdict(by_k[p.short["strike"]]) if p.short["strike"] in by_k else {}), "value": vs}
        p.exit_flag = fl or fs
        log["exits"].append({"symbol": p.symbol, "entry": p.entry_date, "held": p.sessions_held, "flag": p.exit_flag})

    # 2. New entries
    prev = sessions[-2]
    try:
        symbols, lots = _universe(prev)
    except BhavcopyNotAvailable:
        print(f"ERROR: no F&O bhavcopy for {prev}; cannot build the universe.")
        return 1
    quotes = broker.get_quotes(symbols + [REFERENCE_SYMBOL])
    nifty = quotes.pop(REFERENCE_SYMBOL, None)
    stock_q = {s: q for s, q in quotes.items() if q.prev_close > 0}
    surges = sorted((q for q in stock_q.values() if q.change_pct >= SURGE_PCT), key=lambda q: -q.change_pct)
    market = {"nifty_change_pct": nifty.change_pct if nifty else None, "vix": None,
              "breadth_up_share": round(sum(1 for q in stock_q.values() if q.change_pct > 0) / max(len(stock_q), 1), 3),
              "surges": len(surges), "universe": len(stock_q)}

    for q in surges:
        sym = q.symbol
        if any(p.symbol == sym and p.open for p in positions) or in_cooldown(positions, sym, sessions_since):
            log["skips"].append({"symbol": sym, "reason": "open position or 10-session cooldown"})
            continue
        try:
            closes = _prior_closes(broker, sym, today)
        except Exception as e:
            log["skips"].append({"symbol": sym, "reason": f"history failed: {e}"})
            continue
        if is_fresh_52w_high(closes, q.ltp):
            log["skips"].append({"symbol": sym, "reason": "fresh 52-week high (or < 252 sessions of history)"})
            continue
        try:
            first = _chain(client, sym)
            choice = choose_expiry([(d, ep) for d, ep, _ in parse_expiries(first)], today)
            if choice is None:
                log["skips"].append({"symbol": sym, "reason": "no expiry with >= 5 weekdays"})
                continue
            exp, epoch = choice
            data = first if epoch == (parse_expiries(first)[0][1] if parse_expiries(first) else "") \
                else _chain(client, sym, epoch)
            legs, spot, vix = _calls(data)
        except Exception as e:
            log["skips"].append({"symbol": sym, "reason": f"option chain failed: {e}"})
            continue
        market["vix"] = market["vix"] or vix
        long_, short, reason = pick_legs(legs, spot or q.ltp)
        if reason:
            log["skips"].append({"symbol": sym, "reason": reason,
                                 "long": asdict(long_) if long_ else None, "short": asdict(short) if short else None})
            continue
        pos = Position(symbol=sym, entry_date=today.isoformat(), expiry=exp.isoformat(), expiry_epoch=epoch,
                       lot=lots.get(sym, 0), spot_entry=spot or q.ltp, long=asdict(long_), short=asdict(short),
                       debit_real=long_.ask - short.bid, debit_mid=long_.mid - short.mid,
                       market={**market}, last_session=today.isoformat())
        positions.append(pos)
        log["entries"].append({"symbol": sym, "change_pct": q.change_pct, "expiry": pos.expiry,
                               "long": long_.strike, "short": short.strike})

    log["market"] = market
    n_open = sum(1 for p in positions if p.open)
    n_closed = sum(1 for p in positions if not p.open)
    print(f"{today} 23b: {len(surges)} surges, {len(log['entries'])} entries, {len(log['exits'])} exits, "
          f"{len(log['skips'])} skips; {n_open} open, {n_closed} closed (P&L hidden until 60 closed).")
    for e in log["entries"]:
        print(f"  entry {e['symbol']} +{e['change_pct']:.1f}% {e['expiry']} {e['long']:g}/{e['short']:g} CE")
    for s in log["skips"]:
        print(f"  skip  {s['symbol']}: {s['reason']}")
    if args.dry_run:
        print("(dry run: nothing written)")
        return 0
    save_positions(pos_path, positions)
    append_jsonl(base / "runs.jsonl", log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
