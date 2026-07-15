"""
QuantOS — Cockpit Analyst Chat Route
──────────────────────────────────────
Public endpoint (the cockpit is a static browser app — it cannot hold the
X-Cloud-Secret used by agent-only write routes, since Vite inlines any
VITE_ env var into the public JS bundle). Protected instead by a blunt
daily message cap (cloud/analyst/chat.py's CHAT_DAILY_LIMIT) — real
endpoint-level auth is a separate, not-yet-decided piece of the broader
cockpit security design.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from cloud.analyst.chat import ChatLimitExceeded, ask_analyst

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analyst", tags=["analyst"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


@router.post("/chat")
async def chat(payload: ChatRequest):
    try:
        reply = await ask_analyst(payload.message)
        return {"reply": reply, "limited": False}
    except ChatLimitExceeded as e:
        return {"reply": str(e), "limited": True}
    except Exception as e:
        logger.error("Analyst chat failed: %s", e)
        return {"reply": "Analyst is unavailable right now — try again shortly.", "limited": False}
