#!/usr/bin/env python3
"""
QuantOS — review_structure: the code ranks the structures, Claude picks one with context
───────────────────────────────────────────────────────────────────────────────────────────
1. core/mcp_tools/market.pick_structure: every structure priced from the live
   chain, strike rules R1-R6, target / stop / stall / flat P&L
2. core/ideas/reviewer: Claude (config/models.yaml "structure_review") reads
   those rows plus levels, OI and the web, and picks one by id or "none";
   code discards anything that isn't a candidate
3. --log: both picks go to the trade-idea log (core/ideas/dual.py), scored
   daily at 15:25, so the reviewer's value is measured, not assumed

Places NO orders. Prints the qorder dry-run line for the final pick when it's
a vertical.

    python scripts/review_structure.py HDFCBANK --bear --target 665 --stop 705 --days 10
    python scripts/review_structure.py INDHOTEL --bull --target 835 --stop 757 --days 10 --log
    python scripts/review_structure.py HDFCBANK --bear --target 665 --stop 705 --days 10 --thesis hold
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ideas import dual, reviewer  # noqa: E402
from core.ideas.log import IST, make_idea  # noqa: E402


def fmt_row(r: dict) -> str:
    flags = "ok" if not r.get("flags") else " | ".join(r["flags"])
    deltas = "/".join(f"{x:+.2f}" for x in r.get("deltas") or [])
    m = r.get("max_at")
    max_at = f"  max@{m['price']:g} {m['label']}" if m else ""
    return (f"{r['id']:<40} entry {r.get('entry')!s:>7}  target {r.get('if_target')!s:>8}  stop {r.get('if_stop_or_stall')!s:>8}"
            f"  flat {r.get('if_flat')!s:>7}  needs {r.get('needs_p')}  delta {deltas}{max_at}  [{flags}]")


def regime_line(ps: dict) -> str:
    v, iv = (ps.get("regime") or {}).get("velocity"), (ps.get("regime") or {}).get("iv") or {}
    vs = f"velocity {v['k']} ({v['label']})" if v else "velocity n/a"
    ivs = (f"ATM IV {iv['iv']:.1%}, rank {iv['rank']} ({iv['label']})" if "rank" in iv
           else f"IV rank n/a ({iv.get('error')})")
    return f"{vs} · {ivs}"


def qorder_line(ps: dict, row: dict) -> str:
    s = dual.structure_of(row, int(ps.get("lot") or 0))
    if not s:
        return ""
    right = "call" if s["kind"] in ("bull_call", "bear_call") else "put"
    code = "<ICICI code>"
    if s["kind"] in ("bull_call", "bear_put"):
        return (f"qorder.py spread-open {code} {s['expiry']} {right} {s['long_strike']:g} {s['short_strike']:g} "
                f"{s['lot']} --max-debit {round(float(row['entry']) * 1.1, 2)}")
    return f"(credit spread: open the long {s['long_strike']:g} first, then sell the {s['short_strike']:g})"


def load_env_file(path: Path) -> None:
    """KEY=VALUE lines from the services' env file (e.g. ANTHROPIC_API_KEY), without overriding
    anything already set. Values are never printed."""
    import os
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbol")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--bull", action="store_true")
    g.add_argument("--bear", action="store_true")
    ap.add_argument("--target", type=float, required=True)
    ap.add_argument("--stop", type=float, required=True)
    ap.add_argument("--days", type=int, required=True)
    ap.add_argument("--thesis", choices=["move", "hold"], default="move")
    ap.add_argument("--budget", type=float, default=0)
    ap.add_argument("--log", action="store_true", help="write both picks to the trade-idea log")
    ap.add_argument("--json", action="store_true", help="print the full result as JSON")
    a = ap.parse_args(argv)

    load_env_file(Path(__file__).resolve().parent.parent / ".env.cloud-api")
    import anthropic
    from core import prompts
    from core.llm.registry import model_for
    from core.mcp_tools import market as mt
    from core.mcp_tools.live import LiveMarket

    market = LiveMarket()
    ps = mt.pick_structure(market, a.symbol, "bull" if a.bull else "bear", a.target, a.stop, a.days,
                           budget=a.budget, thesis=a.thesis)
    if not ps.get("top"):
        print(f"No candidates for {a.symbol}: {ps.get('error') or 'empty chain'}")
        return 1
    rev, ctx = reviewer.review(market, anthropic.Anthropic(timeout=300.0), ps,
                               prompts.load("structure_review_system"), datetime.now(IST))

    print(f"{ps['symbol']} spot {ps['spot']} · ATR {ps.get('atr14')} · {ps['view']['direction']} "
          f"target {a.target:g} stop {a.stop:g} in {a.days}d · thesis {a.thesis}")
    print(regime_line(ps))
    for w in ps.get("warnings") or []:
        print(f"! {w}")
    print("\nCandidates (code-scored, rule-passing first):")
    for r in ctx["candidates"]:
        print("  " + fmt_row(r))
    print(f"\nTool's top: {(rev.tool_top or {}).get('id')}")
    print(f"Reviewer:   {(rev.pick or {}).get('id') or rev.verdict.upper()}  ({rev.verdict})"
          + (f"  error: {rev.error}" if rev.error else ""))
    if rev.reasoning:
        print(f"\n{rev.reasoning}")
    for label, text in (("Why", rev.why), ("Risks", rev.risks), ("Event before expiry", rev.event)):
        if text:
            print(f"{label}: {text}")
    if rev.accepted_flags:
        print(f"Accepted flags: {rev.accepted_flags}")
    if rev.view_score is not None:
        print(f"View score (logged only): {rev.view_score}  {rev.view_reason}")
    if rev.searches:
        print(f"Web searches: {', '.join(rev.searches)}")
    final = rev.final
    if final:
        line = qorder_line(ps, final)
        print(f"\nFinal pick: {final['id']}" + (f"\nDry run: {line}" if line else ""))
    else:
        print("\nFinal pick: none (the reviewer passed on this view)")

    if a.log:
        from scripts.trade_ideas import load, save
        pair = f"{datetime.now(IST):%Y%m%d%H%M}-{ps['symbol']}"
        ideas = load()
        for raw in dual.ideas_for_review(rev, ps, model_for(reviewer.FEATURE), pair):
            idea = make_idea(raw)
            if any(i["id"] == idea["id"] for i in ideas):
                idea["id"] = f"{idea['id']}-{sum(i['id'].startswith(idea['id']) for i in ideas) + 1}"
            ideas.append(idea)
            print(f"logged {idea['id']} ({idea['source']})")
        save(ideas)
    if a.json:
        print(json.dumps({"review": rev.__dict__, "context": ctx}, default=str, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
