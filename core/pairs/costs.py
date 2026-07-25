"""
QuantOS — Pairs Trading: F&O Stock-Futures Transaction Cost Model
────────────────────────────────────────────────────────────────
See docs/PAIRS_TRADING_METHODOLOGY.md "Cost model" section for full
sourcing. A NEW model, not a reuse of core/risk/costs.py's DELIVERY_COST_MODEL
(cash-equity STT/stamp shape doesn't fit futures turnover) or
core/options/vrp/costs.py's options model (rates are on premium, futures
turnover has no premium). Follows the SAME time-varying-schedule pattern
vrp/costs.py already established for options STT, extended here to THREE
schedules since this backtest's window (2024-01-01+) spans more rate
changes than either prior model's window did:

  - Futures STT (sell side only): 0.0125% -> 0.02% (2024-10-01) -> 0.05% (2026-04-01)
  - Exchange transaction charge: uniform 0.00173% both legs from 2024-10-01,
    applied across the whole window as a stated approximation for the
    pre-2024-10-01 slab period (same approximation vrp/costs.py made for
    options' pre-2024-10-01 slab gap)
  - GST base: (brokerage + exchange) before 2025-04-01, (brokerage +
    exchange + SEBI) from 2025-04-01 -- SEBI turnover fees only started
    attracting GST from that date, a real nuance neither prior cost model
    in this project needed to model since their backtest windows sat
    entirely after the cutover

Brokerage (0.03% of turnover, capped Rs20/order) mirrors core/risk/costs.py's
equity shape but is UNCALIBRATED against Fyers' actual F&O brokerage
calculator -- open item in the methodology doc, not resolved here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

BROKERAGE_PCT = 0.0003       # 0.03% of turnover per order, UNCALIBRATED for F&O -- see module docstring
BROKERAGE_FLAT = 20.0        # capped Rs20/order, same equity-shape assumption
STAMP_PCT = 0.00002          # 0.002% on the buy leg only, sourced 2026-07-25
SEBI_PCT = 0.000001          # Rs10/crore, uniform across segments
EXCHANGE_TXN_PCT = 0.0000173  # Rs1.73/lakh, uniform both legs, effective 2024-10-01
GST_PCT = 0.18

GST_SEBI_CUTOVER = date(2025, 4, 1)  # SEBI fee starts attracting GST from this date

_STT_SELL_SCHEDULE = [
    (date(2000, 1, 1), 0.000125),   # 0.0125%, in effect at this backtest's 2024-01-01 window start
    (date(2024, 10, 1), 0.0002),    # 0.02%, Budget 2024
    (date(2026, 4, 1), 0.0005),     # 0.05%, Budget 2026
]


def _rate_asof(schedule: list, d: date) -> float:
    rate = schedule[0][1]
    for effective_from, r in schedule:
        if effective_from <= d:
            rate = r
        else:
            break
    return rate


def stt_sell_rate(d: date) -> float:
    return _rate_asof(_STT_SELL_SCHEDULE, d)


def _round_to_rupee(amount: float) -> float:
    return float(math.floor(amount + 0.5))


@dataclass(frozen=True)
class LegCostBreakdown:
    brokerage: float
    stt:       float
    exchange:  float
    sebi:      float
    stamp:     float
    gst:       float

    @property
    def total(self) -> float:
        return self.brokerage + self.stt + self.exchange + self.sebi + self.stamp + self.gst


def _brokerage(turnover: float) -> float:
    return min(BROKERAGE_PCT * turnover, BROKERAGE_FLAT)


def _gst_base(brokerage: float, exchange: float, sebi: float, trade_date: date) -> float:
    base = brokerage + exchange
    if trade_date >= GST_SEBI_CUTOVER:
        base += sebi
    return base


def buy_leg_cost(price: float, lot_size: int, num_lots: int, trade_date: date) -> LegCostBreakdown:
    turnover = abs(price) * lot_size * num_lots
    brokerage = _brokerage(turnover)
    exchange = EXCHANGE_TXN_PCT * turnover
    sebi = SEBI_PCT * turnover
    stamp = _round_to_rupee(STAMP_PCT * turnover)
    gst = GST_PCT * _gst_base(brokerage, exchange, sebi, trade_date)
    return LegCostBreakdown(brokerage=brokerage, stt=0.0, exchange=exchange, sebi=sebi, stamp=stamp, gst=gst)


def sell_leg_cost(price: float, lot_size: int, num_lots: int, trade_date: date) -> LegCostBreakdown:
    turnover = abs(price) * lot_size * num_lots
    brokerage = _brokerage(turnover)
    stt = _round_to_rupee(stt_sell_rate(trade_date) * turnover)
    exchange = EXCHANGE_TXN_PCT * turnover
    sebi = SEBI_PCT * turnover
    gst = GST_PCT * _gst_base(brokerage, exchange, sebi, trade_date)
    return LegCostBreakdown(brokerage=brokerage, stt=stt, exchange=exchange, sebi=sebi, stamp=0.0, gst=gst)


def position_cost(
    entry_price: float, exit_price: float, lot_size: int, num_lots: int,
    direction: str, entry_date: date, exit_date: date,
) -> float:
    """Total round-trip INR cost of one futures position (one leg of a
    pair). direction == "BUY": long (buy at entry, sell at exit). Any other
    direction is treated as a short (sell at entry, buy-to-cover at exit) --
    same convention as core/risk/costs.py's CostModel.for_trade."""
    if direction == "BUY":
        entry_cost = buy_leg_cost(entry_price, lot_size, num_lots, entry_date)
        exit_cost = sell_leg_cost(exit_price, lot_size, num_lots, exit_date)
    else:
        entry_cost = sell_leg_cost(entry_price, lot_size, num_lots, entry_date)
        exit_cost = buy_leg_cost(exit_price, lot_size, num_lots, exit_date)
    return entry_cost.total + exit_cost.total
