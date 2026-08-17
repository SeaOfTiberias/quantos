"""
core/vault/stages.py — the stage classifier.

Three things are being protected.

First, that first-match-wins actually wins: the stages are mutually exclusive,
so the note's line order is the whole tie-break, and a reordering that changes
answers must be visible as a test failure rather than as a different chart.

Second — and this is the one that matters — that an unevaluable clause STOPS
the classification instead of falling through. Falling through is the
dangerous behaviour: a warm-up failure inside the Stage 4 test would silently
promote a declining stock to Stage 2, which is this project's canonical
failure shape (a missing input rendering as a confident answer).

Third, that the classifier stays out of the gate path. `Stage` and `Verdict`
are different types on purpose; the day something starts branching execution
on a stage, the fail-closed argument in core/vault/models.py stops holding.
"""

import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.brokers.base import OHLCV
from core.vault.facts import MarketFacts
from core.vault.models import Stage, StageClause
from core.vault.parser import parse_note
from core.vault.stages import (
    StageSyntaxError,
    bars_in_stage,
    classify,
    parse_stage_clause,
    stage_timeline,
    stage_transitions,
    validate_clauses,
)

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)

WEINSTEIN_NOTE = Path("obsidian_vault/QuantOS/brain/Stan_Weinstein_Stage_Analysis.md")


def bars(closes, volumes=None):
    volumes = volumes or [100_000] * len(closes)
    return [
        OHLCV(timestamp=_BASE + timedelta(days=i), open=c, high=c * 1.01,
              low=c * 0.99, close=c, volume=v)
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]


def clause(text, line_number=1):
    return parse_stage_clause(text, note_name="test", line_number=line_number)


# Long enough to warm up sma(150)[125], which needs 275 bars. Every series
# below is 400 bars for the same reason the live fetch window is 400 days.
def rising(n=400, rate=0.004, start=100.0):
    return [start * math.exp(i * rate) for i in range(n)]


def falling(n=400, rate=0.004, start=100.0):
    return [start * math.exp(-i * rate) for i in range(n)]


def flat(n=400, start=100.0, amplitude=0.02):
    return [start * (1 + amplitude * math.sin(i / 9.0)) for i in range(n)]


class TestClauseSyntax:

    def test_bare_stage_is_the_terminal_default(self):
        c = clause("stage 1")
        assert c.stage is Stage.BASING and c.is_default and c.expression is None

    def test_stage_with_condition(self):
        c = clause("stage 4 when close < sma(150)")
        assert c.stage is Stage.DECLINING
        assert c.expression == "close < sma(150)"
        assert not c.is_default

    def test_optional_phase_label(self):
        c = clause("stage 2 pivot when close > sma(150)")
        assert c.stage is Stage.ADVANCING
        assert c.phase == "pivot"
        assert c.display == "Stage 2 · pivot"

    def test_phase_is_optional(self):
        assert clause("stage 2 when close > sma(150)").display == "Stage 2"

    @pytest.mark.parametrize("bad", [
        "stage 5 when close > sma(150)",      # no fifth stage
        "stage 0",                            # nor a zeroth
        "stage two when close > sma(150)",    # word, not digit
        "when close > sma(150)",              # no stage at all
        "close > sma(150)",                   # a rule, in the wrong block
    ])
    def test_malformed_clause_rejected(self, bad):
        with pytest.raises(StageSyntaxError):
            clause(bad)

    def test_expression_validated_eagerly_at_parse_time(self):
        """A typo must surface when the vault loads, not on the morning the
        chart is first read — same contract as parse_expression."""
        with pytest.raises(StageSyntaxError):
            clause("stage 2 when close > smaa(150)")

    def test_expression_must_be_a_condition_not_a_number(self):
        with pytest.raises(StageSyntaxError):
            clause("stage 2 when sma(150)")


class TestFirstMatchWins:

    def test_earlier_clause_beats_a_later_one_that_also_matches(self):
        facts = MarketFacts("TEST", bars(rising()))
        clauses = [
            clause("stage 4 when close > sma(200)", 1),   # true, and first
            clause("stage 2 when close > sma(200)", 2),   # equally true
        ]
        assert classify(clauses, facts).stage is Stage.DECLINING

    def test_reordering_changes_the_answer(self):
        """Line order is load-bearing. If this ever stops being true the
        block has silently become conjunctive."""
        facts = MarketFacts("TEST", bars(rising()))
        a = clause("stage 4 when close > sma(200)", 1)
        b = clause("stage 2 when close > sma(200)", 2)
        assert classify([a, b], facts).stage is Stage.DECLINING
        assert classify([b, a], facts).stage is Stage.ADVANCING

    def test_falls_through_to_the_default(self):
        facts = MarketFacts("TEST", bars(rising()))
        clauses = [clause("stage 4 when close < sma(200)", 1), clause("stage 1", 2)]
        result = classify(clauses, facts)
        assert result.stage is Stage.BASING
        assert "default" in result.reason

    def test_no_default_and_no_match_is_unclassified(self):
        facts = MarketFacts("TEST", bars(rising()))
        result = classify([clause("stage 4 when close < sma(200)")], facts)
        assert result.stage is None
        assert not result.is_classified
        assert "no terminal default" in result.reason

    def test_empty_block_is_unclassified(self):
        facts = MarketFacts("TEST", bars(rising()))
        assert classify([], facts).stage is None


