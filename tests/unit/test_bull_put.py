from datetime import date

import pytest

from core.backtest import bull_put as bp


def test_atm_and_strikes_round_half_up():
    assert bp.atm(22025.0) == 22050
    assert bp.atm(22024.9) == 22000
    assert bp.atm(22075.0) == 22100          # banker's rounding would give 22100 here too; 22025 is the trap
    assert bp.strikes(22010.0) == (21950, 21700)
    assert bp.strikes(22010.0, 300) == (21950, 21650)


def test_spread_result_arithmetic():
    r = bp.spread_result(short_in=120.0, long_in=20.0, short_out=60.0, long_out=8.0)
    assert r.credit == pytest.approx(100.0)
    assert r.debit == pytest.approx(52.0)
    assert r.net == pytest.approx(100.0 - 52.0 - 3.0)
    assert r.max_risk == pytest.approx(150.0)
    assert r.r == pytest.approx(45.0 / 150.0)


def test_spread_loss_capped_by_width():
    # spot crashes through both strikes: spread worth ~ width
    r = bp.spread_result(120.0, 20.0, 400.0, 150.5)
    assert r.debit == pytest.approx(249.5)
    assert r.r == pytest.approx((100 - 249.5 - 3) / 150)
    assert r.r > -1.03


def test_spread_rejects_impossible_credit():
    with pytest.raises(ValueError):
        bp.spread_result(20.0, 30.0, 10.0, 5.0)
    with pytest.raises(ValueError):
        bp.spread_result(300.0, 40.0, 10.0, 5.0)


def test_profit_take_trigger():
    assert bp.profit_take_hit(30.0, 100.0)
    assert not bp.profit_take_hit(30.01, 100.0)


@pytest.mark.parametrize("expiry, monthly, lot", [
    (date(2019, 2, 14), False, 75),
    (date(2021, 7, 22), False, 75),
    (date(2021, 7, 29), True, 50),
    (date(2021, 8, 5), False, 50),
    (date(2024, 4, 25), True, 50),
    (date(2024, 5, 2), False, 25),
    (date(2024, 12, 19), False, 25),
    (date(2024, 12, 26), True, 25),
    (date(2025, 1, 2), False, 75),
    (date(2025, 1, 30), True, 25),
    (date(2025, 2, 27), True, 75),
    (date(2025, 12, 23), False, 75),
    (date(2025, 12, 30), True, 75),
    (date(2026, 1, 6), False, 65),
    (date(2026, 1, 27), True, 65),
])
def test_nifty_lot(expiry, monthly, lot):
    assert bp.nifty_lot(expiry, monthly) == lot


def test_skew_interpolation_and_flat_ends():
    s = bp.Skew((-2.0, -1.0, 0.0), (1.4, 1.2, 1.0))
    assert s.at(-3.0) == 1.4
    assert s.at(0.5) == 1.0
    assert s.at(-1.0) == pytest.approx(1.2)
    assert s.at(-1.5) == pytest.approx(1.3)
    assert bp.FLAT.at(-2.0) == 1.0
