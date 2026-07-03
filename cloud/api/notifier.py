"""
QuantOS — Telegram Notifier
─────────────────────────────
Sends messages via Telegram Bot API.
ADR-05: Every signal requires confirmation before execution.

Setup:
  1. Create bot via @BotFather on Telegram
  2. Send any message to your bot
  3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env / Railway Variables
"""

import logging
import os
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

TELEGRAM_URL  = "https://api.telegram.org"
BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID       = os.getenv("TELEGRAM_CHAT_ID", "")


async def send_whatsapp(message: str) -> bool:
    """
    Send a Telegram message. Function name kept as send_whatsapp
    for API compatibility — all call sites remain unchanged.
    Returns True on success, False on failure (never raises).
    """
    return await send_telegram(message)


async def send_telegram(message: str) -> bool:
    """Send a message via Telegram Bot API."""
    token = BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = CHAT_ID or os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning(
            "Telegram not configured — set TELEGRAM_BOT_TOKEN and "
            "TELEGRAM_CHAT_ID in .env\nMessage would have been:\n%s", message
        )
        return False

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{TELEGRAM_URL}/bot{token}/sendMessage",
                json={
                    "chat_id":    chat_id,
                    "text":       message,
                    "parse_mode": "HTML",
                },
            )
            if resp.status_code == 200:
                logger.info("Telegram message sent to chat %s", chat_id)
                return True
            else:
                logger.error("Telegram send failed: %d — %s",
                             resp.status_code, resp.text[:200])
                return False
    except Exception as e:
        logger.error("Telegram send error: %s", e)
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
    return await send_telegram(message)


async def send_error_alert(context: str, error: str) -> bool:
    """Send system error alert."""
    message = (
        f"⚠️ *QuantOS Alert*\n"
        f"Context: {context}\n"
        f"Error: {error[:200]}"
    )
    return await send_telegram(message)
