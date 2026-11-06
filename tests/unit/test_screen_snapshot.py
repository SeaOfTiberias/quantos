"""
Techno-funda screen snapshot: parser, TradingView links, storage, the latest view and the route.

The page is a synthetic copy of screener.in's screen layout (made-up companies and numbers),
never a saved real page.
"""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from core.techno_funda import screen_snapshot as ss

PAGE = """
<html><body>
<div>  3 results found: Showing page 1 of 1 </div>
<table class="data-table text-nowrap striped">
 <tbody>
  <tr>
   <th class="text" scope="colgroup"><a href="?order=asc">S.No.</a></th>
   <th class="text" scope="colgroup"><a href="?sort=name">Company</a></th>
   <th data-tooltip="Current Price" scope="colgroup"><a href="?sort=cp">CMP <span>Rs.</span></a></th>
   <th data-tooltip="Market Capitalization" scope="colgroup"><a href="?sort=mc">Mar Cap</a></th>
   <th data-tooltip="Piotroski score" scope="colgroup"><a href="?sort=p">Piotski Scr</a></th>
  </tr>
  <tr data-row-company-id="1">
   <td class="text">1.</td>
   <td class="text"><a href="/company/ALPHACO/consolidated/" target="_blank">Alpha Co</a></td>
   <td>1,181.50</td><td>526.86</td><td>8.00</td>
  </tr>
  <tr data-row-company-id="2">
   <td class="text">2.</td>
   <td class="text"><a href="/company/599001/" target="_blank">Beta &amp; Sons</a></td>
   <td>114.50</td><td>259.90</td><td>9.00</td>
  </tr>
  <tr data-row-company-id="3">
   <td class="text">3.</td>
   <td class="text"><a href="/company/M&amp;M-X/" target="_blank">Gamma</a></td>
   <td>-7.20</td><td></td><td>8.00</td>
  </tr>
 </tbody>
</table>
<textarea name="query" id="query-builder">Price &gt; 10 AND
RSI &lt; 65</textarea>
</body></html>
"""


def test_parse_columns_rows_and_query():
    s = ss.parse(PAGE)
    assert s["columns"] == ["Current Price", "Market Capitalization", "Piotroski score"]
    assert s["total"] == 3 and s["pages"] == 1 and s["truncated"] is False
    assert s["query"] == "Price > 10 AND\nRSI < 65"
    a, b, g = s["rows"]
    assert a["name"] == "Alpha Co" and a["nse_symbol"] == "ALPHACO" and a["bse_code"] is None
    assert a["values"] == {"Current Price": 1181.5, "Market Capitalization": 526.86, "Piotroski score": 8.0}
    assert a["screener_url"] == "https://www.screener.in/company/ALPHACO/consolidated/"
    assert a["tradingview_url"] == "https://www.tradingview.com/chart/?symbol=NSE:ALPHACO"
    assert b["name"] == "Beta & Sons"
    assert b["nse_symbol"] is None and b["bse_code"] == "599001" and b["tradingview_url"] is None
    assert g["values"]["Current Price"] == -7.2 and g["values"]["Market Capitalization"] is None


def test_tradingview_symbol_rewrites_ampersand_and_dash():
    assert ss.tradingview_url("M&M") == "https://www.tradingview.com/chart/?symbol=NSE:M_M"
    assert ss.tradingview_url("BAJAJ-AUTO").endswith("NSE:BAJAJ_AUTO")
    assert ss.tradingview_url(None) is None
    assert ss.parse(PAGE)["rows"][2]["tradingview_url"].endswith("NSE:M_M_X")


def test_more_than_one_page_is_flagged_truncated():
    s = ss.parse(PAGE.replace("3 results found: Showing page 1 of 1", "60 results found: Showing page 1 of 3"))
    assert s["total"] == 60 and s["pages"] == 3 and s["truncated"] is True


def test_page_without_results_table_raises():
    with pytest.raises(ValueError):
        ss.parse("<html><body>Please log in</body></html>")


def _snap(session, names):
    return {"session": session, "rows": [{"name": n, "nse_symbol": n, "bse_code": None,
                                          "tradingview_url": ss.tradingview_url(n), "screener_url": None,
                                          "values": {}} for n in names]}


def test_save_load_and_latest_view(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTOS_SCREEN_SNAPSHOTS", str(tmp_path))
    ss.save(_snap("2026-11-03", ["AAA", "BBB"]), date(2026, 11, 3))
    ss.save(_snap("2026-11-04", ["AAA", "CCC"]), date(2026, 11, 4))
    ss.save(_snap("2026-11-05", ["AAA", "CCC", "DDD"]), date(2026, 11, 5))
    (tmp_path / "2026-11-06.json").write_text("{not json", encoding="utf-8")     # skipped, not fatal
    snaps = ss.load_all()
    assert [s["session"] for s in snaps] == ["2026-11-03", "2026-11-04", "2026-11-05"]
    v = ss.latest_view(snaps)
    rows = {r["nse_symbol"]: r for r in v["rows"]}
    assert rows["AAA"]["first_seen"] == "2026-11-03" and rows["AAA"]["days_in_window"] == 3
    assert rows["CCC"]["first_seen"] == "2026-11-04" and rows["CCC"]["days_in_window"] == 2
    assert rows["DDD"]["days_in_window"] == 1
    assert v["dropped"] == [] and v["previous_session"] == "2026-11-04" and v["sessions_recorded"] == 3
    v2 = ss.latest_view(snaps[:2])
    assert [d["nse_symbol"] for d in v2["dropped"]] == ["BBB"]
    assert ss.latest_view([]) is None


def test_saved_file_is_json_named_by_session(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTOS_SCREEN_SNAPSHOTS", str(tmp_path))
    p = ss.save(_snap("2026-11-06", ["AAA"]), date(2026, 11, 6))
    assert p.name == "2026-11-06.json"
    assert json.loads(p.read_text(encoding="utf-8"))["rows"][0]["name"] == "AAA"


def test_route_empty_then_latest(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTOS_SCREEN_SNAPSHOTS", str(tmp_path))
    from cloud.api.main import app
    client = TestClient(app)
    r = client.get("/discovery/screen").json()
    assert r["session"] is None and r["rows"] == [] and r["sessions_recorded"] == 0
    ss.save(_snap("2026-11-06", ["AAA"]), date(2026, 11, 6))
    r = client.get("/discovery/screen").json()
    assert r["session"] == "2026-11-06" and r["rows"][0]["tradingview_url"].endswith("NSE:AAA")
