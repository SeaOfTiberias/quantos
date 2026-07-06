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

from __future__ import annotations

import logging
import os
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

TELEGRAM_URL  = "https://api.telegram.org"
BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID       = os.getenv("TELEGRAM_CHAT_ID", "")


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
    pnl_str = f"\nP&L: INR {pnl:+,.2f}" if pnl is not None else ""
    message = (
        f"✅ Trade Executed\n"
        f"ID: {signal_id}\n"
        f"--------------------\n"
        f"{'🟢 BOUGHT' if action == 'BUY' else '🔴 SOLD'} {symbol}\n"
        f"Qty: {quantity} shares\n"
        f"Price: INR {execution_price:,.2f}{pnl_str}\n"
        f"--------------------\n"
        f"QuantOS · {signal_id}"
    )
    return await send_telegram(message)


async def send_exit_notification(
    signal_id: str,
    symbol: str,
    exit_price: float,
    pnl: float,
    reason: str = "stop_hit",
) -> bool:
    """Send position-closed notification (Task 4: auto stop-loss/trail exit)."""
    reason_label = {"stop_hit": "Stop-loss hit", "manual": "Manually closed"}.get(reason, reason)
    message = (
        f"📤 Position Closed\n"
        f"ID: {signal_id}\n"
        f"--------------------\n"
        f"{symbol}\n"
        f"Exit price: INR {exit_price:,.2f}\n"
        f"P&L: INR {pnl:+,.2f}\n"
        f"Reason: {reason_label}\n"
        f"--------------------\n"
        f"QuantOS · {signal_id}"
    )
    return await send_telegram(message)


async def send_error_alert(context: str, error: str) -> bool:
    """Send system error alert."""
    message = (
        f"⚠️ QuantOS Alert\n"
        f"Context: {context}\n"
        f"Error: {error[:200]}"
    )
    return await send_telegram(message)


async def register_telegram_webhook() -> bool:
    """
    Registers this deployment's /webhook/telegram endpoint with Telegram's
    Bot API (setWebhook). Idempotent — safe to call on every startup.
    Requires TELEGRAM_BOT_TOKEN and PUBLIC_API_URL (or falls back to the
    known Railway URL). TELEGRAM_WEBHOOK_SECRET, if set, is echoed back by
    Telegram on every update as X-Telegram-Bot-Api-Secret-Token.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — skipping webhook registration")
        return False

    public_url = os.getenv("PUBLIC_API_URL", "https://web-production-b5527.up.railway.app")
    webhook_url = f"{public_url.rstrip('/')}/webhook/telegram"
    secret_token = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")

    payload = {"url": webhook_url, "allowed_updates": ["message"]}
    if secret_token:
        payload["secret_token"] = secret_token

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{TELEGRAM_URL}/bot{token}/setWebhook", json=payload)
            data = resp.json()
            if data.get("ok"):
                logger.info("Telegram webhook registered: %s", webhook_url)
                return True
            logger.error("Telegram setWebhook failed: %s", data)
            return False
    except Exception as e:
        logger.error("Telegram setWebhook error: %s", e)
        return False
