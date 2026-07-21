#!/usr/bin/env python3
"""
QuantOS — Options Regime Trigger: standalone manual check
────────────────────────────────────────────────────────────
Manually runs ONE regime-fetch + options-trigger check
(core/options/regime_trigger.py via agent.main._run_options_trigger)
without waking the full agent loop (agent/main.py run_agent()) — which
would also resume Darvas discovery/scanning/live trading, deliberately
mothballed since 2026-07-19, and the daily Fyers token-refresh ritual
that came with it. Same reasoning as scripts/run_rotation_rebalance.py,
which exists for the identical purpose for S8-3 rotation.

Reads options.enabled/dry_run/lots_per_trade from config.yaml exactly
like the live agent loop would — this script does not change what
"enabled: false" or "dry_run: true" mean, it just gives you a way to
trigger the check on demand instead of waiting for the agent's own
regime_every_n_ticks cadence (currently not running anywhere).

Usage:
    python scripts/run_options_trigger_check.py                # uses config.yaml's options.* block
    python scripts/run_options_trigger_check.py --force         # ignore the regime-unchanged dedup
                                                                  # guard, so a repeat manual run on
                                                                  # an unchanged regime still produces
                                                                  # a suggestion (for observation only —
                                                                  # the live agent never does this)
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config, _load_universe, _run_options_trigger, _run_regime_sync  # noqa: E402
from core.options.positions import load_positions as load_options_positions  # noqa: E402
from core.options import regime_trigger as options_regime_trigger  # noqa: E402
from core.regime.service import RegimeService  # noqa: E402

logging.basicConfig(level=logging.INFO,
                     format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("quantos.options_trigger.manual")


def _cloud_url_and_headers(config: dict) -> tuple[str, dict]:
    cloud_url = config["cloud"]["api_url"].rstrip("/")
    cloud_secret = config["cloud"].get("api_secret", "")
    headers = {"X-Cloud-Secret": cloud_secret} if cloud_secret else {}
    return cloud_url, headers


def run(args) -> int:
    """
    Deliberately synchronous at this level, matching agent/main.py's own
    convention (asyncio.run() per async call site, never one outer async
    wrapper) — _run_options_trigger internally does its own asyncio.run()
    for the Claude recommend_strategy() call, exactly like it does when
    invoked from the live agent's synchronous tick loop. Wrapping this
    whole function in an outer `async def main_async` (as first written)
    breaks that: asyncio.run() cannot be called from a running event
    loop, confirmed live 2026-07-21.
    """
    config = load_config(args.config)
    options_cfg = config.get("options", {})

    if not bool(options_cfg.get("enabled", False)):
        logger.warning(
            "options.enabled is false in %s — the trigger would be a no-op. "
            "Set options.enabled: true first (options.dry_run: true is still "
            "the safe default — this only gates whether a suggestion is sent "
            "for Telegram confirmation, not whether real orders are placed).",
            args.config)
        return 1

    from core.brokers import get_broker
    broker = get_broker(config)
    logger.info("Connecting to broker: %s", config.get("broker"))
    broker.connect()

    regime_cfg = config.get("regime", {})
    scanner_cfg = config.get("scanner", {})
    breadth_path = regime_cfg.get(
        "breadth_universe_file", scanner_cfg.get("universe_file", "agent/universe_nifty500.txt"))
    breadth_universe = _load_universe(breadth_path)
    logger.info("Regime breadth universe: %d symbols from %s", len(breadth_universe), breadth_path)

    cloud_url, headers = _cloud_url_and_headers(config)
    regime_service = RegimeService(broker, breadth_universe=breadth_universe)
    # _run_regime_sync both fetches AND POSTs to /regime/sync — needed
    # because /strategy/recommend reads the cloud's SYNCED regime
    # (get_synced_regime()), not anything this script computes locally.
    # A first version of this script called regime_service.get_regime()
    # directly and skipped the sync, which left the cloud regime stale/
    # missing and made /strategy/recommend 503 ("Regime not available
    # yet") — confirmed live 2026-07-21.
    regime_result = _run_regime_sync(regime_service, cloud_url, headers)
    logger.info("Current regime: %s (confidence=%.0f, allowed_strategies=%s)",
                regime_result.regime.value, regime_result.confidence,
                regime_result.allowed_strategies)

    if args.force:
        logger.info("--force: clearing the regime-unchanged dedup guard for this run.")
        if options_regime_trigger.LAST_REGIME_PATH.exists():
            options_regime_trigger.LAST_REGIME_PATH.unlink()

    opts_positions = load_options_positions()

    dry_run = bool(options_cfg.get("dry_run", True))
    if not dry_run:
        logger.warning(
            "!!! options.dry_run is false — if a suggestion is generated it WILL "
            "be sent to Telegram for confirmation (real capital if you then reply "
            "execute). Ctrl+C within 10s to abort.")
        import time
        time.sleep(10)

    _run_options_trigger(broker, config, cloud_url, headers, regime_result, opts_positions)
    logger.info("Done. If a suggestion was built and dry_run is false, check Telegram. "
                "If dry_run is true, check the log lines above for what it would have sent.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--force", action="store_true",
                        help="Ignore the regime-unchanged dedup guard for this run only.")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
