"""
QuantOS — Pairs Trading v2: Point-in-Time-Safe Futures-Roll Back-Adjustment
────────────────────────────────────────────────────────────────────────────
docs/PAIRS_TRADING_V2_METHODOLOGY.md "Fix 2". Builds a roll-adjusted close
series FORWARD from the first day (never backward from "today"), so the
adjustment applied to any day t depends only on roll events that have
already happened by t — the only construction safe for a walk-forward
backtest, where an early formation window must never be influenced by a
roll ratio from a LATER roll it wouldn't have known about yet.

Only feeds core/pairs/cointegration.py's hedge-ratio/ADF estimation and
core/pairs/backtest.py's trading-window z-score computation — never trade
fill prices, P&L, or costs, which always use FuturesDay.close (raw). See
the methodology doc's "what adj_close is NOT used for" section.
"""

from __future__ import annotations

import math
from dataclasses import replace

from core.pairs.backtest import FuturesDay


def build_adjusted_series(raw_days: list[FuturesDay]) -> tuple[list[FuturesDay], int]:
    """raw_days must be sorted ascending by trade_date, one per-symbol
    series (mirrors core/pairs/universe.py's per-symbol output shape).
    Returns (days_with_adj_close_filled_in, n_unadjusted_roll_seams) — the
    seam count is for the results doc's disclosure, not a silently-absorbed
    stat (see the methodology doc's fallback rule: a seam missing a
    same-day next_month_close is left unadjusted, not estimated)."""
    if not raw_days:
        return [], 0

    out: list[FuturesDay] = [replace(raw_days[0], adj_close=raw_days[0].close)]
    offset = 0.0
    n_unadjusted = 0

    for i in range(1, len(raw_days)):
        prev, cur = raw_days[i - 1], raw_days[i]
        if cur.expiry != prev.expiry:
            if prev.next_month_close and prev.next_month_close > 0 and prev.close > 0:
                # Ratio measured on `prev`'s own day -- the last day both
                # the expiring (prev.close) and successor
                # (prev.next_month_close) contracts were simultaneously
                # observed, never post-expiry.
                roll_log_diff = math.log(prev.next_month_close) - math.log(prev.close)
                offset -= roll_log_diff
            else:
                n_unadjusted += 1
                # offset unchanged -- this one seam stays unadjusted

        adj_close = math.exp(math.log(cur.close) + offset) if cur.close > 0 else cur.close
        out.append(replace(cur, adj_close=adj_close))

    return out, n_unadjusted
