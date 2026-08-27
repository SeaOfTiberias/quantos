"""Tests for cloud/api/job_health.py — the scheduled-job health the cockpit's
System Health panel renders in place of the retired agent heartbeat."""

from datetime import datetime, timedelta, timezone

import pytest

from cloud.api import job_health
from datetime import date as date_of  # noqa: E402  (aliased for readability)

from cloud.api.job_health import (
    IST,
    Job,
    _previous_weekday,
    _describe_result,
    _is_fresh,
    _parse_show,
    _parse_timestamp,
    scheduled_jobs,
)

UTC = timezone.utc


# ── systemd output parsing ─────────────────────────────────────────────────

def test_parses_the_timestamp_format_systemd_actually_emits():
    assert _parse_timestamp("Thu 2026-08-27 02:15:14 UTC") == datetime(
        2026, 8, 27, 2, 15, 14, tzinfo=UTC)


@pytest.mark.parametrize("raw", ["n/a", "", "   ", "0"])
def test_never_fired_reads_as_absent_not_as_epoch(raw):
    """`n/a` is what a timer that has never triggered reports. Coercing it to
    1970 would render as an age of 56 years rather than as 'never'."""
    assert _parse_timestamp(raw) is None


def test_a_non_utc_timestamp_is_refused_rather_than_guessed():
    """The box runs UTC. Silently treating some other zone as UTC would shift
    every age by hours and still look plausible."""
    assert _parse_timestamp("Thu 2026-08-27 07:45:14 IST") is None


def test_show_output_is_keyed_by_id_not_by_argument_order():
    """systemctl may decline to report a unit. Keying on position would then
    shift every later unit's values onto the wrong job -- reporting one job's
    health under another job's name."""
    out = ("Id=a.timer\nLastTriggerUSec=Thu 2026-08-27 02:15:14 UTC\n"
           "\n"
           "Id=b.timer\nLastTriggerUSec=n/a\n")
    parsed = _parse_show(out)
    assert set(parsed) == {"a.timer", "b.timer"}
    assert parsed["a.timer"]["LastTriggerUSec"] == "Thu 2026-08-27 02:15:14 UTC"


def test_show_parsing_keeps_values_containing_equals_signs():
    parsed = _parse_show("Id=a.service\nResult=exit-code=3\n")
    assert parsed["a.service"]["Result"] == "exit-code=3"


# ── the exec-condition trap ────────────────────────────────────────────────

def test_exec_condition_is_a_skip_not_a_failure():
    """Both gated units report Result=exec-condition on an ordinary morning:
    whichever of the two triggers arrives second is SUPPOSED to no-op against
    the once-per-day stamp. Calling that a failure paints the panel red every
    normal day, which is how a health panel becomes ignorable."""
    label, failed = _describe_result("exec-condition")
    assert (label, failed) == ("skipped", False)


@pytest.mark.parametrize("raw", ["success", ""])
def test_success_and_empty_are_ok(raw):
    assert _describe_result(raw) == ("ok", False)


def test_a_real_failure_is_reported_as_one():
    label, failed = _describe_result("exit-code")
    assert (label, failed) == ("exit-code", True)


# ── freshness ──────────────────────────────────────────────────────────────

DAILY = Job("d", "Daily", "unit-d", False, "")
GATED = Job("g", "Gated", "unit-g", True, "")


def test_daily_job_is_stale_after_the_window_but_survives_one_miss():
    now = datetime(2026, 8, 27, 3, 0, tzinfo=UTC)
    assert _is_fresh(DAILY, now - timedelta(hours=25), now)[0] is True
    assert _is_fresh(DAILY, now - timedelta(hours=40), now)[0] is False


def test_a_job_that_never_fired_is_not_fresh():
    now = datetime(2026, 8, 27, 3, 0, tzinfo=UTC)
    fresh, why = _is_fresh(DAILY, None, now)
    assert fresh is False and "never" in why


def test_weekday_gated_job_is_not_stale_on_a_monday_morning():
    """THE point of routing these through the trading calendar. A Monday
    07:00 IST check sees Friday's run -- ~72h old -- and a flat 36h window
    would report every weekday-gated job as failed every Monday, for as long
    as the panel existed."""
    monday = datetime(2026, 8, 24, 3, 0, tzinfo=UTC)      # Mon 08:30 IST
    friday_run = datetime(2026, 8, 21, 2, 15, tzinfo=UTC)  # Fri 07:45 IST
    fresh, why = _is_fresh(GATED, friday_run, monday)
    assert fresh is True, why


def test_weekday_gated_job_is_stale_when_it_misses_a_real_session():
    """Same Friday run, but now it is Tuesday: Monday's session came and went
    without a fire, which is a genuine miss and must be caught."""
    tuesday = datetime(2026, 8, 25, 3, 0, tzinfo=UTC)
    friday_run = datetime(2026, 8, 21, 2, 15, tzinfo=UTC)
    fresh, why = _is_fresh(GATED, friday_run, tuesday)
    assert fresh is False
    assert "2026-08-21" in why


