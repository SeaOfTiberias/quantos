"""
core/vault/auditor.py and core/vault/gates.py — the fail-closed contract.

This is the file that matters. `audit_gate` is what stands between a webhook
and a real order, and its entire safety argument is that `allowed` is True in
exactly two situations: everything passed, or a human disabled it in config.

Every other outcome — a rejected rule, an uncomputable rule, a missing vault,
a missing note, an empty note list, an exception from anywhere in the stack —
must come back False. The tests below enumerate those routes deliberately,
because the failure this guards against is not a crash. It is a green light
that nobody chose (memory: quantos-health-signals-mask-dead-broker).
"""

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from core.brokers.base import OHLCV
from core.vault.auditor import StrategyAuditor
from core.vault.gates import (
    audit_gate, reset_shared_auditor, rs_rating_from_rank,
)
from core.vault.index import VaultIndex
from core.vault.models import Verdict

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)

TREND_NOTE = """---
quantos:
  id: trend
---
# Trend

```quantos-rules
close > sma(50)
sma(200) > sma(200)[20]
```
"""

RS_NOTE = """---
quantos:
  id: needs_rs
---
# Needs RS

```quantos-rules
rs_rating >= 70
```
"""

STRICT_NOTE = """---
quantos:
  id: strict
---
# Strict

```quantos-rules
close < sma(200)
```
"""

CONTEXT_ONLY = """---
quantos:
  id: context
---
# Context only, no rules
"""


@pytest.fixture(autouse=True)
def _clean_shared_auditor():
    reset_shared_auditor()
    yield
    reset_shared_auditor()


@pytest.fixture
def vault(tmp_path):
    """Notes go in brain/ — the only layer whose rules may execute.
    See core/vault/layers.py."""
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "Trend.md").write_text(TREND_NOTE, encoding="utf-8")
    (brain / "NeedsRS.md").write_text(RS_NOTE, encoding="utf-8")
    (brain / "Strict.md").write_text(STRICT_NOTE, encoding="utf-8")
    (brain / "Context.md").write_text(CONTEXT_ONLY, encoding="utf-8")
    return tmp_path


def rising_bars(n=400, rate=0.004):
    out = []
    for i in range(n):
        px = 100 * math.exp(i * rate)
        out.append(OHLCV(timestamp=_BASE + timedelta(days=i), open=px, high=px * 1.01,
                         low=px * 0.99, close=px, volume=100_000))
    return out


class TestAuditor:

    def test_pass_when_every_rule_holds(self, vault):
        auditor = StrategyAuditor(VaultIndex.load(vault))
        report = auditor.audit("TEST", rising_bars(), "trend")
        assert report.verdict is Verdict.PASS
        assert report.verdict.is_clear_to_proceed

    def test_fail_names_the_rules_that_failed(self, vault):
        """A report saying only '1 rule failed' sends the reader back to the
        note to work out which — the point of auditing against written rules
        is that the answer cites the rule."""
        auditor = StrategyAuditor(VaultIndex.load(vault))
        report = auditor.audit("TEST", rising_bars(), "strict")
        assert report.verdict is Verdict.FAIL
        assert "close < sma(200)" in report.reason
        assert len(report.failed_rules) == 1

    def test_insufficient_data_outranks_fail(self, vault):
        """Deliberate precedence. FAIL says the market rejected the setup;
        INSUFFICIENT_DATA says the audit did not happen. Collapsing them
        would hide a broken feed inside plausible-looking rejections."""
        auditor = StrategyAuditor(VaultIndex.load(vault))
        report = auditor.audit("TEST", rising_bars(), "needs_rs")   # no rs_rating
        assert report.verdict is Verdict.INSUFFICIENT_DATA
        assert not report.verdict.is_clear_to_proceed

    def test_supplying_the_missing_fact_resolves_it(self, vault):
        auditor = StrategyAuditor(VaultIndex.load(vault))
        report = auditor.audit("TEST", rising_bars(), "needs_rs", rs_rating=85.0)
        assert report.verdict is Verdict.PASS

    def test_short_history_is_insufficient_not_fail(self, vault):
        auditor = StrategyAuditor(VaultIndex.load(vault))
        report = auditor.audit("TEST", rising_bars(n=20), "trend")
        assert report.verdict is Verdict.INSUFFICIENT_DATA

    def test_unknown_note_is_unavailable(self, vault):
        auditor = StrategyAuditor(VaultIndex.load(vault))
        assert auditor.audit("TEST", rising_bars(), "nope").verdict is Verdict.UNAVAILABLE

    def test_note_without_rules_is_unavailable(self, vault):
        """A context note carries no machine-checkable conditions, so it
        cannot vacuously clear a symbol."""
        auditor = StrategyAuditor(VaultIndex.load(vault))
        assert auditor.audit("TEST", rising_bars(), "context").verdict is Verdict.UNAVAILABLE

    def test_empty_history_is_insufficient(self, vault):
        auditor = StrategyAuditor(VaultIndex.load(vault))
        assert auditor.audit("TEST", [], "trend").verdict is Verdict.INSUFFICIENT_DATA


