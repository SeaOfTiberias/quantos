"""scripts/research/darvas_go_no_go_bands.py -- the pure pieces; synthetic returns only."""

from scripts.research.darvas_go_no_go_bands import bands, max_drawdown, pct


def test_max_drawdown_is_the_largest_fall_of_the_running_sum():
    assert max_drawdown([0.1, -0.05, -0.1, 0.2, -0.3]) == 0.3       # peak 0.15, trough -0.15
    assert max_drawdown([0.1, 0.1]) == 0.0
    assert max_drawdown([-0.1, -0.1]) == 0.2                          # from the zero start


def test_bands_use_consecutive_windows():
    nets = [0.1, -0.1] * 10
    b = bands(nets, 2)
    assert b["windows"] == 19 and abs(b["mean_p50"]) < 1e-12 and b["dd_p90"] == 0.1
    assert pct([3, 1, 2], 0.0) == 1 and pct([3, 1, 2], 1.0) == 3
