"""Unit tests for core/surge/live.py (docs/SURGE_23B_METHODOLOGY.md)."""

from dataclasses import asdict
from datetime import date

import pytest

from core.surge.live import (
    Leg, Position, choose_expiry, evaluate, exit_due, exit_value, in_cooldown, is_fresh_52w_high,
    load_positions, pick_legs, save_positions, trade_return, weekdays_after,
)


def _chain(spot_strikes=range(900, 1300, 20), quote=True):
    legs = []
    for k in spot_strikes:
        intrinsic = max(1000 - k, 0)
        mid = intrinsic + 30 * 0.9 ** ((k - 900) / 20)
        legs.append(Leg(f"NSE:X{k}CE", float(k), mid - 0.5 if quote else 0.0, mid + 0.5 if quote else 0.0, mid))
    return legs


def test_weekdays_and_expiry_choice():
    assert weekdays_after(date(2026, 10, 15), date(2026, 10, 22)) == 5   # Thu -> next Thu
    near, far = date(2026, 10, 20), date(2026, 11, 24)
    assert choose_expiry([(far, "f"), (near, "n")], date(2026, 10, 15)) == (far, "f")
    assert choose_expiry([(near, "n")], date(2026, 10, 12)) == (near, "n")


def test_fresh_high():
    closes = [100.0] * 251 + [120.0]
    assert is_fresh_52w_high(closes, 121.0)
    assert not is_fresh_52w_high(closes, 119.0)
    assert is_fresh_52w_high([100.0] * 100, 50.0)    # too little history -> treat as skip


def test_pick_legs_l2w4():
    long_, short, reason = pick_legs(_chain(), spot=1003.0)
    assert reason == ""
    assert long_.strike == 1040 and short.strike == 1120     # ATM 1000, +2 strikes, +4 more


def test_pick_legs_rejects_one_sided_and_off_chain():
    _, _, reason = pick_legs(_chain(quote=False), spot=1000.0)
    assert "two-sided" in reason
    _, _, reason = pick_legs(_chain(range(900, 1100, 20)), spot=1000.0)
    assert "beyond" in reason


def _pos(**kw):
    long_ = Leg("L", 1040.0, 10.0, 10.5, 10.2)
    short = Leg("S", 1120.0, 2.0, 2.4, 2.2)
    base = dict(symbol="AAA", entry_date="2026-10-15", expiry="2026-11-24", expiry_epoch="e", lot=100,
                spot_entry=1003.0, long=asdict(long_), short=asdict(short), debit_real=10.5 - 2.0,
                debit_mid=10.25 - 2.2)
    base.update(kw)
    return Position(**base)


def test_exit_rules_and_values():
    p = _pos()
    assert not exit_due(p, date(2026, 10, 16))
    p.sessions_held = 8
    assert exit_due(p, date(2026, 10, 27))
    assert exit_due(_pos(expiry="2026-10-27"), date(2026, 10, 26))   # 1 weekday left
    assert exit_value(Leg("L", 1040, 30, 31, 30.5), "long") == (30, "")
    assert exit_value(Leg("S", 1120, 6, 7, 6.5), "short") == (7, "")
    assert exit_value(Leg("S", 1120, 0, 0, 6.5), "short") == (6.5, "ltp_fallback")


def test_cooldown():
    p = _pos()
    assert in_cooldown([p], "AAA", {"2026-10-15": 3})
    assert not in_cooldown([p], "AAA", {"2026-10-15": 11})
    assert not in_cooldown([p], "BBB", {"2026-10-15": 3})


def test_store_roundtrip_and_return(tmp_path):
    p = _pos(exit_date="2026-10-27", long_exit={"value": 30.0}, short_exit={"value": 7.0}, sessions_held=8)
    save_positions(tmp_path / "p.jsonl", [p, _pos(symbol="BBB")])
    loaded = load_positions(tmp_path / "p.jsonl")
    assert [x.symbol for x in loaded] == ["AAA", "BBB"] and loaded[1].open
    gross, costs, ret = trade_return(loaded[0])
    assert gross == pytest.approx((30 - 7) - 8.5)
    assert 0 < costs < 2 and ret == pytest.approx((gross - costs) / 8.5)
    assert trade_return(loaded[1]) is None


def test_evaluate_hides_pnl_until_60():
    closed = [_pos(symbol=f"S{i}", exit_date="2026-10-27", long_exit={"value": 12.0},
                   short_exit={"value": 2.0}, sessions_held=8) for i in range(10)]
    v = evaluate(closed)
    assert not v.ready and v.passed is None and "no P&L" in v.lines[0]
    assert v.profit_factor == 0.0
