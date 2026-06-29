"""
QuantOS — Uptime Monitor
──────────────────────────
US-15: Sends WhatsApp alert if the cloud API goes down.

Run this on the local agent machine (or any always-on device)
as a lightweight watchdog alongside the agent process.

Usage:
    python deploy/monitor.py --url https://your-app.railway.app

It pings /health every CHECK_INTERVAL seconds.
If the API fails MAX_FAILURES consecutive checks, it fires a WhatsApp alert.
Auto-recovers — sends an "all clear" when the API comes back up.
"""

import argparse
import asyncio
import logging
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

logger = logging.getLogger("quantos.monitor")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

CHECK_INTERVAL = 60      # seconds between health checks
MAX_FAILURES   = 3       # consecutive failures before alerting
TIMEOUT        = 10      # HTTP timeout per check


async def send_whatsapp_alert(message: str, phone: str, api_key: str) -> None:
    """Send WhatsApp alert via CallMeBot."""
    import urllib.parse
    url = (
        f"https://api.callmebot.com/whatsapp.php"
        f"?phone={phone}&text={urllib.parse.quote(message)}&apikey={api_key}"
    )
    try:
        urllib.request.urlopen(url, timeout=10)
        logger.info("WhatsApp alert sent")
    except Exception as e:
        logger.error("WhatsApp alert failed: %s", e)


def check_health(url: str) -> tuple[bool, str]:
    """
    Ping the /health endpoint.
    Returns (is_healthy, message).
    """
    try:
        resp = urllib.request.urlopen(f"{url}/health", timeout=TIMEOUT)
        if resp.status == 200:
            return True, "OK"
        return False, f"HTTP {resp.status}"
    except urllib.error.URLError as e:
        return False, str(e.reason)
    except Exception as e:
        return False, str(e)


async def run_monitor(api_url: str, phone: str, api_key: str) -> None:
    """Main monitor loop."""
    logger.info("QuantOS Monitor started — watching %s", api_url)
    logger.info("Check interval: %ds | Alert after %d failures", CHECK_INTERVAL, MAX_FAILURES)

    failures      = 0
    alert_sent    = False
    last_status   = True   # assume healthy at start

    while True:
        is_healthy, message = check_health(api_url)

        if is_healthy:
            if not last_status and alert_sent:
                # Recovery — send all-clear
                recovery_msg = (
                    f"✅ *QuantOS API Recovered*\n"
                    f"URL: {api_url}\n"
                    f"Time: {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n"
                    f"Status: Back online"
                )
                await send_whatsapp_alert(recovery_msg, phone, api_key)
                logger.info("API recovered — all-clear sent")
                alert_sent = False

            failures    = 0
            last_status = True
            logger.debug("Health check OK")

        else:
            failures   += 1
            last_status = False
            logger.warning(
                "Health check FAILED (%d/%d): %s", failures, MAX_FAILURES, message
            )

            if failures >= MAX_FAILURES and not alert_sent:
                alert_msg = (
                    f"🚨 *QuantOS API DOWN*\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"URL: {api_url}\n"
                    f"Error: {message}\n"
                    f"Failures: {failures} consecutive\n"
                    f"Time: {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"⚠️ Signals are NOT being processed.\n"
                    f"Check Railway dashboard immediately."
                )
                await send_whatsapp_alert(alert_msg, phone, api_key)
                logger.error("ALERT SENT — API has been down for %d checks", failures)
                alert_sent = True

        await asyncio.sleep(CHECK_INTERVAL)


def main():
    parser = argparse.ArgumentParser(description="QuantOS API uptime monitor")
    parser.add_argument(
        "--url",
        default=os.getenv("QUANTOS_API_URL", "https://your-app.railway.app"),
        help="QuantOS Cloud API URL",
    )
    parser.add_argument(
        "--phone",
        default=os.getenv("CALLMEBOT_PHONE", ""),
        help="WhatsApp phone number",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("CALLMEBOT_API_KEY", ""),
        help="CallMeBot API key",
    )
    args = parser.parse_args()

    if not args.phone or not args.api_key:
        logger.error(
            "WhatsApp not configured. Set CALLMEBOT_PHONE and CALLMEBOT_API_KEY "
            "or pass --phone and --api-key"
        )

    asyncio.run(run_monitor(args.url, args.phone, args.api_key))


if __name__ == "__main__":
    main()
