"""
Tests for agent/auth/fyers_auth.py's shared OAuth helpers -- factored out
2026-09-03 so cloud/api/fyers_auth_routes.py's dashboard-triggered token
refresh reuses the exact same session-creation/parsing/exchange logic as
the CLI script, rather than a second implementation.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from agent.auth.fyers_auth import (  # noqa: E402
    exchange_auth_code,
    generate_auth_url,
    parse_auth_code,
)


def _config():
    return {"credentials": {"api_key": "app-id", "api_secret": "shh",
                             "redirect_uri": "https://trade.fyers.in/api-login/redirect-uri/index.html"}}


# ─── parse_auth_code ─────────────────────────────────────────────────────

def test_parse_auth_code_from_full_redirect_url():
    url = "https://trade.fyers.in/api-login/redirect-uri/index.html?s=ok&code=ABC123&state=quantos"
    assert parse_auth_code(url) == "ABC123"


def test_parse_auth_code_from_url_with_auth_code_param():
    url = "https://trade.fyers.in/api-login/redirect-uri/index.html?auth_code=XYZ789&state=quantos"
    assert parse_auth_code(url) == "XYZ789"


def test_parse_auth_code_from_raw_code_value():
    assert parse_auth_code("  RAWCODE456  ") == "RAWCODE456"


def test_parse_auth_code_empty_raises():
    with pytest.raises(ValueError):
        parse_auth_code("")


# ─── generate_auth_url ───────────────────────────────────────────────────

def test_generate_auth_url_builds_session_and_returns_url():
    mock_session = MagicMock()
    mock_session.generate_authcode.return_value = "https://api.fyers.in/authorize?..."
    with patch("fyers_apiv3.fyersModel.SessionModel", return_value=mock_session) as mock_ctor:
        url = generate_auth_url(_config())
    assert url == "https://api.fyers.in/authorize?..."
    mock_ctor.assert_called_once_with(
        client_id="app-id", secret_key="shh",
        redirect_uri="https://trade.fyers.in/api-login/redirect-uri/index.html",
        response_type="code", grant_type="authorization_code", state="quantos",
    )


# ─── exchange_auth_code ──────────────────────────────────────────────────

def test_exchange_auth_code_success():
    mock_session = MagicMock()
    mock_session.generate_token.return_value = {"s": "ok", "access_token": "real-token-abc"}
    with patch("fyers_apiv3.fyersModel.SessionModel", return_value=mock_session):
        token = exchange_auth_code(_config(), "some-pasted-code")
    mock_session.set_token.assert_called_once_with("some-pasted-code")
    assert token == "real-token-abc"


def test_exchange_auth_code_parses_pasted_url_first():
    mock_session = MagicMock()
    mock_session.generate_token.return_value = {"s": "ok", "access_token": "tok"}
    url = "https://trade.fyers.in/api-login/redirect-uri/index.html?auth_code=THECODE&state=quantos"
    with patch("fyers_apiv3.fyersModel.SessionModel", return_value=mock_session):
        exchange_auth_code(_config(), url)
    mock_session.set_token.assert_called_once_with("THECODE")


def test_exchange_auth_code_raises_on_fyers_rejection():
    mock_session = MagicMock()
    mock_session.generate_token.return_value = {"s": "error", "message": "invalid code"}
    with patch("fyers_apiv3.fyersModel.SessionModel", return_value=mock_session):
        with pytest.raises(RuntimeError):
            exchange_auth_code(_config(), "bad-code")


def test_exchange_auth_code_raises_on_unparseable_input():
    with pytest.raises(ValueError):
        exchange_auth_code(_config(), "")
