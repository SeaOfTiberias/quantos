#!/usr/bin/env python3
"""
QuantOS — derive the NSE trading calendar from observed index sessions.

Regenerates `core/reference/data/nse_trading_days.txt`. Run this to extend the
covered window; the calendar fails closed outside it rather than guessing, so
extending is a deliberate act with a committed artifact, not a silent default.

MUST RUN ON THE VM. Fyers whitelists one static IP (161.118.189.29) and the
token refresh is interactive:

    ssh -i "<key>" ubuntu@161.118.189.29
    cd ~/quantos && .venv/bin/python scripts/derive_nse_calendar.py
    # then copy core/reference/data/nse_trading_days.txt back and commit it

WHY THE INDEX AND NOT THE BHAVCOPY
──────────────────────────────────
The obvious source is the local bhavcopy cache — 737 parsed files, free, no
broker needed. It is the wrong source, and the reason is worth keeping:

those files were fetched day-by-day by the very `_weekdays()` helpers this
calendar exists to replace. That loop never requested a Saturday, so the cache
contains no Saturday and *cannot evidence one*. Deriving from it would launder
the bug into the fix and produce a calendar that confirms itself.

Asking the broker for a date *range* inverts the control: the response reports
whichever days exist, including ones the caller did not think to ask about.
That is how the 11 weekend sessions surfaced. Bhavcopy is kept below as a
cross-check — a source that can produce false negatives is still useful for
catching false positives.

WHAT COUNTS AS A SESSION
────────────────────────
A date on which NIFTY 50 produced a daily bar. Index-level, so it is unaffected
by any single stock being suspended, and it covers cash and F&O alike since
they share the NSE session calendar. It does not distinguish a full session
from a special one-hour Muhurat session — both are sessions for every purpose
this calendar serves.
"""

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config          # noqa: E402
from core.brokers import get_broker         # noqa: E402
from core.regime.fetcher import NIFTY_SYMBOL  # noqa: E402

OUT_PATH = Path(__file__).resolve().parent.parent / "core" / "reference" / "data" / "nse_trading_days.txt"
BHAVCOPY_DIR = Path("data_cache/nse_bhavcopy/parsed")

FIRST_YEAR = 2015          # Fyers daily history reaches at least this far back
RETRIES = 4
BACKOFF_SECONDS = 6        # Fyers returns code 429 "request limit reached"
INTER_YEAR_PAUSE = 2

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("quantos.reference.calendar")


def fetch_sessions(broker, first_year: int, last_year: int) -> set[date]:
    """Every date NIFTY 50 produced a daily bar, walked a year at a time.

    Year-sized chunks keep each response inside Fyers' per-request cap while
    staying well under its rate limit with the pause below.
    """
    days: set[date] = set()
    for year in range(first_year, last_year + 1):
        for attempt in range(RETRIES):
            try:
                candles = broker.get_historical_data(
                    NIFTY_SYMBOL, "1d",
                    datetime(year, 1, 1, tzinfo=timezone.utc),
                    datetime(year, 12, 31, tzinfo=timezone.utc),
                )
                for c in candles:
                    days.add(c.timestamp.date())
                logger.info("  %d: %d sessions", year, len(candles))
                break
            except Exception as exc:                      # noqa: BLE001
                if attempt == RETRIES - 1:
                    logger.error("  %d: FAILED after %d attempts — %s",
                                 year, RETRIES, str(exc)[:120])
                else:
                    time.sleep(BACKOFF_SECONDS)
        time.sleep(INTER_YEAR_PAUSE)
    return days


def crosscheck_bhavcopy(days: set[date]) -> None:
    """Every cached bhavcopy date must be a session. The converse need not hold.

    A bhavcopy file is proof a session happened, so a file with no matching
    session means the derivation missed a real day — that is a hard failure.
    Sessions with no file are expected: the old fetcher never asked for
    weekends, and the cache starts well after 2015.
    """
    if not BHAVCOPY_DIR.exists():
        logger.info("\nbhavcopy cross-check: skipped (%s not present — "
                    "expected on the VM, which holds no cache)", BHAVCOPY_DIR)
        return

    files = {
        date(int(f.name[:4]), int(f.name[4:6]), int(f.name[6:8]))
        for f in BHAVCOPY_DIR.glob("*.csv")
    }
    if not files:
        logger.info("\nbhavcopy cross-check: skipped (cache empty)")
        return

    lo, hi = min(files), max(files)
    in_window = {d for d in days if lo <= d <= hi}
    orphans = sorted(files - days)

    logger.info("\nbhavcopy cross-check over %s .. %s", lo, hi)
    logger.info("  cached files            : %d", len(files))
    logger.info("  derived sessions        : %d", len(in_window))
    logger.info("  sessions with no file   : %d  (weekend sessions the old "
                "day-by-day fetcher never requested)", len(in_window - files))
    if orphans:
        raise SystemExit(
            f"CROSS-CHECK FAILED: {len(orphans)} bhavcopy file(s) have no "
            f"derived session — the derivation missed real days: {orphans[:10]}"
        )
    logger.info("  files with no session   : 0  ✓")


def report_naive_delta(days: set[date]) -> None:
    """Quantify what the calendar is worth against the helper it replaces."""
    lo, hi = min(days), max(days)
    naive, d = set(), lo
    while d <= hi:
        if d.weekday() < 5:
            naive.add(d)
        d += timedelta(days=1)

    false_pos = naive - days      # holidays the naive helper counts as sessions
    false_neg = days - naive      # real weekend sessions it drops

    logger.info("\nversus naive weekday() < 5, over %s .. %s", lo, hi)
    logger.info("  naive claims            : %d days", len(naive))
    logger.info("  actual sessions         : %d days", len(days))
    logger.info("  false positives         : %d  (%.1f%% of naive's days were "
                "holidays)", len(false_pos), 100 * len(false_pos) / len(naive))
    logger.info("  false negatives         : %d  (real sessions dropped)",
                len(false_neg))
    for d in sorted(false_neg):
        logger.info("      %s  %s", d, d.strftime("%A"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="agent/config.yaml")
    ap.add_argument("--from-year", type=int, default=FIRST_YEAR)
    ap.add_argument("--to-year", type=int, default=date.today().year)
    ap.add_argument("--dry-run", action="store_true",
                    help="derive and report, but do not write the data file")
    args = ap.parse_args()

    broker = get_broker(load_config(args.config))
    if not broker.connect():
        logger.error("broker connect failed — refresh the Fyers token first")
        return 1

    logger.info("Deriving NSE sessions from %s daily bars, %d..%d",
                NIFTY_SYMBOL, args.from_year, args.to_year)
    days = fetch_sessions(broker, args.from_year, args.to_year)
    if not days:
        logger.error("no sessions derived — refusing to write an empty calendar")
        return 1

    crosscheck_bhavcopy(days)
    report_naive_delta(days)

    if args.dry_run:
        logger.info("\n--dry-run: not writing %s", OUT_PATH)
        return 0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        "\n".join(d.isoformat() for d in sorted(days)) + "\n", encoding="utf-8"
    )
    logger.info("\nWrote %d sessions to %s", len(days), OUT_PATH)
    logger.info("Commit that file — the VM has no bhavcopy cache and cannot "
                "regenerate it from local data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
