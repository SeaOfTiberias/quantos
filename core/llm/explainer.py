"""
QuantOS — trade-event explainer (docs/TERMINAL_ARCHITECTURE.md §5.1: "LLMs explain, code decides")
─────────────────────────────────────────────────────────────────────────────────────────────────────
When a watcher's rule fires (close, target, emergency, time) or a held stock
opens with a sharp gap, the alert goes out at once, exactly as before. Then,
in a background thread, one Claude call (with up to two web searches for the
day's news) writes 2-3 sentences on WHY the stock is moving -- market-wide,
sector or stock-specific -- and that arrives as a follow-up message. It never
changes, delays or blocks the alert, and it never advises.

Data sent to Claude: the symbol, the structure and direction, the rule that
fired and its levels, and public market data. Never quantity, P&L or the
account (P2 stays home; §5.5). Capped per day (`max_per_day`). Off unless
`trade_explainer.enabled` is true in agent/config.yaml.
"""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from core.llm.calllog import log_call
from core.llm.registry import model_for

IST = timezone(timedelta(hours=5, minutes=30))
STATE_PATH = Path.home() / ".quantos" / "trade_explainer_state.json"
FEATURE = "trade_explainer"
WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 2,
              "user_location": {"type": "approximate", "country": "IN", "timezone": "Asia/Kolkata"}}
MAX_CONTINUATIONS = 2
FORBIDDEN_KEYS = {"qty", "quantity", "lots", "pnl", "p_and_l", "account", "avg_price", "entry_cost", "max_loss",
                  "max_profit", "last_pnl", "peak_pnl"}


def gap_atr(open_px: Optional[float], prev_close: Optional[float], atr: Optional[float]) -> Optional[float]:
    """Today's opening gap in ATRs (signed), or None without the inputs."""
    if not open_px or not prev_close or not atr:
        return None
    return round((open_px - prev_close) / atr, 2)


def redact(d: Any) -> Any:
    """Drop household fields (quantity, P&L, account) at any depth."""
    if isinstance(d, dict):
        return {k: redact(v) for k, v in d.items() if k.lower() not in FORBIDDEN_KEYS}
    if isinstance(d, list):
        return [redact(x) for x in d]
    return d


def market_context(market, symbol: str) -> dict:
    """Public market data for the prompt, best effort: the stock vs Nifty / Bank Nifty today,
    ATR, the 5-session futures OI build-up."""
    from core.mcp_tools import market as mt
    ctx: dict[str, Any] = {}
    try:
        q = {r["symbol"]: r for r in mt.quote(market, [symbol, "NIFTY", "BANKNIFTY"])}
        s = q.get(symbol.upper(), {})
        ctx["stock_today"] = {k: s.get(k) for k in ("ltp", "open", "high", "low", "prev_close", "chg_pct")}
        ctx["nifty_chg_pct"] = q.get("NIFTY", {}).get("chg_pct")
        ctx["banknifty_chg_pct"] = q.get("BANKNIFTY", {}).get("chg_pct")
    except Exception as e:
        ctx["quote_error"] = type(e).__name__
    try:
        lv = mt.levels(market, symbol)
        ctx.update(atr14=lv.get("atr14"), atr_pct=lv.get("atr_pct"), trend=lv.get("trend"),
                   high_52w=lv.get("high_52w"), low_52w=lv.get("low_52w"))
    except Exception as e:
        ctx["levels_error"] = type(e).__name__
    try:
        oi = mt.oi_buildup(market, symbol)
        if "label" in oi:
            ctx["oi_5d"] = {k: oi[k] for k in ("label", "price_chg_pct", "oi_chg_pct")}
    except Exception:
        pass
    if ctx.get("stock_today") and ctx.get("atr14"):
        g = gap_atr(ctx["stock_today"].get("open"), ctx["stock_today"].get("prev_close"), ctx["atr14"])
        if g is not None:
            ctx["open_gap_atr"] = g
    return ctx


def call_claude(client, context: dict) -> Optional[str]:
    """One explanation. Server-side web search; pause_turn resumed up to MAX_CONTINUATIONS;
    a refusal or empty answer returns None."""
    import time
    from core import prompts
    model = model_for(FEATURE)
    user = json.dumps(context, separators=(",", ":"), default=str)
    messages: list[dict] = [{"role": "user", "content": user}]
    response = None
    for _ in range(MAX_CONTINUATIONS + 1):
        started, response = time.perf_counter(), None
        try:
            response = client.beta.messages.create(
                model=model, max_tokens=2000, system=prompts.load("trade_explainer_system"),
                output_config={"effort": "low"}, tools=[WEB_SEARCH], messages=messages,
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            )
        finally:
            log_call(FEATURE, model, response, started)
        if response.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": response.content}]
    if response is None or response.stop_reason == "refusal":
        return None
    text = " ".join(b.text.strip() for b in response.content if getattr(b, "type", "") == "text").strip()
    return text or None


