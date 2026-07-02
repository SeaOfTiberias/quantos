"""
US-09 GitHub Strategy Versioning — Unit Tests
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from core.versioning.models import BacktestDelta, StrategyVersion, StrategyRegistry
from core.versioning.service import (
    StrategyVersioningService, _diff_params, _next_version,
)


class TestBacktestDelta:

    def test_sharpe_change_computed(self):
        delta = BacktestDelta(sharpe_before=1.2, sharpe_after=1.5)
        assert delta.sharpe_change == pytest.approx(0.3)

    def test_win_rate_change_computed(self):
        delta = BacktestDelta(win_rate_before=0.55, win_rate_after=0.60)
        assert delta.win_rate_change == pytest.approx(0.05)

    def test_is_improvement_true_when_sharpe_increases(self):
        delta = BacktestDelta(sharpe_before=1.0, sharpe_after=1.3)
        assert delta.is_improvement is True

    def test_is_improvement_false_when_sharpe_decreases(self):
        delta = BacktestDelta(sharpe_before=1.3, sharpe_after=1.0)
        assert delta.is_improvement is False

    def test_is_improvement_none_without_data(self):
        delta = BacktestDelta()
        assert delta.is_improvement is None

    def test_to_dict_structure(self):
        delta = BacktestDelta(sharpe_before=1.0, sharpe_after=1.2)
        d = delta.to_dict()
        assert "sharpe" in d
        assert d["sharpe"]["delta"] == pytest.approx(0.2)


class TestStrategyRegistry:

    def test_register_and_get_current(self):
        reg = StrategyRegistry()
        params = {"lookback": 20, "min_consolidation": 3}
        reg.register("darvas_breakout", params)
        assert reg.get_current("darvas_breakout") == params

    def test_get_current_unknown_returns_none(self):
        reg = StrategyRegistry()
        assert reg.get_current("unknown") is None

    def test_get_history_empty_initially(self):
        reg = StrategyRegistry()
        reg.register("darvas_breakout", {})
        assert reg.get_history("darvas_breakout") == []

    def test_add_version_updates_current(self):
        reg = StrategyRegistry()
        reg.register("darvas_breakout", {"lookback": 20})
        version = StrategyVersion(
            strategy_name="darvas_breakout", version="1.1.0",
            parameters={"lookback": 25}, changed_params=["lookback"],
            author="system", commit_message="Update lookback", rationale="test",
            timestamp=datetime.now(timezone.utc),
        )
        reg.add_version(version)
        assert reg.get_current("darvas_breakout") == {"lookback": 25}
        assert len(reg.get_history("darvas_breakout")) == 1


class TestDiffParams:

    def test_detects_changed_value(self):
        old = {"lookback": 20, "min_vol": 1.3}
        new = {"lookback": 25, "min_vol": 1.3}
        assert _diff_params(old, new) == ["lookback"]

    def test_detects_added_key(self):
        old = {"lookback": 20}
        new = {"lookback": 20, "new_param": 5}
        assert "new_param" in _diff_params(old, new)

    def test_detects_removed_key(self):
        old = {"lookback": 20, "old_param": 5}
        new = {"lookback": 20}
        assert "old_param" in _diff_params(old, new)

    def test_no_diff_returns_empty(self):
        params = {"lookback": 20, "min_vol": 1.3}
        assert _diff_params(params, params) == []

    def test_empty_dicts_no_diff(self):
        assert _diff_params({}, {}) == []

    def test_from_empty_to_params(self):
        new = {"lookback": 20}
        assert "lookback" in _diff_params({}, new)


class TestNextVersion:

    def test_first_version(self):
        assert _next_version([]) == "1.0.0"

    def test_increments_minor(self):
        v = StrategyVersion(
            strategy_name="x", version="1.0.0", parameters={},
            changed_params=[], author="system", commit_message="test",
            rationale="", timestamp=datetime.now(timezone.utc),
        )
        assert _next_version([v]) == "1.1.0"

    def test_multiple_increments(self):
        versions = []
        for i in range(3):
            versions.append(StrategyVersion(
                strategy_name="x", version=f"1.{i}.0", parameters={},
                changed_params=[], author="system", commit_message="test",
                rationale="", timestamp=datetime.now(timezone.utc),
            ))
        assert _next_version(versions) == "1.3.0"

    def test_invalid_version_resets(self):
        v = StrategyVersion(
            strategy_name="x", version="invalid", parameters={},
            changed_params=[], author="system", commit_message="test",
            rationale="", timestamp=datetime.now(timezone.utc),
        )
        assert _next_version([v]) == "1.0.0"


class TestStrategyVersioningService:

    @pytest.mark.asyncio
    async def test_first_update_creates_version_1_0_0(self):
        service = StrategyVersioningService()

        with patch("core.versioning.service._generate_commit_message",
                   new_callable=AsyncMock, return_value="Initial Darvas parameters"):
            v = await service.update_strategy(
                "darvas_breakout", {"lookback": 20}, push_to_github=False,
            )

        assert v.version == "1.0.0"
        assert v.strategy_name == "darvas_breakout"

    @pytest.mark.asyncio
    async def test_second_update_increments_version(self):
        service = StrategyVersioningService()

        with patch("core.versioning.service._generate_commit_message",
                   new_callable=AsyncMock, return_value="test"):
            await service.update_strategy(
                "darvas_breakout", {"lookback": 20}, push_to_github=False,
            )
            v2 = await service.update_strategy(
                "darvas_breakout", {"lookback": 25}, push_to_github=False,
            )

        assert v2.version == "1.1.0"
        assert "lookback" in v2.changed_params

    @pytest.mark.asyncio
    async def test_no_change_returns_last_version(self):
        service = StrategyVersioningService()
        params = {"lookback": 20}

        with patch("core.versioning.service._generate_commit_message",
                   new_callable=AsyncMock, return_value="test"):
            v1 = await service.update_strategy("darvas_breakout", params, push_to_github=False)
            v2 = await service.update_strategy("darvas_breakout", params, push_to_github=False)

        assert v1.version == v2.version   # no new version created

    @pytest.mark.asyncio
    async def test_backtest_delta_attached(self):
        service = StrategyVersioningService()
        delta = BacktestDelta(sharpe_before=1.0, sharpe_after=1.3)

        with patch("core.versioning.service._generate_commit_message",
                   new_callable=AsyncMock, return_value="Improve Sharpe"):
            v = await service.update_strategy(
                "darvas_breakout", {"lookback": 25},
                backtest_delta=delta, push_to_github=False,
            )

        assert v.backtest_delta is not None
        assert v.backtest_delta.sharpe_change == pytest.approx(0.3)

    @pytest.mark.asyncio
    async def test_commit_message_uses_claude(self):
        service = StrategyVersioningService()

        with patch("core.versioning.service._generate_commit_message",
                   new_callable=AsyncMock, return_value="feat(darvas): increase lookback from 20 to 25") as mock_gen:
            v = await service.update_strategy(
                "darvas_breakout", {"lookback": 25}, push_to_github=False,
            )

        mock_gen.assert_called_once()
        assert "lookback" in v.commit_message or "darvas" in v.commit_message

    @pytest.mark.asyncio
    async def test_get_history_returns_all_versions(self):
        service = StrategyVersioningService()

        with patch("core.versioning.service._generate_commit_message",
                   new_callable=AsyncMock, return_value="test"):
            await service.update_strategy("darvas_breakout", {"lookback": 20}, push_to_github=False)
            await service.update_strategy("darvas_breakout", {"lookback": 25}, push_to_github=False)

        history = service.get_history("darvas_breakout")
        assert len(history) == 2

    def test_weekly_changelog_empty(self):
        service = StrategyVersioningService()
        changelog = service.weekly_changelog()
        assert "No strategy changes" in changelog

    @pytest.mark.asyncio
    async def test_weekly_changelog_with_changes(self):
        service = StrategyVersioningService()

        with patch("core.versioning.service._generate_commit_message",
                   new_callable=AsyncMock, return_value="Update lookback period"):
            await service.update_strategy("darvas_breakout", {"lookback": 25}, push_to_github=False)

        changelog = service.weekly_changelog()
        assert "darvas_breakout" in changelog
        assert "Update lookback period" in changelog
