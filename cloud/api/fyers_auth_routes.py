"""
QuantOS — Dashboard-Triggered Fyers Token Refresh
──────────────────────────────────────────────────
Fyers has no refresh-token flow for third-party apps — a human has to
log in on Fyers' own page daily (see agent/auth/fyers_auth.py's module
docstring). That login step is irreducible and stays manual. This
replaces the REST of the previous "SSH in, activate venv, run a script,
paste a code into a terminal" flow with two dashboard-facing calls,
reusing fyers_auth.py's exact session-creation/parse/exchange logic
(single source of truth, not a second implementation):

  POST /auth/fyers/start    -> generates the Fyers login URL server-side
  POST /auth/fyers/complete -> exchanges a pasted code for a real token,
                                writes it to the same path
                                quantos-token-refreshed.path already
                                watches (so the existing token-gated
                                batch — spread-probe, rotation-pilot,
                                paper-momentum, momentum-shortlist —
                                fires automatically, no new plumbing
                                needed there), then restarts
                                quantos-agent so it picks up the fresh
                                token too.

No new auth dependency beyond nginx's existing Basic auth in front of
this whole API (see deploy/nginx/quantos-cockpit.conf) — same protection
model as every other cockpit-facing route (signals/market/discovery/...).
require_cloud_secret (used by /agent/halt) is for the AGENT calling INTO
this API, not the browser calling it, so it doesn't apply here.

The agent restart runs `sudo systemctl restart quantos-agent` directly.
No new sudo grant is being made by adding this: the VM's `ubuntu` user
(quantos-cloud-api.service's own User=) already has unrestricted
passwordless sudo (confirmed via `sudo -l`, same "hobby-project risk
level" tradeoff already documented for this box's lack of TLS — see
deploy/nginx/quantos-cockpit.conf's own comment). The command is still
hardcoded with no user-supplied input reaching the shell, so a bug in
THIS route specifically can't be tricked into running something else,
even though the underlying OS-level door is already open regardless.
"""

from __future__ import annotations

import logging
import subprocess

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.auth.fyers_auth import exchange_auth_code, generate_auth_url, load_config, save_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/fyers", tags=["auth"])

CONFIG_PATH = "agent/config.yaml"
AGENT_SERVICE = "quantos-agent"
RESTART_TIMEOUT_SECS = 15


@router.post("/start")
async def start_fyers_login():
    """Returns the Fyers login URL for the browser to open in a new tab
    -- no side effects, safe to call repeatedly."""
    try:
        config = load_config(CONFIG_PATH)
        auth_url = generate_auth_url(config)
    except Exception as e:
        logger.error("Fyers auth URL generation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    return {"auth_url": auth_url}


class CompleteRequest(BaseModel):
    code: str  # the pasted redirect URL, or just the auth_code value


@router.post("/complete")
async def complete_fyers_login(body: CompleteRequest):
    """Exchanges the pasted code for a real access token, persists it,
    and restarts quantos-agent. Returns 400 (not 500) on a bad/expired
    code -- that's a normal retry-with-a-fresh-login case, not a server
    error."""
    try:
        config = load_config(CONFIG_PATH)
        access_token = exchange_auth_code(config, body.code)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Fyers token exchange failed unexpectedly: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    save_token(access_token)
    restarted, detail = _restart_agent()
    return {"status": "ok", "agent_restarted": restarted, "restart_detail": detail}


def _restart_agent() -> tuple[bool, str]:
    """Best-effort: the token is already saved by the time this runs, so
    a restart failure here is reported back but doesn't undo that --
    the existing token-refreshed.path pipeline still fires regardless,
    and a manual `sudo systemctl restart quantos-agent` remains the
    fallback exactly like every other step in this flow used to be."""
    try:
        result = subprocess.run(
            ["sudo", "/usr/bin/systemctl", "restart", AGENT_SERVICE],
            capture_output=True, text=True, timeout=RESTART_TIMEOUT_SECS,
        )
        if result.returncode == 0:
            return True, "restarted"
        return False, f"systemctl exited {result.returncode}: {result.stderr.strip()}"
    except Exception as e:
        logger.error("Agent restart failed: %s", e)
        return False, str(e)