def test_previous_weekday_walks_back_over_a_weekend():
    from datetime import date
    assert _previous_weekday(date(2026, 8, 24)) == date(2026, 8, 21)  # Mon -> Fri
    assert _previous_weekday(date(2026, 8, 25)) == date(2026, 8, 24)  # Tue -> Mon


def test_a_stale_calendar_still_measures_monday_against_friday():
    """The derived calendar's coverage ended 2026-08-18, before this panel was
    written, so every current date takes the DateOutOfRange branch. That
    branch must NOT fall back to an hours window -- 72h from Friday would have
    quietly reinstated the exact Monday false alarm the calendar was there to
    prevent. Weekday arithmetic keeps the verdict right without holiday data.
    """
    from core.reference.calendar import coverage
    assert coverage()[1] < date_of(2026, 8, 24), "calendar now covers this; revisit"

    monday = datetime(2026, 8, 24, 3, 0, tzinfo=UTC)
    friday_run = datetime(2026, 8, 21, 2, 15, tzinfo=UTC)
    fresh, why = _is_fresh(GATED, friday_run, monday)
    assert fresh is True
    assert "weekday" in why, why


def test_calendar_failure_degrades_to_a_window_instead_of_raising(monkeypatch):
    """A calendar problem must never take down the observability endpoint."""
    import core.reference.calendar as cal
    monkeypatch.setattr(cal, "previous_trading_day",
                        lambda d: (_ for _ in ()).throw(RuntimeError("boom")))
    now = datetime(2026, 8, 27, 3, 0, tzinfo=UTC)
    fresh, why = _is_fresh(GATED, now - timedelta(hours=10), now)
    assert fresh is True
    assert "calendar" in why


# ── the endpoint payload ───────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_cache():
    job_health._cache.update(at=0.0, jobs=None)
    yield
    job_health._cache.update(at=0.0, jobs=None)


@pytest.mark.asyncio
async def test_no_systemd_degrades_to_unavailable_rather_than_raising(monkeypatch):
    """On a dev laptop there is no systemctl at all. The panel says so; the
    rest of the observability payload is unaffected."""
    async def _none(units):
        return {}
    monkeypatch.setattr(job_health, "_systemctl_show", _none)
    payload = await scheduled_jobs()
    assert payload["available"] is False
    assert payload["jobs"] == []


@pytest.mark.asyncio
async def test_a_normal_morning_reports_every_job_ok(monkeypatch):
    """The real 2026-08-27 shape: the shortlist timer fired at 02:15 and its
    service reports exec-condition because the token path had already run it."""
    now = datetime(2026, 8, 27, 3, 0, tzinfo=UTC)

    async def _fake(units):
        out = {}
        for job in job_health.TRACKED:
            out[f"{job.unit}.timer"] = {
                "Id": f"{job.unit}.timer",
                "LastTriggerUSec": "Thu 2026-08-27 02:15:14 UTC",
                "NextElapseUSecRealtime": "Fri 2026-08-28 02:15:00 UTC",
            }
            out[f"{job.unit}.service"] = {
                "Id": f"{job.unit}.service", "Result": "exec-condition",
            }
        return out

    monkeypatch.setattr(job_health, "_systemctl_show", _fake)
    payload = await scheduled_jobs(now=now)
    assert payload["available"] is True
    assert payload["ok_count"] == payload["total"] == len(job_health.TRACKED)
    assert all(j["result"] == "skipped" and not j["failed"] for j in payload["jobs"])
    assert all(j["armed"] for j in payload["jobs"])


@pytest.mark.asyncio
async def test_a_failed_unit_is_not_ok_even_when_it_fired_on_time(monkeypatch):
    now = datetime(2026, 8, 27, 3, 0, tzinfo=UTC)

    async def _fake(units):
        out = {}
        for job in job_health.TRACKED:
            out[f"{job.unit}.timer"] = {
                "Id": f"{job.unit}.timer",
                "LastTriggerUSec": "Thu 2026-08-27 02:15:14 UTC",
                "NextElapseUSecRealtime": "Fri 2026-08-28 02:15:00 UTC",
            }
            out[f"{job.unit}.service"] = {
                "Id": f"{job.unit}.service", "Result": "exit-code",
            }
        return out

    monkeypatch.setattr(job_health, "_systemctl_show", _fake)
    payload = await scheduled_jobs(now=now)
    assert payload["ok_count"] == 0
    assert all(j["fresh"] and j["failed"] for j in payload["jobs"])


@pytest.mark.asyncio
async def test_the_retired_agent_is_not_tracked():
    """quantos-agent is disabled. Listing a retired unit is exactly how the
    panel came to report a permanently dead system in the first place."""
    assert all("agent" not in j.unit for j in job_health.TRACKED)
