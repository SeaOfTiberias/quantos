"""
QuantOS — Fyers OAuth Login
───────────────────────────
One-time (or periodic — Fyers tokens expire daily) login flow to obtain
a Fyers access token and persist it locally at ~/.quantos/fyers_token.

Fyers has no refresh-token-only flow for third-party apps: you must
re-run this script whenever the token expires (typically once per day).

Usage:
    python agent/auth/fyers_auth.py
    python agent/auth/fyers_auth.py --config agent/config.yaml
"""

import argparse
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import yaml

# Allow running as `python agent/auth/fyers_auth.py` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

TOKEN_PATH = Path.home() / ".quantos" / "fyers_token"


def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        print(f"Config not found at {config_path}")
        sys.exit(1)
    with open(path) as f:
        return yaml.safe_load(f)


def capture_auth_code(redirect_uri: str) -> str:
    """Spin up a one-shot local HTTP server to catch the OAuth redirect."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    parsed = urlparse(redirect_uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80

    captured = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            qs = parse_qs(urlparse(self.path).query)
            captured["auth_code"] = qs.get("auth_code", [None])[0] or qs.get("code", [None])[0]
            captured["error"] = qs.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            if captured.get("auth_code"):
                body = b"<h2>QuantOS: Fyers login received. You can close this tab.</h2>"
            else:
                body = b"<h2>QuantOS: Fyers login failed. Check the terminal.</h2>"
            self.wfile.write(body)

        def log_message(self, *args):
            pass  # silence default HTTP logging

    server = HTTPServer((host, port), Handler)
    print(f"Waiting for redirect on {redirect_uri} ...")
    while "auth_code" not in captured:
        server.handle_request()

    if captured.get("error"):
        print(f"Fyers login error: {captured['error']}")
        sys.exit(1)
    if not captured.get("auth_code"):
        print("No auth_code received from redirect.")
        sys.exit(1)

    return captured["auth_code"]


def main():
    parser = argparse.ArgumentParser(description="QuantOS Fyers OAuth login")
    parser.add_argument("--config", default="agent/config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    creds = config["credentials"]
    app_id = creds["api_key"]
    secret_key = creds["api_secret"]
    redirect_uri = creds["redirect_uri"]

    from fyers_apiv3 import fyersModel

    session = fyersModel.SessionModel(
        client_id=app_id,
        secret_key=secret_key,
        redirect_uri=redirect_uri,
        response_type="code",
        grant_type="authorization_code",
        state="quantos",
    )

    auth_url = session.generate_authcode()
    print("Opening Fyers login in your browser...")
    print(auth_url)
    webbrowser.open(auth_url)

    auth_code = capture_auth_code(redirect_uri)

    session.set_token(auth_code)
    response = session.generate_token()

    if response.get("s") != "ok" or "access_token" not in response:
        print(f"Token exchange failed: {response}")
        sys.exit(1)

    access_token = response["access_token"]

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(access_token)
    try:
        TOKEN_PATH.chmod(0o600)
    except OSError:
        pass  # chmod is a no-op on Windows filesystems without POSIX perms

    print(f"Access token saved to {TOKEN_PATH}")
    print("Run `python agent/main.py` to connect.")


if __name__ == "__main__":
    main()
