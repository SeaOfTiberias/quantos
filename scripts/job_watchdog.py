#!/usr/bin/env python3
"""
QuantOS — job watchdog (docs/EXECUTION_PLAN_2026-11-19.md, E1), on the VM
──────────────────────────────────────────────────────────────────────────
Reads every enabled quantos-*.timer, its service and the always-on services from
systemd, checks them (core/ops/watchdog.py) and Telegrams each fault once per IST day,
and a "cleared" line when it goes away. The run at or after 21:00 IST always sends a
one-line summary, so a silent evening means the watchdog itself is down.

Read-only: it never starts, stops or edits a unit.

    .venv/bin/python scripts/job_watchdog.py              # check, send
    .venv/bin/python scripts/job_watchdog.py --dry-run    # print, send nothing, keep no state
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ops import watchdog as wd  # noqa: E402

HOME = Path.home() / ".quantos"
STATE = HOME / "job_watchdog_state.json"
SUMMARY_FROM_HOUR = 21                     # IST
LOOKBACK_H = 26                            # calendar fires looked for in the last 26 hours
ITERATIONS = 2000                          # enough for an every-minute calendar over 26 hours
SHOW = ["Type", "ActiveState", "Result", "InactiveExitTimestamp", "TimeoutStartUSec"]


def run(*cmd: str) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout


def show(unit: str, props: list[str]) -> dict:
    return wd.parse_show(run("systemctl", "show", unit, *[f"-p{p}" for p in props]))


def expected_last(specs: list[str], now: datetime) -> Optional[datetime]:
    base = (now - timedelta(hours=LOOKBACK_H)).strftime("%Y-%m-%d %H:%M:%S UTC")
    fires = []
    for spec in specs:
        txt = run("systemd-analyze", "calendar", spec, f"--iterations={ITERATIONS}", f"--base-time={base}")
        for ln in txt.splitlines():
            if "Next elapse:" in ln or "Iter. #" in ln:
                t = wd.parse_ts(ln.split(":", 1)[1])
                if t is not None:
                    if t > now:
                        break
                    fires.append(t)
    return wd.latest_fire(fires, now)


def newest_mtime(p: Path) -> Optional[datetime]:
    try:
        ts = [f.stat().st_mtime for f in p.iterdir()] if p.is_dir() else [p.stat().st_mtime]
    except OSError:
        return None
    return datetime.fromtimestamp(max(ts), tz=timezone.utc) if ts else None


def unit_from(name: str, s: dict, timer: bool, now: datetime) -> wd.Unit:
    u = wd.Unit(name=name, type=s.get("Type", "oneshot"), active=s.get("ActiveState", "inactive"),
                result=s.get("Result", "success"), started=wd.parse_ts(s.get("InactiveExitTimestamp", "")),
                timeout_s=wd.parse_timespan(s.get("TimeoutStartUSec", "")), timer=timer)
    if name in wd.OUTPUTS:
        u.output = wd.OUTPUTS[name].format(today=now.astimezone(wd.IST).date().isoformat())
        u.output_mtime = newest_mtime(HOME / u.output)
    return u


def gather(now: datetime) -> list[wd.Unit]:
    units = []
    rows = run("systemctl", "list-unit-files", "quantos-*.timer", "--state=enabled", "--no-legend").splitlines()
    for timer in sorted(r.split()[0] for r in rows if r.strip()):
        t = show(timer, ["Unit", "LastTriggerUSec", "TimersCalendar"])
        svc = t.get("Unit") or timer.replace(".timer", ".service")
        u = unit_from(svc, show(svc, SHOW), True, now)
        u.last_trigger = wd.parse_ts(t.get("LastTriggerUSec", ""))
        u.expected_last = expected_last(wd.calendar_specs(t.get("TimersCalendar", "")), now)
        units.append(u)
    for svc in wd.ALWAYS_ON:
        units.append(unit_from(svc, show(svc, SHOW), False, now))
    return units


def send(msg: str) -> None:
    from cloud.api.notifier import send_telegram
    asyncio.run(send_telegram(msg))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    from core.reference.calendar import is_trading_day
    now = datetime.now(timezone.utc)
    units = gather(now)
    cal, notes = wd.safe_calendar(is_trading_day)
    faults = wd.check(units, now, cal) + notes
    state = {}
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text())
        except ValueError:
            state = {}
    msgs, new_state = wd.notify(faults, state, now.astimezone(wd.IST).date())
    if now.astimezone(wd.IST).hour >= SUMMARY_FROM_HOUR:
        msgs.append(wd.summary(units, faults))
    if a.dry_run:
        print(f"{len(units)} units, {len(faults)} faults")
        for u in units:
            print(f"  {u.name:48} {u.type:8} {u.active:11} {u.result:15} last {u.last_trigger} expected {u.expected_last}")
        print("\n".join(msgs) or "(nothing to send)")
        return 0
    for m in msgs:
        send(m)
    STATE.write_text(json.dumps(new_state, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
