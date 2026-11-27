"""E1 spread calibration helpers -- synthetic only."""

import pytest

from scripts import calibrate_option_spreads as cs


def test_sample_every_fifth_alphabetical_deduped():
    u = ["E", "A", "B", "C", "D", "F", "A", "G", "H", "I", "J", "K"]
    assert cs.sample(u) == ["A", "F", "K"]


def test_atm_strike_ties_low():
    assert cs.atm_strike([90.0, 100.0, 110.0], 105.0) == 100.0
    assert cs.atm_strike([90.0, 100.0, 110.0], 107.0) == 110.0


def test_leg_row_and_summary():
    ok = cs.leg_row("t", "A", 100, "2026-12-29", 100, "CE", {"bid": 4.9, "ask": 5.1})
    assert ok["status"] == "ok" and ok["half_spread_frac"] == pytest.approx(0.02)
    bad = cs.leg_row("t", "A", 100, "2026-12-29", 100, "PE", {"bid": 0, "ask": 5.1})
    assert bad["status"] == "no two-sided quote"
    s = cs.summarize([ok, bad, cs.leg_row("t", "B", 100, "x", 100, "CE", {"bid": 9, "ask": 11})])
    assert s["quoted"] == 2 and s["excluded"] == 1 and s["h_mean"] == pytest.approx((0.02 + 0.1) / 2)
