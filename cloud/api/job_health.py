"""
QuantOS — Scheduled Job Health
───────────────────────────────
What the System Health panel shows in place of the retired agent heartbeat.

The cockpit used to report a single `heartbeat` sourced from quantos-agent's
regime/watchlist sync. That agent was mothballed on 2026-07-27 and nothing
replaced the signal, so the panel has been reporting "agent never synced" in
red ever since — while four systemd timers ran the actual daily work. The
dashboard was monitoring the one thing deliberately switched off and was blind
to everything that was running.

This reads the timers directly. `systemctl show` is read-only and needs no
root (the API runs as the same `ubuntu` user that owns the units), and it is
the only source that knows the truth about a schedule — an artifact in the
database tells you a job produced output once, not that it is still armed to
run tomorrow.

Two traps this deliberately handles, both learned from the live units:

`Result=exec-condition` is NOT a failure. quantos-momentum-shortlist and
quantos-orb-spread-probe both carry an ExecCondition, and a skip is the
designed outcome: the shortlist is triggered by BOTH a token-refresh path
unit and a fallback timer, and whichever arrives second is supposed to no-op
against the once-per-day stamp. Painting that red would mean the panel is red
every single normal morning. For the same reason `ExecMain*Timestamp` reads
`n/a` on those units — a skipped invocation never execs anything — which is
why last-run comes from the TIMER's LastTriggerUSec rather than the service.

Weekends and holidays. quantos-momentum-shortlist and quantos-orb-spread-probe
are weekday-gated, so on any Monday their last run is Friday's. A flat "stale
after 36h" window would report both as failed every Monday morning. Those two
are judged against the NSE trading calendar instead; the two that genuinely
run every calendar day keep the simple window.

This reports whether a job FIRED on schedule, which is what the panel claims.
It is not a claim that the work inside succeeded — the shortlist's own
updated_at, already on the discovery endpoints, is the check for that.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# IST — every schedule gate on the box evaluates in Asia/Kolkata, so the
# trading-day comparison has to as well (see the momentum-shortlist unit's
# ExecCondition, which is explicit about this for the same reason).
IST = timezone(timedelta(hours=5, minutes=30))

# Long enough to survive one missed day (an expired token, a VM hiccup),
# short enough to catch two. Same reasoning and same number as the heartbeat
# window it replaces.
DAILY_STALE_SECONDS = float(os.getenv("JOB_STALE_SECONDS", str(36 * 3600)))

# Used only when neither the calendar nor weekday arithmetic can be applied
# (the calendar raised something unexpected). Four days clears a
# Friday->Monday gap plus a holiday.
CALENDAR_FALLBACK_SECONDS = 96 * 3600

_CACHE_TTL_SECONDS = 20.0
_cache: dict = {"at": 0.0, "jobs": None}


@dataclass(frozen=True)
class Job:
    key: str
    label: str
    unit: str          # without the .timer/.service suffix
    trading_day: bool  # True = weekday/holiday-gated, judge against the calendar
    note: str


# Only enabled timers belong here. quantos-agent is deliberately absent: it is
# disabled, and listing a retired unit is how the panel got into this state.
TRACKED: tuple[Job, ...] = (
    Job("momentum-shortlist", "Shortlist", "quantos-momentum-shortlist",
        True, "Mon-Fri 02:15 UTC, also fires on token refresh"),
    Job("paper-momentum", "Paper momentum", "quantos-paper-momentum",
        False, "daily 02:05 UTC, acts on quarter boundaries"),
    Job("rotation-pilot", "Rotation pilot", "quantos-rotation-pilot",
        False, "daily 02:10 UTC, acts on quarter boundaries"),
    Job("orb-spread-probe", "ORB probe", "quantos-orb-spread-probe",
        True, "3x per trading session, market hours only"),
)

_PROPS = ("Id", "LastTriggerUSec", "NextElapseUSecRealtime", "Result", "ActiveState")


def _parse_timestamp(raw: str) -> Optional[datetime]:
    """systemd renders these as 'Thu 2026-08-27 02:15:14 UTC', or 'n/a' when
    the event has never happened. Anything not clearly UTC is returned as None
    rather than guessed at — a wrong timezone here would silently shift every
    age by hours, which is worse than an honest gap."""
    raw = (raw or "").strip()
    if not raw or raw == "n/a" or raw == "0":
        return None
    parts = raw.split()
    if len(parts) < 2 or parts[-1] not in ("UTC", "GMT"):
        logger.debug("Unparseable systemd timestamp: %r", raw)
        return None
    try:
        stamp = datetime.strptime(" ".join(parts[1:-1]), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        logger.debug("Unparseable systemd timestamp body: %r", raw)
        return None
    return stamp.replace(tzinfo=timezone.utc)


def _parse_show(stdout: str) -> dict[str, dict[str, str]]:
    """`systemctl show a b c` emits one property block per unit, separated by
    blank lines. Keyed on the Id property rather than on argument order, so a
    unit systemd declines to report cannot silently shift every later unit's
    values onto the wrong job."""
    units: dict[str, dict[str, str]] = {}
    block: dict[str, str] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            if block.get("Id"):
                units[block["Id"]] = block
            block = {}
            continue
        key, _, value = line.partition("=")
        block[key] = value
    if block.get("Id"):
        units[block["Id"]] = block
    return units


async def _systemctl_show(units: list[str]) -> dict[str, dict[str, str]]:
    """One subprocess for every unit, not one per unit. Returns {} on any
    failure — no systemd (a dev laptop, a container), no systemctl on PATH, a
    timeout — because this panel must never be the reason the whole
    observability endpoint 500s."""
    args = ["systemctl", "show", *units]
    for prop in _PROPS:
        args.append(f"--property={prop}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
    except (FileNotFoundError, NotImplementedError, asyncio.TimeoutError, OSError) as e:
        logger.info("Job health unavailable (%s): %s", type(e).__name__, e)
        return {}
    except Exception as e:  # noqa: BLE001 — see docstring
        logger.warning("Job health probe failed (%s): %s", type(e).__name__, e)
        return {}
    return _parse_show(stdout.decode("utf-8", errors="replace"))


def _previous_weekday(d):
    """The most recent Mon-Fri strictly before `d`. Holiday-blind by
    construction -- it is the degraded path, used only when the derived NSE
    calendar cannot answer for the date in question."""
    prev = d - timedelta(days=1)
    while prev.weekday() >= 5:  # 5=Sat, 6=Sun
        prev -= timedelta(days=1)
    return prev


def _is_fresh(job: Job, last: Optional[datetime], now: datetime) -> tuple[bool, str]:
    """(fresh, why). `why` is rendered by the cockpit, so it explains the
    verdict rather than restating it."""
    if last is None:
        return False, "has never fired"

    age = (now - last).total_seconds()

    if not job.trading_day:
        fresh = age <= DAILY_STALE_SECONDS
        return fresh, ("fired within the last day" if fresh
                       else "no run in over 36h")

    # Weekday-gated: the newest run we can legitimately expect is the previous
    # trading session's (today's, once it has fired). Comparing dates in IST
    # means a Monday morning is measured against Friday, not against 72h ago.
    try:
        from core.reference.calendar import DateOutOfRange, previous_trading_day

        today_ist = now.astimezone(IST).date()
        last_ist = last.astimezone(IST).date()
        try:
            expected_since = previous_trading_day(today_ist)
            basis = "trading session"
        except DateOutOfRange:
            # The derived calendar is only as current as the last run of
            # scripts/derive_nse_calendar.py, and it went stale before this
            # panel was written (coverage ended 2026-08-18 while this shipped
            # on 08-27). Falling back to an hours window here would have
            # quietly reinstated the Monday false alarm this whole branch
            # exists to prevent, so fall back to weekday arithmetic instead:
            # it still measures Monday against Friday, and only misjudges the
            # session after an NSE holiday -- which reads as one day of
            # "stale", not as a permanently red panel.
            expected_since = _previous_weekday(today_ist)
            basis = "weekday (calendar not extended past its coverage)"
        fresh = last_ist >= expected_since
        return fresh, (f"fired on the latest {basis}" if fresh
                       else f"nothing since {last_ist}, expected {expected_since}")
    except Exception as e:  # noqa: BLE001 — a calendar problem must not 500
        logger.warning("Trading-calendar check failed for %s (%s): %s",
                       job.key, type(e).__name__, e)
        fresh = age <= CALENDAR_FALLBACK_SECONDS
        return fresh, "fired recently (calendar unavailable)"


def _describe_result(raw: str) -> tuple[str, bool]:
    """(label, is_failure). `exec-condition` means the unit's ExecCondition
    said don't run — a deliberate skip, and the NORMAL state for both gated
    units here. Treating it as failure would paint the panel red every
    ordinary morning."""
    result = (raw or "").strip()
    if result in ("", "success"):
        return "ok", False
    if result == "exec-condition":
        return "skipped", False
    return result, True


async def scheduled_jobs(now: Optional[datetime] = None) -> dict:
    """Health of every tracked timer, for the cockpit's System Health panel.

    Cached briefly: the cockpit polls this and nothing here changes faster
    than once a day, so there is no reason to spawn a subprocess per poll.
    """
    now = now or datetime.now(timezone.utc)
    if _cache["jobs"] is not None and (time.monotonic() - _cache["at"]) < _CACHE_TTL_SECONDS:
        return _cache["jobs"]

    units: list[str] = []
    for job in TRACKED:
        units.append(f"{job.unit}.timer")
        units.append(f"{job.unit}.service")
    shown = await _systemctl_show(units)

    if not shown:
        payload = {"available": False,
                   "reason": "systemd is not reachable from the API process",
                   "jobs": []}
        _cache.update(at=time.monotonic(), jobs=payload)
        return payload

    jobs = []
    for job in TRACKED:
        timer = shown.get(f"{job.unit}.timer", {})
        service = shown.get(f"{job.unit}.service", {})
        last = _parse_timestamp(timer.get("LastTriggerUSec", ""))
        nxt = _parse_timestamp(timer.get("NextElapseUSecRealtime", ""))
        result, failed = _describe_result(service.get("Result", ""))
        fresh, why = _is_fresh(job, last, now)
        jobs.append({
            "key": job.key,
            "label": job.label,
            "unit": f"{job.unit}.timer",
            "note": job.note,
            "last_run": last.isoformat() if last else None,
            "age_seconds": round((now - last).total_seconds(), 1) if last else None,
            "next_run": nxt.isoformat() if nxt else None,
            "result": result,
            "failed": failed,
            "fresh": fresh,
            "why": why,
            # Green only when the schedule fired when it should have AND the
            # last invocation did not error.
            "ok": fresh and not failed,
            "armed": nxt is not None,
        })

    payload = {
        "available": True,
        "jobs": jobs,
        "ok_count": sum(1 for j in jobs if j["ok"]),
        "total": len(jobs),
    }
    _cache.update(at=time.monotonic(), jobs=payload)
    return payload
