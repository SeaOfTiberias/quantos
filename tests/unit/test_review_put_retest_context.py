"""scripts/review_put_retest_context.py -- rule matching, stats and the expiry calendar."""

from datetime import date, timedelta

from scripts.review_put_retest_context import matches, monthly_expiry, stats, welch_t


def test_rule_needs_every_condition_and_skips_missing_values():
    rule = {"conditions": [{"feature": "days_to_results", "op": "<=", "value": 5},
                           {"feature": "sector", "op": "in", "value": ["bank", "it"]}]}
    assert matches(rule, {"days_to_results": 3, "sector": "bank"})
    assert not matches(rule, {"days_to_results": 3, "sector": "auto"})
    assert not matches(rule, {"days_to_results": None, "sector": "bank"})


def test_stats_and_welch():
    kept = stats([{"ret": 1.0, "win": True}, {"ret": 0.8, "win": True}, {"ret": -0.5, "win": False}])
    skipped = stats([{"ret": -1.0, "win": False}, {"ret": -0.9, "win": False}])
    assert kept["n"] == 3 and round(kept["pf"], 2) == 3.6
    assert welch_t(kept, skipped) > 0


def test_expiry_is_last_tuesday_or_the_trading_day_before():
    cal = [date(2026, 11, 2) + timedelta(days=i) for i in range(70)]
    cal = [d for d in cal if d.weekday() < 5 and d != date(2026, 11, 24)]   # 24-Nov a holiday
    assert monthly_expiry(date(2026, 11, 10), cal) == date(2026, 11, 23)
    assert monthly_expiry(date(2026, 11, 25), cal) == date(2026, 12, 29)