class TestUnevaluableStops:
    """The load-bearing safety property of this module."""

    def test_unevaluable_clause_does_not_fall_through(self):
        """40 bars cannot warm up sma(150). The honest answer is 'unknown',
        NOT the next clause's stage — a warm-up failure must never be able to
        promote a name into Stage 2."""
        facts = MarketFacts("TEST", bars(rising(n=40)))
        clauses = [
            clause("stage 4 when sma(150) < sma(150)[25]", 1),   # unevaluable
            clause("stage 2 when close > sma(20)", 2),           # would match
        ]
        result = classify(clauses, facts)
        assert result.stage is None
        assert "could not be evaluated" in result.reason

    def test_unevaluable_clause_does_not_reach_the_default_either(self):
        facts = MarketFacts("TEST", bars(rising(n=40)))
        clauses = [
            clause("stage 4 when sma(150) < sma(150)[25]", 1),
            clause("stage 1", 2),
        ]
        assert classify(clauses, facts).stage is None

    def test_missing_history_is_unclassified_not_stage_one(self):
        facts = MarketFacts("TEST", bars(rising(n=10)))
        result = classify([clause("stage 2 when close > sma(150)", 1),
                           clause("stage 1", 2)], facts)
        assert result.stage is not Stage.BASING
        assert result.stage is None

    def test_reason_names_the_clause_and_the_missing_term(self):
        facts = MarketFacts("TEST", bars(rising(n=40)))
        result = classify([clause("stage 4 when sma(150) < sma(150)[25]", 7)], facts)
        assert "line 7" in result.reason
        assert "sma(150)" in result.reason


class TestValidation:

    def test_default_before_the_end_is_flagged(self):
        problems = validate_clauses([
            clause("stage 1", 1),
            clause("stage 2 when close > sma(150)", 2),
        ])
        assert any("can never be reached" in p for p in problems)

    def test_missing_terminal_default_is_flagged(self):
        problems = validate_clauses([clause("stage 2 when close > sma(150)", 1)])
        assert any("no terminal default" in p for p in problems)

    def test_well_formed_block_is_clean(self):
        assert validate_clauses([
            clause("stage 4 when close < sma(150)", 1),
            clause("stage 1", 2),
        ]) == []


class TestTimeline:

    def test_timeline_is_oldest_first_and_ends_at_the_latest_bar(self):
        facts = MarketFacts("TEST", bars(rising()))
        clauses = [clause("stage 2 when close > sma(200)", 1), clause("stage 1", 2)]
        timeline = stage_timeline(clauses, facts, bars=30)
        assert len(timeline) == 30
        assert [offset for offset, _ in timeline] == list(range(29, -1, -1))
        assert timeline[-1][0] == 0

    def test_unclassified_bars_are_kept_not_dropped(self):
        """Dropping them would make a chart look like the stock did not exist
        during its own warm-up."""
        facts = MarketFacts("TEST", bars(rising(n=200)))
        clauses = [clause("stage 3 when sma(150)[25] > sma(150)[125]", 1),
                   clause("stage 1", 2)]
        timeline = stage_timeline(clauses, facts, bars=200)
        assert len(timeline) == 200
        assert any(r.stage is None for _, r in timeline)

    def test_transitions_report_only_stage_changes(self):
        facts = MarketFacts("TEST", bars(rising()))
        clauses = [clause("stage 2 when close > sma(200)", 1), clause("stage 1", 2)]
        timeline = stage_timeline(clauses, facts, bars=50)
        # A pure uptrend never leaves Stage 2 inside the window.
        assert stage_transitions(timeline) == []

    def test_transitions_ignore_phase_changes(self):
        """`2 · pivot` -> `2 · advancing` is not a transition. Reporting it
        would bury the four real ones."""
        closes = rising()
        volumes = [100_000] * 380 + [10_000] * 20     # volume dries up at the end
        facts = MarketFacts("TEST", bars(closes, volumes))
        clauses = [
            clause("stage 2 pivot when close > sma(200) and volume_sma(5) / volume_sma(50) < 0.40", 1),
            clause("stage 2 when close > sma(200)", 2),
            clause("stage 1", 3),
        ]
        timeline = stage_timeline(clauses, facts, bars=40)
        phases = {r.phase for _, r in timeline}
        assert phases == {"", "pivot"}            # the phase really did change
        assert stage_transitions(timeline) == []  # the stage did not

    def test_bars_in_stage_counts_the_current_run(self):
        facts = MarketFacts("TEST", bars(rising()))
        clauses = [clause("stage 2 when close > sma(200)", 1), clause("stage 1", 2)]
        timeline = stage_timeline(clauses, facts, bars=25)
        assert bars_in_stage(timeline) == 25

    def test_bars_in_stage_is_none_when_unclassified(self):
        """'0 bars in no stage' would read as a fresh transition."""
        facts = MarketFacts("TEST", bars(rising(n=40)))
        clauses = [clause("stage 2 when sma(150) > sma(150)[25]", 1)]
        assert bars_in_stage(stage_timeline(clauses, facts, bars=5)) is None


