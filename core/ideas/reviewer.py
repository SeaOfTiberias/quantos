"""
QuantOS — Structure reviewer: an LLM picks among code-scored candidates
────────────────────────────────────────────────────────────────────────
The 2026-10-25 HDFC Bank review showed where a model adds value to option
structure choice: context the arithmetic can't see -- how slowly the stock
moves, support and resistance on the way to the target, an event before
expiry, whether the view itself is sound. It also showed where a model
doesn't: its own option math and an uncovered ratio spread.

So the split is:
  code   core/ideas/structure.candidates() prices every structure from the live
         chain, applies strike rules R1-R6 and scores target / stop / stall /
         flat (core/mcp_tools/market.pick_structure returns the rows)
  model  reads those rows plus public market context (and the web, for events
         and news), picks ONE row by id or "none", and says why
  code   validates the pick: an id that isn't a candidate is discarded and the
         tool's top pick stands

It also rates the view itself (view_score 0-1, view_reason). That rating
changes nothing -- not the pick, not the size; it is logged next to each idea
so that, once enough are scored, we can test whether the model's doubts
predicted the losers before giving it any say over direction.

Only public market data goes into the prompt: the symbol, the view, quotes,
levels, OI build-up and the candidate rows. Never quantity held, P&L or the
account. Logged with core.llm.log_call; model from config/models.yaml
("structure_review").
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from core.llm.calllog import log_call
from core.llm.registry import model_for

FEATURE = "structure_review"
MAX_CANDIDATES = 10
WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 2,
              "user_location": {"type": "approximate", "country": "IN", "timezone": "Asia/Kolkata"}}
MAX_CONTINUATIONS = 2
CANDIDATE_KEYS = ("structure", "expiry", "entry", "if_target", "if_stop_or_stall", "if_stall", "if_flat", "worst",
                  "needs_p", "ev_per_worst", "fits", "flags", "deltas", "net_delta", "max_at")


def candidate_id(row: dict) -> str:
    return f"{row['structure']} {row.get('expiry') or ''}".strip()


def shortlist(ps: dict, n: int = MAX_CANDIDATES) -> list[dict]:
    """The rows the model sees: the tool's top rows, then the best of each family, de-duplicated,
    each with an `id`."""
    out, seen = [], set()
    for row in (ps.get("top") or []) + (ps.get("best_by_family") or []):
        cid = candidate_id(row)
        if cid in seen:
            continue
        seen.add(cid)
        out.append({"id": cid, **{k: row.get(k) for k in CANDIDATE_KEYS}})
        if len(out) >= n:
            break
    return out


def build_context(ps: dict, stock: dict, market: dict, as_of: str) -> dict:
    v = ps.get("view") or {}
    return {
        "as_of_ist": as_of,
        "symbol": ps.get("symbol"),
        "view": {k: v.get(k) for k in ("direction", "target", "stop", "days", "thesis")},
        "spot": ps.get("spot"), "lot_size": ps.get("lot"), "atr14": ps.get("atr14"),
        "regime": ps.get("regime"), "warnings": ps.get("warnings") or [],
        "stock": stock, "market": market,
        "candidates": shortlist(ps),
    }


_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)


def parse_answer(text: str) -> Optional[dict]:
    """The last ```json block, or failing that the last {...} in the text."""
    blocks = _JSON_BLOCK.findall(text or "")
    cands = blocks or re.findall(r"(\{[^{}]*\"pick\"[^{}]*\})", text or "", re.S)
    for raw in reversed(cands):
        try:
            d = json.loads(raw)
            if isinstance(d, dict) and "pick" in d:
                return d
        except ValueError:
            continue
    return None


@dataclass
class Review:
    tool_top: Optional[dict]                  # the code's first row (rule-passing first)
    pick: Optional[dict] = None               # the model's chosen row; None = "none" or invalid
    verdict: str = "tool"                     # "agree" | "differ" | "none" | "invalid" | "error"
    why: str = ""
    risks: str = ""
    event: str = ""
    fits_view: Optional[bool] = None
    accepted_flags: list = field(default_factory=list)
    reasoning: str = ""
    error: str = ""
    searches: list = field(default_factory=list)   # per web search: "ok:<n results>" or "error:<code>"
    view_score: Optional[float] = None        # the model's 0-1 rating of the view itself: logged, never acted on
    view_reason: str = ""

    @property
    def final(self) -> Optional[dict]:
        """What to trade: the model's valid pick, else the tool's top (never on an explicit "none")."""
        if self.verdict == "none":
            return None
        return self.pick or self.tool_top


def validate(answer: Optional[dict], candidates: list[dict], text: str = "") -> Review:
    top = candidates[0] if candidates else None
    r = Review(tool_top=top, reasoning=(text or "").split("```")[0].strip()[:1500])
    if answer is None:
        r.verdict, r.error = "invalid", "no JSON answer"
        return r
    r.why, r.risks = str(answer.get("why", ""))[:600], str(answer.get("risks", ""))[:600]
    r.event = str(answer.get("event_before_expiry", ""))[:300]
    r.fits_view = answer.get("fits_view") if isinstance(answer.get("fits_view"), bool) else None
    r.accepted_flags = [str(x) for x in (answer.get("accepted_flags") or [])][:6]
    try:
        vs = float(answer.get("view_score"))
        r.view_score = round(vs, 2) if 0.0 <= vs <= 1.0 else None
    except (TypeError, ValueError):
        r.view_score = None
    r.view_reason = str(answer.get("view_reason", ""))[:300]
    pick = str(answer.get("pick", "")).strip()
    if pick.lower() == "none":
        r.verdict = "none"
        return r
    by_id = {c["id"]: c for c in candidates}
    if pick not in by_id:
        r.verdict, r.error = "invalid", f"pick {pick!r} is not a candidate id"
        return r
    r.pick = by_id[pick]
    r.verdict = "agree" if top and pick == top["id"] else "differ"
    return r


