"""
agent/main.py — S8-3 rotation orchestration glue: _run_rotation_rebalance
(loads config, calls core/rotation/executor.py, reports to cloud) and
_report_rotation_to_cloud (best-effort POST to /rotation/report).
"""

from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest

import agent.main as main


@dataclass
class _FakeRebalanceResult:
    buys: list = field(default_factory=list)
    sells: list = field(default_factory=list)
    skipped_buys: list = field(default_factory=list)
    dry_run: bool = True


class TestReportRotationToCloud:

    def test_posts_expected_payload_shape(self, monkeypatch):
        captured = {}

        def _fake_post(url, json, headers, timeout):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return MagicMock(raise_for_status=lambda: None)

        monkeypatch.setattr(main.requests, "post", _fake_post)

        result = _FakeRebalanceResult(
            buys=[{"symbol": "A", "quantity": 10}],
            sells=[{"symbol": "B", "quantity": 5}],
            skipped_buys=[{"symbol": "C", "reason": "halted"}],
            dry_run=False,
        )
        main._report_rotation_to_cloud("http://cloud", {"X-Cloud-Secret": "s"}, result)

        assert captured["url"] == "http://cloud/rotation/report"
        assert captured["json"]["buys"] == result.buys
        assert captured["json"]["sells"] == result.sells
        assert captured["json"]["skipped_buys"] == result.skipped_buys
        assert captured["json"]["dry_run"] is False
        assert captured["headers"] == {"X-Cloud-Secret": "s"}

    def test_network_failure_is_swallowed_not_raised(self, monkeypatch):
        def _boom(*a, **kw):
            raise ConnectionError("cloud unreachable")

        monkeypatch.setattr(main.requests, "post", _boom)

        # Must not raise.
        main._report_rotation_to_cloud("http://cloud", {}, _FakeRebalanceResult())


class TestRunRotationRebalance:

    def test_skips_when_universe_file_empty(self, monkeypatch):
        monkeypatch.setattr(main, "_load_universe", lambda path: [])
        called = {}
        monkeypatch.setattr(main, "_report_rotation_to_cloud",
                            lambda *a, **k: called.setdefault("reported", True))

        main._run_rotation_rebalance(
            broker=MagicMock(), config={"rotation": {"universe_file": "x.txt"}},
            cloud_url="http://cloud", headers={})

        assert "reported" not in called

    def test_calls_executor_with_configured_params_and_reports_result(self, monkeypatch):
        import core.rotation.executor as executor_module

        captured_kwargs = {}

        async def _fake_run_weekly_rebalance(broker, universe, *, top_n, position_size, dry_run):
            captured_kwargs.update(top_n=top_n, position_size=position_size,
                                   dry_run=dry_run, universe=universe)
            return _FakeRebalanceResult(dry_run=dry_run)

        monkeypatch.setattr(executor_module, "run_weekly_rebalance", _fake_run_weekly_rebalance)
        monkeypatch.setattr(main, "_load_universe", lambda path: ["A", "B"])

        reported = {}
        monkeypatch.setattr(main, "_report_rotation_to_cloud",
                            lambda cloud_url, headers, result: reported.setdefault("result", result))

        config = {"rotation": {
            "universe_file": "agent/universe_nifty500.txt",
            "top_n": 5, "position_size": 50_000, "dry_run": False,
        }}
        main._run_rotation_rebalance(broker=MagicMock(), config=config,
                                     cloud_url="http://cloud", headers={})

        assert captured_kwargs["top_n"] == 5
        assert captured_kwargs["position_size"] == 50_000
        assert captured_kwargs["dry_run"] is False
        assert captured_kwargs["universe"] == ["A", "B"]
        assert "result" in reported

    def test_defaults_applied_when_rotation_config_missing_keys(self, monkeypatch):
        import core.rotation.executor as executor_module

        captured_kwargs = {}

        async def _fake_run_weekly_rebalance(broker, universe, *, top_n, position_size, dry_run):
            captured_kwargs.update(top_n=top_n, position_size=position_size, dry_run=dry_run)
            return _FakeRebalanceResult(dry_run=dry_run)

        monkeypatch.setattr(executor_module, "run_weekly_rebalance", _fake_run_weekly_rebalance)
        monkeypatch.setattr(main, "_load_universe", lambda path: ["A"])
        monkeypatch.setattr(main, "_report_rotation_to_cloud", lambda *a, **k: None)

        main._run_rotation_rebalance(broker=MagicMock(), config={"rotation": {}},
                                     cloud_url="http://cloud", headers={})

        assert captured_kwargs["top_n"] == 20
        assert captured_kwargs["position_size"] == 100_000
        assert captured_kwargs["dry_run"] is True   # safe default: dry-run until explicitly disabled
