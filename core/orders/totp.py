"""
QuantOS — one-time codes for releasing orders from the dashboard (user, 2026-11-16)
───────────────────────────────────────────────────────────────────────────────────
The release page sits on the open web behind one password (nginx basic auth). A release also
needs a 6-digit code from an authenticator app on the user's phone (RFC 6238 TOTP, SHA-1, 30 s),
so a saved or stolen password alone can't send an order.

The secret lives in ~/.quantos/release_totp.json (P3: never printed, logged or committed), made
once on the VM with scripts/release_setup.py. Each code works once (the last used time step is
stored), and five wrong codes lock releases for 15 minutes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from pathlib import Path
from typing import Callable, Optional

SECRET_PATH = Path.home() / ".quantos" / "release_totp.json"
STEP = 30
DIGITS = 6
WINDOW = 1            # accept the previous and next 30 s step too (phone clock drift)
MAX_FAILS = 5
LOCK_S = 15 * 60


def code_at(secret_b32: str, step: int) -> str:
    key = base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8))
    mac = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    o = mac[-1] & 0x0F
    n = (struct.unpack(">I", mac[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** DIGITS
    return str(n).zfill(DIGITS)


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def uri(secret_b32: str, label: str = "QuantOS release") -> str:
    return f"otpauth://totp/{label.replace(' ', '%20')}?secret={secret_b32}&issuer=QuantOS&digits={DIGITS}&period={STEP}"


class Verifier:
    def __init__(self, path: Path = SECRET_PATH, clock: Callable[[], float] = time.time):
        self.path, self.clock = path, clock

    def configured(self) -> bool:
        return self.path.exists()

    def _load(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, d: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.path)

    def check(self, code: str) -> Optional[str]:
        """None if the code is good (and burns it); else why not."""
        if not self.configured():
            return "release codes are not set up (run scripts/release_setup.py on the VM)"
        d = self._load()
        now = self.clock()
        if d.get("locked_until", 0) > now:
            return f"too many wrong codes: releases locked for {int(d['locked_until'] - now) // 60 + 1} more minutes"
        code = (code or "").strip()
        step = int(now // STEP)
        good = None
        if len(code) == DIGITS and code.isdigit():
            for s in range(step - WINDOW, step + WINDOW + 1):
                if hmac.compare_digest(code_at(d["secret"], s), code):
                    good = s
                    break
        if good is None:
            d["fails"] = d.get("fails", 0) + 1
            if d["fails"] >= MAX_FAILS:
                d["fails"], d["locked_until"] = 0, now + LOCK_S
            self._save(d)
            return "wrong code"
        if good <= d.get("last_step", -1):
            return "that code was already used: wait for the next one"
        d.update(last_step=good, fails=0)
        self._save(d)
        return None
