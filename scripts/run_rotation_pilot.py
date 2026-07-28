#!/usr/bin/env python3
"""
QuantOS — Momentum Turnover Real-Capital Pilot: daily-fired quarterly trigger
──────────────────────────────────────────────────────────────────────────────
core/rotation/pilot_executor.py's own quarter-boundary gate makes this a safe
no-op on every day that isn't a quarter boundary, and self-healing on days the
gate WAS due but this run failed (most likely cause: the same stale-Fyers-
auth-token risk scripts/run_rotation_rebalance.py already documents — the
next day's run retries automatically).

Runs ALONGSIDE agent/paper_rotation_positions.py's paper walk-forward, not
instead of it — see agent/config.yaml's rotation_pilot block for why. No
cloud/Telegram integration in this first version (same deliberate scoping as
scripts/run_paper_momentum_walkforward.py) — failures are visible via
`journalctl -u quantos-rotation-pilot` during the user's existing daily VM
check-in.

Usage:
    python scripts/run_rotation_pilot.py
    python scripts/run_rotation_pilot.py --dry-run   # force dry-run regardless of config
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import TRADE_HISTORY_PATH, load_config, _load_universe  # noqa: E402
from core.rotation.pilot_executor import run_quarterly_pilot_rebalance  # noqa: E402

logging.basicConfig(level=logging.INFO,
                     format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("quantos.rotation.pilot.manual")


async def main_async(args) -> int:
    config = load_config(args.config)
    pilot_cfg = config.get("rotation_pilot", {})

    if not bool(pilot_cfg.get("enabled", False)):
        logger.info("Rotation pilot: rotation_pilot.enabled is false in config — no-op.")
        return 0

    from core.brokers import get_broker
    broker = get_broker(config)
    logger.info("Connecting to broker: %s", config.get("broker"))
    broker.connect()

    universe_path = pilot_cfg.get("universe_file", "agent/universe_nifty500.txt")
    top_n = int(pilot_cfg.get("top_n", 20))
    position_size = float(pilot_cfg.get("position_size", 2500))
    capital_reference = float(pilot_cfg.get("capital_reference", 53000))
    max_loss_pct = float(pilot_cfg.get("max_loss_pct", 0.25))
    dry_run = True if args.dry_run else bool(pilot_cfg.get("dry_run", True))

    if not dry_run:
        logger.warning(
            "!!! LIVE MODE — config.yaml's rotation_pilot.dry_run is false and "
            "--dry-run wasn't passed. This run will place REAL orders with REAL "
            "capital. Ctrl+C within 10s to abort.")
        time.sleep(10)

    universe = _load_universe(universe_path)
    if not universe:
        raise RuntimeError(f"Rotation pilot universe is empty ({universe_path})")

    logger.info(
        "Rotation pilot: checking quarter-boundary gate (top_n=%d, position_size=%.0f, "
        "capital_reference=%.0f, max_loss_pct=%.1f%%, dry_run=%s) over %d symbols",
        top_n, position_size, capital_reference, max_loss_pct * 100, dry_run, len(universe))

    result = await run_quarterly_pilot_rebalance(
        broker, universe,
        top_n=top_n, position_size=position_size, max_loss_pct=max_loss_pct,
        capital_reference=capital_reference, trade_history_path=TRADE_HISTORY_PATH,
        dry_run=dry_run,
    )

    if result is None:
        logger.info("Rotation pilot: not yet due (no new quarter boundary) — no-op today.")
        return 0

    logger.info("Rotation pilot rebalanced for quarter-end %s: %d buys, %d sells, %d skipped, "
                "cumulative realized pnl Rs%.2f (dry_run=%s)",
                result.quarter_end, len(result.buys), len(result.sells),
                len(result.skipped_buys), result.realized_pnl, result.dry_run)
    for b in result.buys:
        logger.info("  BUY  %-12s qty=%-6d price=%.2f order_id=%s",
                    b["symbol"], b["quantity"], b["price"], b["order_id"])
    for s in result.sells:
        logger.info("  SELL %-12s qty=%-6d entry=%.2f exit=%.2f order_id=%s",
                    s["symbol"], s["quantity"], s["entry_price"], s["exit_price"], s["order_id"])
    for sk in result.skipped_buys:
        logger.info("  SKIP %-12s reason=%s", sk["symbol"], sk["reason"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--dry-run", action="store_true",
                        help="Force dry-run regardless of config's rotation_pilot.dry_run value.")
    args = parser.parse_args()
    try:
        return asyncio.run(main_async(args))
    except Exception as e:
        logger.error("Rotation pilot run failed: %s", e)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
