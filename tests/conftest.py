"""Suite-wide test settings."""

import os

# Importing cloud/api/main.py builds the event filter; keep it off NSE's results feed
# (core/events/service.EventFilterService.from_env).
os.environ.setdefault("QUANTOS_EVENTS_FEED", "off")


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _maps_in_tmp(tmp_path, monkeypatch):
    """map_read builds and saves price maps on demand: keep every test's maps out of ~/.quantos."""
    import core.market_map.read as mr
    monkeypatch.setattr(mr, "MAPS_DIR", tmp_path / "price_maps")
