"""
QuantOS Cloud API — FastAPI Webhook Receiver
─────────────────────────────────────────────
US-01: TradingView Premium → QuantOS → Agent → Broker

Pipeline:
  TradingView alert (or agent/main.py Stage B internal scanner)
    → POST /webhook/tradingview
    → validate secret
    → confluence gate (ADR-04: min score 70)
    → same-day dedup guard (one open signal per symbol per day)
    → event risk filter (US-06)
    → Claude pre-trade analyst (US-04)
    → persist signal to DB
    → notify local agent
    → Telegram confirmation (ADR-05)
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from cloud.api.auth import require_cloud_secret
from cloud.api.db import get_db, Signal
from cloud.api.health import router as health_router
from cloud.api.screener_routes import router as screener_router
from cloud.api.events_routes import router as events_router
from cloud.api.risk_routes import router as risk_router
from cloud.api.correlation_routes import router as correlation_router
from cloud.api.strategy_routes import router as strategy_router
from cloud.api.versioning_routes import router as versioning_router
from cloud.api.backtest_routes import router as backtest_router
from cloud.api.morning_routes import router as morning_router
from cloud.api.options_routes import router as options_router
from cloud.api.discovery_routes import router as discovery_router
from cloud.api.regime_routes import router as regime_router
from cloud.api.positions_routes import router as positions_router
from cloud.api.analyst_routes import router as analyst_router
from cloud.api.observability_routes import router as observability_router
from cloud.api.reconciliation_routes import router as reconciliation_router
from cloud.api.rotation_routes import router as rotation_router
from cloud.api import metrics
from core import prompts
from cloud.api.notifier import send_telegram, register_telegram_webhook, send_exit_notification
from cloud.analyst.pre_trade import analyse_signal
from core.events.service import EventFilterService, format_event_block_whatsapp

logger = logging.getLogger(__name__)

app = FastAPI(
    title="QuantOS Cloud API",
    description="Signal ingestion, AI analysis, and agent coordination",
    version="1.0.0",
)

app.include_router(health_router)
app.include_router(screener_router)
app.include_router(events_router)
app.include_router(risk_router)
app.include_router(correlation_router)
app.include_router(strategy_router)
app.include_router(versioning_router)
app.include_router(backtest_router)
app.include_router(morning_router)
app.include_router(options_router)
app.include_router(discovery_router)
app.include_router(regime_router)
app.include_router(positions_router)
app.include_router(analyst_router)
app.include_router(observability_router)
app.include_router(reconciliation_router)
app.include_router(rotation_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _webhook_latency_middleware(request: Request, call_next):
    """Time the /webhook/tradingview round trip for the observability cockpit
    (S5-6). Covers every return path — confluence reject, dedup, event block,
    happy path, and errors — since it wraps the whole request."""
    if request.url.path != "/webhook/tradingview":
        return await call_next(request)
    started = time.perf_counter()
    try:
        return await call_next(request)
    finally:
        metrics.record_webhook_ms((time.perf_counter() - started) * 1000.0)

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
MIN_CONFLUENCE = float(os.getenv("MIN_CONFLUENCE_SCORE", "70"))
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
# Replay guard window: alerts older (or further in the future) than this
# are rejected. 2 minutes tolerates TradingView delivery lag + minor clock
# skew while making captured-payload replays useless.
MAX_ALERT_AGE_SECONDS = float(os.getenv("MAX_ALERT_AGE_SECONDS", "120"))

_SIGNAL_ID_RE = re.compile(r"(SIG-[A-Z0-9]+-[A-F0-9]+)")


@app.on_event("startup")
async def _preload_prompts():
    # Fail fast at deploy if a prompt file is missing, rather than on the
    # first live signal (S5-8). Only the hot-path pre_trade prompts are
    # webhook-critical; the rest load lazily on first use in their own paths.
    prompts.preload("pre_trade_system", "pre_trade_user")


@app.on_event("startup")
async def _init_signal_db():
    # Gate persistence on a real connectivity check (P0-3): if Postgres is
    # reachable, signals survive redeploys; if not, connect() logs a loud
    # warning and leaves SignalDB on its in-memory fallback so the app boots.
    db = await get_db()
    await db.connect()


@app.on_event("startup")
async def _register_telegram_webhook():
    try:
        await register_telegram_webhook()
    except Exception as e:
        logger.error("Telegram webhook self-registration failed: %s", e)


@app.on_event("startup")
async def _start_notify_sweep():
    # First iteration runs immediately — that's the startup sweep catching
    # signals stranded by a Telegram outage or a mid-flight redeploy.
    asyncio.create_task(_notify_sweep_loop())

# Event risk filter (US-06) — singleton, loaded with macro calendar at startup
_event_filter = EventFilterService()

# NOTE: the correlation gate (S5-5) runs on the local agent, not here — only
# the agent holds a broker to fetch price history (ADR-01). It pushes decisions
# to cloud/api/correlation_routes.py for display. (The old cloud-side
# _correlation_service = None dead-wiring was removed with that change.)


# ─── Models ──────────────────────────────────────────────────────────────────

class TradingViewAlert(BaseModel):
    """
    JSON payload from TradingView Premium webhook alert.

    See pine/darvas_breakout_alert.pine — it builds this exact JSON body
    itself via Pine's alert() function (dynamic multi-timeframe confluence
    score + stop_loss can't be expressed with the static {{plot_N}} message
    template, since those only substitute a single script's own plot()
    values, not values computed across multiple request.security() calls):
    {
      "symbol":            "RELIANCE",
      "action":             "BUY",
      "price":              2950.25,
      "timeframe":         "15m",
      "strategy":          "darvas_breakout",
      "confluence_score":   85.0,
      "stop_loss":          2890.0,
      "secret":            "YOUR_WEBHOOK_SECRET",
      "timestamp":          1751884200
    }
    """
    symbol:            str   = Field(..., description="NSE symbol e.g. RELIANCE")
    action:            str   = Field(..., description="BUY or SELL")
    price:             float = Field(..., description="Signal trigger price")
    timeframe:         str   = Field(..., description="Chart timeframe e.g. 15, 60, D")
    strategy:          str   = Field(..., description="Strategy ID e.g. darvas_breakout")
    confluence_score:  float = Field(default=0, ge=0, le=100)
    stop_loss:         float | None = Field(default=None, description="Darvas box low / stop price")
    secret:            str   = Field(..., description="Webhook validation secret")
    timestamp:         float | None = Field(
        default=None,
        description="Epoch seconds when the alert fired — replay guard, "
                    "payloads outside MAX_ALERT_AGE_SECONDS are rejected",
    )
    notes:             str   = Field(default="")


class SignalResponse(BaseModel):
    signal_id:        str
    symbol:           str
    action:           str
    status:           str
    confidence_score: float | None = None
    message:          str


class ExecutionReport(BaseModel):
    """Reported by the local agent after placing an order via the broker."""
    order_id:         str
    quantity:         int
    execution_price:  float


class FailureReport(BaseModel):
    """Reported by the local agent when it can't size/place a confirmed signal."""
    reason: str