class TestGateAllows:

    def test_allows_only_when_every_note_passes(self, vault):
        decision = audit_gate("TEST", rising_bars(), ["trend"], vault_dir=vault)
        assert decision.allowed is True
        assert decision.verdict is Verdict.PASS

    def test_notes_are_conjunctive(self, vault):
        """Listing two notes means the name must satisfy both."""
        decision = audit_gate("TEST", rising_bars(), ["trend", "strict"], vault_dir=vault)
        assert decision.allowed is False
        assert decision.verdict is Verdict.FAIL

    def test_worst_verdict_wins_across_notes(self, vault):
        decision = audit_gate("TEST", rising_bars(), ["strict", "needs_rs"], vault_dir=vault)
        assert decision.verdict is Verdict.INSUFFICIENT_DATA


class TestGateFailsClosed:
    """Every route to a non-PASS must block."""

    def test_failed_rule_blocks(self, vault):
        assert audit_gate("TEST", rising_bars(), ["strict"], vault_dir=vault).allowed is False

    def test_uncomputable_rule_blocks(self, vault):
        assert audit_gate("TEST", rising_bars(), ["needs_rs"], vault_dir=vault).allowed is False

    def test_short_history_blocks(self, vault):
        assert audit_gate("TEST", rising_bars(n=20), ["trend"], vault_dir=vault).allowed is False

    def test_missing_vault_blocks_without_raising(self, tmp_path):
        decision = audit_gate("TEST", rising_bars(), ["trend"], vault_dir=tmp_path / "gone")
        assert decision.allowed is False
        assert decision.verdict is Verdict.UNAVAILABLE

    def test_missing_note_blocks(self, vault):
        assert audit_gate("TEST", rising_bars(), ["typo"], vault_dir=vault).allowed is False

    def test_empty_note_list_blocks_rather_than_vacuously_passing(self, vault):
        """'All zero audits returned PASS' is technically true and completely
        wrong — it would turn a config typo into an open gate."""
        decision = audit_gate("TEST", rising_bars(), [], vault_dir=vault)
        assert decision.allowed is False
        assert "no strategy notes" in decision.reason

    def test_unexpected_exception_blocks(self, vault, monkeypatch):
        import core.vault.gates as gates
        broken = MagicMock()
        broken.audit_all.side_effect = RuntimeError("boom")
        monkeypatch.setattr(gates, "get_shared_auditor", lambda *a, **k: broken)

        decision = audit_gate("TEST", rising_bars(), ["trend"], vault_dir=vault)
        assert decision.allowed is False
        assert "RuntimeError" in decision.reason

    def test_vault_load_exception_blocks(self, vault, monkeypatch):
        import core.vault.gates as gates
        monkeypatch.setattr(gates, "get_shared_auditor",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("disk gone")))
        assert audit_gate("TEST", rising_bars(), ["trend"], vault_dir=vault).allowed is False


class TestGateDisabledIsNotGateBroken:
    """`enabled=False` is a decision a human made and can see in config.
    'Broken' is a decision nobody made. The two must be distinguishable, or a
    deleted vault directory behaves like a deliberate opt-out."""

    def test_disabled_allows_and_marks_itself_skipped(self, vault):
        decision = audit_gate("TEST", rising_bars(), ["strict"], enabled=False, vault_dir=vault)
        assert decision.allowed is True
        assert decision.skipped is True
        assert "disabled" in decision.log_line()

    def test_broken_gate_is_not_marked_skipped(self, tmp_path):
        decision = audit_gate("TEST", rising_bars(), ["trend"], vault_dir=tmp_path / "gone")
        assert decision.skipped is False
        assert "BLOCK" in decision.log_line()


