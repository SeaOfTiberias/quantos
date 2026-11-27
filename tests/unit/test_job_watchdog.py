"""core/ops/watchdog.py -- synthetic unit states only; no systemctl."""

from datetime import date, datetime, timedelta, timezone

import pytest

from core.ops import watchdog as wd

UTC = timezone.utc
NOW = datetime(2026, 11, 19, 4, 0, tzinfo=UTC)          # 09:30 IST, Thursday
TRADING = (lambda d: d.weekday() < 5)
HOLIDAY = (lambda d: False)


def U(**kw):
    return wd.Unit(**{"name": "quantos-x.service", **kw})


def kinds(units, now=NOW, cal=TRADING):
    return sorted((f.kind, f.unit) for f in wd.check(units, now, cal))


def test_timespans_and_timestamps():
    assert wd.parse_timespan("1min 30s") == 90 and wd.parse_timespan("45min") == 2700
    assert wd.parse_timespan("3h") == 10800 and wd.parse_timespan("500ms") == 0.5
    assert wd.parse_timespan("infinity") is None and wd.parse_timespan("") is None
    with pytest.raises(ValueError):
        wd.parse_timespan("3 parsecs")
    assert wd.parse_ts("Wed 2026-10-07 09:03:50 UTC") == datetime(2026, 10, 7, 9, 3, 50, tzinfo=UTC)
    assert wd.parse_ts("n/a") is None and wd.parse_ts("") is None
    assert wd.parse_show("A=1\nTimersCalendar={ OnCalendar=x ; }\n") == {"A": "1", "TimersCalendar": "{ OnCalendar=x ; }"}


def test_calendar_specs_and_latest_fire():
    tc = ("{ OnCalendar=Mon..Fri *-*-* 10:00:00 ; next_elapse=Thu 2026-11-19 10:00:00 UTC } "
          "{ OnCalendar=Mon..Fri *-*-* 03:45..59:00 ; next_elapse=n/a }")
    assert wd.calendar_specs(tc) == ["Mon..Fri *-*-* 10:00:00", "Mon..Fri *-*-* 03:45..59:00"]
    fires = [NOW - timedelta(minutes=m) for m in (1, 4, 6, 30)]
    assert wd.latest_fire(fires, NOW) == NOW - timedelta(minutes=6)     # within the 5-minute grace: not yet
    assert wd.latest_fire([], NOW) is None


def test_the_option_chain_recorder_case_is_stuck():
    """2026-10-07 09:03:50 UTC to 2026-11-19: activating 43 days with no start timeout."""
    rec = U(name="quantos-option-chain-recorder.service", active="activating",
            started=datetime(2026, 10, 7, 9, 3, 50, tzinfo=UTC), timeout_s=None)
    (f,) = wd.check([rec], NOW, TRADING)
    assert f.kind == "STUCK" and "2026-10-07 14:33 IST" in f.detail and "42 d" in f.detail and "no start timeout" in f.detail


def test_stuck_uses_the_units_own_timeout():
    orb = dict(name="quantos-orb.service", active="activating", timeout_s=180)
    assert kinds([U(**orb, started=NOW - timedelta(minutes=3))]) == []            # 3 min: inside timeout + slack
    assert kinds([U(**orb, started=NOW - timedelta(minutes=5))]) == [("STUCK", "quantos-orb.service")]
    assert kinds([U(active="activating", started=NOW - timedelta(minutes=20))]) == []   # no timeout: 30 min default


def test_failed_missed_and_holidays():
    assert kinds([U(result="exit-code")]) == [("FAILED", "quantos-x.service")]
    assert kinds([U(result="exec-condition")]) == []                              # a holiday skip is fine
    exp = NOW - timedelta(hours=2)
    assert kinds([U(expected_last=exp, last_trigger=exp)]) == []
    assert kinds([U(expected_last=exp, last_trigger=exp - timedelta(days=1))]) == [("MISSED", "quantos-x.service")]
    assert kinds([U(expected_last=exp, last_trigger=None)]) == [("MISSED", "quantos-x.service")]


def test_daemons_must_run_in_market_hours_on_trading_days_only():
    pm = dict(name="quantos-position-manager.service", type="simple", active="inactive")
    assert kinds([U(**pm)]) == [("DOWN", "quantos-position-manager.service")]
    assert kinds([U(**pm)], cal=HOLIDAY) == []
    assert kinds([U(**pm)], now=datetime(2026, 11, 19, 12, 0, tzinfo=UTC)) == []      # 17:30 IST
    assert kinds([U(name="quantos-cloud-api.service", type="simple", active="failed", timer=False)],
                 cal=HOLIDAY) == [("DOWN", "quantos-cloud-api.service")]            # always on


