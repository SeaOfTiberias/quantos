#!/usr/bin/env python3
"""
QuantOS — Spread Watcher (ICICI Direct)
───────────────────────────────────────
Manages the EXIT of option spreads you open yourself in the spouse's ICICI
Direct account, the way scripts/run_trade_watcher.py does for single options
at Fyers. Every CLOSE alert spells out both closing orders.

Orders: with `spread_watcher: {orders: auto}` in agent/config.yaml it also
closes the spread itself on a CLOSE event (core/spread_watcher/executor.py):
short leg bought back first, then the long sold, through the order gateway.
`auto_close: [kinds]` limits which CLOSE kinds act (default: all). With
`orders: alerts` (the default) it places NO orders.

  every 60 s   Breeze positions -> legs -> spreads (core/spread_watcher/legs.py)
               new spread  -> "watching" message with its max loss/profit/breakeven
               gone        -> "closed" message
               uncovered short option -> warning, repeated every 30 min while open
  every 20 s   per spread: stock price + both legs' bid/ask -> close-out value
               -> core/spread_watcher/rules.py -> CLOSE / heads-up alerts

Needs today's ICICI session (cockpit "Log in to ICICI Direct"). ICICI keeps
one live API session per app: a login anywhere else kills this one, so the
watcher re-reads the session file whenever a call fails and says so once.

A per-trade stock-price exit level replaces the trail for that stock:
~/.quantos/spread_watcher_levels.json, e.g. {"TECMAH": 1775} (on touch), or
{"HDFBAN": {"close": 705, "touch": 721, "target": 665}}: stop on the DAILY
close (checked 15:20), emergency on touch, target on touch.
State (peak P&L, best stock price, alerts sent) persists in
~/.quantos/spread_watcher_state.json, so a restart mid-trade loses nothing.

Runs as quantos-spread-watcher.service, 09:15-15:31 IST on weekdays.

Usage:
    python scripts/run_spread_watcher.py
    python scripts/run_spread_watcher.py --once     # one pass, print, no Telegram
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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.auth import breeze_auth  # noqa: E402
from core.spread_watcher.executor import SpreadExecutor  # noqa: E402
from core.spread_watcher.legs import Leg, Spread, group_legs, parse_leg  # noqa: E402
from core.spread_watcher.rules import SpreadRules, SpreadState, evaluate  # noqa: E402

logging.getLogger("httpx").setLevel(logging.WARNING)   # Telegram URLs carry the bot token

IST = timezone(timedelta(hours=5, minutes=30))
QUANTOS_DIR = Path.home() / ".quantos"
STATE_PATH = QUANTOS_DIR / "spread_watcher_state.json"
LEVELS_PATH = QUANTOS_DIR / "spread_watcher_levels.json"
HEARTBEAT_PATH = QUANTOS_DIR / "spread_watcher_heartbeat.json"   # read by GET /spreads (cockpit #/spreads)
ALERTS_PATH = QUANTOS_DIR / "spread_watcher_alerts.jsonl"
CONFIG_PATH = Path("agent/config.yaml")
POSITIONS_EVERY_S = 60
PRICES_EVERY_S = 20
NAKED_REMIND_EVERY_S = 1800
SESSION_START, SESSION_END = (9, 15), (15, 31)


def now_ist() -> datetime:
    return datetime.now(IST)


class Notifier:
    """Telegram from one background thread, so a slow send never stalls pricing."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.q: "queue.Queue[str]" = queue.Queue()
        if enabled:
            threading.Thread(target=self._run, daemon=True).start()

    def send(self, text: str) -> None:
        print(f"[{now_ist():%H:%M:%S}] {'TELEGRAM' if self.enabled else 'ALERT'}: {text}", flush=True)
        if self.enabled:
            self.q.put(text)
            try:                                      # the cockpit's alert timeline
                with ALERTS_PATH.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"at": now_ist().isoformat(timespec="seconds"), "text": text}) + "\n")
            except OSError:
                pass

    def _run(self) -> None:
        from cloud.api.notifier import send_telegram
        while True:
            text = self.q.get()
            try:
                asyncio.run(send_telegram(text))
            except Exception as e:
                print(f"Telegram send failed ({e})", flush=True)


# ─── Breeze calls ────────────────────────────────────────────────────────────

QUOTE_TRIES, QUOTE_RETRY_S = 3, 1.5


