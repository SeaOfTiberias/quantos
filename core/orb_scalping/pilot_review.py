"""
QuantOS — ORB live pilot review (pure)
──────────────────────────────────────
Turns the pilot's live event log (core/orb_scalping/live_trade_log.py) into
closed trades, open positions and anomalies, matched against paper candidate
18's same-day trades. Shared by the Reports card (cloud/api/reports_routes.py)
and the pilot breaker (core/orb_scalping/pilot_guard.py), so what the page
shows and what trips the breaker can never disagree.

Costs are brokerage + statutory only (clean_trade_cost): real fills already
paid the bid-ask spread the paper cost model has to estimate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.orb_scalping.costs import clean_trade_cost
from core.orb_scalping.dry_run_log import DryRunTrade
from core.orb_scalping.live_trade_log import LiveTradeEvent


@dataclass(frozen=True)
class Anomaly:
    timestamp: str        # ISO, of the event that raised it
    kind: str             # no_stop | orphan_exit | unexplained_exit | missing_fill
    message: str


@dataclass
class PilotReview:
    trades: list[dict] = field(default_factory=list)          # closed, priced, oldest first
    open_entries: list[LiveTradeEvent] = field(default_factory=list)
    anomalies: list[Anomaly] = field(default_factory=list)


def review(events: list[LiveTradeEvent], paper: list[DryRunTrade]) -> PilotReview:
    paper_by_key = {(t.underlying, t.entry_timestamp[:10]): t for t in paper}
    out = PilotReview()
    open_by_key: dict = {}
    for e in sorted(events, key=lambda e: e.timestamp):
        key = (e.underlying, e.timestamp[:10])
        if e.event == "entry":
            open_by_key[key] = e
            if not e.stop_order_id:
                out.anomalies.append(Anomaly(e.timestamp, "no_stop",
                    f"{key[1]} {e.underlying}: no protective stop was left resting "
                    f"({e.note or 'see the VM journal'})"))
            continue
        entry = open_by_key.pop(key, None)
        if entry is None:
            out.anomalies.append(Anomaly(e.timestamp, "orphan_exit",
                f"{key[1]} {e.underlying}: exit ({e.reason}) with no matching entry"))
            continue
        if entry.fill_price is None or e.fill_price is None:
            out.anomalies.append(Anomaly(e.timestamp, "missing_fill",
                f"{key[1]} {e.underlying}: missing fill price "
                f"({'entry' if entry.fill_price is None else 'exit'}) -- left out of the curve"))
            continue
        if e.reason in (None, "unknown", "manual"):
            out.anomalies.append(Anomaly(e.timestamp, "unexplained_exit",
                f"{key[1]} {e.underlying}: exit reason '{e.reason}' -- "
                f"the position closed by a path the pilot did not drive"))
        d = datetime.fromisoformat(entry.timestamp).date()
        gross = (e.fill_price - entry.fill_price) * entry.quantity
        costs = clean_trade_cost(entry.fill_price, e.fill_price, entry.quantity, d).total
        p = paper_by_key.get(key)
        # Positive = live did worse than the prices paper recorded.
        shortfall: Optional[float] = None
        if p is not None and p.exit_premium is not None:
            shortfall = round(((entry.fill_price - p.entry_premium)
                               + (p.exit_premium - e.fill_price)) * entry.quantity, 2)
        out.trades.append({
            "label":           f"{entry.underlying} {entry.direction}",
            "underlying":      entry.underlying,
            "entry_timestamp": entry.timestamp,
            "exit_timestamp":  e.timestamp,
            "quantity":        entry.quantity,
            "entry_quote":     entry.quoted_premium,
            "entry_price":     entry.fill_price,
            "exit_price":      e.fill_price,
            "exit_reason":     e.reason or "unknown",
            "gross_pnl":       round(gross, 2),
            "costs":           round(costs, 2),
            "net_pnl":         round(gross - costs, 2),
            "paper_entry":     p.entry_premium if p else None,
            "paper_exit":      p.exit_premium if p else None,
            "paper_reason":    p.exit_reason if p else None,
            "shortfall_vs_paper": shortfall,
        })
    out.trades.sort(key=lambda t: t["exit_timestamp"])
    out.open_entries = list(open_by_key.values())
    return out
