"""QuantOS — Morning Brief API Routes"""
import logging
from fastapi import APIRouter
from core.morning.scheduler import run_morning_brief_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/morning", tags=["morning"])

@router.post("/brief")
async def trigger_morning_brief():
    """Manually trigger the morning intelligence brief."""
    result = await run_morning_brief_job()
    return result

@router.get("/brief/preview")
async def preview_morning_brief():
    """Preview the morning brief without sending to WhatsApp."""
    result = await run_morning_brief_job()
    return {"preview": result["message"]}
