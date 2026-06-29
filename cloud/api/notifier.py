"""
QuantOS — WhatsApp Notifier
────────────────────────────
Sends WhatsApp messages via CallMeBot API.
ADR-05: Every signal requires WhatsApp confirmation before execution.

Setup:
  1. Send "I allow callmebot to send me messages" to +34 644 59 71 74 on WhatsApp
  2. You'll receive your API key by reply
  3. Set CALLMEBOT_PHONE and CALLMEBOT_API_KEY in .env
"""

import logging
import os
import urllib.parse

import httpx

logger = logging.getLogger(__name__)

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"
PHONE     = os.getenv("CALLMEBOT_PHONE", "")
API_KEY   = os.getenv("CALLMEBOT_API_KEY", "")


async def send_whatsapp(message: str) -> bool:
    """
    Send a WhatsApp message via CallMeBot.
    Returns True on success, False on failure (never raises — signal pipeline continues).
    """
    if not PHONE or not API_KEY:
        logger.warning(
            "WhatsApp not configured — set CALLMEBOT_PHONE and CALLMEBOT_API_KEY in .env\n"
            "Message would have been:\n%s", message
        )
        return False

    params = {
        "phone":   PHONE,
        "text":    urllib.parse.quote(message),
        "apikey":  API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(CALLMEBOT_URL, params=params)
            if response.status_code == 200:
                logger.info("WhatsApp message sent to %s", PHONE)
                return True
            else:
                logger.error(
                    "WhatsApp send failed: HTTP %d — %s",
                    response.status_code, response.text[:200]
                )
                return False
    except Exception as e:
        logger.error("WhatsApp send error: %s", e)
        return False


async def send_trade_confirmation(
    signal_id: str,
    symbol: str,
    action: str,
    quantity: int,
    execution_price: float,
    pnl: float | None = None,
) -> bool:
    """Send execution confirmation after order is filled."""
    pnl_str = f"\nP&L: ₹{pnl:+,.2f}" if pnl is not None else ""
    message = (
        f"✅ *Trade Executed*\n"
        f"ID: `{signal_id}`\n"
        f"━━━━━━━━━━━━━━\n"
        f"{'🟢 BOUGHT' if action == 'BUY' else '🔴 SOLD'} *{symbol}*\n"
        f"Qty: {quantity} shares\n"
        f"Price: ₹{execution_price:,.2f}{pnl_str}\n"
        f"━━━━━━━━━━━━━━\n"
        f"QuantOS · {signal_id}"
    )
    return await send_whatsapp(message)


async def send_error_alert(context: str, error: str) -> bool:
    """Send system error alert."""
    message = (
        f"⚠️ *QuantOS Alert*\n"
        f"Context: {context}\n"
        f"Error: {error[:200]}"
    )
    return await send_whatsapp(message)
