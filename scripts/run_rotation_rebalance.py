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

from agent.main import load_config, _load_universe, _report_rotation_to_cloud  # noqa: E402
from core.rotation.executor import run_weekly_rebalance  # noqa: E402

logging.basicConfig(level=logging.INFO,
                     format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("quantos.rotation.manual")


async def main_async(args) -> int:
    config = load_config(args.config)
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
        logger.error("Rotation universe is empty (%s) — aborting.", universe_path)
        return 1

    logger.info(
        "Starting manual rotation rebalance (top_n=%d, position_size=%.0f, "
        "dry_run=%s) over %d symbols", top_n, position_size, dry_run, len(universe))

    result = await run_weekly_rebalance(
        broker, universe, top_n=top_n, position_size=position_size, dry_run=dry_run)

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
        cloud_url = config["cloud"]["api_url"].rstrip("/")
        cloud_secret = config["cloud"].get("api_secret", "")
        headers = {"X-Cloud-Secret": cloud_secret} if cloud_secret else {}
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
