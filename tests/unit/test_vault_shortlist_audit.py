"""
core/vault/shortlist_audit.py and core/vault/narrator.py.

The shortlist annotator has the opposite risk profile to the execution gates:
it can never block anything, so what matters is that it never *costs* the
shortlist anything either. A broken vault must yield a blank column, not a
lost morning list.

The narrator tests pin the one constraint that makes it safe to have at all —
it decorates an already-settled verdict and cannot move it.
"""

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from core.brokers.base import OHLCV
from core.discovery.momentum_shortlist import ShortlistEntry
from core.vault.auditor import StrategyAuditor
from core.vault.index import VaultIndex
from core.vault.models import AuditReport, Verdict
from core.vault.narrator import narrate
from core.vault.shortlist_audit import annotate_with_vault_audit

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)

TREND_NOTE = """---
quantos:
  id: trend
---
# Trend
```quantos-rules
close > sma(50)
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


@pytest.fixture
def vault(tmp_path):
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "Trend.md").write_text(TREND_NOTE, encoding="utf-8")
    (brain / "Strict.md").write_text(STRICT_NOTE, encoding="utf-8")
    return tmp_path


def rising_bars(n=400, rate=0.004):
    out = []
    for i in range(n):
        px = 100 * math.exp(i * rate)
        out.append(OHLCV(timestamp=_BASE + timedelta(days=i), open=px, high=px * 1.01,
                         low=px * 0.99, close=px, volume=100_000))
    return out


def entry(symbol, rank):
    return ShortlistEntry(
        symbol=symbol, close=100.0, momentum_pct=90.0, momentum_rank=rank,
        momentum_tier="LEADER", bucket="LEADER_TIGHT_BASE", base_status="WATCHING",
        trend_up=True,
    )


class TestAnnotator:

    def test_adds_a_verdict_per_entry(self, vault):
        entries = [entry("AAA", 1), entry("BBB", 2)]
        daily = {"AAA": rising_bars(), "BBB": rising_bars()}
        out = annotate_with_vault_audit(entries, daily, ["trend"], vault_dir=vault)
        assert [e.vault_verdict for e in out] == ["PASS", "PASS"]

    def test_records_each_notes_verdict_in_the_detail(self, vault):
        out = annotate_with_vault_audit([entry("AAA", 1)], {"AAA": rising_bars()},
                                        ["trend", "strict"], vault_dir=vault)
        assert "Trend: PASS" in out[0].vault_detail
        assert "Strict: FAIL" in out[0].vault_detail

    def test_headline_verdict_is_the_worst_across_notes(self, vault):
        out = annotate_with_vault_audit([entry("AAA", 1)], {"AAA": rising_bars()},
                                        ["trend", "strict"], vault_dir=vault)
        assert out[0].vault_verdict == "FAIL"

    def test_symbol_with_no_history_is_insufficient_data(self, vault):
        out = annotate_with_vault_audit([entry("AAA", 1)], {}, ["trend"], vault_dir=vault)
        assert out[0].vault_verdict == "INSUFFICIENT_DATA"

    def test_derives_rs_rating_from_the_shortlists_own_ranking(self, vault, tmp_path):
        """The shortlist has already ranked the universe, which is exactly the
        cross-sectional input the notes need and a single symbol cannot
        supply."""
        (tmp_path / "brain").mkdir(exist_ok=True)
        (tmp_path / "brain" / "RS.md").write_text(
            "---\nquantos:\n  id: rs\n---\n# RS\n```quantos-rules\nrs_rating >= 90\n```\n",
            encoding="utf-8")
        entries = [entry(f"S{i}", i) for i in range(1, 11)]
        daily = {e.symbol: rising_bars() for e in entries}
        out = annotate_with_vault_audit(entries, daily, ["rs"], vault_dir=tmp_path)
        assert out[0].vault_verdict == "PASS"     # rank 1 of 10 -> 100
        assert out[-1].vault_verdict == "FAIL"    # rank 10 of 10 -> 0

    def test_rs_rating_survives_a_filtered_subset(self, tmp_path):
        """Ranks come from the full universe, so a caller passing only the top
        bucket must not have every row collapse to INSUFFICIENT_DATA."""
        (tmp_path / "brain").mkdir(exist_ok=True)
        (tmp_path / "brain" / "RS.md").write_text(
            "---\nquantos:\n  id: rs\n---\n# RS\n```quantos-rules\nrs_rating >= 50\n```\n",
            encoding="utf-8")
        subset = [entry("A", 1), entry("B", 2), entry("C", 500)]
        daily = {e.symbol: rising_bars() for e in subset}
        out = annotate_with_vault_audit(subset, daily, ["rs"], vault_dir=tmp_path)
        assert [e.vault_verdict for e in out] == ["PASS", "PASS", "FAIL"]

    def test_original_fields_are_untouched(self, vault):
        out = annotate_with_vault_audit([entry("AAA", 3)], {"AAA": rising_bars()},
                                        ["trend"], vault_dir=vault)
        assert out[0].symbol == "AAA"
        assert out[0].momentum_rank == 3
        assert out[0].bucket == "LEADER_TIGHT_BASE"


class TestAnnotatorNeverCostsTheShortlist:
    """A research aid that vanishes when an optional annotation breaks is a
    worse tool than one with a blank column."""

    def test_missing_vault_leaves_rows_intact(self, tmp_path):
        entries = [entry("AAA", 1), entry("BBB", 2)]
        out = annotate_with_vault_audit(entries, {"AAA": rising_bars()},
                                        ["trend"], vault_dir=tmp_path / "gone")
        assert len(out) == 2
        assert all(e.vault_verdict == "UNAVAILABLE" for e in out)
        assert all(e.symbol for e in out)

    def test_no_notes_configured_leaves_rows_intact(self, vault):
        out = annotate_with_vault_audit([entry("AAA", 1)], {"AAA": rising_bars()},
                                        [], vault_dir=vault)
        assert len(out) == 1
        assert out[0].vault_verdict == "UNAVAILABLE"

    def test_auditor_exception_marks_one_row_not_the_run(self, vault):
        exploding = MagicMock(spec=StrategyAuditor)
        exploding.audit_all.side_effect = RuntimeError("boom")
        out = annotate_with_vault_audit([entry("AAA", 1)], {"AAA": rising_bars()},
                                        ["trend"], auditor=exploding)
        assert len(out) == 1
        assert out[0].vault_verdict == "UNAVAILABLE"
        assert "RuntimeError" in out[0].vault_detail

    def test_empty_shortlist_is_returned_unchanged(self, vault):
        assert annotate_with_vault_audit([], {}, ["trend"], vault_dir=vault) == []


class TestNarratorCannotChangeTheVerdict:
    """core/options/recommender.py was stripped of exactly this capability on
    2026-07-25 — fluent prose wrapped around a weak label reads as grounded
    analysis when it isn't. The narrator here is structurally unable to."""

    def _report(self, verdict=Verdict.FAIL):
        return AuditReport(symbol="AAA", note_name="Trend", verdict=verdict,
                           reason="1 of 1 rules failed")

    def test_narration_is_attached_without_touching_the_verdict(self):
        client = MagicMock()
        block = MagicMock()
        block.type, block.text = "text", "The stock sits below its 200-day average."
        client.messages.create.return_value = MagicMock(content=[block])

        out = narrate(self._report(Verdict.FAIL), None, client=client)
        assert out.verdict is Verdict.FAIL
        assert "200-day" in out.narration

    def test_no_client_leaves_the_report_untouched(self):
        report = self._report()
        assert narrate(report, None, client=None) is report

    def test_api_error_leaves_the_report_untouched(self):
        client = MagicMock()
        client.messages.create.side_effect = RuntimeError("rate limited")
        report = self._report()
        out = narrate(report, None, client=client)
        assert out is report
        assert out.verdict is Verdict.FAIL

    def test_empty_completion_leaves_the_report_untouched(self):
        client = MagicMock()
        client.messages.create.return_value = MagicMock(content=[])
        report = self._report()
        assert narrate(report, None, client=client) is report

    def test_the_model_never_sees_raw_bars(self):
        """It is given outcomes, not the material to re-derive a different
        answer from."""
        client = MagicMock()
        block = MagicMock()
        block.type, block.text = "text", "ok"
        client.messages.create.return_value = MagicMock(content=[block])

        narrate(self._report(), None, client=client)
        sent = str(client.messages.create.call_args)
        assert "OHLCV" not in sent
