"""Tests for core/orb_scalping/pilot_guard.py -- the live pilot breaker
agreed 2026-09-30: defect triggers + a Rs15k budget, pilot-scoped flag."""

from core.orb_scalping import pilot_guard
from core.orb_scalping.dry_run_log import DryRunTrade
from core.orb_scalping.live_trade_log import LiveTradeEvent


def _entry(day="2026-10-01", fill=100.0, stop="S1", underlying="NIFTY", qty=65):
    return LiveTradeEvent(event="entry", underlying=underlying, option_symbol="NSE:X", direction="PUT",
                          timestamp=f"{day}T04:05:30+00:00", quantity=qty, quoted_premium=fill,
                          fill_price=fill, order_id="E", stop_order_id=stop)


def _exit(day="2026-10-01", fill=110.0, reason="session_flatten", underlying="NIFTY", qty=65):
    return LiveTradeEvent(event="exit", underlying=underlying, option_symbol="NSE:X", direction="PUT",
                          timestamp=f"{day}T09:50:30+00:00", quantity=qty, fill_price=fill, reason=reason)


def _paper(day="2026-10-01", entry=100.0, exit_=110.0, underlying="NIFTY"):
    return DryRunTrade(underlying=underlying, direction="PUT", entry_timestamp=f"{day}T04:05:10+00:00",
                       entry_premium=entry, exit_timestamp=f"{day}T09:50:10+00:00",
                       exit_reason="session_flatten", quantity=130, exit_premium=exit_)


def test_healthy_trade_does_not_trip():
    assert pilot_guard.evaluate([_entry(), _exit()], [_paper()]) is None


def test_no_stop_resting_trips_immediately():
    reason = pilot_guard.evaluate([_entry(stop=None)], [])
    assert reason and "no protective stop" in reason


def test_unexplained_exit_trips():
    assert "manual" in pilot_guard.evaluate([_entry(), _exit(reason="manual")], [_paper()])


def test_shortfall_over_the_limit_trips_and_under_it_does_not():
    # live exit 20 below paper's at 65 qty = Rs1,300 -> fine; 30 below = Rs1,950 -> trips
    assert pilot_guard.evaluate([_entry(), _exit(fill=90.0)], [_paper(exit_=110.0)]) is None
    reason = pilot_guard.evaluate([_entry(), _exit(fill=80.0)], [_paper(exit_=110.0)])
    assert reason and "shortfall" in reason


def test_budget_trips_at_minus_15k_net():
    events, paper = [], []
    for i, day in enumerate(["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-06", "2026-10-07",
                             "2026-10-08", "2026-10-09", "2026-10-12"]):
        events += [_entry(day), _exit(day, fill=70.0, reason="premium_stop")]   # -Rs1,950 gross each
        paper.append(_paper(day, exit_=70.0))                                  # matches paper: no shortfall
    assert "loss budget" in pilot_guard.evaluate(events, paper)
    assert pilot_guard.evaluate(events[:12], paper[:6]) is None                 # 6 losses < Rs15k


def test_acknowledged_events_do_not_retrip_and_budget_restarts():
    events = [_entry(stop=None)]
    assert pilot_guard.evaluate(events, []) is not None
    assert pilot_guard.evaluate(events, [], acknowledged="2026-10-01T05:00:00+00:00") is None


def test_flag_set_read_reset_roundtrip(tmp_path):
    assert pilot_guard.read_pilot_halt(tmp_path) is None
    pilot_guard.set_pilot_halt("test reason", tmp_path)
    assert "test reason" in pilot_guard.read_pilot_halt(tmp_path)
    pilot_guard.reset(tmp_path)
    assert pilot_guard.read_pilot_halt(tmp_path) is None
    assert pilot_guard.acknowledged_until(tmp_path) is not None
    assert not (tmp_path / "halt").exists()        # the global flag is never touched
