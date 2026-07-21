"""
agent/main.py — Phase 2 options orchestration glue: _run_options_trigger
(regime-change -> Telegram confirm prompt) and _execute_options_signal
(CONFIRMED multi-leg signal -> real orders + cloud report). Confirm-
before-execute, matching Darvas — NOT rotation's no-veto carve-out.
"""

import json
from unittest.mock import MagicMock

import pytest

import agent.main as main
from agent import risk_guard
from core.options.executor import ExecutionOutcome, LegFill, FlattenResult


def _suggestion(**overrides):
    payload = {
        "underlying": "NIFTY", "expiry": "2026-07-28", "strategy": "bull_call_spread",
        "legs": [{"action": "BUY", "option_type": "CE", "strike": 24800.0, "premium": 120.0,
                  "quantity": 1, "symbol": "NSE:NIFTY2672824800CE", "lot_size": 65}],
        "rationale": "r", "regime_context": "TRENDING_BULL", "max_profit": 100.0,
        "max_loss": 50.0, "net_premium": -50.0, "probability_of_profit": 55.0,
    }
    payload.update(overrides)
    return payload


@pytest.fixture(autouse=True)
def _isolated_halt(tmp_path, monkeypatch):
    monkeypatch.setattr(risk_guard, "HALT_FLAG_PATH", tmp_path / "halt")


class TestRunOptionsTrigger:

    def test_disabled_by_default_does_nothing(self, monkeypatch):
        monkeypatch.setattr(main.options_regime_trigger, "check_and_build_suggestion",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")))
        main._run_options_trigger(MagicMock(), {}, "http://cloud", {}, MagicMock(), {})
        # no exception means the disabled gate short-circuited before the trigger ran

    def test_no_regime_result_does_nothing(self, monkeypatch):
        called = {}
        monkeypatch.setattr(main.options_regime_trigger, "check_and_build_suggestion",
                            lambda *a, **k: called.setdefault("ran", True))
        main._run_options_trigger(MagicMock(), {"options": {"enabled": True}},
                                  "http://cloud", {}, None, {})
        assert "ran" not in called

    def test_no_suggestion_posts_nothing(self, monkeypatch):
        monkeypatch.setattr(main.options_regime_trigger, "check_and_build_suggestion",
                            lambda *a, **k: None)
        posted = {}
        monkeypatch.setattr(main.requests, "post",
                            lambda *a, **k: posted.setdefault("called", True))
        main._run_options_trigger(MagicMock(), {"options": {"enabled": True, "dry_run": False}},
                                  "http://cloud", {}, MagicMock(), {})
        assert "called" not in posted

    def test_dry_run_does_not_post_to_cloud(self, monkeypatch):
        monkeypatch.setattr(main.options_regime_trigger, "check_and_build_suggestion",
                            lambda *a, **k: _suggestion())
        posted = {}
        monkeypatch.setattr(main.requests, "post",
                            lambda *a, **k: posted.setdefault("called", True))
        main._run_options_trigger(
            MagicMock(), {"options": {"enabled": True, "dry_run": True}},
            "http://cloud", {}, MagicMock(), {})
        assert "called" not in posted

    def test_live_run_posts_suggestion_to_cloud(self, monkeypatch):
        monkeypatch.setattr(main.options_regime_trigger, "check_and_build_suggestion",
                            lambda *a, **k: _suggestion())
        captured = {}

        def _fake_post(url, json, headers, timeout):
            captured["url"] = url
            captured["json"] = json
            return MagicMock(raise_for_status=lambda: None,
                             json=lambda: {"signal_id": "SIG-OPT-X"})

        monkeypatch.setattr(main.requests, "post", _fake_post)
        main._run_options_trigger(
            MagicMock(), {"options": {"enabled": True, "dry_run": False}},
            "http://cloud", {}, MagicMock(), {})

        assert captured["url"] == "http://cloud/options/signal"
        assert captured["json"]["underlying"] == "NIFTY"

    def test_lots_per_trade_passed_through(self, monkeypatch):
        captured_kwargs = {}

        def _fake_check(broker, regime_result, positions, cloud_url, headers,
                       lots=1, underlying="NIFTY"):
            captured_kwargs["lots"] = lots
            return None

        monkeypatch.setattr(main.options_regime_trigger, "check_and_build_suggestion", _fake_check)
        main._run_options_trigger(
            MagicMock(), {"options": {"enabled": True, "lots_per_trade": 3}},
            "http://cloud", {}, MagicMock(), {})
        assert captured_kwargs["lots"] == 3

    def test_trigger_build_exception_is_swallowed(self, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("chain fetch failed")
        monkeypatch.setattr(main.options_regime_trigger, "check_and_build_suggestion", _boom)
        # Must not raise.
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
