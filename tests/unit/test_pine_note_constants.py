"""
The Pine indicator's constants must match the notes it transcribes.

`scripts/crosscheck_stage_pine.py` has checked this since the stage chart
shipped, but only when somebody remembered to run it. That is the same shape
as the falsification bar being a helper eight of nineteen scripts happen to
call — a convention rather than a gate. These tests make it a gate.

The cost of getting it wrong is documented rather than theoretical. The
Minervini note's distance-from-lows threshold read 2.00 until 2026-08-14,
demanding a stock had already doubled off its 52-week low, which rejected
names in exactly the condition the rest of the checklist selects for. RADICO
passed every other price rule and failed on that line alone. Nothing about the
output looked broken — that is precisely why a constant is the cheapest bug to
catch automatically and the most expensive to leave to attention.

These do not test the CHART. Only the constants, and only that the two written
sources agree. Logic parity on real bars is what the cross-check script itself
is for, and TradingView will not hand a script its series over an API, so
neither can verify the rendered result.
"""

from pathlib import Path

import pytest

from scripts.crosscheck_stage_pine import (
    assert_pine_matches_note,
    assert_pine_matches_sepa_note,
    pine_defaults,
)


@pytest.fixture(scope="module")
def defaults():
    return pine_defaults()


def test_every_expected_constant_is_readable_from_the_pine(defaults):
    """A renamed input silently drops out of the check otherwise: the regex
    stops matching, and a mirror that no longer looks at anything passes."""
    for key in ("band", "slope_lag", "prior_lag", "dry_up_ratio",
                "sepa_near_high", "sepa_off_low", "sepa_ma_slope_lag",
                "sepa_rs_min"):
        assert key in defaults, f"{key} could not be read out of the .pine"


def test_pine_matches_the_weinstein_note(defaults):
    assert_pine_matches_note(defaults)


def test_pine_matches_the_minervini_note(defaults):
    assert_pine_matches_sepa_note(defaults)


def test_the_published_sepa_criteria_are_what_shipped(defaults):
    """Pinned deliberately, unlike the calibrated stage-band numbers.

    These are Minervini's published thresholds, not parameters tuned against
    this universe. A change here is a change of template and should have to
    break a test that says so out loud.
    """
    assert defaults["sepa_near_high"] == 0.75, "within 25% of the 52-week high"
    assert defaults["sepa_off_low"] == 1.25, (
        "at least 25% above the 52-week low — 2.00 was the 2026-08-14 bug"
    )
    assert defaults["sepa_ma_slope_lag"] == 20
    assert defaults["sepa_rs_min"] == 70.0


def test_the_dry_up_ratio_is_one_number_shared_by_both_notes(defaults):
    """The Pine holds a single `dryUpRatio` input serving both the stage
    classifier's pivot phase and SEPA's sixth rule, because both notes write
    the identical expression. If the notes ever diverge, one input cannot
    mirror both — assert_pine_matches_sepa_note is what surfaces that, and
    this test records why a single input is correct today."""
    assert defaults["dry_up_ratio"] == 0.40
    assert_pine_matches_note(defaults)
    assert_pine_matches_sepa_note(defaults)


def test_a_wrong_constant_actually_fails(defaults):
    """Guards the guard. A check that cannot fail is worse than none, because
    it reads as coverage. Reintroduces the exact historical bug."""
    broken = dict(defaults)
    broken["sepa_off_low"] = 2.00
    with pytest.raises(SystemExit, match="off-52w-low mismatch"):
        assert_pine_matches_sepa_note(broken)


# ── Pine syntax the notes cannot catch ──────────────────────────────────────

PINE_DIR = Path("pine")


def _illegal_continuation_indents(path: Path) -> list[tuple[int, int, str]]:
    """Wrapped lines indented by a multiple of four.

    Pine uses four-space multiples to denote local blocks, so a continuation
    line indented that way is read as the start of a block instead and the
    compiler reports "end of line without line continuation" against the line
    ABOVE — which is why this is easy to misdiagnose by eye.

    Paren depth is tracked crudely (string-aware, comment-stripped), which is
    enough for these files and keeps the check dependency-free.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    depth, bad = 0, []
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if depth > 0 and stripped and not stripped.startswith("//"):
            indent = len(line) - len(line.lstrip(" "))
            if indent > 0 and indent % 4 == 0:
                bad.append((number, indent, stripped[:60]))
        code = "" if stripped.startswith("//") else line.split("//")[0]
        in_string = False
        for ch in code:
            if ch == '"':
                in_string = not in_string
            elif not in_string:
                if ch in "([":
                    depth += 1
                elif ch in ")]":
                    depth -= 1
        depth = max(depth, 0)
    return bad


@pytest.mark.parametrize(
    "pine_file",
    sorted(PINE_DIR.glob("*.pine")),
    ids=lambda p: p.name,
)
def test_no_continuation_line_is_indented_by_a_multiple_of_four(pine_file):
    """Caught a real compile failure on 2026-08-19.

    The four SEPA tooltip continuations were indented 28 spaces to align under
    `input.float(`, which reads beautifully and does not compile. TradingView
    reported `Syntax error at input 'end of line without line continuation'`
    at line 91 — the line *before* the offending one.

    Nothing local can compile Pine, so every check that removes a round-trip
    to the TradingView editor is worth having. This is the cheapest one.
    """
    offenders = _illegal_continuation_indents(pine_file)
    assert not offenders, "\n".join(
        f"{pine_file}:{n} indented {i} spaces (a multiple of 4) — use 4n±1: {t}"
        for n, i, t in offenders
    )
