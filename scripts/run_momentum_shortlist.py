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

Scans every --universe given (default: both Nifty Alpha 50 and Nifty200
Momentum 30) in one run, sequentially over a single broker connection, and
syncs each to its own labeled slot in the cloud
(cloud/api/momentum_shortlist_routes.py) so the cockpit can show them as
separate panels without one universe's daily sync clobbering the other's.

Usage:
    python scripts/run_momentum_shortlist.py
    python scripts/run_momentum_shortlist.py --universe agent/universe_nifty500.txt
    python scripts/run_momentum_shortlist.py --universe agent/universe_alpha50.txt --universe agent/universe_nifty200momentum30.txt
    python scripts/run_momentum_shortlist.py --no-report   # skip the cloud POST
"""

import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from agent.main import load_config, _load_universe  # noqa: E402
from core.discovery.momentum_shortlist import (  # noqa: E402
    EMA_FAST, EMA_SLOW, ShortlistEntry, build_shortlist, is_uptrend,
)
from core.vault.shortlist_audit import annotate_with_vault_audit  # noqa: E402

logging.basicConfig(level=logging.INFO,
                     format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("quantos.discovery.momentum_shortlist")

# Notes every shortlist row is audited against unless agent/config.yaml's
# `vault.shortlist_notes` overrides. Both ship in obsidian_vault/QuantOS/.
DEFAULT_SHORTLIST_NOTES = ("minervini_vcp", "weinstein_stage2")

# Nifty Alpha 50 (NSE's own risk-adjusted-momentum index, already this
# project's alpha benchmark elsewhere) and Nifty200 Momentum 30 (NSE's own
# momentum-factor index, added 2026-07-29) — both short, already
# momentum-pre-screened lists for a human to actually skim daily, not a
# 500-row table. Nifty 500 added 2026-08-05 so the same top-N names the S8-3
# rotation basket picks (which ranks the full 500) are visible here too --
# the cockpit panel truncates this one to the top 10 by rank since, unlike
# the other two, it isn't pre-screened. Override with one or more --universe
# flags for a different scan.
DEFAULT_UNIVERSE_FILES = [
    "agent/universe_alpha50.txt",
    "agent/universe_nifty200momentum30.txt",
    "agent/universe_nifty500.txt",
]

# core/rotation/ranker.LOOKBACK_DAYS (252 trading days) plus enough calendar
# buffer for weekends/holidays, mirroring core/rotation/paper_executor.py's
# own FETCH_WINDOW_DAYS margin for the same 252-trading-day requirement.
FETCH_WINDOW_DAYS = 400

# core/regime/fetcher.py's own NIFTY_SYMBOL/VIX_SYMBOL convention.
NIFTY_SYMBOL = "NIFTY 50"
VIX_SYMBOL = "INDIA VIX"


def _universe_label(universe_path: str) -> str:
    """Derives the cloud sync slot from a universe filename, e.g.
    "agent/universe_alpha50.txt" -> "alpha50",
    "agent/universe_nifty200momentum30.txt" -> "nifty200momentum30" —
    no separate --label flag needed, and it can't drift out of sync with
    the file it's actually labeling."""
    stem = Path(universe_path).stem  # "universe_alpha50"
    return re.sub(r"^universe_", "", stem) or stem


def _cloud_url_and_headers(config: dict) -> tuple[str, dict]:
    cloud_url = config["cloud"]["api_url"].rstrip("/")
    cloud_secret = config["cloud"].get("api_secret", "")
    headers = {"X-Cloud-Secret": cloud_secret} if cloud_secret else {}
    return cloud_url, headers


def _report_shortlist_to_cloud(config: dict, universe_label: str,
                                entries: list[ShortlistEntry]) -> None:
    from dataclasses import asdict
    cloud_url, headers = _cloud_url_and_headers(config)
    payload = {"entries": [asdict(e) for e in entries]}
    resp = requests.post(f"{cloud_url}/discovery/momentum-shortlist/{universe_label}",
                          json=payload, headers=headers, timeout=15)
    resp.raise_for_status()


