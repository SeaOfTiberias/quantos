"""
QuantOS Cloud API — FastAPI Webhook Receiver
─────────────────────────────────────────────
US-01: TradingView Premium → QuantOS → Agent → Broker

Pipeline:
  TradingView alert
    → POST /webhook/tradingview
    → validate secret
    → confluence gate (ADR-04: min score 70)
    → Claude pre-trade analyst (US-04)
    → persist signal to DB
    → notify local agent
    → WhatsApp confirmation (ADR-05)
"""

import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from cloud.api.db import get_db, Signal
from cloud.api.health import router as health_router
from cloud.api.notifier import send_whatsapp
from cloud.analyst.pre_trade import analyse_signal

logger = logging.getLogger(__name__)

app = FastAPI(
    title="QuantOS Cloud API",
    description="Signal ingestion, AI analysis, and agent coordination",
    version="1.0.0",
)

app.include_router(health_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
MIN_CONFLUENCE = float(os.getenv("MIN_CONFLUENCE_SCORE", "70"))


# ─── Models ──────────────────────────────────────────────────────────────────

class TradingViewAlert(BaseModel):
    """
    JSON payload from TradingView Premium webhook alert.

    Pine Script alert message template:
    {
      "symbol":            "{{ticker}}",
      "action":            "{{strategy.order.action}}",
      "price":             {{close}},
      "timeframe":         "{{interval}}",
      "strategy":          "darvas_breakout",
      "confluence_score":  {{plot_0}},
      "secret":            "YOUR_WEBHOOK_SECRET"
    }
    """
    symbol:            str   = Field(..., description="NSE symbol e.g. RELIANCE")
    action:            str   = Field(..., description="BUY or SELL")
    price:             float = Field(..., description="Signal trigger price")
    timeframe:         str   = Field(..., description="Chart timeframe e.g. 15, 60, D")
    strategy:          str   = Field(..., description="Strategy ID e.g. darvas_breakout")
    confluence_score:  float = Field(default=0, ge=0, le=100)
    secret:            str   = Field(..., description="Webhook validation secret")
    notes:             str   = Field(default="")


class SignalResponse(BaseModel):
    signal_id:        str
    symbol:           str
    action:           str
    status:           str
    confidence_score: float | None = None
    message:          str


# ─── Health ──────────────────────────────────────────────────────────────────

# ─── Webhook ─────────────────────────────────────────────────────────────────

@app.post("/webhook/tradingview", response_model=SignalResponse)
async def tradingview_webhook(alert: TradingViewAlert, request: Request):
    """
    Receives TradingView Premium webhook alerts and routes them
    through the QuantOS signal pipeline.
    """

    # ── 1. Validate secret ───────────────────────────────────────────────────
    if os.getenv("WEBHOOK_SECRET", "") and alert.secret != os.getenv("WEBHOOK_SECRET", ""):
        logger.warning("Rejected webhook — bad secret from %s", request.client.host)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )

    signal_id = f"SIG-{alert.strategy[:4].upper()}-{uuid.uuid4().hex[:8].upper()}"
    logger.info(
        "[%s] %s %s @ %.2f | tf=%s | confluence=%.0f",
        signal_id, alert.action, alert.symbol,
        alert.price, alert.timeframe, alert.confluence_score,
    )

    # ── 2. Confluence gate (ADR-04) ──────────────────────────────────────────
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

    # ── 3. Claude pre-trade analysis (US-04) ─────────────────────────────────
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

    # ── 4. Persist signal ────────────────────────────────────────────────────
    signal_status = "PENDING_CONFIRMATION"
    await _persist_signal(signal_id, alert, signal_status, confidence_score)

    # ── 5. WhatsApp confirmation (ADR-05: human-in-loop) ─────────────────────
    await _send_confirmation_request(signal_id, alert, confidence_score)

    return SignalResponse(
        signal_id=signal_id,
        symbol=alert.symbol,
        action=alert.action,
        status=signal_status,
        confidence_score=confidence_score,
        message="Signal pending WhatsApp confirmation",
    )


@app.get("/signals")
async def list_signals(limit: int = 20):
    """Return recent signals for the cockpit dashboard."""
    db = await get_db()
    signals = await db.fetch_recent_signals(limit=limit)
    return {"signals": signals}


@app.post("/signals/{signal_id}/confirm")
async def confirm_signal(signal_id: str):
    """Called by local agent when user replies 'execute' on WhatsApp."""
    db = await get_db()
    await db.update_signal_status(signal_id, "CONFIRMED")
    logger.info("[%s] Confirmed for execution", signal_id)
    return {"signal_id": signal_id, "status": "CONFIRMED"}


@app.post("/signals/{signal_id}/skip")
async def skip_signal(signal_id: str):
    """Called by local agent when user replies 'skip' on WhatsApp."""
    db = await get_db()
    await db.update_signal_status(signal_id, "SKIPPED")
    logger.info("[%s] Skipped by user", signal_id)
    return {"signal_id": signal_id, "status": "SKIPPED"}


# ─── Helpers ─────────────────────────────────────────────────────────────────

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
            status=signal_status,
            created_at=datetime.now(timezone.utc),
        ))
    except Exception as e:
        logger.error("Failed to persist signal %s: %s", signal_id, e)


async def _send_confirmation_request(signal_id, alert, confidence_score):
    confidence_str = (
        f"Claude confidence: *{confidence_score:.0f}/100*\n"
        if confidence_score is not None else ""
    )
    message = (
        f"🚨 *QuantOS Signal*\n"
        f"ID: `{signal_id}`\n"
        f"━━━━━━━━━━━━━━\n"
        f"{'🟢 BUY' if alert.action == 'BUY' else '🔴 SELL'} *{alert.symbol}*\n"
        f"Price: ₹{alert.price:,.2f}\n"
        f"Strategy: {alert.strategy}\n"
        f"Timeframe: {alert.timeframe}\n"
        f"Confluence: {alert.confluence_score:.0f}/100\n"
        f"{confidence_str}"
        f"━━━━━━━━━━━━━━\n"
        f"Reply *execute* to trade\n"
        f"Reply *skip* to ignore"
    )
    try:
        await send_whatsapp(message)
        logger.info("[%s] WhatsApp confirmation sent", signal_id)
    except Exception as e:
        logger.error("[%s] WhatsApp notification failed: %s", signal_id, e)
