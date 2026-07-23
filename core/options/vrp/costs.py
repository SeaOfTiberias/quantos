"""
QuantOS — VRP Phase 4: Options Transaction Cost Model
────────────────────────────────────────────────────────
Applies real, time-varying NSE F&O charges to each Phase 3 trade
(core/options/vrp/simulator.py) to get a NET result. `core/risk/costs.py`'s
`CostModel` is NOT reused here -- its `round_trip()` shape assumes a real
BUY leg exists (stamp duty on the buy leg, STT on the sell leg), which
doesn't fit a cash-settled short strangle: there is no buy leg at entry
(sell-to-open both legs) and no market order at all at expiry (index
options cash-settle automatically -- an OTM leg just lapses, an ITM leg
settles without either party placing an order). Building fresh, smaller
functions for this specific shape is more honest than forcing it through
a model built for a different one.

Rates below are SOURCED, not guessed, and several are genuinely
time-varying across this backtest's 2023-07-24..2026-07-22 window --
applying today's rate to 2023 data (or vice versa) would misstate history:

- **STT on selling an option** (% of premium, both legs, at entry):
  0.0625% until 2024-09-30, 0.1% from 2024-10-01 (Zerodha Z-Connect's
  2024-10-01 revision notice: "STT increases to 0.1% from 0.0625%"),
  0.15% from 2026-04-01 (Union Budget 2026 F&O STT hike). S8-4's
  `OPTIONS_COST_MODEL` used the single current 0.1% rate -- fine for that
  backtest's shorter/more recent window, but wrong applied across this
  one's full 3-year span.
- **STT on exercising an ITM option at expiry** (% of intrinsic value,
  the leg that finishes ITM only -- an OTM leg triggers no exercise and
  costs nothing): 0.125% since a September 2019 reform switched the base
  from full settlement price to intrinsic value, unchanged by the 2024-10-01
  sell-side revision, then 0.15% from 2026-04-01 (same Budget 2026 change).
  Cash-settled index options have no physical delivery, but NSE still
  applies exercise-side STT to the automatic ITM settlement.
- **Exchange transaction charge**: Rs35.03/lakh of premium (0.03503%),
  confirmed as NSE's current uniform rate (SEBI's 2024 circular mandating
  uniform, non-slab MII charges, effective 2024-10-01) -- same figure
  S8-4's `OPTIONS_COST_MODEL` used. Before 2024-10-01, NSE used a
  volume-tiered SLAB system with no single equivalent rate (member- and
  monthly-turnover-dependent); this module applies the post-2024-10-01
  rate across the WHOLE window as a stated approximation rather than
  reconstruct a slab an individual member would have sat in.
- **SEBI turnover fee**: Rs10/crore (0.0001%), confirmed uniform across
  segments (cash, equity F&O, currency, commodity) and stable across this
  whole window -- same as `core/risk/costs.py`'s equity default.
- **Brokerage**: 0.03% of premium, capped at Rs20/order -- SAME formula
  shape as `core/risk/costs.py`'s equity model. The cap NEVER binds for
  this strategy at any lot size actually used in this window: it only
  matters over `Rs20 / 0.03% = Rs66,667` of per-leg turnover, i.e.
  premium * lot_size > 66,667. The highest premium seen across all 157
  Phase 3 trades was 699.9 points (a blown-through leg's settlement
  value; entry credits topped out at 254 points combined) -- even at
  NIFTY's smallest lot size this window ever used (25), that is
  699.9 * 25 = 17,498, well under the cap threshold. Confirmed against
  the real trade set, not assumed -- this is why lot size (otherwise a
  genuinely messy point-in-time reconstruction across the schema gap
  and multiple SEBI-driven revisions) turns out to not matter for this
  specific strategy's costs at all: every cost component here is a pure
  percentage of premium/intrinsic value, and percentages are lot-size-
  invariant once the flat cap is confirmed non-binding.
- **Stamp duty**: N/A. Stamp applies to the BUY leg; this strategy only
  ever sells to open, and expiry settlement is not a market order either
  way -- there is no buy leg anywhere in its lifecycle.
- **GST**: 18% on (brokerage + exchange + SEBI), same as
  `core/risk/costs.py` -- NOT charged on STT (STT is itself a tax, not a
  service fee).

No cost applies to a leg that expires OTM: no market order is placed
(it simply lapses), so brokerage/exchange/SEBI/GST are all zero, and no
exercise occurs so exercise-STT is zero too.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from core.options.vrp.simulator import BacktestStats, StrangleTrade, stats_from_pcts

BROKERAGE_PCT = 0.0003          # 0.03% of premium, per leg (cap confirmed non-binding -- see module docstring)
EXCHANGE_TXN_PCT = 0.0003503    # Rs35.03/lakh, current NSE F&O rate, applied across the whole window (approximation pre-2024-10-01)
SEBI_PCT = 0.000001             # Rs10/crore, uniform across the whole window
GST_PCT = 0.18                  # on brokerage + exchange + SEBI only, not on STT

# Time-varying STT rate tables: (effective_from_date, rate). Sorted oldest
# first; _rate_asof picks the latest entry whose effective_from <= the date.
_STT_SELL_SCHEDULE = [
    (date(2000, 1, 1), 0.000625),   # in effect for this backtest's entire pre-2024-10-01 span
    (date(2024, 10, 1), 0.001),
    (date(2026, 4, 1), 0.0015),
]
_STT_EXERCISE_SCHEDULE = [
    (date(2000, 1, 1), 0.00125),    # in effect since a Sept-2019 reform, unchanged by the 2024-10-01 sell-side revision
    (date(2026, 4, 1), 0.0015),
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


def stt_exercise_rate(d: date) -> float:
    return _rate_asof(_STT_EXERCISE_SCHEDULE, d)


@dataclass(frozen=True)
class LegCostBreakdown:
    brokerage: float
    stt:       float
    exchange:  float
    sebi:      float
    gst:       float

    @property
    def total(self) -> float:
        return self.brokerage + self.stt + self.exchange + self.sebi + self.gst


def entry_leg_cost(premium_points: float, entry_date: date) -> LegCostBreakdown:
    """Cost of selling one leg to open, in points (same unit as premium --
    lot-size-invariant, see module docstring)."""
    brokerage = BROKERAGE_PCT * premium_points
    stt = stt_sell_rate(entry_date) * premium_points
    exchange = EXCHANGE_TXN_PCT * premium_points
    sebi = SEBI_PCT * premium_points
    gst = GST_PCT * (brokerage + exchange + sebi)
    return LegCostBreakdown(brokerage=brokerage, stt=stt, exchange=exchange, sebi=sebi, gst=gst)


def exit_leg_cost(intrinsic_points: float, expiry_date: date) -> LegCostBreakdown:
    """Cost of a leg's cash settlement at expiry, in points. Zero everywhere
    except exercise STT if the leg finished ITM -- no order is placed, so no
    brokerage/exchange/SEBI/GST applies either way."""
    if intrinsic_points <= 0:
        return LegCostBreakdown(0.0, 0.0, 0.0, 0.0, 0.0)
    stt = stt_exercise_rate(expiry_date) * intrinsic_points
    return LegCostBreakdown(brokerage=0.0, stt=stt, exchange=0.0, sebi=0.0, gst=0.0)


def trade_cost_points(trade: StrangleTrade) -> Optional[float]:
    """Total round-trip cost of one strangle (both legs, entry + exit), in
    points. None if the trade has no settlement data (mirrors
    StrangleTrade.pnl_points -- an unpriced trade has no cost to compute
    either)."""
    if trade.call_exit_value is None or trade.put_exit_value is None:
        return None
    entry = (
        entry_leg_cost(trade.call_entry_premium, trade.entry_date).total
        + entry_leg_cost(trade.put_entry_premium, trade.entry_date).total
    )
    exit_ = (
        exit_leg_cost(trade.call_exit_value, trade.expiry_date).total
        + exit_leg_cost(trade.put_exit_value, trade.expiry_date).total
    )
    return entry + exit_


def net_pnl_points(trade: StrangleTrade) -> Optional[float]:
    """Gross P&L (StrangleTrade.pnl_points) minus this trade's real,
    time-dated transaction costs. None if unpriced."""
    gross = trade.pnl_points
    cost = trade_cost_points(trade)
    if gross is None or cost is None:
        return None
    return gross - cost


def net_pnl_pct_of_credit(trade: StrangleTrade) -> Optional[float]:
    net = net_pnl_points(trade)
    if net is None or trade.entry_credit <= 0:
        return None
    return net / trade.entry_credit * 100.0


def compute_net_stats(trades: list[StrangleTrade]) -> BacktestStats:
    """Same pooled per-trade stats as simulator.compute_stats(), computed on
    NET (post-cost) %-of-credit P&L instead of gross."""
    missing = sum(1 for t in trades if net_pnl_pct_of_credit(t) is None)
    pnls = [p for t in trades if (p := net_pnl_pct_of_credit(t)) is not None]
    return stats_from_pcts(pnls, missing)