def quotes_with_retry(client, **kw) -> dict:
    """Breeze get_quotes, retried: under load it sometimes returns an empty
    body (the SDK raises "Expecting value: line 1 column 1"), about 1 call in
    12 on 2026-10-23. Dropping the session on each one re-logged in every
    pass and left the spread unpriced for minutes."""
    for attempt in range(QUOTE_TRIES):
        try:
            return client.get_quotes(**kw)
        except Exception as e:
            if "Expecting value" not in str(e) or attempt == QUOTE_TRIES - 1:
                raise
            time.sleep(QUOTE_RETRY_S)
    return {}


def _iso_expiry(d) -> str:
    return f"{d.isoformat()}T06:00:00.000Z"


def option_quote(client, leg: Leg) -> tuple[float, float, float]:
    r = quotes_with_retry(client, stock_code=leg.stock_code, exchange_code="NFO", expiry_date=_iso_expiry(leg.expiry),
                          product_type="options", right=leg.right, strike_price=f"{leg.strike:g}")
    rows = r.get("Success") or []
    if r.get("Status") != 200 or not rows:
        raise RuntimeError(f"quote {leg.stock_code} {leg.label}: {r.get('Error')}")
    x = rows[0]
    return float(x.get("best_bid_price") or 0), float(x.get("best_offer_price") or 0), float(x.get("ltp") or 0)


def stock_price(client, code: str) -> float:
    r = quotes_with_retry(client, stock_code=code, exchange_code="NSE", expiry_date="", product_type="cash",
                          right="", strike_price="")
    for x in r.get("Success") or []:
        if x.get("exchange_code") == "NSE" and x.get("ltp"):
            return float(x["ltp"])
    raise RuntimeError(f"no NSE price for {code}: {r.get('Error')}")


def read_legs(client) -> list[Leg]:
    r = client.get_portfolio_positions()
    if r.get("Status") != 200:
        raise RuntimeError(f"positions: {r.get('Error')}")
    legs = []
    for row in r.get("Success") or []:
        leg = parse_leg(row)
        if leg is None and str(row.get("product_type", "")).lower().startswith("option"):
            print(f"  skipped an option row I couldn't read: { {k: row.get(k) for k in list(row)[:12]} }", flush=True)
        if leg:
            legs.append(leg)
    return legs


# ─── Text ────────────────────────────────────────────────────────────────────

def name(sp: Spread) -> str:
    cp = "CE" if sp.long.right == "call" else "PE"
    return (f"{sp.long.stock_code} {sp.kind} {sp.long.strike:g}/{sp.short.strike:g} {cp} "
            f"{sp.long.expiry:%d-%b} ×{sp.qty}")


def watching_text(sp: Spread, st: SpreadState, rules: SpreadRules, auto: bool = False) -> str:
    paid = f"paid {st.entry:.2f}" if st.entry > 0 else f"received {-st.entry:.2f}"
    if st.close_level:
        a = (f"stock daily close beyond {st.close_level:g} (checked {rules.close_check_at})"
             + (f", emergency touch {st.level:g}" if st.level else "") + (f", target {st.target:g}" if st.target else ""))
    else:
        a = f"your level {st.level:g}" if st.level else f"stock {rules.stock_trail_pct:g}% behind its best once in profit"
    return (f"👀 Watching {name(sp)} · {paid} · max loss ₹{st.max_loss:,.0f} · max profit ₹{st.max_profit:,.0f} · "
            f"breakeven {st.breakeven:,.2f}\nExit alerts: {a}; give-back keeps {rules.giveback_keep:.0%} once P&L ≥ "
            f"{rules.giveback_arm_pct:g}% of max; close by the session before {sp.long.expiry:%d-%b}. "
            + ("On a CLOSE I close it myself (short leg first)." if auto else "Alerts only."))


def close_orders(sp: Spread, q_long: tuple, q_short: tuple) -> str:
    return (f"SELL {sp.long.label} @ bid {q_long[0]:.2f}, BUY {sp.short.label} @ ask {q_short[1]:.2f}"
            if sp.long.qty > 0 else "")


# ─── Main loop ───────────────────────────────────────────────────────────────

def apply_levels(st: SpreadState, v) -> None:
    """A number = touch level (the original form); a dict may set touch / close / target."""
    if isinstance(v, dict):
        st.level, st.close_level, st.target = v.get("touch"), v.get("close"), v.get("target")
    else:
        st.level, st.close_level, st.target = v, None, None


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def load_explainer_cfg() -> dict:
    try:
        import yaml
        return (yaml.safe_load(CONFIG_PATH.read_text()) or {}).get("trade_explainer") or {}
    except Exception:
        return {}


def load_section() -> dict:
    try:
        import yaml
        return (yaml.safe_load(CONFIG_PATH.read_text()) or {}).get("spread_watcher") or {}
    except Exception:
        return {}


