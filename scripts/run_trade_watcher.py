#!/usr/bin/env python3
"""
QuantOS — Trade Watcher (stage 1: Telegram alerts only, never places orders)
──────────────────────────────────────────────────────────────────────────────
Manages the EXIT of option positions you open yourself, however you open
them (TradingView panel, Fyers app, web). Push-based, no polling:

  Fyers order socket  --(position update)-->  new long option position?
      -> start managing it: entry = Fyers' own netAvg, qty = netQty
  REST quotes, every 2 s (managed symbols only) --> core/trade_watcher/rules.py
      -> stop / breakeven / trailing-stop events -> Telegram
  position goes flat  -> "closed" message with Fyers' realized P&L, stop managing

Stage 1 contains NO order-placing code: an exit event is a Telegram
message telling you to exit. Stage 2 (a real SL order at Fyers, trailed
automatically) is deliberately not built yet.

On start it also reads open positions over REST once, so a restart mid-
trade picks up where it left off; per-position state (highest premium,
current stop) persists in ~/.quantos/trade_watcher_state.json.

Runs as quantos-trade-watcher.service during market hours; exits at
15:35 IST. Exit rules come from agent/config.yaml's trade_watcher block
(defaults in core/trade_watcher/rules.py).

Usage:
    python scripts/run_trade_watcher.py
"""

import argparse
import asyncio
import json
import logging
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from agent.risk_guard import IST  # noqa: E402
from core.trade_watcher.rules import ExitRules, ManagedPosition, is_option_symbol, on_tick  # noqa: E402

# httpx logs every request URL at INFO, and a Telegram URL carries the bot
# token -- keep it out of journald.
logging.getLogger("httpx").setLevel(logging.WARNING)

TOKEN_PATH = Path.home() / ".quantos" / "fyers_token"
STATE_PATH = Path.home() / ".quantos" / "trade_watcher_state.json"
SESSION_END_IST = (15, 35)
RAISE_NOTIFY_EVERY_S = 120     # trail raises can tick every second; message at most this often
EXIT_REMINDER_EVERY_S = 60
EXIT_REMINDERS = 3
# Every order QuantOS places carries one of these tags (core/brokers/fyers.py
# strips non-alphanumerics, and defaults an untagged order to "quantos"). A
# position whose buy carries one belongs to a QuantOS strategy with its own
# exit logic, so the watcher leaves it alone -- it only manages trades you
# placed yourself.
QUANTOS_TAG_PREFIXES = ("quantos", "orb", "darvas", "rotation")


def is_quantos_tag(tag: Optional[str]) -> bool:
    return bool(tag) and str(tag).lower().startswith(QUANTOS_TAG_PREFIXES)
PRICE_EVERY_S = 2              # REST quote poll for managed positions


def _now_ist() -> datetime:
    return datetime.now(IST)


def _fmt(x: float) -> str:
    return f"{x:,.2f}"


class Notifier:
    """Telegram from a single background thread, so socket callbacks never block."""

    def __init__(self):
        self.q: "queue.Queue[str]" = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def send(self, text: str) -> None:
        print(f"[{_now_ist():%H:%M:%S}] TELEGRAM: {text}", flush=True)
        self.q.put(text)

    def _run(self) -> None:
        from cloud.api.notifier import send_telegram
        while True:
            text = self.q.get()
            try:
                asyncio.run(send_telegram(text))
            except Exception as e:
                print(f"Telegram send failed ({e})", flush=True)


