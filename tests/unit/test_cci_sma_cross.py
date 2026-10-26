"""scripts/backtest_cci_sma_cross.py -- crosses and the two exits on hand-built bars."""

from datetime import date, timedelta

from scripts.backtest_cci_sma_cross import crosses, exit_fixed, exit_opposite, run, state_of


def test_crosses_fire_on_the_turn_only():
    assert crosses([None, -1, -1, 1, 1, 0, -1]) == [(3, 1), (6, -1)]


def test_both_needs_agreement():
    assert state_of("both", (1, 1)) == 1
    assert state_of("both", (1, -1)) == 0
    assert state_of("sma", (1, -1)) == -1


def test_opposite_exit_at_next_open_after_the_flip():
    bars = [(100, 101, 99, 100)] * 3 + [(104, 105, 103, 104)]
    assert exit_opposite(bars, [1, 1, -1, -1], 0, 1) == (3, 104, "open")


def test_fixed_exit_target_and_stop():
    a = 4.0                                             # stop 97 (close), emergency 93, target 103
    up = [(100, 104, 99, 102)]
    assert exit_fixed(up, 0, 1, a) == (0, 103.0, "close")
    down = [(100, 101, 92, 95)]
    assert exit_fixed(down, 0, 1, a) == (0, 93.0, "close")
    slow = [(100, 101, 98, 97.5), (97.5, 98, 96.5, 96.9)]
    assert exit_fixed(slow, 0, 1, a) == (1, 96.9, "close")


def test_reversal_is_taken_at_the_same_open():
    d0 = date(2025, 1, 1)
    closes = [100.0] * 120 + [100.0 + 2 * i for i in range(1, 16)] + [130.0 - 3 * i for i in range(1, 16)]
    daily = {d0 + timedelta(days=i): (c, c + 1, c - 1, c) for i, c in enumerate(closes)}
    res = run({"NIFTY": daily, "X": daily})
    longs, shorts = res[("sma", "opposite", 1)], res[("sma", "opposite", -1)]
    assert longs and len(shorts) <= 1
    assert all(abs(adj) < 1e-9 + 0.1 for _, _, adj in longs)   # X == NIFTY: only the cost is left
