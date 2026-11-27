"""
QuantOS — job watchdog (docs/EXECUTION_PLAN_2026-11-19.md, E1)
──────────────────────────────────────────────────────────────
Pure: unit states in, faults and messages out. No systemctl, no clock, no network;
scripts/job_watchdog.py gathers the states and sends the messages.

Why: ORB 18, 18b and the stop-out probe sat in "activating" from 2026-10-07 to 11-17
(cf1c518), and the option-chain recorder from 2026-10-07 to 11-19, with every health
signal green. A oneshot unit with no start timeout waits forever on a hung socket, and its
timer can't fire again.

Faults, one key per unit and kind:
  STUCK      a unit has been "activating" longer than its start timeout (DEFAULT_STUCK_S
             when it has none) plus SLACK_S.
  FAILED     the last run ended with a result other than success / exec-condition.
  MISSED     the timer's last trigger is older than the latest fire its calendar expected
             (GRACE_S before now).
  DOWN       a daemon (Type=simple, started by a timer) is not active during market hours on
             an NSE trading day, or an always-on service is not active.
  NO_OUTPUT  a run finished with success on a trading day, but the file the job writes is
             older than the run's start (OUTPUTS).
  TOKEN      on a trading day inside TOKEN_WINDOW, a live Fyers call (get_profile) failed:
             every Fyers job will fail until the token is refreshed. Added 2026-11-27 after
             11-26, when the token was dead all day and 11 jobs failed one by one.

A fault is sent once per IST day while it lasts; when it goes away a "cleared" line is sent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Optional

IST = timezone(timedelta(hours=5, minutes=30))
OK_RESULTS = ("success", "exec-condition")
DEFAULT_STUCK_S = 30 * 60          # a unit with no start timeout: stuck after 30 minutes
SLACK_S = 60                       # systemd needs a moment to act on its own timeout
GRACE_S = 5 * 60                   # a fire this recent may not have triggered yet
OUTPUT_SLACK_S = 120               # an output written just before the run start still counts
MARKET = (time(9, 20), time(15, 25))   # IST window in which daemons must be running
# IST window for the live Fyers token check. 08:45 is the first watchdog run that leaves time to
# refresh before the Darvas pre-open (09:02 IST); the token expires overnight, so earlier runs
# would alert every morning.
TOKEN_WINDOW = (time(8, 45), time(15, 30))
ALWAYS_ON = ("quantos-cloud-api.service", "quantos-agent.service")
# The file (under ~/.quantos) each job writes on a successful run; {today} = the IST date.
OUTPUTS = {
    "quantos-option-chain-recorder.service": "option_chains/{today}",
    "quantos-darvas-atr-stop-scan.service": "darvas_atr_stop_plan.json",
    "quantos-fno-screener.service": "fno_screener_latest.json",
    "quantos-trade-ideas.service": "trade_ideas.json",
    "quantos-call-plans.service": "call_plans/state.json",
    "quantos-benchmark-report.service": "reports/benchmark_latest.json",
    "quantos-ledger-score.service": "ledger/scores.json",
    "quantos-evening-brief.service": "brief/brief_latest.json",
}


@dataclass
class Unit:
    name: str                              # the service, e.g. quantos-call-plans.service
    type: str = "oneshot"                  # systemd Type
    active: str = "inactive"               # ActiveState
    result: str = "success"                # Result
    started: Optional[datetime] = None     # InactiveExitTimestamp: when the last run started
    timeout_s: Optional[float] = None      # TimeoutStartUSec; None = infinity
    timer: bool = True                     # started by a quantos timer
    last_trigger: Optional[datetime] = None
    expected_last: Optional[datetime] = None   # the latest fire the calendar expected, <= now - GRACE_S
    output: Optional[str] = None           # OUTPUTS path, resolved
    output_mtime: Optional[datetime] = None    # newest mtime of that file, or of the files in that dir


@dataclass(frozen=True)
class Fault:
    unit: str
    kind: str
    detail: str

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.unit}"


# ─── parsing systemctl output ────────────────────────────────────────────────

_SPAN = {"us": 1e-6, "usec": 1e-6, "ms": 1e-3, "msec": 1e-3, "s": 1, "sec": 1, "min": 60, "m": 60,
         "h": 3600, "hr": 3600, "d": 86400, "day": 86400, "w": 604800}


def parse_timespan(s: str) -> Optional[float]:
    """systemd's '1min 30s', '45min', '3h', '500ms', 'infinity' -> seconds; None for infinity or empty."""
    s = (s or "").strip()
    if not s or s == "infinity":
        return None
    total, found = 0.0, False
    for num, unit in re.findall(r"([\d.]+)\s*([a-z]+)", s):
        if unit not in _SPAN:
            raise ValueError(f"unknown timespan unit {unit!r} in {s!r}")
        total, found = total + float(num) * _SPAN[unit], True
    if not found:
        raise ValueError(f"not a timespan: {s!r}")
    return total


