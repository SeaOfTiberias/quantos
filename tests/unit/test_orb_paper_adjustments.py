"""
Tests for core/orb_scalping/paper_adjustments.py -- the mechanical views
pre-registered 2026-09-30 in docs/ORB_ENTRY_FILTER_METHODOLOGY.md.
"""

from core.orb_scalping.dry_run_log import DryRunTrade
from core.orb_scalping.paper_adjustments import (
    RETRO_STOP_REASON,
    enforce_premium_stop,
    enforce_premium_stop_all,
    exclude_banknifty_expiry_days,
    is_banknifty_expiry_day_trade,
    premium_stop_trigger,
)


def _t(underlying="NIFTY", day="2026-09-29", entry=100.0, exit_=10.0, reason="session_flatten"):
    return DryRunTrade(underlying=underlying, direction="PUT",
                       entry_timestamp=f"{day}T04:10:00+00:00", entry_premium=entry,
                       exit_timestamp=f"{day}T09:50:00+00:00", exit_reason=reason,
                       quantity=30, exit_premium=exit_)


def test_pre_fix_row_past_the_trigger_is_remarked_at_the_trigger():
    # 2026-09-29's actual BANKNIFTY row: 220.35 -> 2.95 at session_flatten.
    t = enforce_premium_stop(_t("BANKNIFTY", entry=220.35, exit_=2.95))
    assert t.exit_premium == premium_stop_trigger(220.35) == 165.2625
    assert t.exit_reason == RETRO_STOP_REASON


def test_index_stop_exit_below_trigger_is_also_remarked():
    # 2026-09-29's NIFTY row exited via the index stop, but after the premium trigger.
    t = enforce_premium_stop(_t(entry=151.0, exit_=94.4, reason="stop"))
    assert t.exit_premium == 113.25


def test_rows_from_the_enforced_era_are_never_touched():
    t = _t(day="2026-09-30", exit_=10.0)
    assert enforce_premium_stop(t) is t


def test_rows_above_trigger_unpriced_or_already_premium_stop_are_untouched():
    for t in (_t(exit_=80.0), _t(exit_=None), _t(exit_=70.0, reason="premium_stop")):
        assert enforce_premium_stop(t) is t


def test_enforce_all_keeps_order_and_length():
    rows = [_t(exit_=10.0), _t(exit_=120.0)]
    out = enforce_premium_stop_all(rows)
    assert [r.exit_premium for r in out] == [75.0, 120.0]


def test_banknifty_expiry_day_detection():
    assert is_banknifty_expiry_day_trade(_t("BANKNIFTY", day="2026-09-29"))      # last Tue of Sep
    assert is_banknifty_expiry_day_trade(_t("BANKNIFTY", day="2026-10-27"))      # last Tue of Oct
    assert not is_banknifty_expiry_day_trade(_t("BANKNIFTY", day="2026-09-28"))
    assert not is_banknifty_expiry_day_trade(_t("NIFTY", day="2026-09-29"))     # NIFTY never


def test_exclusion_drops_only_banknifty_expiry_day_rows():
    rows = [_t("BANKNIFTY", day="2026-09-29"), _t("BANKNIFTY", day="2026-09-28"),
            _t("NIFTY", day="2026-09-29")]
    kept = exclude_banknifty_expiry_days(rows)
    assert [(r.underlying, r.entry_timestamp[:10]) for r in kept] == [
        ("BANKNIFTY", "2026-09-28"), ("NIFTY", "2026-09-29")]
