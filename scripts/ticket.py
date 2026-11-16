#!/usr/bin/env python3
"""
QuantOS — draft an entry ticket for the release page (#/release)
────────────────────────────────────────────────────────────────
Code drafts, code checks, the user releases. This writes a pending ticket and sends nothing;
the user releases it from the dashboard with a one-time code. The strategies' evening jobs will
call core.orders.tickets.Store.draft directly; this CLI is for drafting by hand and for testing
the page in paper mode.

  ticket buy CODE EXPIRY QTY LIMIT [--right call|put --strike K] --symbol NSE --why TEXT
         [--stop S --target T --valid-until 2026-11-17T09:25 --max-move-pct 1 --strategy NAME]
  ticket spread CODE EXPIRY RIGHT LONG_K SHORT_K QTY LONG_LIMIT SHORT_LIMIT --symbol NSE --why TEXT [...]
  ticket list
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.orders.checks import Intent  # noqa: E402
from core.orders.tickets import IST, Store, now_ist  # noqa: E402

ACCOUNT = "icici-spouse"


def next_session_0925() -> datetime:
    d = now_ist().date() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return datetime.combine(d, time(9, 25), IST)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--symbol", required=True)
        p.add_argument("--why", required=True)
        p.add_argument("--strategy", default="manual")
        p.add_argument("--stop", type=float)
        p.add_argument("--target", type=float)
        p.add_argument("--valid-until")
        p.add_argument("--max-move-pct", type=float, default=1.0)

    b = sub.add_parser("buy")
    b.add_argument("code"); b.add_argument("expiry"); b.add_argument("qty", type=int); b.add_argument("limit", type=float)
    b.add_argument("--right", choices=["call", "put"]); b.add_argument("--strike", type=float)
    common(b)
    s = sub.add_parser("spread")
    s.add_argument("code"); s.add_argument("expiry"); s.add_argument("right", choices=["call", "put"])
    s.add_argument("long_k", type=float); s.add_argument("short_k", type=float); s.add_argument("qty", type=int)
    s.add_argument("long_limit", type=float); s.add_argument("short_limit", type=float)
    common(s)
    sub.add_parser("list")
    a = ap.parse_args(argv)
    st = Store()
    if a.cmd == "list":
        for t in st.all():
            print(t["id"], t["status"], t["symbol"], t["strategy"], t["valid_until"], "max loss", t["max_loss"])
        return 0
    exp = date.fromisoformat(a.expiry)
    if a.cmd == "buy":
        right = a.right or "others"
        legs = [Intent(account=ACCOUNT, product="options" if a.right else "futures", code=a.code.upper(), expiry=exp,
                       action="buy", qty=a.qty, price=a.limit, purpose="entry", right=right, strike=a.strike or 0.0)]
    else:
        legs = [Intent(account=ACCOUNT, product="options", code=a.code.upper(), expiry=exp, action="buy", qty=a.qty,
                       price=a.long_limit, purpose="entry", right=a.right, strike=a.long_k),
                Intent(account=ACCOUNT, product="options", code=a.code.upper(), expiry=exp, action="sell", qty=a.qty,
                       price=a.short_limit, purpose="entry", right=a.right, strike=a.short_k)]
    vu = datetime.fromisoformat(a.valid_until).replace(tzinfo=IST) if a.valid_until else next_session_0925()
    t = st.draft(legs, symbol=a.symbol.upper(), why=a.why, strategy=a.strategy, ref_price=legs[0].price,
                 valid_until=vu, stop=a.stop, target=a.target, max_move_pct=a.max_move_pct)
    print(f"drafted {t['id']}: {t['symbol']} max loss {t['max_loss']} valid until {t['valid_until']} (pending on #/release)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
