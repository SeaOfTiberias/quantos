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

import asyncio
import logging
import os
import re

logger = logging.getLogger(__name__)

TELEGRAM_URL  = "https://api.telegram.org"
BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID       = os.getenv("TELEGRAM_CHAT_ID", "")

SEND_RETRIES          = 3
RETRY_BACKOFF_SECONDS = 1.0

# Bot API URLs embed the token as /bot<token>/ — httpx transport errors
# include the request URL in their message, so any raw exception reaching
# the logs is a token leak (P1-5).
_BOT_URL_RE = re.compile(r"/bot[^/\s'\"]*")


def _sanitized(err: BaseException | str, token: str = "") -> str:
    """Render an error for logging with the bot token scrubbed out."""
    text = f"{type(err).__name__}: {err}" if isinstance(err, BaseException) else str(err)
    if token:
        text = text.replace(token, "<redacted>")
    return _BOT_URL_RE.sub("/<redacted>", text)


async def send_telegram(message: str) -> bool:
    """Send a message via Telegram Bot API.

    Retries transient failures (network errors, non-200s) with linear
    backoff. Returns False only after all attempts fail — callers on the
    confirmation path leave the signal un-notified so the periodic sweep
    in cloud/api/main.py re-attempts delivery (P1-4).
    """
    token = BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = CHAT_ID or os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning(
            "Telegram not configured — set TELEGRAM_BOT_TOKEN and "
            "TELEGRAM_CHAT_ID in .env\nMessage would have been:\n%s", message
        )
        return False

    import httpx
    for attempt in range(1, SEND_RETRIES + 1):
        try:
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
            logger.warning("Telegram send failed (attempt %d/%d): %d — %s",
                           attempt, SEND_RETRIES, resp.status_code,
                           _sanitized(resp.text[:200], token))
        except Exception as e:
            logger.warning("Telegram send error (attempt %d/%d): %s",
                           attempt, SEND_RETRIES, _sanitized(e, token))
        if attempt < SEND_RETRIES:
            await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)

    logger.error("Telegram send failed after %d attempts — message not delivered",
                 SEND_RETRIES)
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


async def send_halt_alert(reason: str) -> bool:
    """Send a portfolio kill-switch alert (S4-2 / P0-2).

    The local agent has no Telegram token (ADR-01) — it POSTs the halt to
    /agent/halt and the cloud relays it here, the same agent→cloud→Telegram
    path used for exit notifications. Plain text, no parse_mode."""
    message = (
        f"🛑 TRADING HALTED\n"
        f"--------------------\n"
        f"{reason}\n"
        f"--------------------\n"
        f"New entries are refused (existing stops still managed).\n"
        f"Clear manually: delete ~/.quantos/halt on the agent machine."
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
            logger.error("Telegram setWebhook failed: %s", _sanitized(str(data), token))
            return False
    except Exception as e:
        logger.error("Telegram setWebhook error: %s", _sanitized(e, token))
        return False
