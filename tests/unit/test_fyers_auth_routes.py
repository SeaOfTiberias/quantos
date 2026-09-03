"""
Fyers Auth Routes — Unit Tests
────────────────────────────────
Covers cloud/api/fyers_auth_routes.py's dashboard-triggered token refresh
(POST /auth/fyers/start, POST /auth/fyers/complete). Mocks the Fyers SDK
exchange itself (already covered by tests/unit/test_fyers_auth.py) and
the systemctl restart subprocess call -- these tests are about the
route's request/response contract and error handling, not the OAuth
mechanics.
"""

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import cloud.api.fyers_auth_routes as routes
from cloud.api.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_start_returns_auth_url(client):
    with patch.object(routes, "load_config", return_value={"credentials": {}}), \
         patch.object(routes, "generate_auth_url", return_value="https://fyers.example/authorize"):
        async with client as c:
            resp = await c.post("/auth/fyers/start")
    assert resp.status_code == 200
    assert resp.json() == {"auth_url": "https://fyers.example/authorize"}


@pytest.mark.asyncio
async def test_start_failure_returns_500(client):
    with patch.object(routes, "load_config", side_effect=RuntimeError("config missing")):
        async with client as c:
            resp = await c.post("/auth/fyers/start")
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_complete_success_saves_token_and_restarts_agent(client):
    mock_result = MagicMock(returncode=0, stderr="")
    with patch.object(routes, "load_config", return_value={"credentials": {}}), \
         patch.object(routes, "exchange_auth_code", return_value="real-access-token") as mock_exchange, \
         patch.object(routes, "save_token") as mock_save, \
         patch("subprocess.run", return_value=mock_result) as mock_run:
        async with client as c:
            resp = await c.post("/auth/fyers/complete", json={"code": "pasted-code"})
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok", "agent_restarted": True, "restart_detail": "restarted"}
    mock_exchange.assert_called_once()
    mock_save.assert_called_once_with("real-access-token")
    mock_run.assert_called_once()
    assert mock_run.call_args.args[0] == ["sudo", "/usr/bin/systemctl", "restart", "quantos-agent"]


@pytest.mark.asyncio
async def test_complete_bad_code_returns_400_not_500(client):
    with patch.object(routes, "load_config", return_value={"credentials": {}}), \
         patch.object(routes, "exchange_auth_code", side_effect=RuntimeError("Fyers rejected it")):
        async with client as c:
            resp = await c.post("/auth/fyers/complete", json={"code": "bad-code"})
    assert resp.status_code == 400
    assert "Fyers rejected it" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_complete_empty_code_returns_400():
    with patch.object(routes, "load_config", return_value={"credentials": {}}), \
         patch.object(routes, "exchange_auth_code", side_effect=ValueError("No auth code provided.")):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post("/auth/fyers/complete", json={"code": ""})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_complete_still_reports_ok_when_restart_fails(client):
    # The token is already saved by the time the restart is attempted --
    # a restart failure shouldn't make the whole call look like it failed,
    # since the token-refreshed.path pipeline still fires regardless.
    mock_result = MagicMock(returncode=1, stderr="Failed to restart quantos-agent.service")
    with patch.object(routes, "load_config", return_value={"credentials": {}}), \
         patch.object(routes, "exchange_auth_code", return_value="tok"), \
         patch.object(routes, "save_token"), \
         patch("subprocess.run", return_value=mock_result):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post("/auth/fyers/complete", json={"code": "pasted-code"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["agent_restarted"] is False
    assert "Failed to restart" in body["restart_detail"]
