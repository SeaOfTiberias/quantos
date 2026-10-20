"""agent/auth/breeze_auth.py and cloud/api/breeze_auth_routes.py (Breeze SDK mocked)."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agent.auth import breeze_auth as ba

CREDS = {"account": "test", "api_key": "AB@1&2+c", "api_secret": "s3cr$t"}


@pytest.fixture
def home(tmp_path, monkeypatch):
    (tmp_path / "breeze_credentials.json").write_text(json.dumps(CREDS))
    monkeypatch.setattr(ba, "CREDS_PATH", tmp_path / "breeze_credentials.json")
    monkeypatch.setattr(ba, "SESSION_PATH", tmp_path / "breeze_session.json")
    return tmp_path


def _fake_sdk(funds_status=200, reject=False):
    client = MagicMock()
    if reject:
        client.generate_session.side_effect = Exception("invalid session")
    client.get_funds.return_value = {"Status": funds_status, "Error": None if funds_status == 200 else "bad"}
    return patch("breeze_connect.BreezeConnect", return_value=client), client


def test_login_url_encodes_the_key(home):
    assert ba.login_url() == "https://api.icicidirect.com/apiuser/login?api_key=AB%401%262%2Bc"


@pytest.mark.parametrize("text,want", [
    ("57401630", "57401630"),
    ("  57401630 ", "57401630"),
    ("https://api.icicidirect.com/apiuser/161.118.189.29?apisession=57401630", "57401630"),
    ("http://161.118.189.29/auth/breeze/callback?apisession=57401630&x=1", "57401630"),
])
def test_parse_session_token(text, want):
    assert ba.parse_session_token(text) == want


@pytest.mark.parametrize("bad", ["", "https://x/?foo=1&apisession=", "rm -rf /", "a b"])
def test_parse_rejects_garbage(bad):
    with pytest.raises(ba.BreezeAuthError):
        ba.parse_session_token(bad)


def test_create_session_validates_then_saves(home):
    p, client = _fake_sdk()
    with p:
        rec = ba.create_session("57401630")
    client.generate_session.assert_called_once_with(api_secret="s3cr$t", session_token="57401630")
    saved = json.loads((home / "breeze_session.json").read_text())
    assert saved["session_token"] == "57401630" and saved == rec
    assert ba.session_is_today(ba.load_session())


def test_rejected_token_saves_nothing(home):
    p, _ = _fake_sdk(reject=True)
    with p, pytest.raises(ba.BreezeAuthError):
        ba.create_session("57401630")
    assert not (home / "breeze_session.json").exists()
    p, _ = _fake_sdk(funds_status=500)
    with p, pytest.raises(ba.BreezeAuthError):
        ba.create_session("57401630")
    assert not (home / "breeze_session.json").exists()


def test_stale_session_is_not_today(home):
    old = (datetime.now(ba.IST) - timedelta(days=1)).isoformat()
    (home / "breeze_session.json").write_text(json.dumps({"session_token": "1234", "created_at": old}))
    assert not ba.session_is_today(ba.load_session())
    with pytest.raises(ba.BreezeAuthError):
        ba.connect()


def test_routes(home):
    from cloud.api.main import app
    c = TestClient(app)
    assert c.get("/auth/breeze/status").json() == {"connected_today": False, "created_at": None}
    assert c.post("/auth/breeze/start").json()["auth_url"].endswith("AB%401%262%2Bc")

    p, _ = _fake_sdk()
    with p:
        r = c.get("/auth/breeze/callback", params={"apisession": "57401630"})
    assert r.status_code == 200 and "connected" in r.text and "57401630" not in r.text
    assert c.get("/auth/breeze/status").json()["connected_today"] is True

    p, _ = _fake_sdk(reject=True)
    with p:
        assert c.get("/auth/breeze/callback", params={"apisession": "99999999"}).status_code == 400
        assert c.post("/auth/breeze/complete", json={"code": "99999999"}).status_code == 400
    p, _ = _fake_sdk()
    with p:
        assert c.post("/auth/breeze/complete", json={"code": "x?apisession=11112222"}).json()["status"] == "ok"


def test_status_check_asks_icici(home):
    from cloud.api.main import app
    c = TestClient(app)
    assert c.get("/auth/breeze/status", params={"check": "true"}).json()["valid"] is False   # nothing saved
    p, _ = _fake_sdk()
    with p:
        ba.create_session("57401630")
        assert c.get("/auth/breeze/status", params={"check": "true"}).json()["valid"] is True
    p, _ = _fake_sdk(reject=True)                     # ICICI killed it (a later login elsewhere)
    with p:
        body = c.get("/auth/breeze/status", params={"check": "true"}).json()
    assert body["connected_today"] is True and body["valid"] is False and "rejected" in body["detail"]