class TestTheRealNote:
    """The shipped block in Stan_Weinstein_Stage_Analysis.md, against series
    whose stage is unambiguous by construction."""

    @pytest.fixture(scope="class")
    def clauses(self):
        note = parse_note(WEINSTEIN_NOTE)
        assert note.stage_clauses, "the note lost its ```quantos-stages``` block"
        return note.stage_clauses

    def test_block_is_structurally_valid(self, clauses):
        assert validate_clauses(clauses) == []

    def test_sustained_uptrend_is_stage_2(self, clauses):
        result = classify(clauses, MarketFacts("UP", bars(rising())))
        assert result.stage is Stage.ADVANCING

    def test_sustained_downtrend_is_stage_4(self, clauses):
        result = classify(clauses, MarketFacts("DOWN", bars(falling())))
        assert result.stage is Stage.DECLINING

    def test_rally_into_a_falling_average_is_still_stage_4(self, clauses):
        """The clause order's whole purpose: price back above a falling
        30-week is a Stage 4 bounce, not a Stage 2."""
        decline = falling(n=380)
        closes = decline + [decline[-1] * 1.02 ** i for i in range(1, 21)]
        facts = MarketFacts("BOUNCE", bars(closes))
        assert facts.close(0) > facts.sma(150)              # price IS above it
        assert facts.sma(150) < facts.sma(150, 25)          # but it is falling
        assert classify(clauses, facts).stage is Stage.DECLINING

    def test_flat_after_a_decline_is_stage_1(self, clauses):
        closes = falling(n=250) + flat(n=150, start=falling(n=250)[-1])
        assert classify(clauses, MarketFacts("BASE", bars(closes))).stage is Stage.BASING

    def test_flat_after_an_advance_is_stage_3(self, clauses):
        """The path-dependent case — identical present, opposite past."""
        closes = rising(n=250) + flat(n=150, start=rising(n=250)[-1])
        assert classify(clauses, MarketFacts("TOP", bars(closes))).stage is Stage.TOPPING

    def test_stage_1_and_stage_3_are_told_apart_only_by_history(self, clauses):
        """Same flat tail, opposite prefixes, different answers. If these ever
        agree, the prior-trend lag has stopped reaching far enough back."""
        tail = flat(n=150, start=100.0)
        # Both prefixes END at ~100 so the flat tail is identical in level as
        # well as shape; only the direction of travel into it differs.
        down = [100.0 * math.exp((250 - i) * 0.004) for i in range(250)]
        up = [100.0 * math.exp(-(250 - i) * 0.004) for i in range(250)]
        base = classify(clauses, MarketFacts("A", bars(down + tail)))
        top = classify(clauses, MarketFacts("B", bars(up + tail)))
        assert base.stage is Stage.BASING
        assert top.stage is Stage.TOPPING

    def test_trending_names_classify_before_the_deep_lag_is_needed(self, clauses):
        """First-match-wins short-circuits. A clearly rising name matches the
        Stage 2 clause, which needs only sma(150)[25] = 175 bars, and never
        reaches the Stage 3 clause that needs 250. So the block's history
        requirement is not flat — it is 175 for trending names and 250 only
        for the flat-band ones."""
        result = classify(clauses, MarketFacts("SHORT", bars(rising(n=200))))
        assert result.stage is Stage.ADVANCING

    def test_flat_names_do_need_the_deeper_lag(self, clauses):
        """The flat band is where the prior-trend lag actually binds — and
        the answer there must be unclassified, never the Stage 1 default."""
        result = classify(clauses, MarketFacts("FLAT", bars(flat(n=200))))
        assert result.stage is None
        assert "could not be evaluated" in result.reason

    def test_too_short_for_any_clause_is_unclassified(self, clauses):
        result = classify(clauses, MarketFacts("TINY", bars(rising(n=60))))
        assert result.stage is None
        assert "could not be evaluated" in result.reason

    def test_volume_dry_up_inside_an_uptrend_is_the_pivot_phase(self, clauses):
        closes = rising()
        volumes = [100_000] * 380 + [10_000] * 20
        result = classify(clauses, MarketFacts("PIVOT", bars(closes, volumes)))
        assert result.stage is Stage.ADVANCING
        assert result.phase == "pivot"
        assert result.display == "Stage 2 · pivot"

    def test_reason_carries_the_live_numbers(self, clauses):
        result = classify(clauses, MarketFacts("UP", bars(rising())))
        assert "sma(150)" in result.reason and "=" in result.reason


