"""
agent/main.py — Phase 2 options orchestration glue. _run_options_trigger
(regime-change -> Telegram confirm prompt) is DISABLED 2026-07-25 (Fable
review) — see its docstring in agent/main.py. _execute_options_signal
(CONFIRMED multi-leg signal -> real orders + cloud report) is untouched and
still real — a human can still confirm and execute a manually-built
multi-leg signal, only the auto-suggestion trigger was killed.
"""

import json
from unittest.mock import MagicMock

import pytest

import agent.main as main
from agent import risk_guard
from core.options.executor import ExecutionOutcome, LegFill, FlattenResult


@pytest.fixture(autouse=True)
def _isolated_halt(tmp_path, monkeypatch):
    monkeypatch.setattr(risk_guard, "HALT_FLAG_PATH", tmp_path / "halt")


class TestRunOptionsTrigger:
    """
    DISABLED 2026-07-25 (Fable review): this used to auto-fire a Claude-
    generated, regime-gated multi-leg options suggestion to Telegram on
    every regime change. It's now a structural no-op regardless of config —
    `agent/main.py` no longer even imports `core.options.regime_trigger`,
    so there's nothing left to monkeypatch. These tests lock in "does
    nothing, ever, no matter what's passed" rather than the old
    enabled/dry_run/lots-per-trade branching.
    """

    def test_never_posts_to_cloud_regardless_of_config(self, monkeypatch):
        posted = {}
        monkeypatch.setattr(main.requests, "post",
                            lambda *a, **k: posted.setdefault("called", True))
        main._run_options_trigger(
            MagicMock(), {"options": {"enabled": True, "dry_run": False, "lots_per_trade": 3}},
            "http://cloud", {}, MagicMock(), {})
        assert "called" not in posted

    def test_does_nothing_with_empty_config(self, monkeypatch):
        posted = {}
        monkeypatch.setattr(main.requests, "post",
                            lambda *a, **k: posted.setdefault("called", True))
        main._run_options_trigger(MagicMock(), {}, "http://cloud", {}, MagicMock(), {})
        assert "called" not in posted

    def test_does_nothing_with_no_regime_result(self, monkeypatch):
        posted = {}
        monkeypatch.setattr(main.requests, "post",
                            lambda *a, **k: posted.setdefault("called", True))
        main._run_options_trigger(MagicMock(), {"options": {"enabled": True}},
                                  "http://cloud", {}, None, {})
        assert "called" not in posted

    def test_does_not_raise(self):
        # Must not raise regardless of inputs — it's a pure no-op now.
        main._run_options_trigger(MagicMock(), {"options": {"enabled": True}},
                                  "http://cloud", {}, MagicMock(), {})


class TestExecuteOptionsSignal:

    def _signal(self, **overrides):
        detail = {
            "expiry": "2026-07-28",
            "legs": [{"action": "BUY", "option_type": "CE", "strike": 24800.0,
                      "premium": 120.0, "quantity": 1, "symbol": "NSE:NIFTY2672824800CE",
                      "lot_size": 65}],
        }
        signal = {
            "signal_id": "SIG-OPT-TEST0001", "symbol": "NIFTY",
            "strategy": "bull_call_spread", "options_detail": json.dumps(detail),
        }
        signal.update(overrides)
        return signal

    def test_success_reports_executed_and_stores_position(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "core.options.positions.OPTIONS_POSITIONS_PATH", tmp_path / "options_positions.json")
        outcome = ExecutionOutcome(
            success=True,
            filled_legs=[LegFill(leg={"action": "BUY", "option_type": "CE", "strike": 24800.0,
                                       "symbol": "NSE:NIFTY2672824800CE", "quantity": 1, "lot_size": 65},
                                  order_id="ORD1", fill_price=121.0)],
        )
        monkeypatch.setattr(main.options_executor, "execute_confirmed_signal",
                            lambda broker, sid, legs: outcome)

        captured = {}

        def _fake_post(url, json, headers, timeout):
            captured["url"] = url
            captured["json"] = json
            return MagicMock(raise_for_status=lambda: None)

        monkeypatch.setattr(main.requests, "post", _fake_post)
        opts_positions = {}
        main._execute_options_signal(MagicMock(), "http://cloud", {}, opts_positions, self._signal())

        assert captured["url"] == "http://cloud/options/signal/SIG-OPT-TEST0001/executed"
        assert "NIFTY" in opts_positions

    def test_partial_failure_reports_to_partial_failure_endpoint(self, monkeypatch):
        outcome = ExecutionOutcome(
            success=False,
            filled_legs=[LegFill(leg={"action": "BUY", "option_type": "CE", "strike": 24800.0,
                                       "symbol": "X", "quantity": 1, "lot_size": 65},
                                  order_id="ORD1", fill_price=121.0)],
            failed_leg={"action": "SELL", "option_type": "CE", "strike": 25000.0},
            error="Order rejected",
            flatten_results=[FlattenResult(
                leg={"action": "BUY", "option_type": "CE", "strike": 24800.0},
                flattened=True, order_id="ORD-FLAT-1")],
        )
        monkeypatch.setattr(main.options_executor, "execute_confirmed_signal",
                            lambda broker, sid, legs: outcome)

        captured = {}

        def _fake_post(url, json, headers, timeout):
            captured["url"] = url
            captured["json"] = json
            return MagicMock(raise_for_status=lambda: None)

        monkeypatch.setattr(main.requests, "post", _fake_post)
        main._execute_options_signal(MagicMock(), "http://cloud", {}, {}, self._signal())

        assert captured["url"] == "http://cloud/options/signal/SIG-OPT-TEST0001/partial_failure"
        assert captured["json"]["failed_leg"]["strike"] == 25000.0
        assert captured["json"]["flatten_results"][0]["flattened"] is True

    def test_total_failure_reports_to_generic_failed_endpoint(self, monkeypatch):
        outcome = ExecutionOutcome(success=False, error="Insufficient funds")
        monkeypatch.setattr(main.options_executor, "execute_confirmed_signal",
                            lambda broker, sid, legs: outcome)

        captured = {}

        def _fake_post(url, json, headers, timeout):
            captured["url"] = url
            captured["json"] = json
            return MagicMock(raise_for_status=lambda: None)

        monkeypatch.setattr(main.requests, "post", _fake_post)
        main._execute_options_signal(MagicMock(), "http://cloud", {}, {}, self._signal())

        assert captured["url"] == "http://cloud/signals/SIG-OPT-TEST0001/failed"
        assert captured["json"]["reason"] == "Insufficient funds"

    def test_no_position_stored_on_any_failure(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "core.options.positions.OPTIONS_POSITIONS_PATH", tmp_path / "options_positions.json")
        outcome = ExecutionOutcome(success=False, error="Insufficient funds")
        monkeypatch.setattr(main.options_executor, "execute_confirmed_signal",
                            lambda broker, sid, legs: outcome)
        monkeypatch.setattr(main.requests, "post",
                            lambda *a, **k: MagicMock(raise_for_status=lambda: None))

        opts_positions = {}
        main._execute_options_signal(MagicMock(), "http://cloud", {}, opts_positions, self._signal())
        assert opts_positions == {}
