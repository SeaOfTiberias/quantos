"""
core/vault/rules.py — the rule DSL.

Two things are being protected here. First, that the grammar computes what a
strategy note says it computes. Second, and more important, that anything it
CANNOT compute becomes `passed=None` rather than a truthy accident — the
whole fail-closed contract in core/vault/models.py rests on this module never
returning True when it does not know.
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from core.brokers.base import OHLCV
from core.vault.facts import MarketFacts
from core.vault.models import Rule
from core.vault.rules import RuleSyntaxError, evaluate_rule, parse_expression

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def bars(closes, volumes=None, highs=None, lows=None):
    volumes = volumes or [100_000] * len(closes)
    highs = highs or [c * 1.01 for c in closes]
    lows = lows or [c * 0.99 for c in closes]
    return [
        OHLCV(timestamp=_BASE + timedelta(days=i), open=c, high=h, low=lo, close=c, volume=v)
        for i, (c, v, h, lo) in enumerate(zip(closes, volumes, highs, lows))
    ]


def rising(n=400, rate=0.004, start=100.0):
    return [start * math.exp(i * rate) for i in range(n)]


def rule(expression):
    return Rule(expression=expression, note_name="test", line_number=1)


def check(expression, facts):
    return evaluate_rule(rule(expression), facts)


@pytest.fixture
def uptrend():
    return MarketFacts("TEST", bars(rising()), rs_rating=85.0)


class TestGrammar:

    def test_simple_comparison(self, uptrend):
        assert check("close > sma(50)", uptrend).passed is True

    def test_chained_comparison_reads_like_the_note(self, uptrend):
        """Minervini writes `Close > SMA50 > SMA150 > SMA200` as one line and
        the DSL must accept it that way, not force four separate rules."""
        assert check("close > sma(50) > sma(150) > sma(200)", uptrend).passed is True

    def test_chained_comparison_fails_if_any_link_breaks(self):
        # Flat series: every average collapses onto the same value, so the
        # strict > chain cannot hold.
        facts = MarketFacts("FLAT", bars([100.0] * 400))
        assert check("close > sma(50) > sma(150)", facts).passed is False

    def test_bar_lag_subscript(self, uptrend):
        assert check("sma(200) > sma(200)[20]", uptrend).passed is True

    def test_bar_lag_reversed_is_false_in_an_uptrend(self, uptrend):
        assert check("sma(200) < sma(200)[20]", uptrend).passed is False

    def test_arithmetic(self, uptrend):
        assert check("close >= high(252) * 0.75", uptrend).passed is True

    def test_division(self):
        facts = MarketFacts("V", bars([100.0] * 100, volumes=[10] * 95 + [1] * 5))
        # last 5 bars average 1, the 50-bar average is dominated by 10s
        assert check("volume_sma(5) / volume_sma(50) < 0.40", facts).passed is True

    def test_boolean_or(self, uptrend):
        assert check("close > sma(50) or close < sma(200)", uptrend).passed is True

    def test_unary_minus(self, uptrend):
        assert check("close > -sma(50)", uptrend).passed is True


class TestSubstitutionsAreRecorded:
    """A bare PASS/FAIL is not auditable — the report has to show its work."""

    def test_records_each_term(self, uptrend):
        result = check("close > sma(50)", uptrend)
        assert set(result.substitutions) == {"close", "sma(50)"}
        assert result.substitutions["close"] > result.substitutions["sma(50)"]

    def test_lagged_term_is_labelled_with_its_lag(self, uptrend):
        result = check("sma(200) > sma(200)[20]", uptrend)
        assert "sma(200)" in result.substitutions
        assert "sma(200)[20]" in result.substitutions
        # Two different numbers must not collide under one label.
        assert result.substitutions["sma(200)"] != result.substitutions["sma(200)[20]"]

    def test_detail_renders_values_inline(self, uptrend):
        assert "close=" in check("close > sma(50)", uptrend).detail


class TestInsufficientData:
    """The safety-critical half: unevaluable must never be True."""

    def test_window_longer_than_history_is_unevaluated(self):
        facts = MarketFacts("SHORT", bars(rising(n=30)))
        result = check("close > sma(200)", facts)
        assert result.passed is None
        assert "sma(200)" in result.error

    def test_lag_beyond_history_is_unevaluated(self):
        facts = MarketFacts("SHORT", bars(rising(n=210)))
        assert check("sma(200) > sma(200)[100]", facts).passed is None

    def test_missing_rs_rating_is_unevaluated_not_false(self):
        """The sharp case. rs_rating cannot be derived from one symbol's
        bars, so an audit without one must report that it did not happen —
        not quietly fail the rule, which would read as a market rejection."""
        facts = MarketFacts("TEST", bars(rising()))       # no rs_rating supplied
        result = check("rs_rating >= 70", facts)
        assert result.passed is None
        assert "rs_rating" in result.error

    def test_supplied_rs_rating_evaluates_normally(self):
        facts = MarketFacts("TEST", bars(rising()), rs_rating=85.0)
        assert check("rs_rating >= 70", facts).passed is True

    def test_rs_rating_at_a_lag_is_unevaluated(self):
        """It is a snapshot, not a series. Today's value must not silently
        stand in for a historical one."""
        facts = MarketFacts("TEST", bars(rising()), rs_rating=85.0)
        assert check("rs_rating[10] >= 70", facts).passed is None

    def test_division_by_zero_is_unevaluated_not_a_crash(self):
        facts = MarketFacts("NOVOL", bars([100.0] * 100, volumes=[0] * 100))
        result = check("volume_sma(5) / volume_sma(50) < 0.40", facts)
        assert result.passed is None

    def test_partial_window_refuses_rather_than_understating(self):
        """A '52-week high' from 30 bars is not a 52-week high. Returning the
        partial figure would understate the level every comparison is drawn
        against, which fails a rule in the wrong direction — silently."""
        facts = MarketFacts("SHORT", bars(rising(n=30)))
        assert check("close >= high(252) * 0.75", facts).passed is None


class TestRejectedAtParseTime:
    """The vault is a directory of markdown files that sync and get edited
    casually. Nothing from it reaches an interpreter."""

    @pytest.mark.parametrize("expression", [
        "__import__('os').system('rm -rf /')",
        "open('/etc/passwd').read()",
        "close.__class__",
        "[c for c in range(10)]",
        "lambda: 1",
        "close if close else sma(50)",
    ])
    def test_dangerous_constructs_rejected(self, expression):
        with pytest.raises(RuleSyntaxError):
            parse_expression(expression)

    def test_unknown_name_rejected(self):
        with pytest.raises(RuleSyntaxError, match="unknown term"):
            parse_expression("rsi > 70")

    def test_unknown_function_rejected(self):
        with pytest.raises(RuleSyntaxError, match="unknown function"):
            parse_expression("macd(12) > 0")

    def test_non_comparison_rejected(self):
        """`sma(50)` alone is a half-written rule. Treating its truthiness as
        a verdict would pass for any non-zero average."""
        with pytest.raises(RuleSyntaxError, match="not a comparison"):
            parse_expression("sma(50)")

    def test_string_literal_rejected_at_parse_not_eval(self):
        with pytest.raises(RuleSyntaxError, match="compare numbers only"):
            parse_expression("close > 'sma(50)'")

    def test_non_integer_period_rejected(self):
        with pytest.raises(RuleSyntaxError, match="positive integer"):
            parse_expression("close > sma(50.5)")

    def test_negative_lag_rejected(self):
        with pytest.raises(RuleSyntaxError, match="non-negative"):
            parse_expression("sma(200) > sma(200)[-5]")

    def test_syntax_error_becomes_unevaluated_result_not_an_exception(self):
        """A malformed rule must not take the audit down — it must report as
        unevaluable so the gate blocks with a readable cause."""
        result = check("close > > sma(50)", MarketFacts("T", bars(rising())))
        assert result.passed is None
        assert result.error
