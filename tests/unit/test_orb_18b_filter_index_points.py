"""Sanity for scripts/test_orb_18b_filters_index_points.py's statistics."""
import sys
from pathlib import Path

from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.test_orb_18b_filters_index_points import welch_one_sided  # noqa: E402


def test_welch_matches_scipy_one_sided():
    a, b = [3.0, 5.0, 8.0, 1.0, 9.0, 4.0], [1.0, 2.0, 0.5, 3.0, 2.5, 1.5, 0.0]
    diff, t, p = welch_one_sided(a, b)
    ref = stats.ttest_ind(a, b, equal_var=False, alternative="greater")
    assert abs(t - ref.statistic) < 1e-9 and abs(p - ref.pvalue) < 1e-9
    assert diff > 0
