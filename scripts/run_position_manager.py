#!/usr/bin/env python3
"""
QuantOS — Position Manager for futures in the ICICI Direct account (alerts only)
─────────────────────────────────────────────────────────────────────────────────
Reads open FUTURES positions from ICICI Direct (Breeze) by itself and holds
each one to a written exit plan (core/position_manager/rules.py): the stop is
judged on the DAILY close, an emergency stop and the 1R target on touch, out
by session 10. It answers "should I sell?" with the plan, not the P&L on
screen. Places NO orders.

  every 60 s   Breeze positions -> futures; new one -> plan + "managing" message
               (stop, emergency, target, last session); gone -> "closed" message
  every 30 s   futures LTP -> emergency / target touch alerts (once each)
  15:20 IST    the daily check, once per position per day: CLOSE (beyond the
               stop), TIME (session 10 / expiry) or HOLD with the levels
  first pass of each day  a morning note: today's levels, and a reminder to
               place the resting target and re-place the stop (Breeze stop
               orders are day-only)

ATR(14) comes from Fyers daily bars of the underlying (Breeze's daily history
had a bad 22 Oct TCS low); ICICI codes map to NSE symbols via Breeze
get_names (POWFIN -> PFC). Per-position override, for a discretionary plan:
~/.quantos/position_manager_levels.json, e.g. {"TCS": {"stop": 2495, "target": 2614}}.
State: ~/.quantos/position_manager_state.json (restart-safe).

Runs as quantos-position-manager.service, 09:15-15:31 IST on weekdays.

Usage:
    python scripts/run_position_manager.py
    python scripts/run_position_manager.py --once    # one pass, print, no Telegram, no state written
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import queue
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.auth import breeze_auth  # noqa: E402
from core.position_manager.rules import (  # noqa: E402
    MAX_SESSIONS, FutPosition, Plan, check_close, check_intraday, make_plan, parse_future,
)

logging.getLogger("httpx").setLevel(logging.WARNING)

IST = timezone(timedelta(hours=5, minutes=30))
QUANTOS_DIR = Path.home() / ".quantos"
STATE_PATH = QUANTOS_DIR / "position_manager_state.json"
LEVELS_PATH = QUANTOS_DIR / "position_manager_levels.json"
CONFIG_PATH = Path("agent/config.yaml")
POSITIONS_EVERY_S = 60
PRICES_EVERY_S = 30
CLOSE_CHECK_AT = (15, 20)
SESSION_START, SESSION_END = (9, 15), (15, 31)


def now_ist() -> datetime:
    return datetime.now(IST)


class Notifier:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.q: "queue.Queue[str]" = queue.Queue()
        if enabled:
            threading.Thread(target=self._run, daemon=True).start()

    def send(self, text: str) -> None:
        print(f"[{now_ist():%H:%M:%S}] {'TELEGRAM' if self.enabled else 'ALERT'}: {text}", flush=True)
        if self.enabled:
            self.q.put(text)

    def _run(self) -> None:
        from cloud.api.notifier import send_telegram
        while True:
            text = self.q.get()
            try:
                asyncio.run(send_telegram(text))
            except Exception as e:
                print(f"Telegram send failed ({e})", flush=True)


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


# ─── Market data ─────────────────────────────────────────────────────────────

class Data:
    """Breeze for positions / futures quotes / code mapping; Fyers for daily bars."""

    def __init__(self):
        self.client = None
        self.fyers = None
        self.symbols: dict[str, str] = {}

    def positions(self) -> list[FutPosition]:
        r = self.client.get_portfolio_positions()
        if r.get("Status") != 200:
            raise RuntimeError(f"positions: {r.get('Error')}")
        out = []
        for row in r.get("Success") or []:
            p = parse_future(row)
            if p is None and str(row.get("product_type", "")).lower().startswith("future"):
                print(f"  skipped a futures row I couldn't read: { {k: row.get(k) for k in list(row)[:12]} }", flush=True)
            if p:
                out.append(p)
        return out

    def ltp(self, p: FutPosition) -> float:
        from scripts.run_spread_watcher import quotes_with_retry
        r = quotes_with_retry(self.client, stock_code=p.code, exchange_code="NFO",
                              expiry_date=f"{p.expiry.isoformat()}T06:00:00.000Z",
                              product_type="futures", right="others", strike_price="0")
        rows = r.get("Success") or []
        if r.get("Status") != 200 or not rows or not rows[0].get("ltp"):
            raise RuntimeError(f"quote {p.code} FUT: {r.get('Error')}")
        return float(rows[0]["ltp"])

    def symbol(self, code: str) -> str:
        if code not in self.symbols:
            try:
                n = self.client.get_names(exchange_code="NSE", stock_code=code) or {}
                self.symbols[code] = str(n.get("exchange_stock_code") or code).upper()
            except Exception:
                self.symbols[code] = code
        return self.symbols[code]

    def daily(self, symbol: str, days: int = 45) -> list:
        try:
            if self.fyers is None:
                from agent.main import load_config
                from core.brokers import get_broker
                self.fyers = get_broker(load_config(str(CONFIG_PATH)))
                self.fyers.connect()
            now = datetime.now(timezone.utc)
            return sorted(self.fyers.get_historical_data(symbol, "1d", now - timedelta(days=days), now) or [],
                          key=lambda c: c.timestamp)
        except Exception as e:
            print(f"  Fyers daily bars for {symbol} failed ({e})", flush=True)
            self.fyers = None
            return []


def atr14(bars: list, before: date) -> Optional[float]:
    bars = [b for b in bars if b.timestamp.astimezone(IST).date() < before][-15:]
    if len(bars) < 15:
        return None
    trs = [max(b.high - b.low, abs(b.high - a.close), abs(b.low - a.close)) for a, b in zip(bars, bars[1:])]
    return sum(trs) / len(trs)


def session_no(bars: list, entry_date: date, today: date) -> int:
    days = {b.timestamp.astimezone(IST).date() for b in bars}
    days.add(today)
    return sum(1 for d in days if entry_date <= d <= today)


# ─── Text ────────────────────────────────────────────────────────────────────

def name(p: Plan) -> str:
    return f"{p.symbol} FUT {p.expiry:%d-%b} {'LONG' if p.side > 0 else 'SHORT'} ×{abs(p.qty)} @ {p.entry:g}"


def plan_text(p: Plan) -> str:
    beyond = "below" if p.side > 0 else "above"
    exit_verb = "SELL" if p.side > 0 else "BUY"
    lines = [f"🧭 Managing {name(p)}" + (" (your levels)" if p.source == "override" else " (tested plan)"),
             f"• Stop: a DAILY close {beyond} {p.stop:g} -- checked at 15:20, intraday dips above it are noise"]
    if p.emergency is not None:
        lines.append(f"• Emergency: price touches {p.emergency:g} -- exit at once")
    if p.target is not None:
        lines.append(f"• Target: {p.target:g} -- place a resting {exit_verb} LIMIT there now")
    if p.atr:
        lines.append(f"• ATR {p.atr:g}, 1R = {p.r:g} pts = ₹{p.r * abs(p.qty):,.0f}")
    lines.append(f"• Out by the close of session {MAX_SESSIONS} at the latest. Alerts only -- I place no orders.")
    return "\n".join(lines)


# ─── Loop ────────────────────────────────────────────────────────────────────

class Manager:
    def __init__(self, notify: Notifier, dry: bool):
        self.notify, self.dry = notify, dry
        self.data = Data()
        self.plans: dict[str, Plan] = {k: Plan.from_dict(v) for k, v in load_json(STATE_PATH).items()}
        self.morning_sent: set[str] = set()
        self.current: dict[str, FutPosition] = {}
        self.session_alerted = False

    def save(self) -> None:
        if not self.dry:
            STATE_PATH.write_text(json.dumps({k: p.to_dict() for k, p in self.plans.items()}, indent=1))

    def ensure_client(self) -> bool:
        if self.data.client is not None:
            return True
        try:
            self.data.client = breeze_auth.connect()
            self.session_alerted = False
            return True
        except breeze_auth.BreezeAuthError as e:
            if not self.session_alerted:
                self.session_alerted = True
                self.notify.send(f"⚠️ Position manager can't reach ICICI Direct ({e}). Log in from the cockpit.")
            return False

    def refresh(self) -> None:
        today = now_ist().date()
        levels = load_json(LEVELS_PATH)
        current = self.current = {p.key: p for p in self.data.positions()}
        for key, pos in current.items():
            plan = self.plans.get(key)
            if plan is None or plan.qty != pos.qty or abs(plan.entry - pos.avg_price) > 1e-6:
                sym = self.data.symbol(pos.code)
                atr = atr14(self.data.daily(sym), today)
                override = levels.get(pos.code) or levels.get(sym)
                fresh = make_plan(pos, sym, atr, today, override)
                if plan is not None:                      # added to / partly closed: keep the original entry date
                    fresh.entry_date = plan.entry_date
                self.plans[key] = fresh
                self.notify.send(plan_text(fresh))
        for key in set(self.plans) - set(current):
            p = self.plans.pop(key)
            last = f" Last price seen {p.last_price:g} (P&L ≈ ₹{(p.last_price - p.entry) * p.qty:,.0f})." if p.last_price else ""
            self.notify.send(f"✅ {name(p)} is no longer open.{last}")
        self.save()

    def tick(self) -> None:
        t = now_ist()
        today = t.date()
        for key, plan in self.plans.items():
            pos = self.current.get(key)
            if pos is None:
                continue
            price = self.data.ltp(pos)
            if key not in self.morning_sent:
                self.morning_sent.add(key)
                if plan.entry_date < today:
                    self.notify.send(f"☀️ {name(plan)} · now {price:g} · stop {plan.stop:g} (daily close) · "
                                     f"target {plan.target if plan.target is not None else '-'} · "
                                     "re-place today's stop order (Breeze stops are day-only) and keep the target limit resting.")
            for ev in check_intraday(plan, price):
                head = "🚨" if ev.kind == "EMERGENCY" else "🎯"
                self.notify.send(f"{head} {ev.kind} {name(plan)}: {ev.detail}.")
            if (t.hour, t.minute) >= CLOSE_CHECK_AT and plan.last_check != today.isoformat():
                n = session_no(self.data.daily(plan.symbol, days=30), plan.entry_date, today)
                ev = check_close(plan, price, today, n)
                head = {"CLOSE": "🔴 CLOSE", "TIME": "⏰ TIME", "HOLD": "🟢 HOLD"}[ev.kind]
                self.notify.send(f"{head} {name(plan)}: {ev.detail}.")
        self.save()

    def run(self, once: bool) -> int:
        last_pos = -1e9
        while True:
            t = now_ist()
            if not once and (t.hour, t.minute) >= SESSION_END:
                print("Session over.", flush=True)
                return 0
            if self.ensure_client():
                try:
                    if time.monotonic() - last_pos >= POSITIONS_EVERY_S:
                        self.refresh()
                        last_pos = time.monotonic()
                    self.tick()
                except Exception as e:
                    print(f"[{now_ist():%H:%M:%S}] Breeze call failed ({e}); reconnecting next pass.", flush=True)
                    self.data.client = None
            if once:
                for k, p in self.plans.items():
                    print(f"  {k}: {p.to_dict()}")
                if not self.plans:
                    print("  no open futures positions in ICICI Direct.")
                return 0
            time.sleep(PRICES_EVERY_S)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="one pass, print, send nothing, write no state")
    args = ap.parse_args(argv)
    t = now_ist()
    if not args.once and (t.weekday() >= 5 or (t.hour, t.minute) < SESSION_START or (t.hour, t.minute) >= SESSION_END):
        print("Outside market hours -- nothing to do.")
        return 0
    return Manager(Notifier(enabled=not args.once), dry=args.once).run(once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
