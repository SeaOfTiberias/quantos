"""The judgment step of the daily book routine: a model reads the index, the open books and
(on book days) the day's triaged setups, and decides. Code validates every decision before it is
applied (docs/TRADE_REASONING.md; the split follows core/ideas/reviewer.py).

  code   reads the map for the index and every stock involved, walks the books (book.advance),
         triages the day's playbook setups (triage.triage)
  model  writes the index read; may cancel unfilled positions, add index guards, and on a book
         day picks a new book from the actionable setups (ids only, with groups and fill caps)
  code   validates: unknown ids, filled positions, malformed guards and oversize books are
         rejected and reported, never applied. The model never exits a filled position and never
         sets a price: entries, stops and targets are the playbook's.

Only public market data goes into the prompt (index and stock reads, setups, book states); never
holdings, P&L of the account, or anything from ~/.quantos/ other than the price stores. Logged with
core.llm.log_call; model from config/models.yaml ("book_judge").
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Optional

from core.llm.calllog import log_call
from core.llm.registry import model_for

FEATURE = "book_judge"
MAX_POSITIONS = 8
MAX_SETUPS_SHOWN = 60
GUARD_BAND = 0.15            # a guard level within 15% of the index's last close
WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 3,
              "user_location": {"type": "approximate", "country": "IN", "timezone": "Asia/Kolkata"}}
MAX_CONTINUATIONS = 2
REASONING_DOC = Path(__file__).resolve().parents[2] / "docs" / "TRADE_REASONING.md"

SCHEMA = """Answer with your reasoning in prose first (short, concrete, numbers from the context),
then ONE ```json block:

{
  "index_read": "NIFTY and BANKNIFTY: structure, where price sits, what would prove the read wrong (2-4 sentences)",
  "cancels": [{"book": "<book id>", "id": "<position id, must be in that book's live_unfilled>", "why": "..."}],
  "guards":  [{"book": "<book id>", "index": "NIFTY|BANKNIFTY", "below": 0.0, "cancels": "long", "why": "..."}],
  "new_book": null
}

"guards": use "below" with "cancels": "long", or "above" with "cancels": "short". A guard cancels
that side's unfilled positions from the first session the index trades through the level.

"new_book" only when the context says book_day is true; otherwise null. When used:
  {"why": "the book's thesis in 2-3 sentences",
   "positions": [{"id": "<setup id from setups>", "group": "<name>", "priority": 1}],
   "max_fills": {"<group>": 2},
   "guards": [{"index": "NIFTY", "below": 0.0, "cancels": "long", "why": "..."}],
   "passed_on": "the notable setups you did not take and why (1-3 sentences)"}
At most 8 positions. Ids must come from `setups`. Positions in one group share a fill cap.

Empty lists are fine. Never invent prices; you cannot exit a filled position (exits are the
playbook's rules, run by code)."""


def system_prompt() -> str:
    doc = REASONING_DOC.read_text(encoding="utf-8") if REASONING_DOC.exists() else ""
    return ("You are the trading analyst for QuantOS, a household NSE trading terminal. You make the "
            "book decisions yourself; code validates them. Paper book: nothing you decide places an "
            "order. Follow this procedure, which is the project's own:\n\n" + doc + "\n\n" + SCHEMA)


# ─── context ─────────────────────────────────────────────────────────────────

def brief_read(l1: dict, n_zones: int = 4) -> dict:
    """What the model needs from a full L1 read: states, protected/weak levels, last events and
    the nearest zones above and below the price."""
    if not l1 or "error" in l1:
        return {"error": (l1 or {}).get("error", "no read")}
    price = l1.get("price")
    tf = {}
    for k in ("M", "W", "D"):
        t = l1["tf"].get(k) or {}
        tf[k] = dict(state=t.get("state"), protected=(t.get("protected") or {}).get("price"),
                     weak=(t.get("weak") or {}).get("price"), last_event=t.get("last_event"),
                     atr=t.get("atr"))
    zones = (l1.get("htf") or {}).get("zones") or []
    above = sorted((z for z in zones if z["low"] > price), key=lambda z: z["low"])[:n_zones]
    below = sorted((z for z in zones if z["high"] < price), key=lambda z: -z["high"])[:n_zones]
    inside = [z for z in zones if z["low"] <= price <= z["high"]]
    zs = lambda xs: [dict(low=z["low"], high=z["high"], strong=z.get("strong"), why=z.get("why", "")[:120])
                     for z in xs]
    return dict(price=price, last_date=l1.get("last_date"), tf=tf, atr_w=(l1.get("htf") or {}).get("atr_w"),
                zones_above=zs(above), zones_below=zs(below), inside=zs(inside))


def book_view(book: dict, rows: list[dict], scores: Optional[dict], reads: dict) -> dict:
    return dict(id=book["id"], made=book["made"], why=book.get("why"), rules=book.get("rules"),
                positions=[dict(id=r["id"], side=r["side"], group=r["group"], status=r["status"],
                                reason=r.get("reason"), fill=r.get("fill"),
                                entry=r["setup"]["entry"], stop=r["setup"]["stop"], target=r["setup"]["target"],
                                r=(r["res"].get("r") if not r.get("book_cancel") else None),
                                now=reads.get(r["sym"]))
                           for r in rows],
                live_unfilled=[r["id"] for r in rows if r["status"] == "pending"],
                score=scores)


def build_context(as_of: str, index_reads: dict, books: list[dict], setups: Optional[list[dict]],
                  book_day: bool) -> dict:
    return dict(as_of=as_of, book_day=book_day, index=index_reads, open_books=books,
                setups=(setups or [])[:MAX_SETUPS_SHOWN] if book_day else [])


# ─── answer ──────────────────────────────────────────────────────────────────

_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)


def parse_answer(text: str) -> Optional[dict]:
    for raw in reversed(_JSON_BLOCK.findall(text or "")):
        try:
            d = json.loads(raw)
            if isinstance(d, dict):
                return d
        except ValueError:
            continue
    return None


def _guard(g: Any, closes: dict) -> tuple[Optional[dict], Optional[str]]:
    if not isinstance(g, dict):
        return None, "guard is not an object"
    idx = g.get("index")
    if idx not in closes:
        return None, f"guard index {idx!r} unknown"
    side = g.get("cancels")
    key = "below" if side == "long" else "above" if side == "short" else None
    if key is None or key not in g:
        return None, "guard needs below+long or above+short"
    try:
        lvl = float(g[key])
    except (TypeError, ValueError):
        return None, f"guard level {g.get(key)!r} is not a number"
    c = closes[idx]
    if not c or abs(lvl / c - 1) > GUARD_BAND:
        return None, f"guard level {lvl:g} is more than {GUARD_BAND:.0%} from {idx} {c:g}"
    if (key == "below" and lvl >= c) or (key == "above" and lvl <= c):
        return None, f"guard {key} {lvl:g} is already breached ({idx} {c:g})"
    return {"index": idx, key: lvl, "cancels": side, "why": str(g.get("why", ""))[:300]}, None


def validate(answer: Optional[dict], ctx: dict, closes: dict) -> tuple[dict, list[str]]:
    """The decisions that pass, and every rejection with its reason."""
    out = dict(index_read="", cancels=[], guards=[], new_book=None)
    errors: list[str] = []
    if not isinstance(answer, dict):
        return out, ["no JSON answer"]
    out["index_read"] = str(answer.get("index_read", ""))[:1200]
    live = {b["id"]: set(b["live_unfilled"]) for b in ctx["open_books"]}
    for c in answer.get("cancels") or []:
        b, i = (c or {}).get("book"), (c or {}).get("id")
        if b not in live:
            errors.append(f"cancel: unknown book {b!r}")
        elif i not in live[b]:
            errors.append(f"cancel: {i!r} is not a live unfilled position of book {b}")
        else:
            out["cancels"].append(dict(book=b, id=i, why=str(c.get("why", ""))[:300]))
    for g in answer.get("guards") or []:
        b = (g or {}).get("book")
        if b not in live:
            errors.append(f"guard: unknown book {b!r}")
            continue
        ok, err = _guard(g, closes)
        if err:
            errors.append(f"guard ({b}): {err}")
        else:
            out["guards"].append(dict(ok, book=b))
    nb = answer.get("new_book")
    if nb:
        if not ctx.get("book_day"):
            errors.append("new_book: not a book day")
        elif not isinstance(nb, dict):
            errors.append("new_book: not an object")
        else:
            ids = {s["id"] for s in ctx["setups"]}
            pos, seen = [], set()
            for p in nb.get("positions") or []:
                i = (p or {}).get("id")
                if i not in ids:
                    errors.append(f"new_book: {i!r} is not an actionable setup")
                elif i in seen:
                    errors.append(f"new_book: {i!r} twice")
                else:
                    seen.add(i)
                    try:
                        prio = int(p.get("priority") or 99)
                    except (TypeError, ValueError):
                        prio = 99
                    pos.append(dict(id=i, group=str(p.get("group") or i)[:40], priority=prio))
            if len(pos) > MAX_POSITIONS:
                errors.append(f"new_book: {len(pos)} positions, cut to {MAX_POSITIONS} by priority")
                pos = sorted(pos, key=lambda p: p["priority"])[:MAX_POSITIONS]
            caps = {}
            for g, n in (nb.get("max_fills") or {}).items():
                try:
                    if int(n) >= 1 and any(p["group"] == g for p in pos):
                        caps[str(g)] = int(n)
                    else:
                        errors.append(f"new_book: max_fills {g}={n} ignored")
                except (TypeError, ValueError):
                    errors.append(f"new_book: max_fills {g}={n!r} is not a number")
            guards = []
            for g in nb.get("guards") or []:
                ok, err = _guard(g, closes)
                if err:
                    errors.append(f"new_book guard: {err}")
                else:
                    guards.append(ok)
            if pos:
                out["new_book"] = dict(why=str(nb.get("why", ""))[:800], passed_on=str(nb.get("passed_on", ""))[:600],
                                       positions=pos, max_fills=caps, guards=guards)
            else:
                errors.append("new_book: no valid positions")
    return out, errors


# ─── the call ────────────────────────────────────────────────────────────────

def call_claude(client, context: dict) -> tuple[Optional[str], list[str]]:
    """One judgment: web search allowed (results dates, events), pause_turn resumed, refusal -> None."""
    model = model_for(FEATURE)
    messages: list[dict] = [{"role": "user", "content": json.dumps(context, separators=(",", ":"), default=str)}]
    response, searches = None, []
    for _ in range(MAX_CONTINUATIONS + 1):
        started, response = time.perf_counter(), None
        try:
            response = client.beta.messages.create(
                model=model, max_tokens=16000, system=system_prompt(), output_config={"effort": "high"},
                tools=[WEB_SEARCH], messages=messages,
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            )
        finally:
            log_call(FEATURE, model, response, started)
        for b in response.content or []:
            if getattr(b, "type", "") == "web_search_tool_result":
                c = getattr(b, "content", None)
                searches.append(f"ok:{len(c)}" if isinstance(c, list) else "error")
        if response.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": response.content}]
    if response is None or response.stop_reason == "refusal":
        return None, searches
    text = "\n".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()
    return text or None, searches