class ClosedReport(BaseModel):
    """Reported by the local agent once an auto-exit (stop-loss/trail) has
    closed a position — see Task 4 / agent/main.py _manage_open_positions."""
    exit_price: float
    pnl:        float
    reason:     str = "stop_hit"


class HaltReport(BaseModel):
    """Reported by the local agent when its portfolio kill switch (S4-2)
    trips. The agent has no Telegram token (ADR-01), so it relays the halt
    here and the cloud sends the Telegram alert."""
    reason: str


# ─── Health ──────────────────────────────────────────────────────────────────

# ─── Webhook ─────────────────────────────────────────────────────────────────

@app.post("/webhook/tradingview", response_model=SignalResponse)
async def tradingview_webhook(alert: TradingViewAlert, request: Request):
    """
    Receives TradingView Premium webhook alerts and routes them
    through the QuantOS signal pipeline.
    """

    # ── 1. Validate secret (fail closed) ─────────────────────────────────────
    # A missing WEBHOOK_SECRET must disable the endpoint, not disable the
    # check — this route accepts trade signals for a system that places
    # real orders behind one human tap.
    expected_secret = os.getenv("WEBHOOK_SECRET", "")
    if not expected_secret:
        logger.error("Rejected webhook — WEBHOOK_SECRET is not configured; "
                     "endpoint is disabled until it is set")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook disabled: WEBHOOK_SECRET not configured",
        )
    if not hmac.compare_digest(alert.secret, expected_secret):
        logger.warning("Rejected webhook — bad secret from %s", request.client.host)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )

    # ── 2. Replay guard ──────────────────────────────────────────────────────
    # Both senders (Pine alert() and the agent's Stage B) stamp the payload
    # when it fires; a captured payload replayed later is rejected. abs()
    # also rejects far-future stamps (clock skew beyond tolerance).
    if alert.timestamp is None:
        logger.warning("Rejected webhook — missing timestamp (replay guard) from %s",
                       request.client.host)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing timestamp",
        )
    age_seconds = abs(datetime.now(timezone.utc).timestamp() - alert.timestamp)
    if age_seconds > MAX_ALERT_AGE_SECONDS:
        logger.warning("Rejected webhook — stale timestamp (%.0fs old) from %s",
                       age_seconds, request.client.host)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Stale alert: {age_seconds:.0f}s outside {MAX_ALERT_AGE_SECONDS}s window",
        )

    signal_id = f"SIG-{alert.strategy[:4].upper()}-{uuid.uuid4().hex[:8].upper()}"
    logger.info(
        "[%s] %s %s @ %.2f | tf=%s | confluence=%.0f",
        signal_id, alert.action, alert.symbol,
        alert.price, alert.timeframe, alert.confluence_score,
    )

    # ── 3. Confluence gate (ADR-04) ──────────────────────────────────────────
    if alert.confluence_score < MIN_CONFLUENCE:
        logger.info("[%s] Rejected — confluence %.0f < %.0f",
                    signal_id, alert.confluence_score, MIN_CONFLUENCE)
        await _persist_signal(signal_id, alert, "REJECTED_LOW_CONFLUENCE", None)
        return SignalResponse(
            signal_id=signal_id,
            symbol=alert.symbol,
            action=alert.action,
            status="REJECTED_LOW_CONFLUENCE",
            message=(
                f"Confluence {alert.confluence_score:.0f} "
                f"below threshold {MIN_CONFLUENCE:.0f}"
            ),
        )

    # ── 4. Same-day dedup guard ───────────────────────────────────────────────
    # TradingView Pine Script alerts and the internal scanner (agent/main.py
    # Stage B, strategy="darvas_scanner_internal") can both name the same
    # symbol on the same day — don't let a second source re-fire a signal
    # while an earlier one for it is still pending or confirmed.
    duplicate = await _find_open_signal_today(alert.symbol)
    if duplicate:
        logger.info("[%s] Rejected — duplicate of %s (%s) for %s today",
                    signal_id, duplicate["signal_id"], duplicate["status"], alert.symbol)
        await _persist_signal(signal_id, alert, "REJECTED_DUPLICATE", None)
        return SignalResponse(
            signal_id=signal_id,
            symbol=alert.symbol,
            action=alert.action,
            status="REJECTED_DUPLICATE",
            message=(
                f"Signal {duplicate['signal_id']} already {duplicate['status']} "
                f"for {alert.symbol} today"
            ),
        )

    # ── 5. Event risk filter (US-06) — cheap check before Claude call ───────
    event_check = _event_filter.check(alert.symbol)
    if event_check.is_blocked and not event_check.override_allowed:
        logger.info("[%s] BLOCKED — high-impact event: %s",
                    signal_id, event_check.reason)
        await _persist_signal(signal_id, alert, "BLOCKED_EVENT_RISK", None)
        try:
            await send_telegram(format_event_block_whatsapp(event_check))
        except Exception as e:
            logger.error("Failed to send event block alert: %s", e)
        return SignalResponse(
            signal_id=signal_id,
            symbol=alert.symbol,
            action=alert.action,
            status="BLOCKED_EVENT_RISK",
            message=event_check.reason,
        )
    elif event_check.is_blocked:
        logger.info("[%s] Advisory event risk (override allowed): %s",
                    signal_id, event_check.reason)

    # ── 6. Claude pre-trade analysis (US-04) ─────────────────────────────────
    confidence_score = None
    try:
        confidence_score = await analyse_signal({
            "signal_id":        signal_id,
            "symbol":           alert.symbol,
            "action":           alert.action,
            "price":            alert.price,
            "timeframe":        alert.timeframe,
            "strategy":         alert.strategy,
            "confluence_score": alert.confluence_score,
            "notes":            alert.notes,
        })
        logger.info("[%s] Claude confidence: %.1f", signal_id, confidence_score)
    except Exception as e:
        logger.warning("[%s] Claude analysis failed: %s — proceeding", signal_id, e)

    # ── 7. Persist signal ────────────────────────────────────────────────────
    signal_status = "PENDING_CONFIRMATION"
    await _persist_signal(signal_id, alert, signal_status, confidence_score)

    # ── 8. Telegram confirmation (ADR-05: human-in-loop) ─────────────────────
    await _send_confirmation_request(signal_id, alert, confidence_score)

    return SignalResponse(
        signal_id=signal_id,
        symbol=alert.symbol,
        action=alert.action,
        status=signal_status,
        confidence_score=confidence_score,
        message="Signal pending Telegram confirmation",
    )