def parse_ts(s: str) -> Optional[datetime]:
    """'Wed 2026-11-18 14:30:00 UTC' (systemctl show, systemd-analyze) -> aware UTC; None for n/a or empty."""
    s = (s or "").strip()
    m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*(UTC|IST)?", s)
    if not m or s in ("n/a", "0"):
        return None
    t = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    return t.replace(tzinfo=IST if m.group(2) == "IST" else timezone.utc)


def parse_show(text: str) -> dict:
    """`systemctl show -p A -p B ...` -> {A: value}. A key systemd repeats (TimersCalendar, one
    line per OnCalendar) keeps every value, joined by a space."""
    out: dict = {}
    for ln in text.splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            k, v = k.strip(), v.strip()
            out[k] = f"{out[k]} {v}" if k in out else v
    return out


def calendar_specs(timers_calendar: str) -> list[str]:
    """TimersCalendar ('{ OnCalendar=Mon..Fri *-*-* 14:30:00 ; next_elapse=... }', one block per
    OnCalendar line) -> the specs."""
    return [m.strip() for m in re.findall(r"OnCalendar=([^;]+?)\s*;", timers_calendar or "")]


def latest_fire(elapses: list[datetime], now: datetime, grace_s: float = GRACE_S) -> Optional[datetime]:
    """The latest calendar fire at or before now - grace."""
    cut = now - timedelta(seconds=grace_s)
    past = [t for t in elapses if t <= cut]
    return max(past) if past else None


# ─── the checks ──────────────────────────────────────────────────────────────

def _ist(t: datetime) -> str:
    return t.astimezone(IST).strftime("%Y-%m-%d %H:%M IST")


def _age(s: float) -> str:
    d, rem = divmod(int(s), 86400)
    h, rem = divmod(rem, 3600)
    return f"{d} d {h} h" if d else f"{h} h {rem // 60} min" if h else f"{rem // 60} min"


def check(units: list[Unit], now: datetime, is_trading_day: Callable[[date], bool]) -> list[Fault]:
    """Every fault in `units` at `now` (aware)."""
    out: list[Fault] = []
    today = now.astimezone(IST).date()
    in_market = is_trading_day(today) and MARKET[0] <= now.astimezone(IST).time() <= MARKET[1]
    for u in units:
        if u.active == "activating" and u.started is not None:
            lim = (u.timeout_s if u.timeout_s is not None else DEFAULT_STUCK_S) + SLACK_S
            age = (now - u.started).total_seconds()
            if age > lim:
                tmo = f"timeout {_age(u.timeout_s)}" if u.timeout_s is not None else "no start timeout"
                out.append(Fault(u.name, "STUCK", f"activating since {_ist(u.started)} ({_age(age)}; {tmo})"))
                continue                                  # a stuck unit's other checks say nothing new
        if u.result not in OK_RESULTS and u.active != "activating":
            when = f" (run started {_ist(u.started)})" if u.started else ""
            out.append(Fault(u.name, "FAILED", f"last run ended '{u.result}'{when}"))
        if u.timer and u.expected_last is not None and (u.last_trigger is None or u.last_trigger < u.expected_last):
            last = _ist(u.last_trigger) if u.last_trigger else "never"
            out.append(Fault(u.name, "MISSED", f"expected a run at {_ist(u.expected_last)}; last trigger {last}"))
        daemon = u.type == "simple"
        if daemon and u.active != "active" and (u.name in ALWAYS_ON or (u.timer and in_market)):
            out.append(Fault(u.name, "DOWN", f"{u.active} during {'market hours' if u.timer else 'service time'}"))
        if (u.output and u.result == "success" and u.active == "inactive" and u.started is not None
                and u.started.astimezone(IST).date() == today and is_trading_day(today)):
            if u.output_mtime is None or u.output_mtime < u.started - timedelta(seconds=OUTPUT_SLACK_S):
                seen = _ist(u.output_mtime) if u.output_mtime else "missing"
                out.append(Fault(u.name, "NO_OUTPUT", f"run at {_ist(u.started)} succeeded but ~/.quantos/{u.output} "
                                                      f"was not written (last {seen})"))
    return out


