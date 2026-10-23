"""core/llm -- model registry (config/models.yaml) and the metadata-only call log."""

import json
import time
from types import SimpleNamespace

import pytest

from core.llm import calllog, log_call, model_for, prices


def test_features_resolve_to_todays_models():
    assert model_for("pre_trade") == "claude-sonnet-4-6"
    assert model_for("shortlist_note") == "claude-opus-5"
    assert model_for("no_such_feature") == "claude-sonnet-4-6"          # fallback, not a crash


def test_env_override(monkeypatch):
    monkeypatch.setenv("QUANTOS_MODEL_PRE_TRADE", "claude-opus-5-5")
    assert model_for("pre_trade") == "claude-opus-5-5"


def test_prices_and_estimate():
    assert prices()["claude-opus-5"] == (5.0, 25.0)
    # 1M in + 1M out on Sonnet 4.6 = $18; cache read at 0.1x input, write at 1.25x
    assert calllog.estimate_usd("claude-sonnet-4-6", 1_000_000, 1_000_000) == pytest.approx(18.0)
    assert calllog.estimate_usd("claude-sonnet-4-6", 0, 0, cache_read=1_000_000, cache_write=1_000_000) == pytest.approx(0.3 + 3.75)
    assert calllog.estimate_usd("unknown-model", 1, 1) is None


def test_log_call_writes_metadata_only(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTOS_HOME_DIR", str(tmp_path))
    resp = SimpleNamespace(usage=SimpleNamespace(input_tokens=1000, output_tokens=200,
                                                 cache_read_input_tokens=0, cache_creation_input_tokens=0),
                           stop_reason="end_turn", _request_id="req_1",
                           content=[SimpleNamespace(type="text", text="SECRET PAN ABCDE1234F")])
    log_call("pre_trade", "claude-sonnet-4-6", resp, time.perf_counter())
    raw = (tmp_path / "llm_calls.jsonl").read_text()
    row = json.loads(raw)
    assert row["feature"] == "pre_trade" and row["ok"] and row["input_tokens"] == 1000
    assert row["usd"] == pytest.approx((1000 * 3 + 200 * 15) / 1e6)
    assert "SECRET" not in raw and "ABCDE1234F" not in raw                  # never the content


def test_log_call_records_a_failure_in_finally(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTOS_HOME_DIR", str(tmp_path))
    with pytest.raises(TimeoutError):
        response, started = None, time.perf_counter()
        try:
            raise TimeoutError("slow")
        finally:
            log_call("morning_brief", "claude-sonnet-4-6", response, started)
    row = json.loads((tmp_path / "llm_calls.jsonl").read_text())
    assert row["ok"] is False and row["error"] == "TimeoutError" and row["usd"] == 0.0
