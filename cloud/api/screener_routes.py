"""
QuantOS — Screener API & Scheduler Hook
──────────────────────────────────────────
US-03: Endpoint for uploading TradingView screener CSVs,
plus the scheduled job that runs the full pipeline each morning.

Two ways to feed the screener:
  1. Manual: POST /screener/upload with CSV file
  2. Scheduled: cloud/scheduler picks up a CSV dropped at a watched path
     (e.g. synced from TradingView export automation)
"""

import logging
import os

from fastapi import APIRouter, UploadFile, HTTPException

from core.screener.ingest import parse_screener_csv, apply_pre_filters
from core.screener.ranker import rank_candidates
from core.screener.alerts import format_shortlist_whatsapp, format_shortlist_summary_line
from cloud.api.notifier import send_whatsapp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/screener", tags=["screener"])

MIN_VOLUME = int(os.getenv("SCREENER_MIN_VOLUME", "500000"))
TOP_N      = int(os.getenv("SCREENER_TOP_N", "10"))


@router.post("/upload")
async def upload_screener_csv(file: UploadFile):
    """
    Upload a TradingView screener CSV export.
    Runs the full pipeline: parse → pre-filter → Claude rank → WhatsApp.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    content = (await file.read()).decode("utf-8")
    result = await run_screener_pipeline(content)

    return result


async def run_screener_pipeline(
    csv_content: str,
    nifty_change_pct: float = 0.0,
    send_alert: bool = True,
) -> dict:
    """
    Full screener pipeline — shared by the upload endpoint and
    the scheduled morning job.

    Args:
        csv_content: raw CSV text
        nifty_change_pct: Nifty's change over the lookback period
        send_alert: whether to push the result to WhatsApp

    Returns:
        dict with total_scanned, total_filtered, rankings
    """
    # 1. Parse
    candidates = parse_screener_csv(csv_content)
    if not candidates:
        logger.warning("Screener pipeline: no candidates parsed from CSV")
        return {
            "total_scanned": 0, "total_filtered": 0,
            "rankings": [], "message": "No valid candidates in CSV",
        }

    # 2. Pre-filter (cheap, deterministic — saves Claude cost per ADR-04)
    filtered = apply_pre_filters(candidates, min_volume=MIN_VOLUME)

    # 3. Claude ranking (single batched call)
    rankings = []
    try:
        rankings = await rank_candidates(filtered, nifty_change_pct, top_n=TOP_N)
    except Exception as e:
        logger.error("Claude ranking failed: %s", e)

    # 4. WhatsApp alert
    if send_alert:
        message = format_shortlist_whatsapp(rankings, total_scanned=len(candidates))
        try:
            await send_whatsapp(message)
        except Exception as e:
            logger.error("Failed to send shortlist WhatsApp: %s", e)

    logger.info(
        "Screener pipeline complete: %d scanned → %d filtered → %s",
        len(candidates), len(filtered), format_shortlist_summary_line(rankings),
    )

    return {
        "total_scanned":  len(candidates),
        "total_filtered": len(filtered),
        "rankings":       rankings,
    }
