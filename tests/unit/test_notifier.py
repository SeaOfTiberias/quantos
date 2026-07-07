"""
Telegram Notifier — Unit Tests (S4-5 / P1-4, P1-5)

send_telegram retry behavior and token-safe logging.
"""

import logging
from types import SimpleNamespace

import pytest

import cloud.api.notifier as notifier
from cloud.api.notifier import send_telegram, _sanitized

TOKEN = "123456:ABC-FakeTokenForTests"
OK = SimpleNamespace(status_code=200, text="ok")
SERVER_ERROR = SimpleNamespace(status_code=502, text="bad gateway")


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient — pops one scripted outcome per post.
    An Exception instance is raised; anything else is returned as the response."""

    outcomes: list = []
    posts_made: int = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None):
        _FakeAsyncClient.posts_made += 1
        outcome = _FakeAsyncClient.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def telegram_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setattr(notifier, "BOT_TOKEN", TOKEN)
    monkeypatch.setattr(notifier, "CHAT_ID", "42")
    monkeypatch.setattr(notifier, "RETRY_BACKOFF_SECONDS", 0.01)
    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.outcomes = []
    _FakeAsyncClient.posts_made = 0
    yield


@pytest.mark.asyncio
async def test_send_succeeds_first_try(telegram_env):
    _FakeAsyncClient.outcomes = [OK]
    assert await send_telegram("hello") is True
    assert _FakeAsyncClient.posts_made == 1


@pytest.mark.asyncio
async def test_send_retries_through_transient_errors(telegram_env):
    """P1-4: one network blip must not strand a live signal."""
    _FakeAsyncClient.outcomes = [ConnectionError("boom"), SERVER_ERROR, OK]
    assert await send_telegram("hello") is True
    assert _FakeAsyncClient.posts_made == 3


@pytest.mark.asyncio
async def test_send_gives_up_after_all_retries(telegram_env):
    _FakeAsyncClient.outcomes = [SERVER_ERROR] * notifier.SEND_RETRIES
    assert await send_telegram("hello") is False
    assert _FakeAsyncClient.posts_made == notifier.SEND_RETRIES


@pytest.mark.asyncio
async def test_send_unconfigured_returns_false(monkeypatch):
    monkeypatch.setattr(notifier, "BOT_TOKEN", "")
    monkeypatch.setattr(notifier, "CHAT_ID", "")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert await send_telegram("hello") is False


@pytest.mark.asyncio
async def test_bot_token_never_reaches_logs(telegram_env, caplog):
    """P1-5 AC: with Telegram failing, logs contain neither the token nor
    any /bot URL fragment (httpx errors embed the request URL)."""
    err = Exception(
        f"ConnectError for url 'https://api.telegram.org/bot{TOKEN}/sendMessage'"
    )
    _FakeAsyncClient.outcomes = [err] * notifier.SEND_RETRIES
    with caplog.at_level(logging.DEBUG, logger="cloud.api.notifier"):
        result = await send_telegram("hello")
    assert result is False
    assert TOKEN not in caplog.text
    assert "/bot" not in caplog.text


def test_sanitized_scrubs_token_and_bot_url():
    raw = f"HTTPStatusError: url https://api.telegram.org/bot{TOKEN}/sendMessage failed"
    clean = _sanitized(raw, TOKEN)
    assert TOKEN not in clean
    assert "/bot" not in clean
    assert "sendMessage" in clean  # the rest of the context survives


def test_sanitized_handles_exception_objects():
    e = ValueError(f"something with /bot{TOKEN}/x inside")
    clean = _sanitized(e, TOKEN)
    assert clean.startswith("ValueError")
    assert TOKEN not in clean
    assert "/bot" not in clean