def in_token_window(now: datetime, is_trading_day: Callable[[date], bool]) -> bool:
    ist = now.astimezone(IST)
    return is_trading_day(ist.date()) and TOKEN_WINDOW[0] <= ist.time() <= TOKEN_WINDOW[1]


def fyers_reason(err: str) -> str:
    """A Fyers connect error -> 'code -16: Token is Invalid or Expired'. Only the code and message
    are kept, so no profile or account field reaches a log or a Telegram message."""
    code = re.search(r"'code':\s*(-?\d+)", err or "")
    msg = re.search(r"'message':\s*'([^']{0,120})'", err or "")
    if code or msg:
        return f"code {code.group(1) if code else '?'}: {msg.group(1) if msg else 'no message'}"
    return (err or "unknown error").splitlines()[0][:120]


def token_faults(probe_error: Optional[str], now: datetime, is_trading_day: Callable[[date], bool]) -> list[Fault]:
    """probe_error: None when the live Fyers call worked, else a short reason (no account data).
    A fault only on a trading day inside TOKEN_WINDOW."""
    if probe_error is None or not in_token_window(now, is_trading_day):
        return []
    return [Fault("fyers-token", "TOKEN", f"live Fyers check failed at {_ist(now)}: {probe_error[:140]}")]


def safe_calendar(fn: Callable[[date], bool]) -> tuple[Callable[[date], bool], list[Fault]]:
    """The NSE calendar, falling back to weekdays when it doesn't cover a date (it raises); the
    returned list gets one CALENDAR fault the first time that happens."""
    notes: list[Fault] = []

    def day(d: date) -> bool:
        try:
            return fn(d)
        except Exception as e:                            # DateOutOfRange: the derived calendar is stale
            if not notes:
                notes.append(Fault("nse-calendar", "CALENDAR", f"{str(e)[:140]} -- weekdays used instead"))
            return d.weekday() < 5
    return day, notes


def fix_hint(f: Fault) -> str:
    if f.kind == "CALENDAR":
        return ("add the next year's NSE holiday list to core/reference/data/nse_holidays.txt, or run "
                "scripts/derive_nse_calendar.py (see its docstring); then deploy")
    if f.kind == "TOKEN":
        return "refresh the Fyers token (cockpit button); Fyers jobs that already failed today do not re-run by themselves"
    if f.kind == "STUCK":
        return f"sudo systemctl stop {f.unit}  (the timer starts a fresh run)"
    if f.kind in ("FAILED", "NO_OUTPUT"):
        return f"journalctl -u {f.unit} -n 50"
    if f.kind == "MISSED":
        return f"systemctl status {f.unit.replace('.service', '.timer')}"
    return f"sudo systemctl status {f.unit}"


def notify(faults: list[Fault], state: dict, today: date) -> tuple[list[str], dict]:
    """(messages, new state). state = {"open": {fault key: last IST date alerted}}. A fault is
    sent once per day while it lasts; one that has gone is sent once as cleared."""
    open_ = dict((state or {}).get("open", {}))
    msgs = []
    now_keys = {f.key for f in faults}
    for f in faults:
        if open_.get(f.key) != today.isoformat():
            msgs.append(f"🐕 {f.kind} {f.unit.replace('.service', '')}: {f.detail}. Fix: {fix_hint(f)}")
            open_[f.key] = today.isoformat()
    for k in sorted(set(open_) - now_keys):
        kind, unit = k.split(":", 1)
        msgs.append(f"✅ cleared {kind} {unit.replace('.service', '')}")
        del open_[k]
    return msgs, {"open": open_}


def summary(units: list[Unit], faults: list[Fault]) -> str:
    """The evening heartbeat: proves the watchdog ran."""
    if not faults:
        return f"🐕 watchdog: {len(units)} QuantOS units checked, all healthy"
    names = ", ".join(sorted({f"{f.kind} {f.unit.replace('.service', '')}" for f in faults}))
    return f"🐕 watchdog: {len(units)} units checked, {len(faults)} open: {names}"
