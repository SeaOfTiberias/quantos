#!/usr/bin/env python3
"""
QuantOS — set up the release page's one-time codes (run once on the VM, by the user)
───────────────────────────────────────────────────────────────────────────────────
Makes ~/.quantos/release_totp.json (0600) and prints the otpauth:// link to add to an
authenticator app (Google Authenticator, Microsoft Authenticator, 1Password: "enter a setup key"
works with the secret too). Refuses to overwrite an existing secret without --replace.

Run it in your own terminal, not through an agent: the secret is P3 and must not land in a
model's context or a log.

  python scripts/release_setup.py            # create, print the link once
  python scripts/release_setup.py --check 123456
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.orders.totp import SECRET_PATH, Verifier, new_secret, uri  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--check", metavar="CODE")
    a = ap.parse_args(argv)
    if a.check:
        why = Verifier().check(a.check)
        print("code OK" if why is None else why)
        return 0 if why is None else 1
    if SECRET_PATH.exists() and not a.replace:
        print(f"{SECRET_PATH} exists; add --replace to make a new one (the old app entry stops working)")
        return 1
    s = new_secret()
    SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRET_PATH.write_text(json.dumps(dict(secret=s)), encoding="utf-8")
    os.chmod(SECRET_PATH, 0o600)
    print("Add this to your authenticator app (shown once):")
    print(uri(s))
    print(f"setup key: {s}")
    print("Then test it: python scripts/release_setup.py --check <code>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
