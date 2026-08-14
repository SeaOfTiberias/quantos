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


class TestRuleTally:
    """Both bundled notes are strict conjunctive screens — 0 of 50 Alpha 50
    names cleared both on 2026-08-14 — so the headline verdict is FAIL for
    nearly every name on nearly every day and cannot separate "missed by one
    rule" from "nowhere close". The tally is what makes the column readable.
    """

    def test_counts_rules_across_every_note(self, vault):
        out = annotate_with_vault_audit([entry("AAA", 1)], {"AAA": rising_bars()},
                                        ["trend", "strict"], vault_dir=vault)
        # trend passes its 1 rule, strict fails its 1
        assert out[0].vault_rules_passed == 1
        assert out[0].vault_rules_total == 2

    def test_a_clean_pass_tallies_everything(self, vault):
        out = annotate_with_vault_audit([entry("AAA", 1)], {"AAA": rising_bars()},
                                        ["trend"], vault_dir=vault)
        assert (out[0].vault_rules_passed, out[0].vault_rules_total) == (1, 1)

    def test_the_detail_carries_each_notes_own_tally(self, vault):
        out = annotate_with_vault_audit([entry("AAA", 1)], {"AAA": rising_bars()},
                                        ["trend", "strict"], vault_dir=vault)
        assert "Trend: PASS (1/1)" in out[0].vault_detail
        assert "Strict: FAIL (0/1)" in out[0].vault_detail

    def test_an_unevaluable_rule_counts_in_the_total_but_not_the_pass(self, tmp_path):
        """INSUFFICIENT_DATA must not inflate the tally — a rule that could
        not be computed is not a rule that held. `rs_rating` is the live case:
        it is injected, so a note asking for it has a rule that is neither
        passed nor failed."""
        (tmp_path / "brain").mkdir()
        (tmp_path / "brain" / "Mixed.md").write_text(
            "---\nquantos:\n  id: mixed\n---\n# Mixed\n"
            "```quantos-rules\nclose > sma(50)\nrs_rating >= 90\n```\n",
            encoding="utf-8")
        # One entry, so rs_rating_from_rank has no universe to work with and
        # the second rule stays unevaluable.
        out = annotate_with_vault_audit([entry("AAA", 0)], {"AAA": rising_bars()},
                                        ["mixed"], vault_dir=tmp_path)
        assert out[0].vault_verdict == "INSUFFICIENT_DATA"
        assert out[0].vault_rules_passed == 1      # close > sma(50) held
        assert out[0].vault_rules_total == 2       # the rs_rating rule still counts

    def test_no_history_scores_nothing_rather_than_zero_of_n(self, vault):
        """The auditor returns before evaluating any rule, so 0/0 is honest:
        the cockpit falls back to the verdict word instead of rendering a
        misleading '0/1'."""
        out = annotate_with_vault_audit([entry("AAA", 1)], {}, ["trend"], vault_dir=vault)
        assert out[0].vault_verdict == "INSUFFICIENT_DATA"
        assert out[0].vault_rules_total == 0

    def test_no_tally_when_the_vault_never_loaded(self, tmp_path):
        """None, not 0/0 — 'not attempted' and 'attempted and scored nothing'
        are different states, and the cockpit renders them differently."""
        out = annotate_with_vault_audit([entry("AAA", 1)], {"AAA": rising_bars()},
                                        ["trend"], vault_dir=tmp_path / "gone")
        assert out[0].vault_verdict == "UNAVAILABLE"
        assert out[0].vault_rules_passed is None
        assert out[0].vault_rules_total is None

    def test_no_tally_when_the_audit_raises(self, vault):
        auditor = MagicMock()
        auditor.audit_all.side_effect = RuntimeError("boom")
        out = annotate_with_vault_audit([entry("AAA", 1)], {"AAA": rising_bars()},
                                        ["trend"], vault_dir=vault, auditor=auditor)
        assert out[0].vault_verdict == "UNAVAILABLE"
        assert out[0].vault_rules_total is None

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