@app.get("/signals")
async def list_signals(limit: int = 20, status: str | None = None):
    """Return recent signals for the cockpit dashboard.

    Public/unauthenticated, matching the read-only pattern used by
    /regime/status, /observability, and /discovery/watchlist — no
    credentials in the payload. Write actions (confirm/skip/executed/
    failed/halt) remain behind require_cloud_secret.
    """
    db = await get_db()
    signals = await db.fetch_recent_signals(limit=limit, status=status)
    return {"signals": signals}


@app.post("/signals/{signal_id}/confirm")
async def confirm_signal(signal_id: str, _auth=Depends(require_cloud_secret)):
    """Mark a signal CONFIRMED — normally triggered by the Telegram webhook
    below when the user replies 'execute', kept as a direct route for
    admin/dashboard use."""
    await _set_signal_status(signal_id, "CONFIRMED")
    return {"signal_id": signal_id, "status": "CONFIRMED"}


@app.post("/signals/{signal_id}/skip")
async def skip_signal(signal_id: str, _auth=Depends(require_cloud_secret)):
    """Mark a signal SKIPPED — normally triggered by the Telegram webhook
    below when the user replies 'skip'."""
    await _set_signal_status(signal_id, "SKIPPED")
    return {"signal_id": signal_id, "status": "SKIPPED"}


