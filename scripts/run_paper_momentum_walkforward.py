#!/usr/bin/env python3
"""
QuantOS — Momentum Turnover Walk-Forward: daily-fired paper rebalance trigger
──────────────────────────────────────────────────────────────────────────────
docs/MOMENTUM_TURNOVER_WALKFORWARD_METHODOLOGY.md. Meant to run once a day
(deploy/systemd/quantos-paper-momentum.timer) — core/rotation/paper_executor.py's
own quarter-boundary gate makes this a safe no-op on every day that isn't a
quarter boundary, and self-healing on days the gate WAS due but this run
failed (most likely cause: the same stale-Fyers-auth-token risk
scripts/run_rotation_rebalance.py already documents — the next day's run
retries automatically).

No real capital, ever — core/rotation/paper_executor.py never calls
broker.place_order(). No cloud/Telegram integration in this first version
(deliberately scoped out, see the methodology doc's "what is genuinely new"
section) — failures are visible via `journalctl -u quantos-paper-momentum`
during the user's existing daily VM check-in.

Usage:
    python scripts/run_paper_momentum_walkforward.py
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config, _load_universe  # noqa: E402
from core.rotation.paper_executor import run_quarterly_paper_rebalance  # noqa: E402
from scripts.backtest_rs_momentum import DELIVERY_COST_MODEL  # noqa: E402

logging.basicConfig(level=logging.INFO,
                     format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("quantos.rotation.paper_walkforward.manual")


async def main_async() -> int:
    config = load_config("agent/config.yaml")
    from core.brokers import get_broker
    broker = get_broker(config)
    logger.info("Connecting to broker: %s", config.get("broker"))
    broker.connect()

    universe = _load_universe("agent/universe_nifty500.txt")
    if not universe:
        raise RuntimeError("Paper walk-forward universe is empty (agent/universe_nifty500.txt)")

    result = await run_quarterly_paper_rebalance(
        broker, universe, cost_model=DELIVERY_COST_MODEL)

    if result is None:
        logger.info("Paper walk-forward: not yet due (no new quarter boundary) — no-op today.")
        return 0

    logger.info("Paper walk-forward rebalanced for quarter-end %s: %d buys, %d sells, "
                "%d skipped, equity now Rs%.0f",
                result.quarter_end, len(result.buys), len(result.sells),
                len(result.skipped_buys), result.equity_after)
    for b in result.buys:
        logger.info("  BUY  %-12s qty=%-6d price=%.2f", b["symbol"], b["quantity"], b["price"])
    for s in result.sells:
        logger.info("  SELL %-12s qty=%-6d entry=%.2f exit=%.2f",
                    s["symbol"], s["quantity"], s["entry_price"], s["exit_price"])
    for sk in result.skipped_buys:
        logger.info("  SKIP %-12s reason=%s", sk["symbol"], sk["reason"])
    return 0


def main() -> int:
    try:
        return asyncio.run(main_async())
    except Exception as e:
        logger.error("Paper walk-forward run failed: %s", e)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