def load_orders_cfg() -> dict:
    try:
        import yaml
        return (yaml.safe_load(CONFIG_PATH.read_text()) or {}).get("orders") or {}
    except Exception:
        return {}


def load_rules() -> SpreadRules:
    try:
        import yaml
        cfg = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        return SpreadRules.from_config(cfg.get("spread_watcher"))
    except Exception:
        return SpreadRules()


class SpreadWatcher:
    def __init__(self, rules: SpreadRules, notify: Notifier, dry: bool = False):
        self.rules, self.notify, self.dry = rules, notify, dry
        self.client = None
        self.session_alerted = False
        self.spreads: dict[str, Spread] = {}
        self.states: dict[str, SpreadState] = {k: SpreadState.from_dict(v) for k, v in load_json(STATE_PATH).items()}
        self.naked_last: dict[str, float] = {}
        self.naked: list = []
        self.views: dict[str, dict] = {}          # display-only extras for the cockpit, per spread
        from core.llm.explainer import Explainer
        self.explainer = Explainer({} if dry else load_explainer_cfg(), notify.send)
        self.nse: dict[str, str] = {}             # ICICI code -> NSE symbol (HDFBAN -> HDFCBANK)
        section = {} if dry else load_section()
        self.auto = section.get("orders") == "auto"
        self.auto_kinds = tuple(section.get("auto_close") or ())
        self.executor: Optional[SpreadExecutor] = None

    def nse_symbol(self, code: str) -> str:
        if code not in self.nse:
            try:
                n = self.client.get_names(exchange_code="NSE", stock_code=code) or {}
                self.nse[code] = str(n.get("exchange_stock_code") or code).upper()
            except Exception:
                return code
        return self.nse[code]

    def save(self) -> None:
        if self.dry:                      # --once must not mark alerts as sent for the real watcher
            return
        STATE_PATH.write_text(json.dumps({k: {**s.to_dict(), "view": self.views.get(k)}
                                          for k, s in self.states.items()}))

    def heartbeat(self, session_ok: bool) -> None:
        if self.dry:
            return
        HEARTBEAT_PATH.write_text(json.dumps({
            "at": now_ist().isoformat(timespec="seconds"), "session_ok": session_ok,
            "spreads": len(self.spreads),
            "naked": [{"stock_code": x.stock_code, "label": x.label, "expiry": x.expiry.isoformat(),
                       "qty": -x.qty, "avg_price": x.avg_price} for x in self.naked],
            "rules": self.rules.__dict__,
        }))

    def ensure_client(self) -> bool:
        if self.client is not None:
            return True
        try:
            self.client = breeze_auth.connect()
            self.session_alerted = False
            if self.auto:
                from core.orders.gateway import Gateway, limits_from
                cfg = load_orders_cfg()
                self.executor = SpreadExecutor(Gateway(self.client, live=bool(cfg.get("live")),
                                                       limits=limits_from(cfg)),
                                               self.notify.send, kinds=self.auto_kinds)
            print(f"[{now_ist():%H:%M:%S}] ICICI Direct session OK.", flush=True)
            return True
        except breeze_auth.BreezeAuthError as e:
            if not self.session_alerted:
                self.session_alerted = True
                self.notify.send(f"⚠️ Spread watcher can't reach ICICI Direct ({e}). "
                                 "Log in from the cockpit; I'll pick the session up by myself.")
            return False

    def drop_client(self, why: Exception) -> None:
        print(f"[{now_ist():%H:%M:%S}] Breeze call failed ({why}); reconnecting next pass.", flush=True)
        self.client = None

    def refresh_positions(self) -> None:
        spreads, naked, _lone = group_legs(read_legs(self.client))
        levels = load_json(LEVELS_PATH)
        current = {sp.key: sp for sp in spreads}
        for key, sp in current.items():
            st = self.states.get(key)
            if st is None:
                st = self.states[key] = SpreadState.open(sp)
                apply_levels(st, levels.get(sp.long.stock_code))
                self.notify.send(watching_text(sp, st, self.rules, self.executor is not None))
            else:
                apply_levels(st, levels.get(sp.long.stock_code))   # cleared in the cockpit -> back to the trail
        for key in (set(self.spreads) | set(self.states)) - set(current):   # states too: closed while we were down
            st = self.states.pop(key, None)
            last = f" Last P&L seen ≈ ₹{st.last_pnl:,.0f}." if st and st.last_pnl is not None else ""
            label = name(self.spreads[key]) if key in self.spreads else key.replace("|", " ")
            self.notify.send(f"✅ {label} is no longer open.{last}")
        self.spreads = current
        self.naked = naked
        for key, sp in current.items():
            self.views.setdefault(key, {})
            self.views[key].update(stock_code=sp.long.stock_code, kind=sp.kind, right=sp.long.right,
                                   expiry=sp.long.expiry.isoformat(), long_strike=sp.long.strike,
                                   short_strike=sp.short.strike, qty=sp.qty,
                                   long_avg=sp.long.avg_price, short_avg=sp.short.avg_price)
        for key in list(self.views):
            if key not in current:
                del self.views[key]
        for leg in naked:
            k = f"{leg.stock_code}|{leg.expiry}|{leg.right}|{leg.strike:g}"
            if time.monotonic() - self.naked_last.get(k, -1e9) >= NAKED_REMIND_EVERY_S:
                self.naked_last[k] = time.monotonic()
                risk = "unlimited if it rises" if leg.right == "call" else "large if it falls"
                self.notify.send(f"🚨 UNCOVERED SHORT: {leg.stock_code} {leg.label} {leg.expiry:%d-%b} ×{-leg.qty}, "
                                 f"sold @ {leg.avg_price:.2f}, with no long leg against it. Loss is {risk}. "
                                 "Buy it back or add a long leg.")
        self.save()

    def price_spreads(self) -> None:
        today, now = now_ist().date(), now_ist().time()
        for key, sp in self.spreads.items():
            st = self.states[key]
            spot = stock_price(self.client, sp.long.stock_code)
            ql, qs = option_quote(self.client, sp.long), option_quote(self.client, sp.short)
            quoted = ql[0] > 0 and qs[1] > 0
            value = (ql[0] - qs[1]) if quoted else (ql[2] - qs[2])
            self.views.setdefault(key, {}).update(long_quote=list(ql), short_quote=list(qs), quoted=quoted,
                                                  updated_at=now_ist().isoformat(timespec="seconds"))
            sym = self.nse_symbol(sp.long.stock_code)
            self.explainer.check_gap(key, sym, name(sp), 1 if st.bullish else -1)
            for ev in evaluate(st, spot, value, today, now, self.rules):
                acting = bool(ev.close and self.executor and self.executor.wants(ev.kind))
                if acting:
                    self.executor.request(st, ev.kind)
                head = "🔴 CLOSE" if ev.close else "ℹ️"
                orders = f"\nClose both legs: {close_orders(sp, ql, qs)}" if ev.close else ""
                basis = "" if quoted else " (no two-sided quote: valued at last traded prices)"
                self.notify.send(f"{head} {name(sp)} · {ev.detail}.\nP&L now ₹{st.last_pnl:,.0f} "
                                 f"(best ₹{st.peak_pnl:,.0f}, max ₹{st.max_profit:,.0f}){basis}.{orders}"
                                 + (("\nClosing it now by rule: short leg first." if acting
                                     else "\nAlerts only: place the orders yourself.") if ev.close else ""))
                if ev.close:
                    self.explainer.explain(sym, {
                        "alert": ev.kind, "stock_now": spot,
                        "instrument": f"{sym} {sp.kind} {sp.long.strike:g}/{sp.short.strike:g} "
                                      f"{'CE' if sp.long.right == 'call' else 'PE'} expiring {sp.long.expiry:%d-%b}",
                        "levels": {"close_stop": st.close_level, "emergency_touch": st.level, "target": st.target,
                                   "breakeven": st.breakeven}})
            if self.executor and st.close_reason:
                self.executor.close(sp, st, name(sp))
        self.save()

    def run(self, once: bool = False) -> int:
        last_pos = -1e9
        while True:
            t = now_ist()
            if not once and (t.hour, t.minute) >= SESSION_END:
                print("Session over.", flush=True)
                return 0
            ok = self.ensure_client()
            if ok:
                try:
                    if time.monotonic() - last_pos >= POSITIONS_EVERY_S:
                        self.refresh_positions()
                        last_pos = time.monotonic()
                    self.price_spreads()
                except Exception as e:
                    self.drop_client(e)
                    ok = False
            self.heartbeat(ok)
            if once:
                for k, st in self.states.items():
                    print(f"  {k}: P&L {st.last_pnl} best {st.peak_pnl} stop {st.stock_stop} sent {st.sent}")
                return 0
            time.sleep(PRICES_EVERY_S)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="one pass, print alerts, send nothing")
    args = ap.parse_args(argv)
    t = now_ist()
    if not args.once and (t.weekday() >= 5 or (t.hour, t.minute) < SESSION_START or (t.hour, t.minute) >= SESSION_END):
        print("Outside market hours -- nothing to do.")
        return 0
    return SpreadWatcher(load_rules(), Notifier(enabled=not args.once), dry=args.once).run(once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
