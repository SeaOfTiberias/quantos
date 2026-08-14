"""
Momentum Shortlist Routes — Unit Tests
────────────────────────────────────────
Covers the disk-backed cache added 2026-08-11. The scan behind these
endpoints takes ~11 minutes over ~580 symbols and now runs on the daily
Fyers token refresh (deploy/systemd/quantos-momentum-shortlist.path), so a
restart that silently emptied all three cockpit tabs would leave them blank
until the next morning — and deploying restarts the API by definition.

The cache is explicitly best-effort: every failure path here asserts that a
broken cache degrades to "empty until the next sync" rather than breaking a
sync or a boot.
"""

import json

import pytest
from httpx import AsyncClient, ASGITransport

import cloud.api.auth as auth
import cloud.api.momentum_shortlist_routes as routes
from cloud.api.main import app


@pytest.fixture(autouse=True)
def _isolated_store(monkeypatch, tmp_path):
    """Never touch the developer's real ~/.quantos/shortlist_cache.json."""
    monkeypatch.setattr(routes, "_shortlist_store", {})
    monkeypatch.setattr(routes, "_last_synced_at", {})
    monkeypatch.setenv("QUANTOS_SHORTLIST_CACHE", str(tmp_path / "cache.json"))
    monkeypatch.setattr(auth, "CLOUD_SECRET", "test-secret", raising=False)


def _entry(symbol="TVSMOTOR", rank=1) -> dict:
    return {
        "symbol": symbol,
        "close": 100.0,
        "momentum_pct": 99.8,
        "momentum_rank": rank,
        "momentum_tier": "LEADER",
        "bucket": "LEADER_TIGHT_BASE",
        "base_status": "FRESH BREAKOUT",
        "trend_up": True,
        "box_width_pct": 16.8,
        "dist_to_ceil": -1.5,
        "rr_ratio": 7.2,
        "vol_ratio": 4.81,
    }


async def _sync(universe: str, entries: list[dict]) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/discovery/momentum-shortlist/{universe}",
            json={"entries": entries},
            headers={"X-Cloud-Secret": "test-secret"},
        )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_sync_writes_cache_file(tmp_path):
    await _sync("alpha50", [_entry()])

    cached = json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))
    assert list(cached) == ["alpha50"]
    assert cached["alpha50"]["entries"][0]["symbol"] == "TVSMOTOR"
    assert cached["alpha50"]["updated_at"] is not None


@pytest.mark.asyncio
async def test_load_cache_restores_entries_and_timestamp(tmp_path):
    await _sync("nifty500", [_entry("PIDILITIND")])
    updated_at_before = routes._last_synced_at["nifty500"]

    # Simulate a process restart: drop the in-memory state, re-read the file.
    routes._shortlist_store.clear()
    routes._last_synced_at.clear()
    routes._load_cache()

    assert routes._shortlist_store["nifty500"][0]["symbol"] == "PIDILITIND"
    assert routes._last_synced_at["nifty500"] == updated_at_before


@pytest.mark.asyncio
async def test_each_universe_survives_independently(tmp_path):
    """A second universe's sync must not clobber the first one's cache —
    the same wholesale-replace bug the in-memory store was keyed to avoid."""
    await _sync("alpha50", [_entry("TVSMOTOR")])
    await _sync("nifty200momentum30", [_entry("MOTHERSON")])

    routes._shortlist_store.clear()
    routes._last_synced_at.clear()
    routes._load_cache()

    assert routes._shortlist_store["alpha50"][0]["symbol"] == "TVSMOTOR"
    assert routes._shortlist_store["nifty200momentum30"][0]["symbol"] == "MOTHERSON"


def test_load_cache_tolerates_missing_file():
    routes._load_cache()          # no file written at all
    assert routes._shortlist_store == {}


def test_load_cache_tolerates_corrupt_json(tmp_path):
    (tmp_path / "cache.json").write_text("{not json", encoding="utf-8")
    routes._load_cache()          # must not raise
    assert routes._shortlist_store == {}


def test_load_cache_tolerates_wrong_shape(tmp_path):
    (tmp_path / "cache.json").write_text('["a", "list"]', encoding="utf-8")
    routes._load_cache()
    assert routes._shortlist_store == {}


