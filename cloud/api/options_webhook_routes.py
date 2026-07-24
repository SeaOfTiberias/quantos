"""
QuantOS — TradingView-Driven Options Webhook
─────────────────────────────────────────────────────────────
Human-triggered options entry/exit, added 2026-07-25 to replace the killed
regime-gated auto-suggestion (see core/options/recommender.py's module
docstring). The direction/timing/template choice is YOURS — made on
TradingView, where trailing-stop logic (strategy.exit's trail_points/
trail_offset) is far easier to express than against Fyers directly, which
is the whole reason this exists instead of an agent-side trailing stop.
QuantOS's job is just the mechanical part: real chain analysis for entries,
real order placement for exits.

No custom Pine script is required. TradingView's native "Create Alert"
dialog lets you set a literal JSON Message body on any condition you
build (a price cross, your own trailing-stop logic, or just "once") —
paste this endpoint's URL as the Webhook URL and a JSON body matching
OptionsWebhookAlert below as the Message. See
docs/OPTIONS_WEBHOOK_SETUP.md for the exact steps.

Two actions, both requiring only {underlying, template, action, secret}:
  - "open":  queues an entry request. The agent polls, fetches the real
             option chain, computes real legs/Greeks via POST
             /strategy/recommend, and sends a Telegram confirm prompt
             (cloud/api/options_routes.py's POST /options/signal) — same
             human-tap gate as every other order this codebase places.
  - "close": queues an exit request. The agent polls, finds the matching
             OptionsPosition by underlying, and flattens every leg
             IMMEDIATELY, no confirm — same precedent as the equity
             auto_exit stop order (a risk-management action shouldn't wait
             on a Telegram tap). "template" must match the open position's
             strategy or the close is refused (logged, not silently
             dropped) — a mismatched template most likely means a stale/
             wrong alert firing, not the position you meant to close.

The pending queue is in-memory (mirrors discovery_routes.py's
_watchlist_store) — resets on every Railway redeploy. That's fine: a lost
"open" request just means no suggestion fires this time (nothing was ever
committed), and a lost "close" request is no worse than the trailing stop
never having existed — it does NOT silently leave a stale queued close
that fires late against a since-changed position, which would be worse.
"""

import hmac
import logging
import os
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from cloud.api.auth import require_cloud_secret
from cloud.api.notifier import send_telegram

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook/options", tags=["options-webhook"])

MAX_ALERT_AGE_SECONDS = float(os.getenv("MAX_ALERT_AGE_SECONDS", "120"))
MAX_QUEUE_SIZE = 50   # bounds unbounded growth if the agent is ever down for a while

# In-memory FIFO — the agent claims (pops) one at a time. Resets on redeploy,
# same as discovery_routes.py's _watchlist_store; see module docstring.
_pending: deque = deque()


class OptionsWebhookAlert(BaseModel):
    underlying: str
    template:   str            # StrategyTemplate value, e.g. "bull_call_spread"
    action:     str            # "open" | "close"
    secret:     str
    timestamp:  Optional[float] = None   # epoch seconds — replay guard, same as /webhook/tradingview


class PendingOptionsRequest(BaseModel):
    request_id: str
    underlying: str
    template:   str
    action:     str
    queued_at:  str


@router.post("", response_model=PendingOptionsRequest)
async def receive_options_webhook(alert: OptionsWebhookAlert, request: Request):
    """Receives a TradingView (or any) webhook alert and queues it for the
    agent to act on. Real chain fetch/order placement happens agent-side
    only — ADR-01, only the agent holds a connected broker."""

    expected_secret = os.getenv("WEBHOOK_SECRET", "")
    if not expected_secret:
        logger.error("Rejected options webhook — WEBHOOK_SECRET not configured")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                             "Webhook disabled: WEBHOOK_SECRET not configured")
    if not hmac.compare_digest(alert.secret, expected_secret):
        logger.warning("Rejected options webhook — bad secret from %s", request.client.host)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook secret")

    if alert.timestamp is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing timestamp")
    age_seconds = abs(datetime.now(timezone.utc).timestamp() - alert.timestamp)
    if age_seconds > MAX_ALERT_AGE_SECONDS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                             f"Stale alert: {age_seconds:.0f}s outside {MAX_ALERT_AGE_SECONDS}s window")

    if alert.action not in ("open", "close"):
        raise HTTPException(422, f"action must be 'open' or 'close', got {alert.action!r}")

    if len(_pending) >= MAX_QUEUE_SIZE:
        logger.error("Options webhook queue full (%d) — dropping oldest unclaimed request",
                      MAX_QUEUE_SIZE)
        _pending.popleft()

    item = PendingOptionsRequest(
        request_id=f"OWH-{uuid.uuid4().hex[:8].upper()}",
        underlying=alert.underlying.upper(),
        template=alert.template,
        action=alert.action,
        queued_at=datetime.now(timezone.utc).isoformat(),
    )
    _pending.append(item)
    logger.info("[%s] Queued options webhook: %s %s %s",
                item.request_id, alert.action, alert.underlying, alert.template)
    return item


@router.post("/claim")
async def claim_pending_request(_auth=Depends(require_cloud_secret)):
    """Agent polls this every tick. Pops (not just peeks) the oldest
    pending request so a slow-processing agent can't claim the same item
    twice — if the agent crashes mid-processing, that one request is lost
    (see module docstring: acceptable, no worse than never having fired)."""
    if not _pending:
        return {"request": None}
    return {"request": _pending.popleft().model_dump()}


class ClosedLegInput(BaseModel):
    action:      str
    option_type: str
    strike:      float


class OptionsClosedReport(BaseModel):
    underlying: str
    legs:       list[ClosedLegInput]
    reason:     str = "trailing_stop_webhook"


@router.post("/closed")
async def report_closed(payload: OptionsClosedReport, _auth=Depends(require_cloud_secret)):
    """Called by the agent after flatten_position() closes every leg of a
    position — informational only (no confirm was needed to get here), so
    this just notifies Telegram of what happened rather than persisting a
    new signal row."""
    leg_lines = "\n".join(
        f"  {leg.action} {leg.option_type} {leg.strike:g}" for leg in payload.legs
    )
    message = (
        f"🔻 QuantOS Options Position Closed ({payload.reason})\n"
        f"--------------------\n"
        f"{payload.underlying}\n{leg_lines}\n"
        f"--------------------\n"
        f"Closed automatically — no confirmation was required for this exit."
    )
    try:
        await send_telegram(message)
    except Exception as e:
        logger.error("Failed to send options-closed notification: %s", e)
    logger.info("Options position closed for %s (%s)", payload.underlying, payload.reason)
    return {"closed": True}