class Watcher:
    def __init__(self, rules: ExitRules, notifier: Notifier, state_path: Path = STATE_PATH):
        self.rules = rules
        self.notify = notifier.send
        self.state_path = state_path
        self.lock = threading.Lock()
        self.positions: dict[str, ManagedPosition] = {}
        self.ignored_short: set[str] = set()
        self.system_symbols: set[str] = set()     # opened by a QuantOS strategy: never managed
        # symbol -> the QuantOS tag on one of today's buys of it, or None.
        # Wired to the Fyers tradebook in main(); called OUTSIDE the lock.
        self.tag_lookup = lambda symbol: None
        self.last_raise_sent: dict[str, float] = {}
        self.pending_raise: dict[str, float] = {}
        self.exit_reminders: dict[str, tuple[float, int]] = {}
        self.subscribe = lambda symbols: None     # wired to the data socket in main()
        self.unsubscribe = lambda symbols: None
        self._saved = self._load_state()

    # ── persistence ──────────────────────────────────────────────────
    def _load_state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({s: p.to_dict() for s, p in self.positions.items()}, indent=2))

    # ── positions (order socket + startup REST read) ─────────────────
    def on_position(self, p: dict) -> None:
        """One Fyers position record: symbol, netQty, netAvg, buyAvg, realized_profit."""
        symbol = p.get("symbol", "")
        if not is_option_symbol(symbol):
            return
        net_qty = int(p.get("netQty") or 0)
        if symbol in self.system_symbols:
            return
        if net_qty > 0 and symbol not in self.positions:
            try:
                tag = self.tag_lookup(symbol)
            except Exception as e:
                tag = None
                print(f"tradebook tag lookup failed for {symbol} ({e}); managing it as manual", flush=True)
            if is_quantos_tag(tag):
                self.system_symbols.add(symbol)
                print(f"{symbol}: opened by QuantOS (tag {tag}) -- not managed", flush=True)
                return
        with self.lock:
            managed = self.positions.get(symbol)
            if net_qty > 0:
                entry = float(p.get("netAvg") or p.get("buyAvg") or 0)
                if entry <= 0:
                    return
                if managed is None:
                    self._start(symbol, entry, net_qty)
                elif net_qty != managed.quantity:
                    self.notify(f"ℹ️ {self._short(symbol)}: quantity {managed.quantity} → {net_qty}, "
                                f"avg {_fmt(entry)}. Stop stays {_fmt(managed.stop)}.")
                    managed.quantity, managed.entry = net_qty, entry
                    self._save_state()
            elif net_qty < 0:
                if symbol not in self.ignored_short:
                    self.ignored_short.add(symbol)
                    self.notify(f"⚪ {self._short(symbol)}: short position ({net_qty}) — not managed; "
                                f"the watcher only manages bought options.")
            elif managed is not None:
                realized = p.get("realized_profit")
                pnl = f"₹{float(realized):,.0f}" if realized is not None else "see Fyers"
                self.notify(f"✅ {self._short(symbol)} closed. Realized P&L {pnl}. "
                            f"(Last stop was {_fmt(managed.stop)}.)")
                del self.positions[symbol]
                self.exit_reminders.pop(symbol, None)
                self.pending_raise.pop(symbol, None)
                self._save_state()
                self.unsubscribe([symbol])

    def _start(self, symbol: str, entry: float, qty: int) -> None:
        saved = self._saved.get(symbol)
        if saved and abs(saved.get("entry", 0) - entry) < 0.01 and saved.get("quantity") == qty:
            pos = ManagedPosition.from_dict(saved)        # restart mid-trade: keep high and stop
            resumed = True
        else:
            pos = ManagedPosition.open(symbol, entry, qty, self.rules)
            resumed = False
        self.positions[symbol] = pos
        self._save_state()
        r = self.rules
        self.notify(
            f"{'🔁 Resumed' if resumed else '🟢 Managing'} {self._short(symbol)} × {qty} @ {_fmt(entry)}\n"
            f"Stop {_fmt(pos.stop)}"
            + (f" · breakeven at +{r.breakeven_at_pct:g}%" if r.breakeven_at_pct > 0 else "")
            + f" · trail {r.trail_pct:g}% below high after +{r.trail_after_pct:g}%\n"
            f"(Alerts only — exit yourself when told to.)")
        self.subscribe([symbol])

    # ── ticks (data socket) ──────────────────────────────────────────
    def on_tick(self, symbol: str, ltp: float) -> None:
        with self.lock:
            pos = self.positions.get(symbol)
            if pos is None:
                return
            events = on_tick(pos, ltp, self.rules)
            if not events:
                return
            for e in events:
                pnl = (e.price - pos.entry) * pos.quantity
                name = self._short(symbol)
                if e.kind == "exit":
                    self.notify(f"🔴 EXIT NOW {name}: {_fmt(e.price)} hit the "
                                f"{'trailing ' if pos.trail_on else ''}stop {_fmt(e.stop)}. "
                                f"P&L ≈ ₹{pnl:,.0f}")
                    self.exit_reminders[symbol] = (time.time(), 0)
                elif e.kind == "breakeven":
                    self.notify(f"🟡 {name}: up {self._gain(pos)}%, stop moved to entry {_fmt(e.stop)}.")
                elif e.kind == "trail_on":
                    self.notify(f"🟠 {name}: trailing now. High {_fmt(pos.high)}, stop {_fmt(e.stop)}. "
                                f"P&L ≈ ₹{pnl:,.0f}")
                    self.last_raise_sent[symbol] = time.time()
                elif e.kind == "stop_raised":
                    self.pending_raise[symbol] = e.stop
            self._save_state()

    def _gain(self, pos: ManagedPosition) -> str:
        return f"{(pos.high / pos.entry - 1) * 100:.0f}"

    # ── periodic (main loop) ─────────────────────────────────────────
    def tick_housekeeping(self) -> None:
        now = time.time()
        with self.lock:
            for symbol, stop in list(self.pending_raise.items()):
                pos = self.positions.get(symbol)
                if pos is None or pos.exit_alerted:
                    self.pending_raise.pop(symbol, None)
                    continue
                if now - self.last_raise_sent.get(symbol, 0) >= RAISE_NOTIFY_EVERY_S:
                    self.notify(f"⬆️ {self._short(symbol)}: stop raised to {_fmt(pos.stop)} "
                                f"(high {_fmt(pos.high)}, LTP {_fmt(pos.last_ltp or 0)}).")
                    self.last_raise_sent[symbol] = now
                    self.pending_raise.pop(symbol, None)
            for symbol, (sent_at, n) in list(self.exit_reminders.items()):
                if symbol not in self.positions or n >= EXIT_REMINDERS:
                    continue
                if now - sent_at >= EXIT_REMINDER_EVERY_S:
                    pos = self.positions[symbol]
                    self.notify(f"🔴 Still open: {self._short(symbol)} × {pos.quantity}, LTP "
                                f"{_fmt(pos.last_ltp or 0)}, stop was {_fmt(pos.stop)}. Exit now.")
                    self.exit_reminders[symbol] = (now, n + 1)

    @staticmethod
    def _short(symbol: str) -> str:
        return symbol.split(":", 1)[-1]