class TestFitsTheLiveFetchWindow:
    """Regression guard for the bug the first calibration run found.

    The Stage 3 clause originally used `sma(150)[125]`, needing 275 warmed-up
    bars. The live fetch (FETCH_WINDOW_DAYS = 400 calendar days) returns 271.
    So no symbol on the exchange could satisfy it, every flat-band name came
    back unclassified, and Stages 1 and 3 were empty at all nine band widths.

    Every test above missed it because their series are 400 bars long. These
    use the number the market actually supplies. If a future edit lengthens a
    lag past the fetch window, this is what should fail — not a chart quietly
    reporting that nothing is basing.
    """

    # Measured across the Nifty 500 on 2026-08-17: median 271, max 271,
    # min 255. The minimum is the number to design against, not the median.
    LIVE_BARS = 271
    SHORTEST_OBSERVED = 255

    @pytest.fixture(scope="class")
    def clauses(self):
        return parse_note(WEINSTEIN_NOTE).stage_clauses

    @pytest.mark.parametrize("shape", ["rising", "falling", "flat"])
    def test_every_shape_classifies_on_a_live_sized_history(self, clauses, shape):
        series = {"rising": rising, "falling": falling, "flat": flat}[shape]
        result = classify(clauses, MarketFacts("LIVE", bars(series(n=self.LIVE_BARS))))
        assert result.is_classified, (
            f"a {shape} name is unclassifiable on {self.LIVE_BARS} bars, which is "
            f"what the live fetch returns — a clause's lag now exceeds the window"
        )

    @pytest.mark.parametrize("shape", ["rising", "falling", "flat"])
    def test_every_shape_classifies_on_the_shortest_observed_history(self, clauses, shape):
        series = {"rising": rising, "falling": falling, "flat": flat}[shape]
        result = classify(clauses, MarketFacts("MIN", bars(series(n=self.SHORTEST_OBSERVED))))
        assert result.is_classified

    def test_flat_band_reaches_stage_1_and_3_not_unclassified(self, clauses):
        """The precise symptom: a flat series must land in a stage, because
        this is the only path to Stages 1 and 3 existing at all."""
        down = [100.0 * math.exp((120 - i) * 0.004) for i in range(120)]
        up = [100.0 * math.exp(-(120 - i) * 0.004) for i in range(120)]
        tail = flat(n=151, start=100.0)
        base = classify(clauses, MarketFacts("BASE", bars(down + tail)))
        top = classify(clauses, MarketFacts("TOP", bars(up + tail)))
        assert base.stage is Stage.BASING
        assert top.stage is Stage.TOPPING

    def test_deepest_lag_in_the_note_fits_the_window(self, clauses):
        """Reads the requirement out of the shipped clauses rather than
        hardcoding it, so it keeps working if the block is rewritten."""
        deepest = 0
        for clause in clauses:
            for period, lag in re.findall(r"sma\((\d+)\)\[(\d+)\]", clause.expression or ""):
                deepest = max(deepest, int(period) + int(lag))
            for period in re.findall(r"sma\((\d+)\)(?!\[)", clause.expression or ""):
                deepest = max(deepest, int(period))
        assert 0 < deepest <= self.SHORTEST_OBSERVED, (
            f"the note's deepest clause needs {deepest} bars; the shortest live "
            f"history observed is {self.SHORTEST_OBSERVED}"
        )


class TestSeparationFromTheGate:
    """A stage must never become a permission."""

    def test_stage_is_not_a_verdict(self):
        from core.vault.models import Verdict
        assert not isinstance(Stage.ADVANCING, Verdict)
        assert not hasattr(Stage.ADVANCING, "is_clear_to_proceed")

    def test_gates_module_does_not_read_stages(self):
        """A grep-level guard. If a gate ever starts branching on a stage,
        the fail-closed argument in core/vault/models.py no longer holds and
        this test should be the thing that says so."""
        source = Path("core/vault/gates.py").read_text(encoding="utf-8")
        assert "stage" not in source.lower().replace("stage_", "")