class TestExecutionGatesAreOffByDefault:
    """Both gates veto paths that spend money. Shipping this code must not
    change what either path does until someone edits config deliberately
    (memory: feedback-confirm-before-scaling-capital)."""

    def test_options_webhook_open_is_ungated_without_config(self, monkeypatch):
        import agent.main as main
        called = {}
        monkeypatch.setattr(main, "_vault_gate_allows",
                            lambda *a, **k: called.setdefault("gated", True))
        # Bail out immediately after the gate check would have run, by
        # handing it a template that fails validation.
        main._handle_options_webhook_open(MagicMock(), "http://cloud", {}, {},
                                          "NIFTY", "not_a_real_template", 1, None)
        assert "gated" not in called

    def test_options_webhook_gate_runs_when_switched_on(self, monkeypatch):
        import agent.main as main
        called = {}
        monkeypatch.setattr(main, "_vault_gate_allows",
                            lambda *a, **k: called.setdefault("gated", True) or False)
        main._handle_options_webhook_open(
            MagicMock(), "http://cloud", {}, {}, "NIFTY", "bull_call_spread", 1,
            {"vault": {"gate_options_webhook": True, "notes": ["trend"]}})
        assert called.get("gated") is True

    def test_pilot_gate_helper_blocks_when_history_is_unavailable(self, vault):
        """Fail closed on the money path: a broker that cannot answer must
        not produce an entry."""
        import asyncio
        from core.rotation.pilot_executor import _vault_filter_buys
        broker = MagicMock()

        async def _run():
            import scripts.validate_regime_classifier as vrc
            original = vrc.fetch_chunked_daily

            async def _boom(*a, **k):
                raise RuntimeError("broker down")

            vrc.fetch_chunked_daily = _boom
            try:
                return await _vault_filter_buys(
                    broker, ["AAA"], asyncio.Semaphore(1),
                    {"notes": ["trend"], "dir": str(vault)})
            finally:
                vrc.fetch_chunked_daily = original

        allowed, skipped = asyncio.run(_run())
        assert allowed == []
        assert "history unavailable" in skipped[0]["reason"]


class TestVaultGateAllows:
    """`_vault_gate_allows` is the agent-side half of the options-webhook gate,
    and until 2026-08-14 nothing exercised it — every test above monkeypatches
    it away to check the *wiring*, which meant its own body was never run.

    It shipped asking the broker for timeframe "1D". The adapters match the
    string literally and raise on anything unknown, and this function's
    except-clause turns any fetch failure into a permanent BLOCK. So the gate
    would have vetoed 100% of signals the moment it was switched on, while
    looking exactly like a working fail-closed gate in the logs.
    """

    def _broker(self, bars=None):
        """A broker as strict as the real adapter about both things the gate
        got wrong: the timeframe literal, and Fyers' 366-day range cap."""
        from core.brokers.base import BrokerError
        from core.brokers.fyers import _TF_MAP

        broker = MagicMock()
        supply = rising_bars() if bars is None else bars

        def _history(symbol, timeframe, from_date, to_date):
            if timeframe not in _TF_MAP:
                raise BrokerError(f"Unsupported timeframe: {timeframe}. "
                                  f"Use one of: {list(_TF_MAP)}")
            if (to_date - from_date).days > 366:
                raise BrokerError("History fetch failed: Date range cannot "
                                  "exceed 366 days for 1D resolution")
            return supply

        broker.get_historical_data.side_effect = _history
        return broker

    def test_requests_a_timeframe_the_adapters_actually_accept(self, vault):
        import agent.main as main
        allowed = main._vault_gate_allows(
            {"vault": {"dir": str(vault), "notes": ["trend"]}},
            "TEST", self._broker(), context="test")
        assert allowed is True

    def test_the_timeframe_is_exactly_1d(self, vault):
        import agent.main as main
        broker = self._broker()
        main._vault_gate_allows({"vault": {"dir": str(vault), "notes": ["trend"]}},
                                "TEST", broker, context="test")
        assert broker.get_historical_data.call_args[0][1] == "1d"

    def test_a_failing_rule_still_blocks(self, vault):
        """The gate must keep vetoing for the RIGHT reason, not because its
        own data fetch broke."""
        import agent.main as main
        assert main._vault_gate_allows(
            {"vault": {"dir": str(vault), "notes": ["strict"]}},
            "TEST", self._broker(), context="test") is False

    def test_a_broken_fetch_blocks(self, vault):
        import agent.main as main
        broker = MagicMock()
        broker.get_historical_data.side_effect = RuntimeError("socket closed")
        assert main._vault_gate_allows(
            {"vault": {"dir": str(vault), "notes": ["trend"]}},
            "TEST", broker, context="test") is False


class TestRsRatingFromRank:

    def test_top_rank_is_100(self):
        assert rs_rating_from_rank(1, 500) == 100.0

    def test_bottom_rank_is_zero(self):
        assert rs_rating_from_rank(500, 500) == 0.0

    def test_midpoint_is_about_50(self):
        assert 49 < rs_rating_from_rank(250, 499) < 51

    def test_single_symbol_universe(self):
        assert rs_rating_from_rank(1, 1) == 100.0

    @pytest.mark.parametrize("rank,size", [(0, 100), (101, 100), (1, 0), (-1, 10)])
    def test_out_of_range_returns_none_rather_than_a_wrong_percentile(self, rank, size):
        assert rs_rating_from_rank(rank, size) is None
