"""
agent/main.py — S8-3 weekly rotation scheduling gate. Mirrors the existing
Stage-A discovery marker-file pattern (_should_run_discovery_today /
_mark_discovery_ran_today) but keyed on ISO calendar week instead of ISO
date, since the agent restarts at most daily and a weekly rebalance must
survive those restarts without re-firing every day.
"""

from datetime import date
from unittest.mock import patch

import pytest

import agent.main as main


@pytest.fixture(autouse=True)
def _isolated_rotation_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "LAST_ROTATION_PATH", tmp_path / "last_rotation_run.txt")


class TestIsoWeekMarker:

    def test_format_is_year_dash_w_two_digit_week(self):
        # 2026-07-20 falls in real ISO week 30 — a genuine date.today()
        # return value already has a working isocalendar(), no need to
        # stub the method itself.
        with patch("agent.main.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 20)
            assert main._iso_week_marker() == "2026-W30"


class TestShouldRunRotationThisWeek:

    def test_true_when_no_marker_file_exists(self):
        assert main._should_run_rotation_this_week() is True

    def test_false_after_marking_ran_this_week(self):
        main._mark_rotation_ran_this_week()
        assert main._should_run_rotation_this_week() is False

    def test_true_again_once_marker_is_a_different_week(self):
        main.LAST_ROTATION_PATH.parent.mkdir(parents=True, exist_ok=True)
        main.LAST_ROTATION_PATH.write_text("2020-W01")
        assert main._should_run_rotation_this_week() is True

    def test_true_on_unreadable_marker_file(self, monkeypatch):
        main.LAST_ROTATION_PATH.parent.mkdir(parents=True, exist_ok=True)
        main.LAST_ROTATION_PATH.write_text("2020-W01")

        real_read_text = type(main.LAST_ROTATION_PATH).read_text

        def _boom(self, *a, **kw):
            if self == main.LAST_ROTATION_PATH:
                raise OSError("disk gremlin")
            return real_read_text(self, *a, **kw)

        monkeypatch.setattr(type(main.LAST_ROTATION_PATH), "read_text", _boom)
        assert main._should_run_rotation_this_week() is True


class TestMarkRotationRanThisWeek:

    def test_creates_parent_dir_and_writes_current_week(self):
        main._mark_rotation_ran_this_week()
        assert main.LAST_ROTATION_PATH.exists()
        assert main.LAST_ROTATION_PATH.read_text() == main._iso_week_marker()
