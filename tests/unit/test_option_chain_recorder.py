"""Tests for the read-only option-chain recorder (2026-09-30)."""

import csv
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.marketdata.option_chain_recorder import COLUMNS, append_rows, flatten, parse_expiries  # noqa: E402
import scripts.record_option_chains as rec  # noqa: E402

# Shape copied from a real Fyers optionchain response (2026-09-30).
RESP = {
    "callOi": 164228870, "putOi": 106087280,
    "expiryData": [{"date": "13-10-2026", "expiry": "1791886200", "expiry_flag": "W"},
                   {"date": "06-10-2026", "expiry": "1791281400", "expiry_flag": "W"}],
    "indiavixData": {"ltp": 13.49, "symbol": "NSE:INDIAVIX-INDEX"},
    "optionsChain": [
        {"option_type": "", "ltp": 22620.45, "fp": 22700, "strike_price": -1, "symbol": "NSE:NIFTY50-INDEX"},
        {"option_type": "PE", "strike_price": 22500, "symbol": "NSE:NIFTY26O0622500PE", "bid": 79.95,
         "ask": 80.7, "ltp": 80.75, "volume": 134121585, "oi": 6659250, "oich": 2598830, "prev_oi": 4060420},
        {"option_type": "CE", "strike_price": 22500, "symbol": "NSE:NIFTY26O0622500CE", "bid": 220.1,
         "ask": 220.65, "ltp": 220.65, "volume": 19644755, "oi": 2295930, "oich": 1599325, "prev_oi": 696605},
    ],
}
NOW = datetime(2026, 9, 30, 6, 0, 50, tzinfo=timezone.utc)


def test_parse_expiries_sorted_soonest_first():
    assert [e[0] for e in parse_expiries(RESP)] == [date(2026, 10, 6), date(2026, 10, 13)]
    assert parse_expiries(RESP)[0][1] == "1791281400"


def test_flatten_one_row_per_contract_with_index_future_vix_context():
    rows = flatten(RESP, "NIFTY", date(2026, 10, 6), "W", NOW)
    assert len(rows) == 2                                             # the index row is context, not a contract
    pe = next(r for r in rows if r["option_type"] == "PE")
    assert (pe["spot"], pe["future"], pe["vix"]) == (22620.45, 22700, 13.49)
    assert (pe["bid"], pe["ask"], pe["oi_change"], pe["days_to_expiry"]) == (79.95, 80.7, 2598830, 6)
    assert pe["total_put_oi"] == 106087280
    assert set(pe) == set(COLUMNS)


def test_append_rows_writes_header_once(tmp_path):
    rows = flatten(RESP, "NIFTY", date(2026, 10, 6), "W", NOW)
    p = append_rows(rows, "NIFTY", NOW.date(), base=tmp_path)
    append_rows(rows, "NIFTY", NOW.date(), base=tmp_path)
    data = list(csv.DictReader(p.open(encoding="utf-8")))
    assert len(data) == 4 and p.name == "NIFTY.csv" and p.parent.name == "2026-09-30"


class _FakeClient:
    def __init__(self):
        self.calls = []

    def optionchain(self, data):
        self.calls.append(data["timestamp"])
        return {"code": 200, "data": RESP}


def test_record_index_fetches_the_two_nearest_expiries(monkeypatch, tmp_path):
    monkeypatch.setattr(rec, "append_rows", lambda rows, u, d: append_rows(rows, u, d, base=tmp_path))
    monkeypatch.setattr(rec.time, "sleep", lambda s: None)
    monkeypatch.setattr(rec, "recorder_dir", lambda: tmp_path)
    client = _FakeClient()
    n = rec.record_index(client, "NIFTY", "NSE:NIFTY50-INDEX", NOW)
    assert client.calls == ["", "1791886200"]      # nearest via "", then the 2nd expiry by epoch
    assert n == 4

    cov = (tmp_path / "2026-09-30" / "coverage.csv").read_text().splitlines()
    assert cov[1].split(",")[1:5] == ["NIFTY", "2", "0", "4"]


def test_coverage_flags_a_response_without_futures_price(monkeypatch, tmp_path):
    monkeypatch.setattr(rec, "append_rows", lambda rows, u, d: append_rows(rows, u, d, base=tmp_path))
    monkeypatch.setattr(rec, "recorder_dir", lambda: tmp_path)
    monkeypatch.setattr(rec.time, "sleep", lambda s: None)
    no_fp = {**RESP, "optionsChain": [{**RESP["optionsChain"][0], "fp": None}] + RESP["optionsChain"][1:]}

    class _C(_FakeClient):
        def optionchain(self, data):
            return {"code": 200, "data": no_fp}
    rec.record_index(_C(), "NIFTY", "NSE:NIFTY50-INDEX", NOW)
    assert "missing future" in (tmp_path / "2026-09-30" / "coverage.csv").read_text()
