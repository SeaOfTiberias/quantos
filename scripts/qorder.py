#!/usr/bin/env python3
"""
QuantOS — qorder: orders the user releases, ICICI Direct (Breeze), from the VM
───────────────────────────────────────────────────────────────────────────────
A model may draft the command; nothing is sent without --yes, which is the
user's release. Every order goes through core/orders/gateway.py: the checks
in core/orders/checks.py, then the journal (~/.quantos/orders.jsonl). With
`orders: {live: false}` in agent/config.yaml the gateway journals "paper" and
sends nothing; ~/.quantos/ORDERS_OFF stops everything.

Codes are ICICI's (INDHOT for INDHOTEL, TCS, NESIND). EXPIRY is YYYY-MM-DD.
Option legs take --right call|put --strike K. Prices are limits.

  qorder quote CODE EXPIRY [--right R --strike K]
  qorder buy|sell CODE EXPIRY QTY LIMIT [--right R --strike K] [--exit] [--yes]
  qorder work buy|sell CODE EXPIRY QTY [--right R --strike K] [--exit] [--yes]
                                     marketable limit at the touch, re-priced until filled
  qorder spread-open CODE EXPIRY RIGHT LONG_K SHORT_K QTY --max-debit D [--yes]
                                     buys the long leg first, then sells the short leg
  qorder spread-close CODE EXPIRY RIGHT LONG_K SHORT_K QTY [--yes]
                                     buys back the short leg first, then sells the long leg
  qorder oco CODE EXPIRY --target T --stop S [--yes]
                                     resting target + stop (GTT) on the open futures position
  qorder status OID | cancel OID [--yes] | gtt-book | gtt-cancel GID [--yes] | book | journal [N]

Places orders only for the spouse's ICICI Direct account; the son's account
can't be named here at all (core/orders/checks.Limits.accounts).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.auth import breeze_auth  # noqa: E402
from core.orders.checks import Intent, round_tick  # noqa: E402
from core.orders.gateway import JOURNAL, Gateway, limits_from  # noqa: E402

CONFIG_PATH = Path(__file__).resolve().parent.parent / "agent" / "config.yaml"
ACCOUNT = "icici-spouse"


def orders_cfg() -> dict:
    try:
        import yaml
        return (yaml.safe_load(CONFIG_PATH.read_text()) or {}).get("orders") or {}
    except Exception:
        return {}


def leg(a, action: str, qty: int, price: float = 0.05, purpose: str = "entry", **kw) -> Intent:
    right = (getattr(a, "right", None) or "others").lower()
    strike = float(getattr(a, "strike", None) or 0)
    return Intent(account=ACCOUNT, product="options" if right != "others" else "futures", code=a.code.upper(),
                  expiry=date.fromisoformat(a.expiry), action=action, qty=int(qty), price=price,
                  purpose=purpose, right=right, strike=strike, **kw)


def ticket(i: Intent) -> str:
    what = "FUT" if i.product == "futures" else f"{i.strike:g} {'CE' if i.right == 'call' else 'PE'}"
    trig = f" trigger {i.trigger:g}" if i.trigger else ""
    return f"{i.action.upper()} {i.qty} {i.code} {i.expiry:%d-%b-%Y} {what} @ {i.price:g}{trig} [{i.purpose}]"


def dry(g: Gateway, i: Intent) -> int:
    """Without --yes: show the ticket and what the checks say, send nothing."""
    from core.orders.checks import check
    reasons = check(i, g.context(i), g.limits)
    print("TICKET ", ticket(i))
    print("CHECKS ", "pass" if not reasons else "FAIL: " + "; ".join(reasons))
    print("Not sent. Add --yes to release it." + ("" if g.live else " (orders.live is false: it would be paper)"))
    return 0 if not reasons else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="qorder", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def inst(p, opt=True):
        p.add_argument("code")
        p.add_argument("expiry")
        if opt:
            p.add_argument("--right", choices=["call", "put"])
            p.add_argument("--strike", type=float)

    q = sub.add_parser("quote"); inst(q)
    for side in ("buy", "sell"):
        p = sub.add_parser(side); inst(p)
        p.add_argument("qty", type=int); p.add_argument("limit", type=float)
        p.add_argument("--exit", action="store_true"); p.add_argument("--yes", action="store_true")
    w = sub.add_parser("work")
    w.add_argument("action", choices=["buy", "sell"]); inst(w)
    w.add_argument("qty", type=int); w.add_argument("--exit", action="store_true"); w.add_argument("--yes", action="store_true")
    for name in ("spread-open", "spread-close"):
        p = sub.add_parser(name); inst(p, opt=False)
        p.add_argument("right", choices=["call", "put"]); p.add_argument("long_k", type=float)
        p.add_argument("short_k", type=float); p.add_argument("qty", type=int)
        if name == "spread-open":
            p.add_argument("--max-debit", type=float, required=True)
        p.add_argument("--yes", action="store_true")
    o = sub.add_parser("oco"); inst(o, opt=False)
    o.add_argument("--target", type=float, required=True); o.add_argument("--stop", type=float, required=True)
    o.add_argument("--yes", action="store_true")
    s = sub.add_parser("status"); s.add_argument("oid")
    c = sub.add_parser("cancel"); c.add_argument("oid"); c.add_argument("--yes", action="store_true")
    sub.add_parser("gtt-book")
    gc = sub.add_parser("gtt-cancel"); gc.add_argument("gid"); gc.add_argument("--yes", action="store_true")
    sub.add_parser("book")
    j = sub.add_parser("journal"); j.add_argument("n", nargs="?", type=int, default=20)
    a = ap.parse_args(argv)

    if a.cmd == "journal":
        for line in (JOURNAL.read_text().splitlines() if JOURNAL.exists() else [])[-a.n:]:
            r = json.loads(line)
            print(r["ts"], r["kind"], "SENT" if r["sent"] else ("ok-paper" if r["ok"] else "REFUSED"),
                  r.get("order_id") or "", (r.get("intent") or {}).get("code", ""), "; ".join(r.get("reasons") or []))
        return 0

    cfg = orders_cfg()
    g = Gateway(breeze_auth.connect(), account=ACCOUNT, live=bool(cfg.get("live")), limits=limits_from(cfg))

    if a.cmd == "quote":
        print(g.quote(leg(a, "buy", 1)))
        return 0
    if a.cmd in ("buy", "sell"):
        i = leg(a, a.cmd, a.qty, a.limit, "exit" if a.exit else "entry")
        if not a.yes:
            return dry(g, i)
        r = g.place(i)
        print(ticket(i), "->", r)
        return 0 if r.ok else 1
    if a.cmd == "work":
        i = leg(a, a.action, a.qty, purpose="exit" if a.exit else "entry")
        q = g.quote(i)
        i = replace(i, price=round_tick((q["ask"] if a.action == "buy" else q["bid"]) or 0.05, up=a.action == "buy"))
        if not a.yes:
            return dry(g, i)
        r = g.work(i)
        print(ticket(i), "->", r)
        return 0 if r.ok else 1
    if a.cmd in ("spread-open", "spread-close"):
        lng = leg(argparse.Namespace(code=a.code, expiry=a.expiry, right=a.right, strike=a.long_k), "buy", a.qty)
        sht = leg(argparse.Namespace(code=a.code, expiry=a.expiry, right=a.right, strike=a.short_k), "sell", a.qty)
        ql, qs = g.quote(lng), g.quote(sht)
        if a.cmd == "spread-open":
            debit = (ql["ask"] or 0) - (qs["bid"] or 0)
            print(f"long {a.long_k:g} ask {ql['ask']} · short {a.short_k:g} bid {qs['bid']} · debit {debit:.2f} "
                  f"(max {a.max_debit:g}) · max loss ₹{debit * a.qty:,.0f}")
            if not ql["ask"] or not qs["bid"] or debit > a.max_debit:
                print("REFUSED: no quotes, or the debit is over --max-debit")
                return 1
            first, second = replace(lng, price=round_tick(ql["ask"], True)), replace(sht, price=round_tick(qs["bid"], False))
        else:
            first = replace(sht, action="buy", purpose="exit", price=round_tick(qs["ask"] or 0.05, True))
            second = replace(lng, action="sell", purpose="exit", price=round_tick(ql["bid"] or 0.05, False))
            print(f"close: buy back {a.short_k:g} at ~{qs['ask']}, then sell {a.long_k:g} at ~{ql['bid']}")
        if not a.yes:
            dry(g, first)
            print("SECOND", ticket(second), "(checked after the first fills)")
            return 0
        r1 = g.work(first)
        print("1.", ticket(first), "->", r1)
        if not r1.ok:
            print("Stopped: the first leg didn't fill, so the second wasn't sent.")
            return 1
        r2 = g.work(second)
        print("2.", ticket(second), "->", r2)
        if not r2.ok:
            print("⚠️  Second leg NOT filled. Open now:",
                  "a lone long option (max loss = its premium)" if a.cmd == "spread-open"
                  else "the long leg only (the short was bought back)")
        return 0 if r2.ok else 1
    if a.cmd == "oco":
        held = g.positions()
        key = (a.code.upper(), date.fromisoformat(a.expiry), "others", 0.0)
        qty = held.get(key, 0)
        if not qty:
            print(f"No open futures position in {key}.")
            return 1
        act, up = ("sell", False) if qty > 0 else ("buy", True)
        slip = 0.01 if qty > 0 else -0.01
        base = leg(argparse.Namespace(code=a.code, expiry=a.expiry), act, abs(qty), gtt=True)
        tgt = replace(base, price=round_tick(a.target, up), trigger=round_tick(a.target, up), purpose="target")
        stp = replace(base, price=round_tick(a.stop * (1 - slip), up), trigger=round_tick(a.stop, up), purpose="stop")
        print("TARGET", ticket(tgt)); print("STOP  ", ticket(stp))
        if not a.yes:
            print("Not sent. Add --yes to release it.")
            return 0
        r = g.place_oco(tgt, stp, positions=held)
        print("->", r)
        if r.ok and r.sent:
            print("in the broker's GTT book:", g.verify_gtt(r.order_id))
        return 0 if r.ok else 1
    if a.cmd == "status":
        print(g.status(a.oid))
        return 0
    if a.cmd in ("cancel", "gtt-cancel"):
        oid = a.oid if a.cmd == "cancel" else a.gid
        if not a.yes:
            print(f"Would cancel {oid}. Add --yes.")
            return 0
        print(g.cancel(oid) if a.cmd == "cancel" else g.cancel_gtt(oid))
        return 0
    if a.cmd == "gtt-book":
        for x in g.gtt_book():
            print(x)
        return 0
    if a.cmd == "book":
        for k, v in g.positions().items():
            print(k, v)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