def tag_from_tradebook(trades: list[dict], symbol: str) -> Optional[str]:
    """The QuantOS tag on any of today's BUY fills of `symbol`, else None
    (side 1 = buy in Fyers' tradebook). Conservative on purpose: if a QuantOS
    strategy bought this symbol at all today, the watcher stays out of it."""
    for t in trades:
        if t.get("symbol") != symbol or int(t.get("side") or 0) != 1:
            continue
        tag = t.get("orderTag") or t.get("ordertag")
        if is_quantos_tag(tag):
            return tag
    return None


def _read_rest_positions(app_id: str, token: str) -> list[dict]:
    from fyers_apiv3 import fyersModel
    client = fyersModel.FyersModel(client_id=app_id, token=token, is_async=False, log_path="")
    resp = client.positions()
    if resp.get("s") != "ok":
        raise RuntimeError(f"positions read failed: {resp}")
    return resp.get("netPositions", []) or []


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="agent/config.yaml")
    args = ap.parse_args(argv)

    config = load_config(args.config)
    cfg = config.get("trade_watcher", {}) or {}
    if not cfg.get("enabled", False):
        print("trade_watcher.enabled is false in agent/config.yaml -- nothing to do.")
        return 0
    rules = ExitRules.from_config(cfg)
    app_id = config["credentials"]["api_key"]
    token = TOKEN_PATH.read_text().strip()
    ws_token = f"{app_id}:{token}"

    from fyers_apiv3.FyersWebsocket import order_ws

    notifier = Notifier()
    watcher = Watcher(rules, notifier)
    log_dir = str(Path.home() / ".quantos")

    def _on_positions(msg):
        p = (msg or {}).get("positions") or {}
        if p:
            watcher.on_position(p)

    order_sock = order_ws.FyersOrderSocket(
        access_token=ws_token, log_path=log_dir, reconnect=True,
        on_positions=_on_positions,
        on_connect=lambda: order_sock.subscribe(data_type="OnPositions"),
        on_error=lambda m: print(f"order socket error: {m}", flush=True),
        on_close=lambda m: print(f"order socket closed: {m}", flush=True),
    )

    from fyers_apiv3 import fyersModel
    rest = fyersModel.FyersModel(client_id=app_id, token=token, is_async=False, log_path="")

    def _tag_lookup(symbol: str) -> Optional[str]:
        resp = rest.tradebook()
        if resp.get("s") != "ok":
            raise RuntimeError(f"tradebook read failed: {resp}")
        return tag_from_tradebook(resp.get("tradeBook", []) or [], symbol)

    watcher.tag_lookup = _tag_lookup
    order_sock.connect()

    # Pick up anything already open (e.g. a restart mid-trade).
    for p in _read_rest_positions(app_id, token):
        watcher.on_position(p)
    open_n = len(watcher.positions)
    notifier.send(f"👀 Trade watcher live. Rules: stop {rules.initial_stop_pct:g}%"
                  + (f", breakeven +{rules.breakeven_at_pct:g}%" if rules.breakeven_at_pct > 0 else "")
                  + f", trail {rules.trail_pct:g}% after +{rules.trail_after_pct:g}%. "
                  f"{open_n} open option position(s). Alerts only.")

    # Prices come from REST quotes every PRICE_EVERY_S, not the data socket.
    # 2026-10-07, first two live trades: calling the data socket's
    # subscribe() from the order-socket callback blocked while holding the
    # watcher lock, which froze the price loop. REST polling is one call per
    # loop for all managed symbols, well inside Fyers' rate limits.
    def _rest_prices(symbols: list[str]) -> None:
        resp = rest.quotes({"symbols": ",".join(symbols)})
        if resp.get("s") != "ok":
            print(f"quotes error: {resp}", flush=True)
            return
        for q in resp.get("d", []) or []:
            ltp = (q.get("v") or {}).get("lp")
            if q.get("n") and ltp:
                watcher.on_tick(q["n"], float(ltp))

    token_mtime = TOKEN_PATH.stat().st_mtime
    last_status = 0.0
    while True:
        if time.time() - last_status >= 60:
            last_status = time.time()
            with watcher.lock:
                for p in watcher.positions.values():
                    print(f"[{_now_ist():%H:%M:%S}] {p.symbol} ltp={p.last_ltp} high={p.high} "
                          f"stop={p.stop} trail={p.trail_on}", flush=True)
        time.sleep(PRICE_EVERY_S)
        with watcher.lock:
            symbols = list(watcher.positions)
        if symbols:
            try:
                _rest_prices(symbols)
            except Exception as e:
                print(f"REST quote failed ({e})", flush=True)
        watcher.tick_housekeeping()
        now = _now_ist()
        if (now.hour, now.minute) >= SESSION_END_IST:
            print("Session over -- exiting.", flush=True)
            break
        if TOKEN_PATH.stat().st_mtime != token_mtime:
            print("Fyers token refreshed -- restarting to reconnect with it.", flush=True)
            return 75          # systemd Restart=always brings us back with the new token
    try:
        order_sock.close_connection()
    except Exception:
        pass
    time.sleep(3)              # let the notifier flush
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
