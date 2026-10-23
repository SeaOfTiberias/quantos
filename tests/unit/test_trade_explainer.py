"""core/llm/explainer.py -- follow-up context for watcher alerts (fake market, fake Claude)."""

import json
from types import SimpleNamespace

import pytest

from core.llm import explainer as ex


class FakeMarket:
    def __init__(self, open_px=700.0, prev=680.0):
        self.open_px, self.prev = open_px, prev


def fake_context(open_px=700.0, prev=680.0, atr=16.0):
    return {"stock_today": {"open": open_px, "prev_close": prev, "ltp": open_px, "chg_pct": 2.9},
            "nifty_chg_pct": 0.3, "atr14": atr,
            **({"open_gap_atr": ex.gap_atr(open_px, prev, atr)} if open_px else {})}


class FakeClient:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        return self.replies.pop(0)


def reply(text, stop="end_turn"):
    usage = SimpleNamespace(input_tokens=500, output_tokens=60, cache_read_input_tokens=0,
                            cache_creation_input_tokens=0, server_tool_use=SimpleNamespace(web_search_requests=1))
    return SimpleNamespace(stop_reason=stop, usage=usage, _request_id="r",
                           content=[SimpleNamespace(type="text", text=text)] if text else [])


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTOS_HOME_DIR", str(tmp_path))
    sent = []
    holder = {"ctx": fake_context()}
    monkeypatch.setattr(ex, "market_context", lambda m, s: holder["ctx"])
    def make(replies, **cfg):
        client = FakeClient(replies)
        e = ex.Explainer({"enabled": True, **cfg}, sent.append, market_factory=FakeMarket,
                         client_factory=lambda: client, state_path=tmp_path / "state.json", run_async=False)
        return e, client
    return make, sent, holder


def test_gap_and_redact():
    assert ex.gap_atr(700, 680, 16) == 1.25 and ex.gap_atr(None, 680, 16) is None
    out = ex.redact({"alert": "CLOSE", "qty": 650, "levels": {"stop": 705, "pnl": -5000, "max_loss": 5005}})
    assert out == {"alert": "CLOSE", "levels": {"stop": 705}}


def test_explain_sends_followup_without_household_data(setup):
    make, sent, _ = setup
    e, client = make([reply("Banks fell with the market; no stock-specific news found.")])
    e.explain("hdfcbank", {"alert": "CLOSE", "qty": 650, "pnl": -3000, "levels": {"close_stop": 705}})
    assert sent == ["🧠 HDFCBANK: Banks fell with the market; no stock-specific news found."]
    kw = client.calls[0]
    body = kw["messages"][0]["content"]
    assert "650" not in body and "-3000" not in body and json.loads(body)["levels"] == {"close_stop": 705}
    assert kw["tools"][0]["type"] == "web_search_20260209" and kw["fallbacks"] == "default"
    assert kw["output_config"] == {"effort": "low"} and kw["model"] == "claude-opus-5-5"


def test_pause_turn_is_resumed_and_refusal_is_silent(setup):
    make, sent, _ = setup
    e, client = make([reply(None, stop="pause_turn"), reply("Stock-specific: block deal (NSE).")])
    e.explain("TCS", {"alert": "TARGET"})
    assert len(client.calls) == 2 and client.calls[1]["messages"][1]["role"] == "assistant"
    assert sent[-1].startswith("🧠 TCS: Stock-specific")
    e2, _ = make([reply("x", stop="refusal")])
    e2.explain("TCS", {"alert": "CLOSE"})
    assert len(sent) == 1


def test_daily_cap(setup):
    make, sent, _ = setup
    e, _ = make([reply("a"), reply("b")], max_per_day=1)
    e.explain("A", {"alert": "CLOSE"})
    e.explain("B", {"alert": "CLOSE"})
    assert sent == ["🧠 A: a"]


def test_gap_check_waits_for_the_open_then_alerts_once(setup):
    make, sent, holder = setup
    e, _ = make([reply("Sector rally.")])
    holder["ctx"] = fake_context(open_px=None)
    e.check_gap("k1", "HDFCBANK", "HDFC bear put", side=-1)
    assert sent == []                                      # no open yet: not marked, retried next pass
    holder["ctx"] = fake_context(open_px=700.0, prev=680.0, atr=16.0)
    e.check_gap("k1", "HDFCBANK", "HDFC bear put", side=-1)
    assert "⚡ GAP" in sent[0] and "+1.2 ATR" in sent[0] and "AGAINST the position" in sent[0]
    assert sent[1] == "🧠 HDFCBANK: Sector rally."
    e.check_gap("k1", "HDFCBANK", "HDFC bear put", side=-1)
    assert len(sent) == 2                                  # once per day


def test_small_gap_and_disabled_do_nothing(setup, tmp_path):
    make, sent, holder = setup
    holder["ctx"] = fake_context(open_px=684.0, prev=680.0, atr=16.0)
    e, client = make([])
    e.check_gap("k2", "X", "x", side=1)
    off = ex.Explainer({"enabled": False}, sent.append, market_factory=FakeMarket, state_path=tmp_path / "s2.json")
    off.explain("X", {"alert": "CLOSE"})
    assert sent == [] and client.calls == []


def test_prompt_exists():
    from core import prompts
    assert "Do not advise" in prompts.load("trade_explainer_system")
