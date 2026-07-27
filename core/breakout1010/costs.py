"""
QuantOS — 10:10 Breakout Cost Model (candidate 15)
─────────────────────────────────────────────────────
Buy-to-open / sell-to-close option round-trip cost, per
docs/BREAKOUT_1010_METHODOLOGY.md's "Cost model" section. Composes two
already-sourced pieces rather than rebuilding either:

- core/risk/costs.py's CostModel.round_trip() — the buy/sell-leg mechanics
  (STT on the sell leg, stamp duty on the buy leg, brokerage/exchange/
  SEBI/GST on both, direction-agnostic). Structurally exactly this trade's
  shape (buy an option, sell it same day) but its DEFAULT rates are NSE
  cash-equity rates, wrong for F&O options.
- core/options/vrp/costs.py's stt_sell_rate() and EXCHANGE_TXN_PCT — the
  time-varying options-specific rates already sourced for the VRP
  candidate (STT: 0.0625% until 2024-09-30, 0.1% from 2024-10-01, 0.15%
  from 2026-04-01; exchange: Rs35.03/lakh). Stamp duty (0.003%, buy leg)
  and SEBI/GST are the same across cash and F&O segments, so CostModel's
  own defaults apply unchanged there.
"""

from __future__ import annotations

from datetime import date

from core.options.vrp.costs import EXCHANGE_TXN_PCT, stt_sell_rate
from core.risk.costs import CostBreakdown, CostModel


def trade_cost(entry_premium: float, exit_premium: float, lot_size: float,
                entry_date: date) -> CostBreakdown:
    """Round-trip cost (INR) of buying `lot_size` units at `entry_premium`
    and selling at `exit_premium`, using F&O-options rates as of
    `entry_date` (the STT/exchange schedule is looked up once, at entry —
    same trades-same-day convention as every trigger in this design)."""
    model = CostModel(
        stt_pct=stt_sell_rate(entry_date),
        exchange_txn_pct=EXCHANGE_TXN_PCT,
    )
    return model.round_trip(buy_price=entry_premium, sell_price=exit_premium, quantity=lot_size)
