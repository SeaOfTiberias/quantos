"""
Save today's snapshot of the user's screener.in techno-funda screen (record only).

Run by deploy/systemd/quantos-screen-snapshot.timer at 16:30 IST on weekdays. Skips NSE
holidays (the page wouldn't change). One GET of one page; nothing is traded or sent anywhere.
See core/techno_funda/screen_snapshot.py.

    python scripts/run_screen_snapshot.py            # today's session
    python scripts/run_screen_snapshot.py --force    # also on a non-trading day (testing)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from core.reference import calendar  # noqa: E402
from core.techno_funda import screen_snapshot as ss  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="run even on a non-trading day")
    args = ap.parse_args()

    now = datetime.now(IST)
    session = now.date()
    if not args.force:
        try:
            if not calendar.is_trading_day(session):
                print(f"{session} is not an NSE trading day; nothing to record.")
                return 0
        except calendar.CalendarError as e:
            print(f"calendar check failed ({e}); recording anyway.")

    resp = requests.get(ss.SCREEN_URL, headers={"User-Agent": ss.USER_AGENT}, timeout=30)
    resp.raise_for_status()
    snap = ss.parse(resp.text)
    snap.update({"session": session.isoformat(), "fetched_at": now.isoformat(timespec="seconds"),
                 "url": ss.SCREEN_URL})
    path = ss.save(snap, session)
    names = ", ".join(r["name"] for r in snap["rows"]) or "(none)"
    print(f"{session}: {len(snap['rows'])} stocks{' (TRUNCATED, page 1 only)' if snap['truncated'] else ''}"
          f" -> {path}\n  {names}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
