"""Triage a universe of playbook plans into the setups worth acting on now
(docs/TRADE_REASONING.md, step 3). Pure functions, no I/O.

A SETUP is dropped from the actionable list when:
  - its entry is more than MAX_DIST_ATR daily ATRs from the price (unlikely to fill in the
    10-session window; a heuristic, untested);
  - the price is already at or beyond its target ("missed": the move happened without us);
  - it is a short on a stock with no futures (cash shorts cannot be carried overnight).
Risk per lot is (entry - stop) distance times the futures lot, in rupees, before costs.
"""
from __future__ import annotations

MAX_DIST_ATR = 3.0


def triage_one(sym: str, track: str, plan: dict, price: float, atr_d: float,
               lots: dict[str, int], max_dist_atr: float = MAX_DIST_ATR) -> dict | None:
    """One plan -> a triage row, or None if the plan is not a SETUP."""
    if plan.get("status") != "SETUP":
        return None
    long = plan["side"] == "long"
    entry, stop, target = float(plan["entry"]), float(plan["stop"]), float(plan["target"])
    risk = abs(entry - stop)
    dist = abs(entry - price) / atr_d if atr_d else float("inf")
    missed = price >= target if long else price <= target
    lot = lots.get(sym)
    reasons = []
    if missed:
        reasons.append("missed: price already at or past the target")
    if dist > max_dist_atr:
        reasons.append(f"far: entry {dist:.1f} ATR(D) away")
    if not long and lot is None:
        reasons.append("short with no futures")
    return dict(sym=sym, track=track, side=plan["side"], entry=entry, stop=stop, target=target,
                rr=plan.get("rr"), band=plan.get("band"), price=price,
                dist_atr=round(dist, 2), gap_pct=round((entry / price - 1) * 100, 2),
                risk_pct=round(risk / entry * 100, 2), lot=lot,
                lot_risk=round(risk * lot, 2) if lot else None,
                half_risk=bool(plan.get("half_risk")), actionable=not reasons, drop=reasons)


def triage(rows: list[dict], lots: dict[str, int], max_dist_atr: float = MAX_DIST_ATR) -> list[dict]:
    """Scan rows (sym, price, atr_d, p1, p2) -> triage rows for every SETUP, actionable first,
    then by distance."""
    out = []
    for r in rows:
        if "error" in r:
            continue
        for track in ("p1", "p2"):
            t = triage_one(r["sym"], track, r[track], r["price"], r["atr_d"], lots, max_dist_atr)
            if t:
                out.append(t)
    return sorted(out, key=lambda t: (not t["actionable"], t["dist_atr"]))


def pairs(rows: list[dict], tol: float = 0.005) -> list[str]:
    """Stocks where the P2 target is the P1 entry (within tol): trade them in sequence, not both
    sides at once (docs/TRADE_REASONING.md, step 5)."""
    out = []
    for r in rows:
        p1, p2 = r.get("p1", {}), r.get("p2", {})
        if p1.get("status") == "SETUP" and p2.get("status") == "SETUP" and p1["side"] != p2["side"]:
            if abs(p2["target"] - p1["entry"]) <= tol * p1["entry"]:
                out.append(r["sym"])
    return out
