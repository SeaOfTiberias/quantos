"""
pine/weinstein_stage_journey.pine must agree with core/vault/stages.py.

The Pine indicator is a hand transcription of the ```quantos-stages``` block
in Stan_Weinstein_Stage_Analysis.md. Nothing forces two implementations of
one idea to stay together except a test, and this repo has the scar to prove
it: darvasBox() in pine/darvas_breakout_alert.pine reset boxReady before
testing for a breakout, suppressing nearly every real signal for months while
the Python engine it mirrored was fine. It took a three-year Strategy Tester
run returning zero entries to surface it.

scripts/crosscheck_stage_pine.py can be pointed at real bars on the VM. This
runs the same comparison over synthetic series in the unit suite, so drift is
caught on the commit that introduces it rather than whenever someone next
remembers to run a script.
"""

import pytest

from core.vault.parser import parse_note
from scripts.crosscheck_stage_pine import (
    NOTE_PATH,
    assert_pine_matches_note,
    compare,
    pine_defaults,
    synthetic_series,
)

WINDOW = 120


@pytest.fixture(scope="module")
def defaults():
    return pine_defaults()


@pytest.fixture(scope="module")
def clauses():
    parsed = parse_note(NOTE_PATH).stage_clauses
    assert parsed, "the note lost its ```quantos-stages``` block"
    return parsed


@pytest.fixture(scope="module")
def series():
    return synthetic_series()


def test_pine_input_defaults_match_the_notes_constants(defaults):
    """A mirror that agrees on logic but not on numbers still shows two
    different charts. Raises SystemExit on mismatch."""
    assert_pine_matches_note(defaults)


@pytest.mark.parametrize("shape", [
    "UPTREND", "DOWNTREND", "CHOPPY", "TOPPING", "BASING", "DEADCAT",
    "PIVOT", "SHORT", "TOOSHORT",
])
def test_pine_and_python_agree(shape, series, clauses, defaults):
    mismatches = compare(shape, series[shape], clauses, defaults, window=WINDOW)
    assert mismatches == [], (
        f"{shape}: the .pine and core/vault/stages.py disagree on "
        f"{len(mismatches)} of {WINDOW} bars — first: {mismatches[0]}"
    )


class TestTheCheckHasTeeth:
    """A cross-check that cannot fail is worse than none: it certifies
    agreement it never tested for. Each parameter is deliberately drifted and
    the comparison must notice."""

    @pytest.mark.parametrize("field,drifted", [
        ("band", 0.02),           # 1% -> 2% flat band
        ("slope_lag", 30),        # sma(150)[25] -> [30]
        ("prior_lag", 125),       # the exact bug the live calibration found
        ("dry_up_ratio", 0.90),   # phase boundary moved
    ])
    def test_injected_drift_is_detected(self, field, drifted, series, clauses, defaults):
        bad = dict(defaults)
        bad[field] = drifted
        total = sum(len(compare(name, candles, clauses, bad, window=WINDOW))
                    for name, candles in series.items())
        assert total > 0, (
            f"drifting {field} to {drifted} produced no mismatch — the "
            f"cross-check is not actually comparing this parameter"
        )
