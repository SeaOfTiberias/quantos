"""
S4-8 · First integration test harness (P2-4)

End-to-end exercise of the real signal pipeline:

    POST /webhook/tradingview
      → real confluence + replay + same-day dedup guards
      → real Claude pre-trade analyst  (Anthropic SDK transport mocked)
      → real in-memory SignalDB persist
      → real Telegram confirmation     (httpx transport mocked)

Only the two *external transports* are doubled — the Anthropic
`messages.create` call and the httpx POST to Telegram. Everything between
them (the webhook handler, `analyse_signal`, `_extract_confidence_score`,
`_persist_signal`, the dedup lookup, `_send_confirmation_request` →
`_deliver_confirmation` → `send_telegram` retries → `mark_notified`) is
the production code path. This is the webhook→persist→Telegram flow the
audit flagged as having zero end-to-end coverage (P2-4).

Failure injection covers the three scenarios the audit named as untested:
  • duplicate delivery  — a same-symbol re-fire is REJECTED_DUPLICATE and
    the human is notified exactly once (P1-3 fix).
  • Claude exception    — the analyst call raising must not sink the
    signal; it persists "unscored" (confidence None) and still notifies
    (P1-9 honest-unscored path).
  • Telegram outage     — all sends failing leaves the signal
    PENDING_CONFIRMATION and un-notified (notified_at None) so the
    re-notify sweep retries, rather than the signal stranding silently
    (P1-4 fix).

Each of these tests would have failed against pre-Sprint-4 `main` (double
same-day position, fake 50.0 score, silently stranded signal) and passes
now — the "failing-then-fixed" acceptance criterion.
"""

import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
# Capture the REAL httpx client before any test monkeypatches
# httpx.AsyncClient (the notifier's transport). The ASGI test client below
# must keep using the real one even while the notifier's is a double.
from httpx import AsyncClient as _RealAsyncClient, ASGITransport

import cloud.api.db as db
import cloud.api.notifier as notifier
from cloud.api.main import app
from cloud.api.db import get_db

SECRET = "integration_secret"
CLAUDE_CREATE = "cloud.analyst.pre_trade._claude.messages.create"


# ─── Transport doubles ────────────────────────────────────────────────────────

class _FakeTelegram:
    """Stands in for httpx.AsyncClient inside notifier.send_telegram.
    Records each posted message body; when `fail` is set every post raises,
    simulating a total Telegram outage across all retries."""

    sent: list = []
    fail: bool = False

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None):
        if _FakeTelegram.fail:
            raise ConnectionError("telegram unreachable")
        _FakeTelegram.sent.append(json)
        return SimpleNamespace(status_code=200, text="ok")


def _claude_response(score: float):
    """A minimal Anthropic Messages response carrying a submit_score
    tool_use block — the exact shape _extract_confidence_score parses."""
    block = SimpleNamespace(
        type="tool_use",
        name="submit_score",
        input={
            "confidence_score": score,
            "regime_alignment": "MODERATE",
            "key_concern": "extension risk after a fast run",
            "key_strength": "clean box breakout on volume",
            "recommendation": "EXECUTE",
        },
    )
    return SimpleNamespace(content=[block])


# ─── Fixtures / helpers ───────────────────────────────────────────────────────

@pytest.fixture
def pipeline_env(monkeypatch):
    """Fresh in-memory SignalDB + a configured-but-mocked-transport Telegram."""
    # Fresh DB singleton so each test asserts against a clean store.
    monkeypatch.setattr(db, "_db_instance", None)
    # Webhook fails closed without a secret; give it a known one.
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    # Telegram "configured" so send_telegram actually attempts a send …
    monkeypatch.setattr(notifier, "BOT_TOKEN", "123456:FAKE-TOKEN")
    monkeypatch.setattr(notifier, "CHAT_ID", "42")
    monkeypatch.setattr(notifier, "RETRY_BACKOFF_SECONDS", 0.01)  # keep the outage test fast
    # … but the network transport is a double.
    monkeypatch.setattr("httpx.AsyncClient", _FakeTelegram)
    _FakeTelegram.sent = []
    _FakeTelegram.fail = False
    yield


def _payload(symbol: str, **overrides) -> dict:
    p = {
        "symbol": symbol, "action": "BUY", "price": 2950.0,
        "timeframe": "1h", "strategy": "darvas_breakout",
        "confluence_score": 88, "stop_loss": 2870.0,
        "secret": SECRET, "timestamp": time.time(),
    }
    p.update(overrides)
    return p


