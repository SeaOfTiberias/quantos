"""
QuantOS — Transaction Cost & Slippage Model
────────────────────────────────────────────────
S5-1 (P1-7): the NSE intraday-equity charge stack a discount broker (Fyers)
applies to every round trip, plus a configurable slippage allowance. Until
this existed, expectancy and Kelly sizing were computed on GROSS P&L — every
edge looked bigger than it trades. This module makes those inputs net-of-cost.

Charge stack (NSE equity INTRADAY, MIS product), each expressed as a fraction
of turnover unless noted:

  • Brokerage        — min(0.03% of turnover, ₹20) PER executed order (per leg)
  • STT/CTT          — 0.025% on the SELL leg only, rounded to the nearest ₹
  • Exchange txn     — 0.00307% on both legs. This is NSE's 0.00297% cash-segment
                       transaction charge PLUS the ₹10/crore (0.0001%) IPFT levy,
                       which Fyers' contract note folds into this one line.
  • SEBI turnover    — 0.0001% (₹10 per crore) on both legs
  • Stamp duty       — 0.003% on the BUY leg only, rounded to the nearest ₹
  • GST              — 18% on (brokerage + exchange txn + SEBI)
  • Slippage         — configurable bps per leg (0 for realized fills, which
                       already embed slippage; > 0 for frictionless backtests)

Defaults are CALIBRATED against the Fyers brokerage calculator (2026-07): equity
intraday buy 1000 / sell 1100 / qty 100 reproduces Fyers' ₹86.06 total to the
paisa (see tests/unit/test_costs.py). Rates are still DEFAULTS, not gospel —
SEBI/exchange revise them and they differ by segment (delivery STT is 0.1% both
legs, stamp 0.015%; options use a different exchange rate entirely). They live
on the `CostModel` dataclass so a caller can override any of them and re-tune
against a fresh contract note. No I/O, no broker calls — safe to import anywhere.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def _round_to_rupee(amount: float) -> float:
    """Round a statutory charge to the nearest whole rupee (half up), matching
    how STT and stamp duty appear on the contract note (e.g. 27.5 → 28)."""
    return float(math.floor(amount + 0.5))


# ─── Charge breakdown ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CostBreakdown:
    """Every component of a round-trip cost, for contract-note reconciliation
    and cockpit display. All amounts in INR."""
    brokerage:      float
    stt:            float
    exchange_txn:   float
    sebi:           float
    stamp_duty:     float
    gst:            float
    slippage:       float

    @property
    def total(self) -> float:
        return round(
            self.brokerage + self.stt + self.exchange_txn
            + self.sebi + self.stamp_duty + self.gst + self.slippage,
            2,
        )

    def as_dict(self) -> dict[str, float]:
        d = {
            "brokerage":    round(self.brokerage, 2),
            "stt":          round(self.stt, 2),
            "exchange_txn": round(self.exchange_txn, 2),
            "sebi":         round(self.sebi, 2),
            "stamp_duty":   round(self.stamp_duty, 2),
            "gst":          round(self.gst, 2),
            "slippage":     round(self.slippage, 2),
        }
        d["total"] = self.total
        return d


# ─── Cost model ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CostModel:
    """
    A configurable NSE equity transaction-cost model. Defaults describe the
    Fyers INTRADAY (MIS) stack as of 2026-07. Fractions of turnover unless the
    name says otherwise; percentages are written as fractions (0.0003 == 0.03%).
    """
    brokerage_pct:     float = 0.0003      # 0.03% per order …
    brokerage_flat:    float = 20.0        # … capped at ₹20 per order
    stt_pct:           float = 0.00025     # 0.025% on the SELL leg only (→ nearest ₹)
    exchange_txn_pct:  float = 0.0000307   # 0.00307% both legs (NSE 0.00297% + IPFT 0.0001%)
    sebi_pct:          float = 0.000001    # ₹10/crore == 0.0001% both legs
    stamp_pct:         float = 0.00003     # 0.003% on the BUY leg only (→ nearest ₹)
    gst_pct:           float = 0.18        # 18% on brokerage + exchange + SEBI
    slippage_bps:      float = 0.0         # per leg; 0 for realized fills

    # ── Per-leg brokerage ──────────────────────────────────────────────────────
    def _brokerage(self, turnover: float) -> float:
        return min(self.brokerage_pct * turnover, self.brokerage_flat)

    def _slippage(self, turnover: float) -> float:
        return turnover * self.slippage_bps / 10_000.0

    # ── Round trip ──────────────────────────────────────────────────────────────
    def round_trip(self, buy_price: float, sell_price: float, quantity: float) -> CostBreakdown:
        """
        Full cost of buying `quantity` at `buy_price` and selling at
        `sell_price`, regardless of which leg came first. Direction-agnostic:
        STT is charged on the sell leg and stamp duty on the buy leg whether the
        position was long (buy→sell) or short (sell→buy).
        """
        buy_turnover  = abs(buy_price) * abs(quantity)
        sell_turnover = abs(sell_price) * abs(quantity)
        turnover      = buy_turnover + sell_turnover

        brokerage = self._brokerage(buy_turnover) + self._brokerage(sell_turnover)
        stt       = _round_to_rupee(self.stt_pct * sell_turnover)
        exchange  = self.exchange_txn_pct * turnover
        sebi      = self.sebi_pct * turnover
        stamp     = _round_to_rupee(self.stamp_pct * buy_turnover)
        gst       = self.gst_pct * (brokerage + exchange + sebi)
        slippage  = self._slippage(buy_turnover) + self._slippage(sell_turnover)

        return CostBreakdown(
            brokerage=brokerage, stt=stt, exchange_txn=exchange, sebi=sebi,
            stamp_duty=stamp, gst=gst, slippage=slippage,
        )

    def for_trade(
        self, entry_price: float, exit_price: float, quantity: float, direction: str,
    ) -> CostBreakdown:
        """
        Map a directional trade onto buy/sell legs and return its round-trip
        cost. A "BUY" (long) enters on the buy leg; a "SELL" (short) enters on
        the sell leg. Any non-"BUY" direction is treated as a short.
        """
        if direction == "BUY":
            buy_price, sell_price = entry_price, exit_price
        else:  # SELL / short — entry is the sell leg, exit is the buy-to-cover
            buy_price, sell_price = exit_price, entry_price
        return self.round_trip(buy_price, sell_price, quantity)

    def cost_of(
        self, entry_price: float, exit_price: float, quantity: float, direction: str,
    ) -> float:
        """Convenience: just the total round-trip INR cost for a directional trade."""
        return self.for_trade(entry_price, exit_price, quantity, direction).total


# The model applied to REALIZED trades (broker fills already embed slippage, so
# slippage_bps stays 0 here). Backtests build their own model with slippage > 0.
DEFAULT_COST_MODEL = CostModel()
