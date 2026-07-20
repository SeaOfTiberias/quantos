#!/usr/bin/env python3
"""
QuantOS — S8-3 Weekly Rotation: standalone manual trigger
──────────────────────────────────────────────────────────
Manually runs ONE rotation rebalance cycle (core/rotation/executor.py)
without waking the full agent loop (agent/main.py run_agent()) — which
would also resume Darvas discovery/scanning/live trading, deliberately
mothballed since 2026-07-19 pending Sprint 8's conclusions (S7-3: no
demonstrated Darvas edge; S8-1: regime classifier doesn't reliably
separate outcomes). This script only ever connects the broker and runs
rotation — no Stage A/B, no cloud signal polling.

Reports the result to the cloud the same way the live agent's automatic
weekly gate would (EXECUTED signal rows if not dry-run, one consolidated
Telegram summary either way) — so a manual run here is observable the
same way an eventual automatic one would be. Skip that with --no-report.

Also reports a Telegram alert on any failure (POST /rotation/failed) —
this matters most when triggered unattended by
deploy/systemd/quantos-rotation.timer, since the most likely failure
(a stale Fyers auth token) can't self-heal: the interactive OAuth refresh
still needs a human, and without an alert a missed weekly refresh would
just fail silently in a systemd log nobody's watching.

Usage:
    python scripts/run_rotation_rebalance.py                # uses config.yaml's rotation.* block
    python scripts/run_rotation_rebalance.py --dry-run       # force dry-run regardless of config
    python scripts/run_rotation_rebalance.py --no-report     # skip the cloud POST / Telegram summary
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from agent.main import load_config, _load_universe, _report_rotation_to_cloud  # noqa: E402
from core.rotation.executor import run_weekly_rebalance  # noqa: E402

logging.basicConfig(level=logging.INFO,
                     format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("quantos.rotation.manual")


def _cloud_url_and_headers(config: dict) -> tuple[str, dict]:
    cloud_url = config["cloud"]["api_url"].rstrip("/")
    cloud_secret = config["cloud"].get("api_secret", "")
    headers = {"X-Cloud-Secret": cloud_secret} if cloud_secret else {}
    return cloud_url, headers


def _report_failure_to_cloud(config: dict, error: str) -> None:
    try:
        cloud_url, headers = _cloud_url_and_headers(config)
        resp = requests.post(f"{cloud_url}/rotation/failed", json={"error": error},
                             headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        logger.error("Also failed to report this failure to the cloud: %s", e)


async def main_async(args) -> int:
    config = load_config(args.config)

    try:
        from core.brokers import get_broker
        broker = get_broker(config)
        logger.info("Connecting to broker: %s", config.get("broker"))
        broker.connect()

        rotation_cfg = config.get("rotation", {})
        universe_path = rotation_cfg.get("universe_file", "agent/universe_nifty500.txt")
        top_n = int(rotation_cfg.get("top_n", 20))
        position_size = float(rotation_cfg.get("position_size", 100_000))
        dry_run = True if args.dry_run else bool(rotation_cfg.get("dry_run", True))

        if not dry_run:
            logger.warning(
                "!!! LIVE MODE — config.yaml's rotation.dry_run is false and --dry-run "
                "wasn't passed. This run will place REAL orders with REAL capital. "
                "Ctrl+C within 10s to abort.")
            time.sleep(10)

        universe = _load_universe(universe_path)
        if not universe:
            raise RuntimeError(f"Rotation universe is empty ({universe_path})")

        logger.info(
            "Starting manual rotation rebalance (top_n=%d, position_size=%.0f, "
            "dry_run=%s) over %d symbols", top_n, position_size, dry_run, len(universe))

        result = await run_weekly_rebalance(
            broker, universe, top_n=top_n, position_size=position_size, dry_run=dry_run)
    except Exception as e:
        logger.error("Rotation run failed: %s", e)
        if not args.no_report:
            _report_failure_to_cloud(config, str(e))
        raise

    logger.info("Rotation: %d buys, %d sells, %d skipped (dry_run=%s)",
                len(result.buys), len(result.sells), len(result.skipped_buys), result.dry_run)
    for b in result.buys:
        logger.info("  BUY  %-12s qty=%-6d price=%.2f order_id=%s",
                    b["symbol"], b["quantity"], b["price"], b["order_id"])
    for s in result.sells:
        logger.info("  SELL %-12s qty=%-6d entry=%.2f order_id=%s",
                    s["symbol"], s["quantity"], s["entry_price"], s["order_id"])
    for sk in result.skipped_buys:
        logger.info("  SKIP %-12s reason=%s", sk["symbol"], sk["reason"])

    if not args.no_report:
        cloud_url, headers = _cloud_url_and_headers(config)
        _report_rotation_to_cloud(cloud_url, headers, result)
        logger.info("Reported to cloud — check Telegram for the summary.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--dry-run", action="store_true",
                        help="Force dry-run regardless of config's rotation.dry_run value.")
    parser.add_argument("--no-report", action="store_true",
                        help="Skip POSTing the result to the cloud (no Telegram summary, no signal rows).")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