def _load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


class Explainer:
    """Background follow-ups for watcher alerts. `send` is the watcher's Telegram sender;
    `market_factory` builds a Market (core/mcp_tools/live.LiveMarket) lazily, once."""

    def __init__(self, cfg: Optional[dict], send: Callable[[str], None], market_factory: Callable[[], Any] = None,
                 client_factory: Callable[[], Any] = None, state_path: Path = STATE_PATH, run_async: bool = True):
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", False))
        self.max_per_day = int(cfg.get("max_per_day", 12))
        self.gap_threshold = float(cfg.get("gap_atr", 1.0))
        self.send = send
        self.state_path = state_path
        self.run_async = run_async
        self._market_factory = market_factory or self._live_market
        self._client_factory = client_factory or self._anthropic
        self._market = None
        self._client = None
        self._lock = threading.Lock()

    @staticmethod
    def _live_market():
        from core.mcp_tools.live import LiveMarket
        return LiveMarket()

    @staticmethod
    def _anthropic():
        import anthropic
        return anthropic.Anthropic(timeout=90.0)

    def _today_state(self) -> dict:
        s = _load_state(self.state_path)
        today = datetime.now(IST).date().isoformat()
        return s if s.get("date") == today else {"date": today, "count": 0, "gap_checked": []}

    def _save(self, s: dict) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(s))
        except OSError:
            pass

    def _take_slot(self) -> bool:
        with self._lock:
            s = self._today_state()
            if s["count"] >= self.max_per_day:
                return False
            s["count"] += 1
            self._save(s)
            return True

    def market(self):
        if self._market is None:
            self._market = self._market_factory()
        return self._market

    # ── public ────────────────────────────────────────────────────────────────

    def explain(self, symbol: str, event: dict) -> None:
        """Queue a follow-up explanation for an alert that was just sent."""
        if not self.enabled or not self._take_slot():
            return
        job = lambda: self._run(symbol, event)  # noqa: E731
        if self.run_async:
            threading.Thread(target=job, daemon=True).start()
        else:
            job()

    def check_gap(self, key: str, symbol: str, label: str, side: int) -> None:
        """Once per position per day: an opening gap of >= gap_atr ATRs sends an alert, then context.
        `side` = +1 if the position gains when the stock rises, -1 if it gains when it falls."""
        if not self.enabled or key in self._today_state()["gap_checked"]:
            return
        try:
            ctx = market_context(self.market(), symbol)
        except Exception as e:
            print(f"explainer: gap check for {symbol} failed ({e})", flush=True)
            return
        g = ctx.get("open_gap_atr")
        if g is None:                      # no open yet (or no ATR): try again on the next pass
            return
        with self._lock:
            s = self._today_state()
            if key in s["gap_checked"]:
                return
            s["gap_checked"].append(key)
            self._save(s)
        if abs(g) < self.gap_threshold:
            return
        good = (g > 0) == (side > 0)
        st = ctx.get("stock_today") or {}
        self.send(f"⚡ GAP {label}: {symbol} opened {st.get('open')} vs {st.get('prev_close')} prev close "
                  f"({g:+.1f} ATR) -- {'in your favour' if good else 'AGAINST the position'}. The plan's levels "
                  "still decide; check the emergency stop.")
        self.explain(symbol, {"alert": "opening gap", "gap_atr": g, "position_direction":
                              "gains if the stock rises" if side > 0 else "gains if the stock falls"})

    def _run(self, symbol: str, event: dict) -> None:
        try:
            ctx = {"symbol": symbol.upper(), **redact(event)}
            ctx["market"] = market_context(self.market(), symbol)
            ctx["as_of_ist"] = datetime.now(IST).isoformat(timespec="minutes")
            if self._client is None:
                self._client = self._client_factory()
            text = call_claude(self._client, ctx)
            if text:
                self.send(f"🧠 {symbol.upper()}: {text}")
        except Exception as e:
            print(f"explainer: {symbol} failed ({type(e).__name__}: {e})", flush=True)