def test_no_output_when_a_successful_run_wrote_nothing():
    run = NOW - timedelta(minutes=30)
    base = dict(name="quantos-call-plans.service", output="call_plans/state.json", started=run)
    assert kinds([U(**base, output_mtime=run + timedelta(minutes=3))]) == []
    assert kinds([U(**base, output_mtime=run - timedelta(days=1))]) == [("NO_OUTPUT", "quantos-call-plans.service")]
    assert kinds([U(**base, output_mtime=None)]) == [("NO_OUTPUT", "quantos-call-plans.service")]
    assert kinds([U(**base, output_mtime=None)], cal=HOLIDAY) == []                 # no NSE session, no file due
    assert kinds([U(**base, output_mtime=None, result="exec-condition")]) == []
    assert kinds([U(**{**base, "started": run - timedelta(days=1)}, output_mtime=None)]) == []   # not today's run


def test_once_a_day_then_cleared():
    f = wd.Fault("quantos-x.service", "STUCK", "activating since ...")
    today = date(2026, 11, 19)
    msgs, st = wd.notify([f], {}, today)
    assert len(msgs) == 1 and msgs[0].startswith("🐕 STUCK quantos-x") and "sudo systemctl stop quantos-x.service" in msgs[0]
    assert wd.notify([f], st, today)[0] == []                                      # same day: quiet
    msgs2, st2 = wd.notify([f], st, today + timedelta(days=1))
    assert len(msgs2) == 1                                                         # next day: again
    msgs3, st3 = wd.notify([], st2, today + timedelta(days=1))
    assert msgs3 == ["✅ cleared STUCK quantos-x"] and st3 == {"open": {}}


def test_summary_is_the_heartbeat():
    us = [U(), U(name="quantos-y.service")]
    assert wd.summary(us, []) == "🐕 watchdog: 2 QuantOS units checked, all healthy"
    s = wd.summary(us, [wd.Fault("quantos-y.service", "FAILED", "x")])
    assert "1 open: FAILED quantos-y" in s


def test_a_stale_calendar_falls_back_to_weekdays_and_says_so():
    def stale(d):
        raise ValueError(f"{d} is outside the derived calendar (2015-01-01 .. 2026-08-18)")
    cal, notes = wd.safe_calendar(stale)
    assert cal(date(2026, 11, 19)) and not cal(date(2026, 11, 21)) and cal(date(2026, 11, 20))
    assert len(notes) == 1 and notes[0].kind == "CALENDAR" and "2026-08-18" in notes[0].detail
    assert "derive_nse_calendar" in wd.fix_hint(notes[0])


def test_repeated_timerscalendar_lines_keep_every_schedule():
    """systemd prints one TimersCalendar line per OnCalendar (orb-spread-probe: 09:45, 06:30, 04:05)."""
    two = wd.parse_show("TimersCalendar={ OnCalendar=*-*-* 09:45:00 ; next_elapse=n/a }\n"
                        "TimersCalendar={ OnCalendar=*-*-* 04:05:00 ; next_elapse=n/a }")
    assert wd.calendar_specs(two["TimersCalendar"]) == ["*-*-* 09:45:00", "*-*-* 04:05:00"]


# ─── TOKEN (2026-11-27, after the 11-26 dead-token day) ──────────────────

def test_token_fault_only_on_trading_days_inside_the_window():
    at = lambda h, m: datetime(2026, 11, 26, h, m, tzinfo=UTC) - timedelta(hours=5, minutes=30)   # IST wall time
    err = "code -16: Token is Invalid or Expired"
    assert wd.token_faults(err, at(8, 30), TRADING) == []          # before 08:45: the overnight expiry, not news
    [f] = wd.token_faults(err, at(8, 45), TRADING)
    assert f.kind == "TOKEN" and "Token is Invalid" in f.detail and "08:45 IST" in f.detail
    assert wd.token_faults(err, at(15, 30), TRADING) != []
    assert wd.token_faults(err, at(15, 45), TRADING) == []
    assert wd.token_faults(err, at(10, 0), HOLIDAY) == []
    assert wd.token_faults(None, at(10, 0), TRADING) == []         # the call worked


def test_token_fault_is_sent_once_then_cleared_after_the_refresh():
    f = wd.Fault("fyers-token", "TOKEN", "live Fyers check failed")
    d = date(2026, 11, 26)
    msgs, st = wd.notify([f], {}, d)
    assert len(msgs) == 1 and "TOKEN fyers-token" in msgs[0] and "refresh the Fyers token" in msgs[0]
    assert wd.notify([f], st, d)[0] == []
    msgs, _ = wd.notify([], st, d)
    assert msgs == ["✅ cleared TOKEN fyers-token"]


def test_fyers_reason_keeps_only_code_and_message():
    raw = ("Fyers connect error: Fyers connection failed: "
           "{'s': 'error', 'code': -16, 'message': 'Token is Invalid or Expired'}")
    assert wd.fyers_reason(raw) == "code -16: Token is Invalid or Expired"
    leaky = "Fyers connection failed: {'code': 500, 'message': 'x', 'data': {'name': 'SYNTHETIC USER'}}"
    assert "SYNTHETIC" not in wd.fyers_reason(leaky)
    assert wd.fyers_reason("HTTPSConnectionPool: read timed out\nmore") == "HTTPSConnectionPool: read timed out"
