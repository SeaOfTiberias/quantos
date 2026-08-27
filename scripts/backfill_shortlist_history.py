#!/usr/bin/env python3
"""
QuantOS — Backfill shortlist history from journald
───────────────────────────────────────────────────
cloud/api/shortlist_history.py started recording on 2026-08-27, so the
Morning Brief tab would otherwise have had nothing to compare against until
2026-08-28 and nothing useful for a week. The scan has been logging its full
ranked board to journald since 2026-07-29, though, so the history can be
reconstructed rather than waited for.

What survives the round trip, and what does not
───────────────────────────────────────────────
The log line (scripts/run_momentum_shortlist.py::_log_summary) carries
symbol, momentum %, trend, breakout state, 50/200 cross, box width, rr, and
the PER-NOTE vault scores. That is everything the brief's flags key on.

It does NOT carry `close`, `stage`, or `vault_verdict` — those are NULL on
backfilled rows, and every such row is stamped source='journald-backfill' so
a reader can tell a reconstructed day from a synced one. They are not
guesses; they are honestly absent.

`momentum_rank` is DERIVED, not read: build_shortlist assigns rank by
sorting on momentum_pct descending (core/discovery/momentum_shortlist.py
:385-394), so re-sorting the logged percentages reproduces it exactly, with
one caveat — the log rounds to one decimal, so two names within 0.1% of each
other can swap adjacent positions. That moves a rank by one and cannot
change a bucket, which is assigned from the tier, itself read from the log's
own bucket header rather than recomputed.

Days before 2026-08-06 logged only a partial board (50-210 lines against
~563 today, from before all three universes were wired), so they are
reconstructed as far as they go and reported as partial. A day whose line
count looks truncated is still written: the brief compares against the most
recent session that EXISTS, so a thin day is worse than a full one but far
better than a gap.

Usage (on the VM, where the journal lives):
    journalctl -u quantos-momentum-shortlist --no-pager \\
        | python scripts/backfill_shortlist_history.py --stdin
    python scripts/backfill_shortlist_history.py --since "2026-07-01"
    python scripts/backfill_shortlist_history.py --since "2026-07-01" --dry-run
"""

import argparse
import asyncio
import json
import logging
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cloud.api.shortlist_history import IST, get_history  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("quantos.shortlist.backfill")

BACKFILL_SOURCE = "journald-backfill"

# The python logger's own timestamp, which is UTC on the VM. Preferred over
# journald's syslog prefix because it carries a four-digit year -- the syslog
# prefix ("Aug 27 01:32:53") does not, and inferring the year around a New
# Year boundary is exactly the kind of guess this file exists to avoid.
_TS = re.compile(r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}")

# "[nifty500] Fetching daily history for 500 symbols" — opens a universe block.
_UNIVERSE = re.compile(r"\[(?P<universe>[a-z0-9_]+)\] Fetching daily history")

# "LEADER_TIGHT_BASE (28):" — opens a bucket block within the current universe.
_BUCKET = re.compile(
    r"momentum_shortlist: (?P<bucket>LEADER_TIGHT_BASE|LEADER_EXTENDED|"
    r"BUILDING_BASE|WATCH) \((?P<count>\d+)\):")

# One ranked row. Fields are %-padded in the source format string, so every
# separator is matched as \s+ and the two states containing a space
# ("IN BOX", "NO BASE") are picked up by the non-greedy runs.
_ENTRY = re.compile(
    r"momentum_shortlist:\s{2,}(?P<symbol>[A-Z0-9&.\-]+)\s+"
    r"momentum=(?P<momentum>-?[\d.]+)%\s+"
    r"trend=(?P<trend>UP|down)\s+"
    r"breakout=(?P<breakout>.*?)\s+"
    r"50/200=(?P<cross>.*?)\s+"
    r"width=(?P<width>[\d.]+%|—|-)\s+"
    r"rr=(?P<rr>[\d.]+|—|-)\s+"
    r"vault=(?P<vault>.*?)\s*$")

# "OUT 27d" / "BULL 16d" — a state plus how many sessions it has held.
_STATE_DAYS = re.compile(r"^(?P<state>[A-Z ]+?)(?:\s+(?P<days>\d+)d)?$")

# "Minervini=5/6 Weinstein=3/5"
_NOTE = re.compile(r"(?P<label>[A-Za-z][A-Za-z0-9_]*)=(?P<passed>\d+)/(?P<total>\d+)")


def _num(raw):
    """'15.6%' / '6.73' / '—' -> float or None. An em dash is the scan's own
    marker for 'this name has no base', so it must become None, never 0.0 —
    a zero box width would read as an infinitely tight base."""
    if raw in (None, "—", "-", ""):
        return None
    try:
        return float(raw.rstrip("%"))
    except ValueError:
        return None


def _split_state(raw):
    """'OUT 27d' -> ('OUT', 27); 'NEAR' -> ('NEAR', None); '—' -> (None, None)."""
    raw = (raw or "").strip()
    if raw in ("", "—", "-"):
        return None, None
    m = _STATE_DAYS.match(raw)
    if not m:
        return raw, None
    days = m.group("days")
    return m.group("state").strip(), int(days) if days else None


