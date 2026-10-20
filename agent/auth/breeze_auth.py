"""
QuantOS — ICICI Direct (Breeze) daily session
─────────────────────────────────────────────
Breeze, like Fyers, has no refresh-token flow: the account holder logs in on
ICICI's own page every day (password + OTP), and ICICI hands back a session
token (`apisession`, 8 digits) that is good for that day. That login stays
manual. Everything after it is automated:

  - The Breeze app's redirect URL points at this VM's
    /auth/breeze/callback (cloud/api/breeze_auth_routes.py), so ICICI's
    redirect delivers the token straight here -- nothing to copy or paste.
  - If the redirect can't reach the VM, the cockpit's paste box (or this
    script) takes the redirect URL or the bare token instead.

The token is checked with a real call (get_funds) before it is saved, so a
saved session is always one that worked. Credentials (api_key, api_secret)
live in ~/.quantos/breeze_credentials.json, outside the repo, chmod 600; the
session in ~/.quantos/breeze_session.json, same.

Account: the spouse's ICICI Direct account (the one spreads are traded in).
Read-only use for now; Breeze orders also need the registered static IP and
stay gated behind an explicit go-ahead (docs/TERMINAL_ARCHITECTURE.md §7c).

Usage:
    python agent/auth/breeze_auth.py                 # prints the login URL, then asks for the token
    python agent/auth/breeze_auth.py 57401630        # or the full redirect URL
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, quote_plus, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

QUANTOS_DIR = Path(os.getenv("QUANTOS_HOME_DIR") or Path.home() / ".quantos")
CREDS_PATH = QUANTOS_DIR / "breeze_credentials.json"
SESSION_PATH = QUANTOS_DIR / "breeze_session.json"
LOGIN_BASE = "https://api.icicidirect.com/apiuser/login?api_key="
IST = timezone(timedelta(hours=5, minutes=30))


class BreezeAuthError(ValueError):
    """Bad or expired session token, or missing credentials. A retry with a
    fresh login is the fix, so routes map this to 400, not 500."""


def load_credentials(path: Optional[Path] = None) -> dict:
    path = path or CREDS_PATH
    try:
        creds = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise BreezeAuthError(f"Breeze credentials not readable at {path}: {e}") from e
    if not creds.get("api_key") or not creds.get("api_secret"):
        raise BreezeAuthError(f"{path} needs api_key and api_secret")
    return creds


def login_url(creds: Optional[dict] = None) -> str:
    """ICICI's login page for this app. The key can contain @, & and the
    like, so it must be URL-encoded."""
    creds = creds or load_credentials()
    return LOGIN_BASE + quote_plus(creds["api_key"])


def parse_session_token(text: str) -> str:
    """Accepts the bare token or the whole redirect URL (?apisession=...)."""
    text = (text or "").strip()
    if not text:
        raise BreezeAuthError("empty session token")
    if "apisession" in text:
        values = parse_qs(urlparse(text).query).get("apisession") or re.findall(r"apisession=(\w+)", text)
        if not values:
            raise BreezeAuthError("no apisession value in the pasted URL")
        text = values[0]
    if not re.fullmatch(r"[A-Za-z0-9]{4,64}", text):
        raise BreezeAuthError("that doesn't look like a Breeze session token")
    return text


def _client(creds: dict, token: str):
    from breeze_connect import BreezeConnect
    breeze = BreezeConnect(api_key=creds["api_key"])
    try:
        breeze.generate_session(api_secret=creds["api_secret"], session_token=token)
    except Exception as e:                       # the SDK raises bare Exceptions on a bad token
        raise BreezeAuthError(f"ICICI rejected the session token: {e}") from e
    return breeze


def create_session(text: str, creds: Optional[dict] = None, path: Optional[Path] = None) -> dict:
    """Validate the token with a real call, then save it. Returns the saved record."""
    path = path or SESSION_PATH
    creds = creds or load_credentials()
    token = parse_session_token(text)
    funds = _client(creds, token).get_funds() or {}
    if funds.get("Status") != 200:
        raise BreezeAuthError(f"session check failed: {funds.get('Error') or funds}")
    record = {"session_token": token, "account": creds.get("account", ""),
              "created_at": datetime.now(IST).isoformat(timespec="seconds")}
    path.write_text(json.dumps(record))
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return record


def load_session(path: Optional[Path] = None) -> Optional[dict]:
    try:
        return json.loads((path or SESSION_PATH).read_text())
    except (OSError, ValueError):
        return None


def session_is_today(record: Optional[dict]) -> bool:
    if not record or not record.get("created_at"):
        return False
    return datetime.fromisoformat(record["created_at"]).astimezone(IST).date() == datetime.now(IST).date()


def connect():
    """A ready BreezeConnect client from today's saved session, for the
    trade watcher and friends. Raises BreezeAuthError when there is none."""
    record = load_session()
    if not session_is_today(record):
        raise BreezeAuthError("no ICICI Direct session for today -- log in from the cockpit")
    return _client(load_credentials(), record["session_token"])


def main(argv: Optional[list] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if not argv:
            print(f"Log in here, then paste the redirect URL or the apisession token:\n  {login_url()}")
            argv = [input("> ")]
        record = create_session(argv[0])
    except BreezeAuthError as e:
        print(f"ERROR: {e}")
        return 1
    print(f"ICICI Direct session saved ({record['created_at']}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
