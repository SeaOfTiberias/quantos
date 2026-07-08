"""
Fill reconciliation (Sprint 6) — Unit Tests

Verifies the intended-entry vs actual-fill slippage math (direction-aware,
signed so positive = adverse), the record-skipping rules, and the aggregate
report — including the `suggested_slippage_bps` number that feeds the S5-1 cost
model's per-leg `slippage_bps`.
"""

import pytest

from core.risk.fill_reconciliation import (
    FillDelta,
    SlippageReport,
    delta_from_record,
    reconcile,
    _entry_slippage_bps,
)


def _rec(signal_id="s1", symbol="ACME", action="BUY", price=100.0,
         execution_price=100.0, **extra):
    r = {
        "signal_id": signal_id,
        "symbol": symbol,
        "action": action,
        "price": price,
        "execution_price": execution_price,
    }
    r.update(extra)
    return r


# ─── Directional bps math ─────────────────────────────────────────────────────

def test_buy_adverse_slippage_is_positive():
    # Bought higher than the signal → paid up → adverse.
    assert _entry_slippage_bps("BUY", 100.0, 100.5) == pytest.approx(50.0)


def test_buy_favorable_slippage_is_negative():
    # Bought below the signal → favorable.
    assert _entry_slippage_bps("BUY", 100.0, 99.5) == pytest.approx(-50.0)


def test_sell_adverse_slippage_is_positive():
    # Short entry filled below the signal → received less → adverse.
    assert _entry_slippage_bps("SELL", 100.0, 99.5) == pytest.approx(50.0)


def test_sell_favorable_slippage_is_negative():
    # Short entry filled above the signal → received more → favorable.
    assert _entry_slippage_bps("SELL", 100.0, 100.5) == pytest.approx(-50.0)


def test_action_is_case_insensitive():
    assert _entry_slippage_bps("buy", 100.0, 100.5) == pytest.approx(50.0)


# ─── FillDelta ────────────────────────────────────────────────────────────────

def test_delta_is_adverse_flag_and_abs():
    d = delta_from_record(_rec(action="BUY", price=100.0, execution_price=100.5))
    assert d.is_adverse is True
    assert d.slippage_abs == pytest.approx(0.5)   # paid ₹0.5/share more

    fav = delta_from_record(_rec(action="BUY", price=100.0, execution_price=99.5))
    assert fav.is_adverse is False
    assert fav.slippage_abs == pytest.approx(-0.5)


def test_sell_slippage_abs_sign():
    # SELL filled below signal: received ₹0.5 less → positive "cost" magnitude.
    d = delta_from_record(_rec(action="SELL", price=100.0, execution_price=99.5))
    assert d.slippage_abs == pytest.approx(0.5)


# ─── Record skipping ──────────────────────────────────────────────────────────

def test_unfilled_signal_skipped():
    assert delta_from_record(_rec(execution_price=None)) is None


def test_missing_price_skipped():
    assert delta_from_record(_rec(price=None)) is None


def test_nonpositive_prices_skipped():
    assert delta_from_record(_rec(price=0.0)) is None
    assert delta_from_record(_rec(execution_price=-5.0)) is None


# ─── Aggregate report ─────────────────────────────────────────────────────────

def test_empty_report_is_valid_and_zeroed():
    r = reconcile([])
    assert r.count == 0
    assert r.deltas == []
    assert r.mean_bps == 0.0
    assert r.suggested_slippage_bps == 0.0


def test_report_skips_unreconcilable_records():
    # 2 filled, 1 never filled → count 2.
    records = [
        _rec("a", action="BUY", price=100.0, execution_price=100.5),   # +50
        _rec("b", action="BUY", price=100.0, execution_price=101.0),   # +100
        _rec("c", execution_price=None),                               # skipped
    ]
    r = reconcile(records)
    assert r.count == 2
    assert r.mean_bps == pytest.approx(75.0)
    assert r.median_bps == pytest.approx(75.0)


def test_report_adverse_and_extremes():
    records = [
        _rec("a", action="BUY", price=100.0, execution_price=100.5),   # +50 adverse
        _rec("b", action="BUY", price=100.0, execution_price=99.0),    # -100 favorable
        _rec("c", action="SELL", price=200.0, execution_price=199.0),  # +50 adverse
    ]
    r = reconcile(records)
    assert r.count == 3
    assert r.adverse_count == 2
    assert r.adverse_rate == pytest.approx(2 / 3, abs=1e-6)
    assert r.worst_bps == pytest.approx(50.0)    # most adverse (max signed)
    assert r.best_bps == pytest.approx(-100.0)   # most favorable (min signed)


def test_suggested_slippage_bps_tracks_adverse_mean():
    # Net-adverse set → suggestion equals the mean adverse bps.
    records = [
        _rec("a", action="BUY", price=100.0, execution_price=100.5),   # +50
        _rec("b", action="BUY", price=100.0, execution_price=100.3),   # +30
    ]
    r = reconcile(records)
    assert r.mean_bps == pytest.approx(40.0)
    assert r.suggested_slippage_bps == pytest.approx(40.0)


def test_suggested_slippage_bps_floored_at_zero_when_net_favorable():
    # On average favorable → don't bank on luck; suggest 0 for the cost model.
    records = [
        _rec("a", action="BUY", price=100.0, execution_price=99.0),    # -100
        _rec("b", action="BUY", price=100.0, execution_price=100.2),   # +20
    ]
    r = reconcile(records)
    assert r.mean_bps < 0
    assert r.suggested_slippage_bps == 0.0


def test_to_dict_shape():
    r = reconcile([_rec("a", action="BUY", price=100.0, execution_price=100.5)])
    d = r.to_dict()
    assert d["count"] == 1
    assert d["suggested_slippage_bps"] == pytest.approx(50.0)
    assert len(d["deltas"]) == 1
    assert d["deltas"][0]["symbol"] == "ACME"
    assert d["deltas"][0]["slippage_bps"] == pytest.approx(50.0)


def test_suggested_bps_plugs_into_cost_model():
    # The report's number is a valid per-leg slippage_bps for the S5-1 model.
    from core.risk.costs import CostModel
    r = reconcile([_rec("a", action="BUY", price=100.0, execution_price=100.5)])
    model = CostModel(slippage_bps=r.suggested_slippage_bps)
    # 50 bps per leg on a ₹100k buy leg = ₹500 slippage on that leg.
    bd = model.round_trip(buy_price=100.0, sell_price=100.0, quantity=1000)
    assert bd.slippage == pytest.approx(2 * 500.0)  # both legs at 50 bps
