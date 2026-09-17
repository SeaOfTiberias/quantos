"""
QuantOS — "Good Night" Scalper Cost Model (candidate 20)
──────────────────────────────────────────────────────────────────────
Buy-to-open / sell-to-close option round-trip cost, per
docs/GOODNIGHT_SCALPER_METHODOLOGY.md's "Cost model" section. Reuses the
exact same F&O rate sourcing as candidate 18 (core/options/vrp/costs.py's
time-varying STT/exchange rates, composed with core/risk/costs.py's
CostModel.round_trip()) and the identical Clean/Stressed split pattern
(core/orb_scalping/costs.py is the direct template).

The one real difference: GOODNIGHT_STRESSED_SLIPPAGE_BPS is sourced from a
REAL measured multi-day at-the-actual-entry-window spread sample (the
quantos-goodnight-openwindow-probe.timer's 7 trading days,
2026-09-04..2026-09-15, 242 legs across the universe with SAIL excluded per
the methodology doc's universe section) -- median round-trip spread 2.09% of
premium. Converted to slippage_bps the same way candidate 18's costs.py
does it: slippage_bps = 50 * round_trip_spread_pct, since CostModel charges
the bps rate on BOTH the buy leg's and sell leg's own turnover (round-trip
spread_pct = 2 * slippage_bps / 100).
"""

from __future__ import annotations

from datetime import date

from core.options.vrp.costs import EXCHANGE_TXN_PCT, stt_sell_rate
from core.risk.costs import CostBreakdown, CostModel

# Median round-trip spread, quantos-goodnight-openwindow-probe.timer,
# 2026-09-04..2026-09-15, n=242 legs, SAIL excluded -- see the methodology
# doc's Cost model section for the derivation.
GOODNIGHT_MEASURED_SPREAD_PCT = 2.09
GOODNIGHT_STRESSED_SLIPPAGE_BPS = 50 * GOODNIGHT_MEASURED_SPREAD_PCT  # 104.5


def _model(entry_date: date, slippage_bps: float, brokerage_pct: float = 0.0003) -> CostModel:
    return CostModel(
        stt_pct=stt_sell_rate(entry_date),
        exchange_txn_pct=EXCHANGE_TXN_PCT,
        slippage_bps=slippage_bps,
        brokerage_pct=brokerage_pct,
    )


def clean_trade_cost(entry_premium: float, exit_premium: float, lot_size: float,
                      entry_date: date) -> CostBreakdown:
    """Round-trip cost (INR), no slippage stress -- the cost model exactly
    as specified in the methodology doc's base Cost model section."""
    return _model(entry_date, 0.0).round_trip(
        buy_price=entry_premium, sell_price=exit_premium, quantity=lot_size,
    )


def stressed_trade_cost(entry_premium: float, exit_premium: float, lot_size: float,
                         entry_date: date) -> CostBreakdown:
    """Same cost model plus the real measured spread's slippage-bps
    equivalent -- the methodology doc's Stressed variant, which gates any
    move toward live capital. A Clean-only pass is not sufficient."""
    return _model(entry_date, GOODNIGHT_STRESSED_SLIPPAGE_BPS).round_trip(
        buy_price=entry_premium, sell_price=exit_premium, quantity=lot_size,
    )
