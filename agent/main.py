"""
QuantOS Local Agent
────────────────────
Runs on the customer's machine. Holds broker credentials locally.
Polls QuantOS cloud for pending signals, sends WhatsApp confirmation,
and executes orders via the configured broker adapter.

ADR-01: Keys never leave this machine.
ADR-05: confirm_before_execute = True by default.

Usage:
    python agent/main.py
    python agent/main.py --config path/to/config.yaml
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("quantos.agent")


def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        logger.error(
            "Config not found at %s\n"
            "Copy agent/config.yaml.example to agent/config.yaml and fill in your values.",
            config_path
        )
        sys.exit(1)
    with open(path) as f:
        return yaml.safe_load(f)


def run_agent(config: dict):
    from core.brokers import get_broker

    broker = get_broker(config)
    logger.info("Connecting to broker: %s", config.get("broker"))
    broker.connect()
    logger.info("Broker connected: %s", broker)

    cloud_url = config["cloud"]["api_url"]
    poll_interval = 5  # seconds
    confirm_before_execute = config.get("notifications", {}).get(
        "confirm_before_execute", True
    )

    logger.info(
        "Agent running. Cloud: %s | Confirm-before-execute: %s",
        cloud_url, confirm_before_execute
    )
    logger.info("Press Ctrl+C to stop.")

    try:
        while True:
            # TODO: poll cloud API for pending signals assigned to this agent
            # TODO: if signal pending → send WhatsApp confirmation (ADR-05)
            # TODO: on WhatsApp reply "execute" → place_order via broker
            # TODO: on WhatsApp reply "skip" → log rejection
            time.sleep(poll_interval)

    except KeyboardInterrupt:
        logger.info("Agent stopped.")
        broker.disconnect()


def main():
    parser = argparse.ArgumentParser(description="QuantOS Local Agent")
    parser.add_argument(
        "--config",
        default="agent/config.yaml",
        help="Path to agent config file (default: agent/config.yaml)"
    )
    args = parser.parse_args()
    config = load_config(args.config)
    run_agent(config)


if __name__ == "__main__":
    main()