def _parse_vault(raw: str):
    """'Minervini=5/6 Weinstein=3/5' -> per-note dicts.

    A bare verdict word ('PASS', 'fail', 'no-data', 'n/a', '—') is what the
    scan logs when a name has no per-note scores at all; it yields no notes
    rather than a fabricated zero."""
    notes = [{"label": m.group("label"),
              "rules_passed": int(m.group("passed")),
              "rules_total": int(m.group("total"))}
             for m in _NOTE.finditer(raw or "")]
    return notes


def parse_journal(lines) -> dict:
    """(ist_date, universe) -> list of entry dicts, ranks already assigned."""
    sessions: dict[tuple[str, str], list[dict]] = defaultdict(list)
    universe = None
    bucket = None
    day = None

    for line in lines:
        ts = _TS.search(line)
        if ts:
            utc = datetime.strptime(ts.group("ts"), "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc)
            day = utc.astimezone(IST).date().isoformat()

        u = _UNIVERSE.search(line)
        if u:
            universe = u.group("universe")
            # A new universe block resets the bucket: the first bucket header
            # always follows, and carrying the previous universe's bucket
            # across the boundary would mislabel its first rows.
            bucket = None
            # It also SUPERSEDES anything already collected for this universe
            # today. The service can run twice in a day -- 2026-08-17 did,
            # logging two complete boards -- and appending merges them into
            # one impossible session: every symbol twice, and _assign_ranks
            # numbering 1..100 over a 50-name universe. Last complete run
            # wins, which is the same rule _sql_replace_day applies.
            if day is not None:
                sessions.pop((day, universe), None)
            continue

        b = _BUCKET.search(line)
        if b:
            bucket = b.group("bucket")
            continue

        e = _ENTRY.search(line)
        if not e or not universe or not bucket or not day:
            continue

        bo_state, bo_days = _split_state(e.group("breakout"))
        cross, cross_days = _split_state(e.group("cross"))
        sessions[(day, universe)].append({
            "symbol": e.group("symbol"),
            "bucket": bucket,
            "momentum_pct": _num(e.group("momentum")),
            "breakout_state": bo_state,
            "days_above_ceil": bo_days,
            "trend_up": e.group("trend") == "UP",
            "ma_cross": cross,
            "ma_cross_days": cross_days,
            "box_width_pct": _num(e.group("width")),
            "rr_ratio": _num(e.group("rr")),
            "vault_notes": _parse_vault(e.group("vault")),
            # Not recoverable from the log — see the module docstring.
            "close": None,
            "stage": None,
            "vault_verdict": None,
        })

    for entries in sessions.values():
        _assign_ranks(entries)
    return sessions


def _assign_ranks(entries: list[dict]) -> None:
    """Reproduce build_shortlist's rank: sort by momentum_pct descending,
    number from 1. Mutates in place."""
    ordered = sorted(entries,
                     key=lambda e: (e["momentum_pct"] is None,
                                    -(e["momentum_pct"] or 0.0)))
    for rank, entry in enumerate(ordered, start=1):
        entry["momentum_rank"] = rank


def _read_journal(since: str) -> list[str]:
    cmd = ["journalctl", "-u", "quantos-momentum-shortlist", "--no-pager"]
    if since:
        cmd += ["--since", since]
    logger.info("Reading journal: %s", " ".join(cmd))
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


async def main_async(args) -> int:
    if args.stdin:
        lines = sys.stdin.read().splitlines()
    else:
        try:
            lines = _read_journal(args.since)
        except FileNotFoundError:
            logger.error("journalctl not found — run this on the VM, or pipe a "
                         "captured journal in with --stdin.")
            return 2
        except subprocess.CalledProcessError as e:
            logger.error("journalctl failed (%s): %s", e.returncode, e.stderr.strip())
            return 2

    sessions = parse_journal(lines)
    if not sessions:
        logger.warning("No shortlist sessions parsed from %d lines. Nothing written.",
                       len(lines))
        return 1

    by_day = defaultdict(dict)
    for (day, universe), entries in sessions.items():
        by_day[day][universe] = len(entries)
    logger.info("Parsed %d sessions across %d days:", len(sessions), len(by_day))
    for day in sorted(by_day):
        logger.info("  %s  %s", day,
                    "  ".join(f"{u}={n}" for u, n in sorted(by_day[day].items())))

    if args.dry_run:
        logger.info("--dry-run: nothing written.")
        return 0

    history = await get_history()
    connected = await history.connect()
    if not connected:
        logger.error("No persistent backend (DATABASE_URL unset or unreachable). "
                     "A backfill into the in-memory store would vanish on the next "
                     "restart, so this is refused rather than silently wasted.")
        return 2

    written = 0
    for (day, universe), entries in sorted(sessions.items()):
        n = await history.record_snapshot(
            universe, entries,
            scan_date=datetime.strptime(day, "%Y-%m-%d").date(),
            source=BACKFILL_SOURCE)
        written += n
        logger.info("  wrote %-22s %s: %d rows", universe, day, n)

    logger.info("Backfill complete: %d rows across %d sessions.", written, len(sessions))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", default="2026-07-01",
                    help="journalctl --since value (default: 2026-07-01)")
    ap.add_argument("--stdin", action="store_true",
                    help="read journal text from stdin instead of running journalctl")
    ap.add_argument("--dry-run", action="store_true",
                    help="parse and report, write nothing")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