@app.post("/signals/{signal_id}/executed")
async def executed_signal(signal_id: str, payload: ExecutionReport,
                           _auth=Depends(require_cloud_secret)):
    """Called by the local agent once it has placed the order via the broker."""
    db = await get_db()
    await db.mark_executed(signal_id, payload.execution_price)
    logger.info("[%s] Executed at %.2f (order %s)",
                signal_id, payload.execution_price, payload.order_id)
    signal = await db.get_signal(signal_id)
    if signal:
        try:
            from cloud.api.notifier import send_trade_confirmation
            await send_trade_confirmation(
                signal_id=signal_id, symbol=signal.symbol, action=signal.action,
                quantity=payload.quantity, execution_price=payload.execution_price,
            )
        except Exception as e:
            logger.error("[%s] Trade confirmation notify failed: %s", signal_id, e)
    return {"signal_id": signal_id, "status": "EXECUTED"}


@app.post("/signals/{signal_id}/failed")
async def failed_signal(signal_id: str, payload: FailureReport,
                         _auth=Depends(require_cloud_secret)):
    """Called by the local agent when a CONFIRMED signal couldn't be sized
    or placed (e.g. insufficient funds, broker rejection)."""
    await _set_signal_status(signal_id, "FAILED")
    logger.error("[%s] Execution failed: %s", signal_id, payload.reason)
    try:
        from cloud.api.notifier import send_error_alert
        await send_error_alert(f"Signal {signal_id} execution", payload.reason)
    except Exception as e:
        logger.error("[%s] Failure notify failed: %s", signal_id, e)
    return {"signal_id": signal_id, "status": "FAILED"}


