"""
S5-1 Transaction Cost & Slippage Model — Unit Tests

The headline acceptance criterion: a known round trip reproduces the Fyers
contract-note total within ₹1. We anchor to a fully hand-computed example so
the arithmetic is auditable, and cross-check every component against the
documented NSE INTRADAY stack. When the real rates drift, tune CostModel's
defaults and re-derive the expected numbers here.
"""

import pytest

from core.risk.costs import CostModel, CostBreakdown, DEFAULT_COST_MODEL


# ─── Fyers contract-note reference (the S5-1 AC anchor) ────────────────────────
#
# From the Fyers brokerage calculator (2026-07), NSE equity INTRADAY,
# buy 100 @ ₹1000, sell 100 @ ₹1100:
#   Turnover      = 210,000
#   Brokerage     = min(0.03%·100000, 20) + min(0.03%·110000, 20) = 20 + 20 = 40.00
#   STT (sell)    = round(0.025%·110,000) = round(27.5)           =        28.00
#   exchange txn  = 0.00307%·210,000  (NSE 0.00297% + IPFT 0.0001%) =        6.447
#   SEBI          = 0.0001%·210,000                                =         0.21
#   stamp (buy)   = round(0.003%·100,000) = round(3.0)             =         3.00
#   GST 18%·(brokerage+exchange+SEBI) = 0.18·46.657               =         8.40
#                                                                    ─────────────
#   Total (Fyers) =                                                          86.06

EXPECTED_TOTAL = 86.06


class TestKnownRoundTrip:
    """Reconciles the model against the real Fyers calculator line items."""

    def setup_method(self):
        self.breakdown = DEFAULT_COST_MODEL.round_trip(
            buy_price=1000.0, sell_price=1100.0, quantity=100,
        )

    def test_ac_total_within_one_rupee(self):
        """AC: reproduces the contract-note total within ₹1 (here, to the paisa)."""
        assert self.breakdown.total == pytest.approx(EXPECTED_TOTAL, abs=1.0)

    def test_component_brokerage_capped_per_leg(self):
        assert self.breakdown.brokerage == pytest.approx(40.00, abs=0.01)

    def test_component_stt_sell_side(self):
        assert self.breakdown.stt == pytest.approx(28.00, abs=0.01)

    def test_component_exchange_txn(self):
        assert self.breakdown.exchange_txn == pytest.approx(6.447, abs=0.01)

    def test_component_sebi(self):
        assert self.breakdown.sebi == pytest.approx(0.21, abs=0.01)

    def test_component_stamp_buy_side(self):
        assert self.breakdown.stamp_duty == pytest.approx(3.00, abs=0.01)

    def test_component_gst(self):
        assert self.breakdown.gst == pytest.approx(8.40, abs=0.01)

    def test_total_equals_sum_of_components(self):
        b = self.breakdown
        manual = (b.brokerage + b.stt + b.exchange_txn + b.sebi
                  + b.stamp_duty + b.gst + b.slippage)
        assert b.total == pytest.approx(manual, abs=0.01)  # total is rounded to 2dp

    def test_no_slippage_by_default(self):
        assert self.breakdown.slippage == 0.0


# ─── Brokerage cap behaviour ───────────────────────────────────────────────────

class TestBrokerage:

    def test_small_turnover_uses_percentage(self):
        # 0.03% of ₹10,000 = ₹3 < ₹20 cap → percentage wins.
        b = DEFAULT_COST_MODEL.round_trip(100.0, 100.0, 100)  # ₹10k each leg
        assert b.brokerage == pytest.approx(6.0, abs=0.01)    # 3 + 3

    def test_large_turnover_hits_flat_cap(self):
        # 0.03% of ₹1,000,000 = ₹300 → capped at ₹20 per leg.
        b = DEFAULT_COST_MODEL.round_trip(1000.0, 1000.0, 1000)  # ₹1M each leg
        assert b.brokerage == pytest.approx(40.0, abs=0.01)      # 20 + 20


# ─── Direction handling ────────────────────────────────────────────────────────

class TestDirection:

    def test_long_maps_entry_to_buy_leg(self):
        # Long: entry is the buy leg, exit the sell leg.
        long_cost = DEFAULT_COST_MODEL.for_trade(
            entry_price=1000.0, exit_price=1010.0, quantity=100, direction="BUY")
        rt = DEFAULT_COST_MODEL.round_trip(buy_price=1000.0, sell_price=1010.0, quantity=100)
        assert long_cost.total == pytest.approx(rt.total, abs=0.001)

    def test_short_maps_entry_to_sell_leg(self):
        # Short: entry is the sell leg (STT is charged there), exit buys to cover.
        short_cost = DEFAULT_COST_MODEL.for_trade(
            entry_price=1010.0, exit_price=1000.0, quantity=100, direction="SELL")
        rt = DEFAULT_COST_MODEL.round_trip(buy_price=1000.0, sell_price=1010.0, quantity=100)
        assert short_cost.total == pytest.approx(rt.total, abs=0.001)

    def test_cost_of_returns_total(self):
        total = DEFAULT_COST_MODEL.cost_of(1000.0, 1100.0, 100, "BUY")
        assert total == pytest.approx(EXPECTED_TOTAL, abs=1.0)


# ─── Slippage ──────────────────────────────────────────────────────────────────

class TestSlippage:

    def test_slippage_adds_per_leg_bps(self):
        model = CostModel(slippage_bps=5.0)   # 5 bps = 0.05% per leg
        b = model.round_trip(1000.0, 1010.0, 100)
        # 0.05% of (100,000 + 101,000) = 0.0005 * 201,000 = 100.5
        assert b.slippage == pytest.approx(100.5, abs=0.01)

    def test_slippage_increases_total(self):
        base = DEFAULT_COST_MODEL.round_trip(1000.0, 1010.0, 100).total
        slipped = CostModel(slippage_bps=5.0).round_trip(1000.0, 1010.0, 100).total
        assert slipped > base
        assert slipped == pytest.approx(base + 100.5, abs=0.01)


# ─── Configurability / breakdown surface ───────────────────────────────────────

class TestConfigurability:

    def test_overriding_a_rate_flows_through(self):
        zero_gst = CostModel(gst_pct=0.0)
        assert zero_gst.round_trip(1000.0, 1010.0, 100).gst == 0.0

    def test_breakdown_as_dict_includes_total(self):
        d = DEFAULT_COST_MODEL.round_trip(1000.0, 1100.0, 100).as_dict()
        assert set(d) == {"brokerage", "stt", "exchange_txn", "sebi",
                          "stamp_duty", "gst", "slippage", "total"}
        assert d["total"] == pytest.approx(EXPECTED_TOTAL, abs=1.0)

    def test_zero_quantity_is_costless(self):
        assert DEFAULT_COST_MODEL.cost_of(1000.0, 1010.0, 0, "BUY") == 0.0