async def _post(payload: dict):
    async with _RealAsyncClient(transport=ASGITransport(app=app),
                                base_url="http://test") as client:
        return await client.post("/webhook/tradingview", json=payload)


def _symbol() -> str:
    # Unique per test — the in-memory store's dedup guard is date-scoped, so
    # a stable symbol could collide with a sibling test's leftover signal.
    return f"ITEST{uuid.uuid4().hex[:6].upper()}"


# ─── Happy path (baseline for the failure cases) ──────────────────────────────

@pytest.mark.asyncio
async def test_webhook_to_persist_to_telegram_end_to_end(pipeline_env):
    """The whole path with nothing failing: real persist, real Claude score
    threaded through, real Telegram confirmation delivered + stamped."""
    symbol = _symbol()
    with patch(CLAUDE_CREATE, new=AsyncMock(return_value=_claude_response(82.5))):
        r = await _post(_payload(symbol))

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "PENDING_CONFIRMATION"
    assert body["confidence_score"] == 82.5
    signal_id = body["signal_id"]

    # Persisted for real in the in-memory store …
    signal = await (await get_db()).get_signal(signal_id)
    assert signal is not None
    assert signal.status == "PENDING_CONFIRMATION"
    assert signal.confidence_score == 82.5
    assert signal.notified_at is not None  # mark_notified ran on successful send

    # … and the human got exactly one confirmation carrying the signal id.
    assert len(_FakeTelegram.sent) == 1
    msg = _FakeTelegram.sent[0]["text"]
    assert signal_id in msg
    assert symbol in msg
    assert "82" in msg  # Claude confidence rendered


# ─── Failure injection 1: duplicate delivery ──────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_delivery_is_rejected_and_notified_once(pipeline_env):
    """A re-fired alert for a symbol already PENDING today is rejected as a
    duplicate — one position, one Telegram confirmation (P1-3)."""
    symbol = _symbol()
    with patch(CLAUDE_CREATE, new=AsyncMock(return_value=_claude_response(80.0))):
        first = await _post(_payload(symbol))
        second = await _post(_payload(symbol))

    assert first.json()["status"] == "PENDING_CONFIRMATION"
    assert second.json()["status"] == "REJECTED_DUPLICATE"

    # Both are persisted (audit trail), but only the first notified a human.
    signals = await (await get_db()).fetch_recent_signals(limit=10)
    statuses = sorted(s["status"] for s in signals)
    assert statuses == ["PENDING_CONFIRMATION", "REJECTED_DUPLICATE"]
    assert len(_FakeTelegram.sent) == 1


# ─── Failure injection 2: Claude exception ────────────────────────────────────

@pytest.mark.asyncio
async def test_claude_exception_persists_unscored_and_still_notifies(pipeline_env):
    """If the analyst call raises, the webhook proceeds: the signal persists
    with confidence None ("unscored") and the human is still notified — never
    a fabricated score (P1-9)."""
    symbol = _symbol()
    with patch(CLAUDE_CREATE, new=AsyncMock(side_effect=RuntimeError("claude down"))):
        r = await _post(_payload(symbol))

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "PENDING_CONFIRMATION"
    assert body["confidence_score"] is None

    signal = await (await get_db()).get_signal(body["signal_id"])
    assert signal.confidence_score is None
    assert signal.notified_at is not None  # still delivered

    assert len(_FakeTelegram.sent) == 1
    # The message must NOT invent a Claude confidence line when unscored.
    assert "confidence" not in _FakeTelegram.sent[0]["text"].lower()


# ─── Failure injection 3: Telegram outage ─────────────────────────────────────

@pytest.mark.asyncio
async def test_telegram_outage_leaves_signal_unnotified_for_sweep(pipeline_env):
    """Every Telegram send failing must not fail the webhook nor lose the
    signal: it persists PENDING_CONFIRMATION and un-notified (notified_at
    None) so the re-notify sweep retries it (P1-4)."""
    symbol = _symbol()
    _FakeTelegram.fail = True
    with patch(CLAUDE_CREATE, new=AsyncMock(return_value=_claude_response(90.0))):
        r = await _post(_payload(symbol))

    # The request still succeeds — the trade signal is captured …
    assert r.status_code == 200
    assert r.json()["status"] == "PENDING_CONFIRMATION"

    signal = await (await get_db()).get_signal(r.json()["signal_id"])
    assert signal.status == "PENDING_CONFIRMATION"
    assert signal.notified_at is None  # never delivered → sweep will re-notify

    # send_telegram exhausted its retries; nothing landed.
    assert _FakeTelegram.sent == []