@app.post("/signals/{signal_id}/closed")
async def closed_signal(signal_id: str, payload: ClosedReport,
                         _auth=Depends(require_cloud_secret)):
    """Called by the local agent once auto-exit (Task 4: stop-loss/trail)
    has closed a position — mirrors /executed and /failed above."""
    db = await get_db()
    await db.mark_closed(signal_id, payload.exit_price, payload.pnl)
    logger.info("[%s] Position closed at %.2f (pnl=%.2f, %s)",
                signal_id, payload.exit_price, payload.pnl, payload.reason)
    signal = await db.get_signal(signal_id)
    if signal:
        try:
            await send_exit_notification(
                signal_id=signal_id, symbol=signal.symbol,
                exit_price=payload.exit_price, pnl=payload.pnl, reason=payload.reason,
            )
        except Exception as e:
            logger.error("[%s] Exit notify failed: %s", signal_id, e)
    return {"signal_id": signal_id, "status": "CLOSED"}


@app.post("/agent/halt")
async def agent_halt(payload: HaltReport, _auth=Depends(require_cloud_secret)):
    """Called by the local agent when its portfolio kill switch (S4-2)
    trips — relays the halt to Telegram, since the agent holds no bot
    token (ADR-01). Not signal-scoped: a halt is an account-wide state."""
    logger.critical("Agent reported TRADING HALT: %s", payload.reason)
    try:
        from cloud.api.notifier import send_halt_alert
        await send_halt_alert(payload.reason)
    except Exception as e:
        logger.error("Halt alert notify failed: %s", e)
    return {"status": "HALTED", "reason": payload.reason}


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request,
                            x_telegram_bot_api_secret_token: str = Header(default="")):
    """
    Receives Telegram Bot API updates (set up via register_telegram_webhook()
    on startup). Handles the human-in-loop 'execute' / 'skip' reply (ADR-05).

    The user must reply directly to the original signal alert message —
    the signal ID is parsed out of that message's text, not guessed.
    """
    if TELEGRAM_WEBHOOK_SECRET and not hmac.compare_digest(
            x_telegram_bot_api_secret_token, TELEGRAM_WEBHOOK_SECRET):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad secret token")

    update = await request.json()
    message = update.get("message") or update.get("edited_message") or {}
    text = (message.get("text") or "").strip().lower()
    reply_to = message.get("reply_to_message") or {}
    reply_text = reply_to.get("text") or ""

    if text not in ("execute", "skip"):
        return {"ok": True}  # not a command we care about

    match = _SIGNAL_ID_RE.search(reply_text)
    if not match:
        await send_telegram(
            "Couldn't find a signal ID — reply directly (swipe-to-reply) "
            "to the original QuantOS Signal message."
        )
        return {"ok": True}

    signal_id = match.group(1)
    new_status = "CONFIRMED" if text == "execute" else "SKIPPED"
    await _set_signal_status(signal_id, new_status)

    ack = ("Confirmed — agent will execute shortly." if new_status == "CONFIRMED"
           else "Skipped.")
    await send_telegram(f"[{signal_id}] {ack}")
    return {"ok": True}


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _find_open_signal_today(symbol: str) -> dict | None:
    """Same-day duplicate guard — see the dedup step in tradingview_webhook
    above. Returns the existing signal dict if this symbol already has a
    live or spent signal today, else None. EXECUTED is in the set so a
    re-fired alert can't open a second same-day position on one symbol;
    BLOCKED_EVENT_RISK so a blocked symbol can't be re-attempted until it
    slips through on an event-calendar refresh."""
    db = await get_db()
    return await db.find_open_signal_today(
        symbol,
        ("PENDING_CONFIRMATION", "CONFIRMED", "EXECUTED", "BLOCKED_EVENT_RISK"),
    )


async def _set_signal_status(signal_id: str, new_status: str) -> None:
    db = await get_db()
    await db.update_signal_status(signal_id, new_status)
    logger.info("[%s] Status → %s", signal_id, new_status)