def test_load_cache_skips_malformed_universe_but_keeps_good_ones(tmp_path):
    (tmp_path / "cache.json").write_text(json.dumps({
        "good": {"entries": [_entry()], "updated_at": None},
        "bad":  {"entries": "not-a-list"},
        "also_bad": "not-a-dict",
    }), encoding="utf-8")
    routes._load_cache()

    assert "good" in routes._shortlist_store
    assert "bad" not in routes._shortlist_store
    assert "also_bad" not in routes._shortlist_store


@pytest.mark.asyncio
async def test_sync_survives_unwritable_cache(monkeypatch, tmp_path):
    """An unwritable cache must not fail the sync — the scan's 11 minutes of
    work still has to reach the cockpit."""
    monkeypatch.setenv("QUANTOS_SHORTLIST_CACHE", str(tmp_path / "nope" / "x.json"))

    def _boom(*_a, **_kw):
        raise OSError("read-only filesystem")
    monkeypatch.setattr(routes.Path, "mkdir", _boom)

    await _sync("alpha50", [_entry()])     # asserts 200 internally
    assert routes._shortlist_store["alpha50"][0]["symbol"] == "TVSMOTOR"


@pytest.mark.asyncio
async def test_get_returns_restored_cache(tmp_path):
    await _sync("alpha50", [_entry()])
    routes._shortlist_store.clear()
    routes._last_synced_at.clear()
    routes._load_cache()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/discovery/momentum-shortlist/alpha50")

    body = resp.json()
    assert resp.status_code == 200
    assert body["entries"][0]["symbol"] == "TVSMOTOR"
    assert body["updated_at"] is not None


class TestFieldsSurviveTheRoundTrip:
    """scripts/run_momentum_shortlist.py POSTs `asdict(entry)` wholesale, and
    Pydantic drops undeclared keys in silence. That combination cost the vault
    audit its entire trip to the cockpit: the scan computed a verdict, sent it,
    and the API discarded it before `model_dump()`. Nothing failed, nothing
    logged — the column was simply never there.
    """

    def test_every_dataclass_field_is_declared_on_the_model(self):
        """The structural guard. Any field added to ShortlistEntry and not to
        ShortlistEntryIn is dropped in transit, so assert the model covers the
        dataclass rather than waiting to notice a blank column."""
        from dataclasses import fields as dataclass_fields

        from core.discovery.momentum_shortlist import ShortlistEntry

        sent = {f.name for f in dataclass_fields(ShortlistEntry)}
        accepted = set(routes.ShortlistEntryIn.model_fields)
        assert not (sent - accepted), (
            f"ShortlistEntry fields the API would silently drop: {sorted(sent - accepted)}"
        )

    @pytest.mark.asyncio
    async def test_vault_verdict_and_detail_reach_the_cockpit(self):
        await _sync("alpha50", [dict(_entry(),
                                     vault_verdict="FAIL",
                                     vault_detail="VCP: FAIL (close < sma(200)); Stage: PASS")])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/discovery/momentum-shortlist/alpha50")

        entry = resp.json()["entries"][0]
        assert entry["vault_verdict"] == "FAIL"
        assert "VCP: FAIL" in entry["vault_detail"]

    @pytest.mark.asyncio
    async def test_the_rule_tally_reaches_the_cockpit(self):
        """The tally is what the column actually renders — the verdict alone
        reads FAIL for nearly every name, so losing this would put the panel
        back to showing one value forever."""
        await _sync("alpha50", [dict(_entry(), vault_verdict="FAIL",
                                     vault_rules_passed=9, vault_rules_total=11)])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/discovery/momentum-shortlist/alpha50")

        entry = resp.json()["entries"][0]
        assert (entry["vault_rules_passed"], entry["vault_rules_total"]) == (9, 11)

    @pytest.mark.asyncio
    async def test_the_verdict_survives_a_restart(self, tmp_path):
        await _sync("alpha50", [dict(_entry(), vault_verdict="PASS",
                                     vault_detail="VCP: PASS")])
        routes._shortlist_store.clear()
        routes._load_cache()

        assert routes._shortlist_store["alpha50"][0]["vault_verdict"] == "PASS"

    @pytest.mark.asyncio
    async def test_an_entry_without_the_audit_still_validates(self):
        """Cached entries written before the audit existed, and scans run with
        `vault.annotate_shortlist: false`, both arrive without these keys."""
        await _sync("alpha50", [_entry()])       # no vault keys at all

        stored = routes._shortlist_store["alpha50"][0]
        assert stored["vault_verdict"] is None   # distinct from "UNAVAILABLE"
        assert stored["vault_detail"] is None
