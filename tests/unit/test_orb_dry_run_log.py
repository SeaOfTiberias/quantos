"""
Tests for core/orb_scalping/dry_run_log.py -- the append-only record of
what a dry-run ORB close WOULD have done, since neither live variant
places a real order to leave a natural record of its own.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.orb_scalping.dry_run_log import (  # noqa: E402
    DryRunTrade,
    append_dry_run_trade,
    load_dry_run_trades,
)


def _trade(**overrides) -> DryRunTrade:
    fields = dict(
        underlying="NIFTY", direction="CALL",
        entry_timestamp="2026-09-22T04:10:00+00:00", entry_premium=120.5,
        exit_timestamp="2026-09-22T09:50:00+00:00", exit_reason="session_flatten",
        quantity=65, exit_premium=110.0,
    )
    fields.update(overrides)
    return DryRunTrade(**fields)


def test_append_then_load_round_trips(tmp_path):
    path = tmp_path / "orb_dry_run_trades.jsonl"
    append_dry_run_trade(_trade(), path=path)
    loaded = load_dry_run_trades(path=path)
    assert len(loaded) == 1
    assert loaded[0] == _trade()


def test_append_is_additive_across_multiple_trades(tmp_path):
    path = tmp_path / "orb_dry_run_trades.jsonl"
    append_dry_run_trade(_trade(underlying="NIFTY"), path=path)
    append_dry_run_trade(_trade(underlying="BANKNIFTY"), path=path)
    loaded = load_dry_run_trades(path=path)
    assert [t.underlying for t in loaded] == ["NIFTY", "BANKNIFTY"]


def test_exit_premium_none_is_preserved_not_guessed(tmp_path):
    path = tmp_path / "orb_dry_run_trades.jsonl"
    append_dry_run_trade(_trade(exit_premium=None), path=path)
    loaded = load_dry_run_trades(path=path)
    assert loaded[0].exit_premium is None


def test_load_returns_empty_list_when_file_missing(tmp_path):
    assert load_dry_run_trades(path=tmp_path / "does_not_exist.jsonl") == []


def test_load_skips_a_malformed_line_without_losing_the_rest(tmp_path):
    path = tmp_path / "orb_dry_run_trades.jsonl"
    append_dry_run_trade(_trade(underlying="NIFTY"), path=path)
    with path.open("a", encoding="utf-8") as f:
        f.write("not valid json\n")
    append_dry_run_trade(_trade(underlying="BANKNIFTY"), path=path)

    loaded = load_dry_run_trades(path=path)
    assert [t.underlying for t in loaded] == ["NIFTY", "BANKNIFTY"]


def test_default_and_filtered_paths_are_distinct_constants():
    from core.orb_scalping.dry_run_log import ORB_DRY_RUN_LOG_FILTERED_PATH, ORB_DRY_RUN_LOG_PATH
    assert ORB_DRY_RUN_LOG_PATH != ORB_DRY_RUN_LOG_FILTERED_PATH