async def _persist_signal(signal_id, alert, signal_status, confidence_score):
    try:
        db = await get_db()
        await db.insert_signal(Signal(
            signal_id=signal_id,
            user_id=os.getenv("DEFAULT_USER_ID", "system"),
            symbol=alert.symbol,
            action=alert.action,
            price=alert.price,
            timeframe=alert.timeframe,
            strategy=alert.strategy,
            confluence_score=alert.confluence_score,
            confidence_score=confidence_score,
            stop_loss=alert.stop_loss,
            status=signal_status,
            created_at=datetime.now(timezone.utc),
        ))
    except Exception as e:
        logger.error("Failed to persist signal %s: %s", signal_id, e)


def _confirmation_message(signal_id, symbol, action, price, stop_loss, strategy,
                          timeframe, confluence_score, confidence_score) -> str:
    """Plain-text (no parse_mode) confirmation message — built from bare
    fields so both the webhook path (fresh alert) and the re-notify sweep
    (persisted signal dict) can produce the identical message."""
    confidence_str = (
        f"Claude confidence: {confidence_score:.0f}/100\n"
        if confidence_score is not None else ""
    )
    stop_str = f"Stop loss: INR {stop_loss:,.2f}\n" if stop_loss else ""
    return (
        f"🚨 QuantOS Signal\n"
        f"ID: {signal_id}\n"
        f"--------------------\n"
        f"{'🟢 BUY' if action == 'BUY' else '🔴 SELL'} {symbol}\n"
        f"Price: INR {price:,.2f}\n"
        f"{stop_str}"
        f"Strategy: {strategy}\n"
        f"Timeframe: {timeframe}\n"
        f"Confluence: {confluence_score:.0f}/100\n"
        f"{confidence_str}"
        f"--------------------\n"
        f"Reply (to this message) execute to trade\n"
        f"Reply (to this message) skip to ignore"
    )


async def _deliver_confirmation(signal_id: str, message: str) -> bool:
    """Send a confirmation message; stamp notified_at only on success so
    the sweep below knows which PENDING_CONFIRMATION signals never reached
    the human (P1-4: an unnotified signal used to strand silently)."""
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


async def _send_confirmation_request(signal_id, alert, confidence_score):
    message = _confirmation_message(
        signal_id, alert.symbol, alert.action, alert.price, alert.stop_loss,
        alert.strategy, alert.timeframe, alert.confluence_score, confidence_score,
    )
    await _deliver_confirmation(signal_id, message)


# Re-notify sweep (P1-4): a PENDING_CONFIRMATION signal older than this
# with no successful Telegram delivery gets re-sent.
RENOTIFY_AFTER_SECONDS = float(os.getenv("RENOTIFY_AFTER_SECONDS", "300"))
NOTIFY_SWEEP_INTERVAL_SECONDS = 60


async def _renotify_stranded_signals() -> int:
    """Re-send the confirmation for pending signals that never got one.
    Runs at startup and every NOTIFY_SWEEP_INTERVAL_SECONDS thereafter."""
    db = await get_db()
    pending = await db.fetch_recent_signals(limit=200, status="PENDING_CONFIRMATION")
    now = datetime.now(timezone.utc)
    attempted = 0
    for s in pending:
        if s.get("notified_at"):
            continue
        created = datetime.fromisoformat(s["created_at"])
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if (now - created).total_seconds() < RENOTIFY_AFTER_SECONDS:
            continue  # webhook path may still be delivering/retrying
        message = _confirmation_message(
            s["signal_id"], s["symbol"], s["action"], s["price"], s["stop_loss"],
            s["strategy"], s["timeframe"], s["confluence_score"], s["confidence_score"],
        )
        await _deliver_confirmation(s["signal_id"], message)
        attempted += 1
    return attempted


async def _notify_sweep_loop() -> None:
    while True:
        try:
            n = await _renotify_stranded_signals()
            if n:
                logger.info("Notify sweep re-attempted %d stranded signal(s)", n)
        except Exception as e:
            logger.error("Notify sweep failed: %s", e)
        await asyncio.sleep(NOTIFY_SWEEP_INTERVAL_SECONDS)
