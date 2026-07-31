"""
Telegram Polling Mode — Unit Tests (2026-07-31)

The cloud API moved off Railway onto self-hosting on the Oracle VM,
plain HTTP, no domain/TLS — Telegram refuses to register a webhook on a
non-HTTPS URL, confirmed live. Covers the replacement delivery
mechanism: notifier.delete_telegram_webhook/get_telegram_updates, and
main._process_telegram_update (the shared reply-handling logic,
extracted so both the dormant POST /webhook/telegram route and the
active _telegram_poll_loop use exactly one implementation).
"""

from unittest.mock import AsyncMock, patch

import pytest

from cloud.api.main import _process_telegram_update
from cloud.api.notifier import delete_telegram_webhook, get_telegram_updates

TOKEN = "123456:ABC-FakeTokenForTests"


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Scripted outcomes per get()/post() call. An Exception instance is
    raised; anything else is returned as the response."""

    outcomes: list = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        return self._pop()

    async def post(self, url, json=None):
        return self._pop()

    def _pop(self):
        outcome = _FakeAsyncClient.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def telegram_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.outcomes = []
    yield


# ── delete_telegram_webhook ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_webhook_no_token_returns_false(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert await delete_telegram_webhook() is False


@pytest.mark.asyncio
async def test_delete_webhook_succeeds(telegram_env):
    _FakeAsyncClient.outcomes = [_FakeResponse({"ok": True})]
    assert await delete_telegram_webhook() is True


@pytest.mark.asyncio
async def test_delete_webhook_api_failure_returns_false(telegram_env):
    _FakeAsyncClient.outcomes = [_FakeResponse({"ok": False, "description": "boom"})]
    assert await delete_telegram_webhook() is False


@pytest.mark.asyncio
async def test_delete_webhook_network_error_returns_false(telegram_env):
    _FakeAsyncClient.outcomes = [ConnectionError("no route")]
    assert await delete_telegram_webhook() is False


# ── get_telegram_updates ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_updates_no_token_returns_empty(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert await get_telegram_updates(0, 30) == []


@pytest.mark.asyncio
async def test_get_updates_returns_result_list(telegram_env):
    updates = [{"update_id": 1, "message": {"text": "execute"}}]
    _FakeAsyncClient.outcomes = [_FakeResponse({"ok": True, "result": updates})]
    assert await get_telegram_updates(0, 30) == updates


@pytest.mark.asyncio
async def test_get_updates_empty_result_on_no_new_messages(telegram_env):
    _FakeAsyncClient.outcomes = [_FakeResponse({"ok": True, "result": []})]
    assert await get_telegram_updates(0, 30) == []


@pytest.mark.asyncio
async def test_get_updates_api_failure_returns_empty(telegram_env):
    _FakeAsyncClient.outcomes = [_FakeResponse({"ok": False, "description": "boom"})]
    assert await get_telegram_updates(0, 30) == []


@pytest.mark.asyncio
async def test_get_updates_network_error_returns_empty(telegram_env):
    _FakeAsyncClient.outcomes = [TimeoutError("no response")]
    assert await get_telegram_updates(0, 30) == []


# ── _process_telegram_update (shared by webhook route + poll loop) ─────────

def _update(text: str, reply_text: str = "") -> dict:
    msg = {"text": text}
    if reply_text:
        msg["reply_to_message"] = {"text": reply_text}
    return {"message": msg}


@pytest.mark.asyncio
async def test_process_update_ignores_non_command_text():
    with patch("cloud.api.main.send_telegram", new_callable=AsyncMock) as mock_send:
        await _process_telegram_update(_update("hello there"))
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_process_update_execute_without_signal_id_asks_for_reply():
    with patch("cloud.api.main.send_telegram", new_callable=AsyncMock) as mock_send:
        await _process_telegram_update(_update("execute"))
        mock_send.assert_called_once()
        assert "reply directly" in mock_send.call_args[0][0]


@pytest.mark.asyncio
async def test_process_update_execute_confirms_signal():
    with patch("cloud.api.main._set_signal_status", new_callable=AsyncMock) as mock_set, \
         patch("cloud.api.main.send_telegram", new_callable=AsyncMock) as mock_send:
        await _process_telegram_update(_update("execute", "QuantOS Signal SIG-ABC123-DEADBEEF ..."))
        mock_set.assert_called_once_with("SIG-ABC123-DEADBEEF", "CONFIRMED")
        assert "Confirmed" in mock_send.call_args[0][0]


@pytest.mark.asyncio
async def test_process_update_skip_marks_skipped():
    with patch("cloud.api.main._set_signal_status", new_callable=AsyncMock) as mock_set, \
         patch("cloud.api.main.send_telegram", new_callable=AsyncMock) as mock_send:
        await _process_telegram_update(_update("skip", "QuantOS Signal SIG-XYZ999-CAFEBABE ..."))
        mock_set.assert_called_once_with("SIG-XYZ999-CAFEBABE", "SKIPPED")
        assert "Skipped" in mock_send.call_args[0][0]


@pytest.mark.asyncio
async def test_process_update_is_case_insensitive():
    with patch("cloud.api.main._set_signal_status", new_callable=AsyncMock) as mock_set, \
         patch("cloud.api.main.send_telegram", new_callable=AsyncMock):
        await _process_telegram_update(_update("EXECUTE", "QuantOS Signal SIG-ABC123-DEADBEEF ..."))
        mock_set.assert_called_once_with("SIG-ABC123-DEADBEEF", "CONFIRMED")


@pytest.mark.asyncio
async def test_process_update_reads_edited_message_too():
    with patch("cloud.api.main._set_signal_status", new_callable=AsyncMock) as mock_set, \
         patch("cloud.api.main.send_telegram", new_callable=AsyncMock):
        update = {"edited_message": {
            "text": "execute",
            "reply_to_message": {"text": "QuantOS Signal SIG-ABC123-DEADBEEF ..."},
        }}
        await _process_telegram_update(update)
        mock_set.assert_called_once_with("SIG-ABC123-DEADBEEF", "CONFIRMED")


@pytest.mark.asyncio
async def test_process_update_empty_message_does_not_crash():
    with patch("cloud.api.main.send_telegram", new_callable=AsyncMock) as mock_send:
        await _process_telegram_update({})
        mock_send.assert_not_called()
