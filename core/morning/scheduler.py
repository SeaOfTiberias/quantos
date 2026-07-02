"""
QuantOS — Morning Brief Scheduler
─────────────────────────────────────
US-14: Scheduled job that runs at 8:30 AM IST (03:00 UTC) Mon-Fri.
Assembles data from regime, screener, events, Kelly sizing, P&L,
then fires generate_morning_brief() and sends to WhatsApp.
"""

import logging
from datetime import date, datetime, timezone

from core.morning.brief import MorningBriefData, generate_morning_brief

logger = logging.getLogger(__name__)


async def run_morning_brief_job(
    regime_service=None,
    event_filter=None,
    trade_history=None,
    screener_results: list = None,
) -> dict:
    """
    Assemble all data sources and generate the morning brief.

    Args:
        regime_service: RegimeService instance (US-05)
        event_filter: EventFilterService instance (US-06)
        trade_history: TradeHistoryService instance (US-07)
        screener_results: pre-ranked candidates from US-03 (or empty list)

    Returns:
        dict with message text and delivery status
    """
    logger.info("Running morning brief job at %s", datetime.now(timezone.utc))

    # ── Regime ────────────────────────────────────────────────────────────────
    regime_data = {
        "regime": "UNCERTAIN", "confidence": 0,
        "trend_signal": "UNKNOWN", "vix_signal": "UNKNOWN",
        "darvas_enabled": False, "allowed_strategies": [],
    }
    if regime_service:
        try:
            result = await regime_service.get_regime(force_refresh=True)
            regime_data = {
                "regime": result.regime.value,
                "confidence": result.confidence,
                "trend_signal": result.trend_signal,
                "vix_signal": result.vix_signal,
                "darvas_enabled": result.darvas_enabled,
                "allowed_strategies": result.allowed_strategies,
            }
        except Exception as e:
            logger.error("Regime fetch failed for morning brief: %s", e)

    # ── Upcoming events ───────────────────────────────────────────────────────
    upcoming_events = []
    if event_filter:
        try:
            events = event_filter.calendar.upcoming_events(days_ahead=7)
            upcoming_events = [
                {
                    "event_type":  e.event_type.value,
                    "event_date":  e.event_date.isoformat(),
                    "impact":      e.impact.value,
                    "description": e.description,
                }
                for e in events
            ]
        except Exception as e:
            logger.error("Event calendar fetch failed: %s", e)

    # ── Kelly sizing ──────────────────────────────────────────────────────────
    kelly_size_pct = 0.02      # fallback
    kelly_method   = "FIXED_FALLBACK"
    trade_count    = 0
    prev_pnl       = 0.0
    prev_trades    = 0

    if trade_history:
        try:
            import os
            capital = float(os.getenv("DEFAULT_CAPITAL", "500000"))
            sizing  = trade_history.get_current_sizing("PORTFOLIO", capital)
            kelly_size_pct = sizing.size_pct
            kelly_method   = sizing.method
            stats = trade_history.stats_summary()
            trade_count = stats.get("total_trades", 0)
        except Exception as e:
            logger.error("Trade history fetch failed: %s", e)

    # ── Assemble ──────────────────────────────────────────────────────────────
    data = MorningBriefData(
        date=date.today(),
        regime=regime_data["regime"],
        regime_confidence=regime_data["confidence"],
        trend_signal=regime_data["trend_signal"],
        vix_signal=regime_data["vix_signal"],
        darvas_enabled=regime_data["darvas_enabled"],
        allowed_strategies=regime_data["allowed_strategies"],
        top_candidates=screener_results or [],
        upcoming_events=upcoming_events,
        kelly_size_pct=kelly_size_pct,
        kelly_method=kelly_method,
        trade_history_count=trade_count,
        prev_day_pnl=prev_pnl,
        prev_day_trades=prev_trades,
    )

    brief = await generate_morning_brief(data)

    # ── Send to WhatsApp ──────────────────────────────────────────────────────
    delivered = False
    try:
        from cloud.api.notifier import send_whatsapp
        delivered = await send_whatsapp(brief.whatsapp_message)
    except Exception as e:
        logger.error("WhatsApp delivery failed: %s", e)

    logger.info("Morning brief generated%s", " and delivered" if delivered else " (WhatsApp not configured)")
    return {
        "status":    "delivered" if delivered else "generated",
        "date":      data.date.isoformat(),
        "regime":    data.regime,
        "candidates": len(data.top_candidates),
        "events":    len(data.upcoming_events),
        "message":   brief.whatsapp_message,
    }


def register_morning_brief_job(scheduler, **services) -> None:
    """Register the morning brief as a cron job — 8:30 AM IST = 03:00 UTC."""
    from apscheduler.triggers.cron import CronTrigger

    async def job():
        await run_morning_brief_job(**services)

    scheduler.add_job(
        job,
        trigger=CronTrigger(hour=3, minute=0, day_of_week="mon-fri"),
        id="morning_brief",
        name="Morning Intelligence Brief (8:30 AM IST)",
        replace_existing=True,
    )
    logger.info("Registered job: morning_brief (8:30 AM IST, Mon-Fri)")
