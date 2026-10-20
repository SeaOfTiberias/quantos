"""
QuantOS — Dashboard ICICI Direct (Breeze) login
────────────────────────────────────────────────
The Breeze counterpart of fyers_auth_routes.py, one step further: Breeze
redirects the browser to the app's registered redirect URL with
?apisession=<token>, so when that URL is this VM's /auth/breeze/callback the
token is captured with nothing to paste.

  POST /auth/breeze/start     -> ICICI login URL for the browser to open
  GET|POST /auth/breeze/callback -> ICICI's redirect lands here; validates and
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

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
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


@router.api_route("/callback", methods=["GET", "POST"])
async def breeze_callback(request: Request):
    """ICICI returns the browser here with a form POST (seen 2026-10-20: the
    token rides in the query string of a POST), so accept both methods and
    take apisession from the query or the form body."""
    token = request.query_params.get("apisession", "")
    if not token and request.method == "POST":
        try:
            token = str((await request.form()).get("apisession") or "")
        except Exception:
            token = ""
    try:
        record = await run_in_threadpool(breeze_auth.create_session, token)
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
def breeze_status(check: bool = False):
    """`connected_today` = a session was saved today. ICICI keeps only ONE
    live API session per app, so a later login anywhere (another browser, a
    token captured elsewhere) silently kills the saved one -- `check=true`
    asks ICICI whether it still works (one get_funds call)."""
    record = breeze_auth.load_session()
    out = {"connected_today": breeze_auth.session_is_today(record),
           "created_at": record.get("created_at") if record else None}
    if check:
        out["valid"] = False
        if out["connected_today"]:
            try:
                out["valid"] = (breeze_auth.connect().get_funds() or {}).get("Status") == 200
            except Exception as e:
                out["detail"] = str(e)
    return out
