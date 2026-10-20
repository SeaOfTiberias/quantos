"""
QuantOS — Dashboard ICICI Direct (Breeze) login
────────────────────────────────────────────────
The Breeze counterpart of fyers_auth_routes.py, one step further: Breeze
redirects the browser to the app's registered redirect URL with
?apisession=<token>, so when that URL is this VM's /auth/breeze/callback the
token is captured with nothing to paste.

  POST /auth/breeze/start     -> ICICI login URL for the browser to open
  GET  /auth/breeze/callback  -> ICICI's redirect lands here; validates and
                                 saves the session, shows a one-line page
  POST /auth/breeze/complete  -> paste fallback (redirect URL or bare token)
  GET  /auth/breeze/status    -> whether today's session exists (no token in it)

All logic lives in agent/auth/breeze_auth.py (single source of truth, as
with Fyers). Same protection as every other cockpit route: nginx Basic auth
in front of /auth (deploy/nginx/quantos-cockpit.conf). The token never
appears in a response.
"""

from __future__ import annotations

import html
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from agent.auth import breeze_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/breeze", tags=["auth"])


@router.post("/start")
def start_breeze_login():
    try:
        return {"auth_url": breeze_auth.login_url()}
    except breeze_auth.BreezeAuthError as e:
        raise HTTPException(status_code=500, detail=str(e))


def _page(ok: bool, text: str) -> HTMLResponse:
    colour = "#22c55e" if ok else "#ef4444"
    body = (f"<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            f"<title>ICICI Direct login</title>"
            f"<body style='background:#0A0E1A;color:#e5e7eb;font-family:monospace;padding:32px'>"
            f"<h2 style='color:{colour}'>{'ICICI Direct connected' if ok else 'ICICI Direct login failed'}</h2>"
            f"<p>{html.escape(text)}</p><p><a style='color:#60a5fa' href='/'>Back to the cockpit</a></p></body>")
    return HTMLResponse(body, status_code=200 if ok else 400)


@router.get("/callback")
def breeze_callback(apisession: str = ""):
    try:
        record = breeze_auth.create_session(apisession)
    except breeze_auth.BreezeAuthError as e:
        return _page(False, f"{e}. Log in again from the cockpit.")
    except Exception as e:
        logger.error("Breeze session creation failed unexpectedly: %s", e)
        return _page(False, "Unexpected error; see the cloud API log.")
    return _page(True, f"Session saved at {record['created_at']}. You can close this tab.")


class CompleteRequest(BaseModel):
    code: str       # the redirect URL, or just the apisession value


@router.post("/complete")
def complete_breeze_login(body: CompleteRequest):
    try:
        record = breeze_auth.create_session(body.code)
    except breeze_auth.BreezeAuthError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Breeze session creation failed unexpectedly: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "ok", "created_at": record["created_at"]}


@router.get("/status")
def breeze_status():
    record = breeze_auth.load_session()
    return {"connected_today": breeze_auth.session_is_today(record),
            "created_at": record.get("created_at") if record else None}
