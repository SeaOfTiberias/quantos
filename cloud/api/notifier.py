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


async def deliver_confirmation(signal_id: str, message: str) -> bool:
    """Send a pending-confirmation message; stamp notified_at only on
    success so the re-notify sweep (cloud/api/main.py) knows which
    PENDING_CONFIRMATION signals never reached the human (P1-4: an
    unnotified signal used to strand silently). Shared by the Darvas flow
    (main.py) and the options execution flow (options_routes.py) — lives
    here rather than in main.py to avoid a circular import between them."""
    from cloud.api.db import get_db

    try:
        sent = await send_telegram(message)
    except Exception as e:
        sent = False
        logger.error("[%s] Telegram notification raised: %s", signal_id, type(e).__name__)
    if sent:
        db = await get_db()
        await db.mark_notified(signal_id)
        logger.info("[%s] Telegram confirmation sent", signal_id)
    else:
        logger.error("[%s] Telegram confirmation NOT delivered — signal stays "
                     "PENDING_CONFIRMATION, re-notify sweep will retry", signal_id)
    return sent


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


async def send_rotation_summary(
    buys: list[dict],
    sells: list[dict],
    skipped_buys: list[dict],
    dry_run: bool,
) -> bool:
    """Send ONE consolidated summary for a whole S8-3 weekly rotation
    rebalance — not a per-trade confirm prompt (unlike send_trade_confirmation,
    used by the discretionary Darvas flow). This strategy runs fully
    automatically with no per-trade human veto, so this message is
    after-the-fact visibility, not an approval request."""
    header = "🔄 Weekly Rotation Rebalance (DRY RUN)" if dry_run else "🔄 Weekly Rotation Rebalance"
    lines = [header, "--------------------"]

    if buys:
        lines.append(f"Bought {len(buys)}:")
        lines += [f"  {b['symbol']} x{b['quantity']} @ INR {b['price']:,.2f}" for b in buys]
    if sells:
        lines.append(f"Sold {len(sells)}:")
        lines += [f"  {s['symbol']} x{s['quantity']} (entry INR {s['entry_price']:,.2f})" for s in sells]
    if skipped_buys:
        lines.append(f"Skipped {len(skipped_buys)}:")
        lines += [f"  {s['symbol']}: {s['reason']}" for s in skipped_buys]
    if not (buys or sells or skipped_buys):
        lines.append("No changes this week — current basket already matches target.")

    lines += ["--------------------", "QuantOS · S8-3 rotation"]
    return await send_telegram("\n".join(lines))


def format_options_confirmation_message(
    signal_id: str,
    underlying: str,
    strategy: str,
    expiry: str,
    legs: list[dict],
    max_profit: float,
    max_loss: float,
    net_premium: float,
    probability_of_profit: float,
    rationale: str,
    regime_context: str,
) -> str:
    """
    Pending-confirmation message for a multi-leg options signal (regime/
    strategy advisor -> real execution). Ends with the exact same "Reply
    execute/skip" convention as _confirmation_message() in cloud/api/main.py
    so the existing Telegram webhook's reply-parsing needs no changes at
    all -- it already extracts the signal ID out of ANY replied-to message
    by regex, regardless of the body above it.
    """
    leg_lines = [
        f"  {leg['action']} {leg['option_type']} {leg['strike']:g} @ INR {leg['premium']:,.2f} "
        f"x{leg['quantity']} lot(s)"
        for leg in legs
    ]
    max_loss_str = "Unlimited" if max_loss == float("-inf") else f"INR {max_loss:,.2f}"
    return (
        f"🧠 QuantOS Options Suggestion\n"
        f"ID: {signal_id}\n"
        f"--------------------\n"
        f"{underlying} · {strategy.replace('_', ' ').title()} · expiry {expiry}\n"
        + "\n".join(leg_lines) + "\n"
        f"--------------------\n"
        f"Net premium: INR {net_premium:+,.2f}\n"
        f"Max profit: INR {max_profit:,.2f}\n"
        f"Max loss: {max_loss_str}\n"
        f"Est. probability of profit: {probability_of_profit:.0f}%\n"
        f"Regime: {regime_context}\n"
        f"Rationale: {rationale}\n"
        f"--------------------\n"
        f"Exit rule: hold to expiry (no active management)\n"
        f"Reply (to this message) execute to trade\n"
        f"Reply (to this message) skip to ignore"
    )


async def send_options_execution_report(
    signal_id: str, underlying: str, legs: list[dict],
) -> bool:
    """All legs filled successfully — after-the-fact confirmation, mirrors
    send_trade_confirmation() but for a multi-leg fill."""
    leg_lines = [
        f"  {'🟢' if leg['action'] == 'BUY' else '🔴'} {leg['action']} {leg['option_type']} "
        f"{leg['strike']:g} @ INR {(leg.get('fill_price') or 0.0):,.2f} "
        f"x{leg['quantity']} lot(s) (order {leg.get('order_id', '?')})"
        for leg in legs
    ]
    message = (
        f"✅ Options Spread Executed\n"
        f"ID: {signal_id}\n"
        f"--------------------\n"
        f"{underlying}\n"
        + "\n".join(leg_lines) + "\n"
        f"--------------------\n"
        f"QuantOS · {signal_id}"
    )
    return await send_telegram(message)


async def send_options_partial_failure_alert(
    signal_id: str,
    underlying: str,
    failed_leg: dict,
    error: str,
    flatten_results: list[dict],
) -> bool:
    """
    URGENT: a multi-leg spread partially filled before a later leg was
    rejected, leaving one or more legs with undefined/naked risk until
    the auto-flatten below either closes them or itself fails. This is
    the loudest alert this project sends — a naked option position is
    exactly the unbounded-risk scenario the spread structure exists to
    prevent, and if the flatten attempt ALSO failed there is no further
    automatic recourse: the user must act in the Fyers app immediately.
    """
    all_flattened = all(f.get("flattened") for f in flatten_results)
    header = (
        "🆘 OPTIONS LEG FAILURE — auto-flattened, please verify"
        if (flatten_results and all_flattened)
        else "🆘🆘 OPTIONS LEG FAILURE — FLATTEN ALSO FAILED, ACT NOW"
    )
    lines = [
        header, "--------------------",
        f"ID: {signal_id}  |  {underlying}",
        f"Failed leg: {failed_leg['action']} {failed_leg['option_type']} "
        f"{failed_leg['strike']:g}",
        f"Reason: {error[:200]}",
        "--------------------",
    ]
    if flatten_results:
        lines.append("Flatten attempts on already-filled legs:")
        for f in flatten_results:
            leg = f["leg"]
            if f.get("flattened"):
                lines.append(
                    f"  OK: closed {leg['action']} {leg['option_type']} "
                    f"{leg['strike']:g} (order {f.get('order_id', '?')})"
                )
            else:
                lines.append(
                    f"  FAILED: {leg['action']} {leg['option_type']} "
                    f"{leg['strike']:g} is STILL OPEN, naked — "
                    f"close it manually in the Fyers app NOW "
                    f"({f.get('error', 'unknown error')[:150]})"
                )
    else:
        lines.append("No prior legs had filled — nothing to flatten.")
    lines += ["--------------------", f"QuantOS · {signal_id}"]
    return await send_telegram("\n".join(lines))


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
