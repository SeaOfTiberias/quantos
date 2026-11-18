"""Suite-wide test settings."""

import os

# Importing cloud/api/main.py builds the event filter; keep it off NSE's results feed
# (core/events/service.EventFilterService.from_env).
os.environ.setdefault("QUANTOS_EVENTS_FEED", "off")


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _maps_in_tmp(tmp_path, monkeypatch):
    """map_read reads the L1 store and the index bars: never the machine's real ones in a test."""
    import core.market_map.read as mr
    monkeypatch.setattr(mr, "L1_ROOT", tmp_path / "l1_store")
    monkeypatch.setattr(mr, "INDEX_ROOT", tmp_path / "index_bars")