async def _sync_market_snapshot(broker, config: dict, no_report: bool) -> None:
    """NIFTY LTP + short-term trend (same EMA9/EMA21 check applied to every
    stock in the shortlist tables, so this reading and theirs never use two
    different definitions of "uptrend") + India VIX LTP. NOT a regime
    classification -- see cloud/api/market_snapshot_routes.py's module
    docstring for why that line is deliberate. Runs once per script
    invocation (not per-universe), before the universe loop, so a slow or
    failing universe scan can't stop this cheap, quick sync from keeping
    the observability heartbeat fresh."""
    from scripts.validate_regime_classifier import fetch_chunked_daily

    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=FETCH_WINDOW_DAYS)
    sem = asyncio.Semaphore(2)

    nifty_daily = await fetch_chunked_daily(broker, NIFTY_SYMBOL, from_date, to_date, sem)
    if not nifty_daily:
        logger.warning("Market snapshot: no NIFTY history returned — skipping sync.")
        return
    trend_up = is_uptrend(nifty_daily, to_date, EMA_FAST, EMA_SLOW)

    loop = asyncio.get_event_loop()
    ltp = await loop.run_in_executor(None, lambda: broker.get_ltp([NIFTY_SYMBOL, VIX_SYMBOL]))
    nifty_ltp = ltp.get(NIFTY_SYMBOL) or nifty_daily[-1].close
    vix_current = ltp.get(VIX_SYMBOL)

    logger.info("Market snapshot: NIFTY=%.1f trend=%s VIX=%s",
                nifty_ltp, "UP" if trend_up else "down",
                f"{vix_current:.2f}" if vix_current is not None else "—")

    if not no_report:
        cloud_url, headers = _cloud_url_and_headers(config)
        resp = requests.post(f"{cloud_url}/market/snapshot",
                              json={"nifty_ltp": nifty_ltp, "nifty_trend_up": trend_up,
                                    "vix_current": vix_current},
                              headers=headers, timeout=15)
        resp.raise_for_status()
        logger.info("Market snapshot synced to cloud.")


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
            breakout = e.breakout_state
            if e.breakout_state == "OUT" and e.days_above_ceil is not None:
                breakout = f"OUT {e.days_above_ceil}d"
            cross = e.ma_cross or "—"
            if e.ma_cross and e.ma_cross_days is not None:
                cross = f"{e.ma_cross} {e.ma_cross_days}d"
            # Vault column abbreviated to keep the line scannable: the full
            # per-note breakdown lives in e.vault_detail and in the cockpit.
            # Per note, never summed -- the two bundled notes' clean-pass sets
            # are disjoint by construction (see shortlist_audit._note_scores).
            vault = " ".join(
                f"{n.label}={n.rules_passed}/{n.rules_total}" for n in e.vault_notes
            ) or {"PASS": "PASS", "FAIL": "fail",
                  "INSUFFICIENT_DATA": "no-data",
                  "UNAVAILABLE": "n/a"}.get(e.vault_verdict or "", "—")
            logger.info("  %-12s momentum=%.1f%% trend=%-4s breakout=%-10s 50/200=%-9s width=%s rr=%s vault=%s",
                        e.symbol, e.momentum_pct, "UP" if e.trend_up else "down", breakout, cross,
                        f"{e.box_width_pct:.1f}%" if e.box_width_pct is not None else "—",
                        f"{e.rr_ratio:.2f}" if e.rr_ratio is not None else "—", vault)


async def _run_one_universe(broker, config: dict, universe_path: str, no_report: bool) -> None:
    label = _universe_label(universe_path)
    universe = _load_universe(universe_path)
    if not universe:
        raise RuntimeError(f"Momentum shortlist universe is empty ({universe_path})")

    logger.info("[%s] Fetching daily history for %d symbols (%s)...",
                label, len(universe), universe_path)
    daily_by_symbol = await _fetch_universe_daily(broker, universe)
    logger.info("[%s] Got history for %d/%d symbols", label, len(daily_by_symbol), len(universe))

    entries = build_shortlist(daily_by_symbol, datetime.now(timezone.utc))
    logger.info("[%s] Shortlist built: %d/%d symbols had enough history to rank",
                label, len(entries), len(daily_by_symbol))

    # Obsidian vault audit (2026-08-14). Annotation only -- the shortlist has
    # no execution path, so this can never block anything; it adds a column
    # saying whether each name satisfies the strategy notes' written rules.
    # Failures are swallowed inside annotate_with_vault_audit and surface as
    # an UNAVAILABLE column, never as a lost shortlist.
    vault_cfg = config.get("vault", {}) or {}
    if vault_cfg.get("annotate_shortlist", True):
        entries = annotate_with_vault_audit(
            entries, daily_by_symbol,
            vault_cfg.get("shortlist_notes", DEFAULT_SHORTLIST_NOTES),
            vault_dir=vault_cfg.get("dir"),
        )

    _log_summary(entries)

    if not no_report:
        _report_shortlist_to_cloud(config, label, entries)
        logger.info("[%s] Synced to cloud (slot=%s) — cockpit will pick this up.", label, label)


async def main_async(args) -> int:
    config = load_config(args.config)

    from core.brokers import get_broker
    broker = get_broker(config)
    logger.info("Connecting to broker: %s", config.get("broker"))
    broker.connect()

    try:
        await _sync_market_snapshot(broker, config, args.no_report)
    except Exception as e:
        # Best-effort: a failed snapshot sync shouldn't block the universe
        # scans below, which are this script's main job.
        logger.error("Market snapshot sync failed (continuing): %s", e)

    for universe_path in args.universe:
        await _run_one_universe(broker, config, universe_path, args.no_report)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--universe", action="append", default=None,
                        help="Universe file to scan; repeatable. Defaults to both "
                             "Alpha 50 and Nifty200 Momentum 30 if omitted.")
    parser.add_argument("--no-report", action="store_true",
                        help="Skip POSTing results to the cloud (local/manual runs).")
    args = parser.parse_args()
    if args.universe is None:
        args.universe = DEFAULT_UNIVERSE_FILES
    try:
        return asyncio.run(main_async(args))
    except Exception as e:
        logger.error("Momentum shortlist run failed: %s", e)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
