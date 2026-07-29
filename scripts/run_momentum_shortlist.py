#!/usr/bin/env python3
"""
QuantOS — Momentum + Base Quality Shortlist: daily standalone run
──────────────────────────────────────────────────────────────────
Discretionary review aid, not a strategy. Ranks a universe by 52-week-high
proximity (core/rotation/ranker.py's well-evidenced momentum score) and
overlays each name's current Darvas weekly base state
(core/darvas/weekly_discovery.py) so a human can skim "momentum leaders in
a tight base" vs. "already extended" vs. "still building" before deciding
whether/what to buy. See core/discovery/momentum_shortlist.py for the full
rationale and core/discovery/momentum_shortlist.py's module docstring for
why neither half of this is a novel claim of edge.

No broker.place_order() call anywhere in this path. No dry_run flag needed
— there's nothing here that could place a real order even misconfigured.

Runs standalone (does not import or wake agent/main.py's run_agent() loop,
so it does NOT revive Darvas discovery/scanning/live trading, which stays
intentionally mothballed) — same pattern as scripts/run_paper_momentum_walkforward.py.

Usage:
    python scripts/run_momentum_shortlist.py
    python scripts/run_momentum_shortlist.py --universe agent/universe_nifty500.txt
    python scripts/run_momentum_shortlist.py --no-report   # skip the cloud POST
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from agent.main import load_config, _load_universe  # noqa: E402
from core.discovery.momentum_shortlist import ShortlistEntry, build_shortlist  # noqa: E402

logging.basicConfig(level=logging.INFO,
                     format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("quantos.discovery.momentum_shortlist")

# Nifty Alpha 50 — NSE's own risk-adjusted-momentum index, and already this
# project's alpha benchmark elsewhere (docs/MOMENTUM_TURNOVER_ABLATION_RESULTS.md).
# Chosen over the full Nifty 500 deliberately: a shorter, already
# momentum-pre-screened list for a human to actually skim daily, not a
# 500-row table. Override with --universe for a wider scan.
DEFAULT_UNIVERSE_FILE = "agent/universe_alpha50.txt"

# core/rotation/ranker.LOOKBACK_DAYS (252 trading days) plus enough calendar
# buffer for weekends/holidays, mirroring core/rotation/paper_executor.py's
# own FETCH_WINDOW_DAYS margin for the same 252-trading-day requirement.
FETCH_WINDOW_DAYS = 400


def _cloud_url_and_headers(config: dict) -> tuple[str, dict]:
    cloud_url = config["cloud"]["api_url"].rstrip("/")
    cloud_secret = config["cloud"].get("api_secret", "")
    headers = {"X-Cloud-Secret": cloud_secret} if cloud_secret else {}
    return cloud_url, headers


def _report_shortlist_to_cloud(config: dict, entries: list[ShortlistEntry]) -> None:
    from dataclasses import asdict
    cloud_url, headers = _cloud_url_and_headers(config)
    payload = {"entries": [asdict(e) for e in entries]}
    resp = requests.post(f"{cloud_url}/discovery/momentum-shortlist",
                          json=payload, headers=headers, timeout=15)
    resp.raise_for_status()


async def _fetch_universe_daily(broker, universe: list[str]) -> dict:
    from scripts.validate_regime_classifier import fetch_chunked_daily

    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=FETCH_WINDOW_DAYS)
    sem = asyncio.Semaphore(2)

    daily_by_symbol = {}
    for symbol in universe:
        candles = await fetch_chunked_daily(broker, symbol, from_date, to_date, sem)
        if candles:
            daily_by_symbol[symbol] = candles
    return daily_by_symbol


def _log_summary(entries: list[ShortlistEntry]) -> None:
    by_bucket: dict[str, list[ShortlistEntry]] = {}
    for e in entries:
        by_bucket.setdefault(e.bucket, []).append(e)

    for bucket in ("LEADER_TIGHT_BASE", "LEADER_EXTENDED", "BUILDING_BASE", "WATCH"):
        rows = by_bucket.get(bucket, [])
        if not rows:
            continue
        logger.info("%s (%d):", bucket, len(rows))
        for e in rows:
            logger.info("  %-12s momentum=%.1f%% base=%-16s width=%s rr=%s",
                        e.symbol, e.momentum_pct, e.base_status,
                        f"{e.box_width_pct:.1f}%" if e.box_width_pct is not None else "—",
                        f"{e.rr_ratio:.2f}" if e.rr_ratio is not None else "—")


async def main_async(args) -> int:
    config = load_config(args.config)

    from core.brokers import get_broker
    broker = get_broker(config)
    logger.info("Connecting to broker: %s", config.get("broker"))
    broker.connect()

    universe = _load_universe(args.universe)
    if not universe:
        raise RuntimeError(f"Momentum shortlist universe is empty ({args.universe})")

    logger.info("Fetching daily history for %d symbols (%s)...", len(universe), args.universe)
    daily_by_symbol = await _fetch_universe_daily(broker, universe)
    logger.info("Got history for %d/%d symbols", len(daily_by_symbol), len(universe))

    entries = build_shortlist(daily_by_symbol, datetime.now(timezone.utc))
    logger.info("Shortlist built: %d/%d symbols had enough history to rank",
                len(entries), len(daily_by_symbol))
    _log_summary(entries)

    if not args.no_report:
        _report_shortlist_to_cloud(config, entries)
        logger.info("Synced to cloud — cockpit's Momentum Shortlist panel will pick this up.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--universe", default=DEFAULT_UNIVERSE_FILE)
    parser.add_argument("--no-report", action="store_true",
                        help="Skip POSTing results to the cloud (local/manual runs).")
    args = parser.parse_args()
    try:
        return asyncio.run(main_async(args))
    except Exception as e:
        logger.error("Momentum shortlist run failed: %s", e)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
