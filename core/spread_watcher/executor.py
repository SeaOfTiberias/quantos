"""
QuantOS — Spread Watcher executor: close a vertical spread by code
───────────────────────────────────────────────────────────────────
Runs only with `spread_watcher: {orders: auto}` in agent/config.yaml; otherwise
the watcher stays alerts only. When core/spread_watcher/rules.evaluate() returns
a CLOSE event of a kind listed in `auto_close` (default: all of them), the
watcher marks the spread and this closes it through core/orders/gateway.py:

  1. buy back the SHORT leg first (marketable limit at the ask, re-priced)
  2. then sell the LONG leg (at the bid, re-priced)

In that order a failure part-way leaves a lone long option (its loss is capped
at its premium), never an uncovered short. A close that doesn't complete is
retried on later passes, up to MAX_ATTEMPTS, then handed to the user.
A model never decides a close: the rules do, and the gateway's checks apply.
"""

from __future__ import annotations

from typing import Callable

from core.orders.checks import Intent, round_tick
from core.spread_watcher.legs import Leg, Spread
from core.spread_watcher.rules import SpreadState

MAX_ATTEMPTS = 3


def leg_exit(leg: Leg, account: str) -> Intent:
    """Closing order for one leg: buy back a short, sell a long. The price is a placeholder;
    gateway.work() prices it at the touch."""
    return Intent(account=account, product="options", code=leg.stock_code, expiry=leg.expiry,
                  action="buy" if leg.qty < 0 else "sell", qty=abs(leg.qty),
                  price=round_tick(max(leg.avg_price, 0.05), up=leg.qty < 0), purpose="exit",
                  right=leg.right, strike=leg.strike)


class SpreadExecutor:
    def __init__(self, gateway, notify: Callable[[str], None], account: str = "icici-spouse",
                 kinds: tuple = ()):
        self.gw, self.notify, self.account = gateway, notify, account
        self.kinds = tuple(kinds)                 # empty = every CLOSE kind

    def wants(self, kind: str) -> bool:
        return not self.kinds or kind in self.kinds

    def request(self, st: SpreadState, kind: str) -> None:
        if self.wants(kind) and not st.close_reason:
            st.close_reason, st.close_attempts = kind, 0

    def close(self, sp: Spread, st: SpreadState, label: str) -> bool:
        """One attempt at closing both legs, short first. Returns True when both are done.
        Only a failed short buy-back is retried (nothing has changed then). Once the short is
        bought back the position is a lone long, which the watcher no longer tracks as a
        spread, so a long leg that won't fill is handed to the user in one message."""
        if not st.close_reason or st.close_attempts >= MAX_ATTEMPTS:
            return False
        st.close_attempts += 1
        n = f"(attempt {st.close_attempts}/{MAX_ATTEMPTS})"
        paper = "" if getattr(self.gw, "live", True) else " (paper)"
        r1 = self.gw.work(leg_exit(sp.short, self.account))
        if not r1.ok:
            last = st.close_attempts >= MAX_ATTEMPTS
            self.notify(("🚨 " if last else "⚠️ ") + f"{label}: auto-close -- buying back the short {sp.short.label} "
                        f"didn't fill ({'; '.join(r1.reasons)}) {n}. Nothing else was sent."
                        + (" I've stopped trying: close it by hand." if last else " Retrying next pass."))
            return False
        reason, st.close_reason = st.close_reason, None
        r2 = self.gw.work(leg_exit(sp.long, self.account))
        if not r2.ok:
            self.notify(f"🚨 {label}: short {sp.short.label} bought back{paper}, but selling the long "
                        f"{sp.long.label} didn't fill ({'; '.join(r2.reasons)}). Sell it by hand -- what's left "
                        "is a long option, loss capped at its premium.")
            return False
        self.notify(f"✅ Closed {label} by rule ({reason}){paper}: short {sp.short.label} bought back, "
                    f"long {sp.long.label} sold.")
        return True