def search_outcomes(content) -> list[str]:
    """Each web_search_tool_result block: "ok:<n>" for a result list, "error:<code>" for an error object."""
    out = []
    for b in content or []:
        if getattr(b, "type", "") != "web_search_tool_result":
            continue
        c = getattr(b, "content", None)
        out.append(f"ok:{len(c)}" if isinstance(c, list) else f"error:{getattr(c, 'error_code', None) or c}")
    return out


def call_claude(client, context: dict, system: str, searches: Optional[list] = None) -> Optional[str]:
    """One review: web search allowed, pause_turn resumed, refusal -> None. Appends each search's
    outcome to `searches` when given."""
    model = model_for(FEATURE)
    messages: list[dict] = [{"role": "user", "content": json.dumps(context, separators=(",", ":"), default=str)}]
    response = None
    for _ in range(MAX_CONTINUATIONS + 1):
        started, response = time.perf_counter(), None
        try:
            response = client.beta.messages.create(
                model=model, max_tokens=16000, system=system, output_config={"effort": "high"},
                tools=[WEB_SEARCH], messages=messages,
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            )
        finally:
            log_call(FEATURE, model, response, started)
        if searches is not None:
            searches += search_outcomes(response.content)
        if response.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": response.content}]
    if response is None or response.stop_reason == "refusal":
        return None
    return "\n".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip() or None


def stock_context(market, symbol: str) -> tuple[dict, dict]:
    """Public data for the prompt, best effort: (stock, market)."""
    from core.mcp_tools import market as mt
    stock: dict[str, Any] = {}
    mkt: dict[str, Any] = {}
    try:
        q = {r["symbol"]: r for r in mt.quote(market, [symbol, "NIFTY", "BANKNIFTY"])}
        s = q.get(symbol.upper(), {})
        stock["today"] = {k: s.get(k) for k in ("ltp", "open", "high", "low", "prev_close", "chg_pct")}
        mkt = {"nifty_chg_pct": q.get("NIFTY", {}).get("chg_pct"),
               "banknifty_chg_pct": q.get("BANKNIFTY", {}).get("chg_pct")}
    except Exception as e:
        stock["quote_error"] = type(e).__name__
    try:
        lv = mt.levels(market, symbol)
        stock.update({k: lv.get(k) for k in ("as_of", "close", "atr14", "atr_pct", "ema9", "ema21", "sma50", "sma200",
                                             "high_52w", "low_52w", "trend", "box", "retest_plans", "recent")})
    except Exception as e:
        stock["levels_error"] = type(e).__name__
    try:
        oi = mt.oi_buildup(market, symbol)
        if "label" in oi:
            stock["oi_5d"] = {k: oi[k] for k in ("label", "price_chg_pct", "oi_chg_pct")}
    except Exception:
        pass
    return stock, mkt


def review(market, client, ps: dict, system: str, as_of: Optional[datetime] = None) -> tuple[Review, dict]:
    """Run one review for a pick_structure result `ps`. Returns (Review, the context sent)."""
    stock, mkt = stock_context(market, ps["symbol"])
    ctx = build_context(ps, stock, mkt, (as_of or datetime.now()).isoformat(timespec="minutes"))
    searches: list[str] = []
    try:
        text = call_claude(client, ctx, system, searches)
    except Exception as e:
        r = validate(None, ctx["candidates"])
        r.verdict, r.error = "error", f"{type(e).__name__}: {e}"[:300]
        return r, ctx
    if text is None:
        r = validate(None, ctx["candidates"])
        r.verdict, r.error, r.searches = "error", "no answer (refusal or empty)", searches
        return r, ctx
    r = validate(parse_answer(text), ctx["candidates"], text)
    r.searches = searches
    return r, ctx
