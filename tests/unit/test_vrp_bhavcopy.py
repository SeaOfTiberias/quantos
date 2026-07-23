"""
VRP Phase 1 — Bhavcopy Fetch/Parse Pipeline — Unit Tests

Fixture CSV bodies below are trimmed real rows pulled from NSE's live archive
(2024-01-01 new-format, 2023-12-29 legacy-format; see core/options/vrp/bhavcopy.py
docstring for the cutover-date probe that established the two date ranges),
not hand-invented data -- so a schema drift in NSE's real columns would show
up here as a parse failure, not silently pass.
"""

import io
import zipfile
from datetime import date

import pytest

from core.options.models import OptionType
from core.options.vrp.bhavcopy import (
    BhavcopyNotAvailable,
    CUTOVER_DATE,
    fetch_raw,
    legacy_format_url,
    new_format_url,
    parse_bhavcopy_zip,
    url_for,
)


# ─── URL selection ──────────────────────────────────────────────────────────

class TestUrlSelection:
    def test_new_format_url_shape(self):
        assert new_format_url(date(2024, 1, 1)) == (
            "https://nsearchives.nseindia.com/content/fo/"
            "BhavCopy_NSE_FO_0_0_0_20240101_F_0000.csv.zip"
        )

    def test_legacy_format_url_shape(self):
        assert legacy_format_url(date(2023, 12, 29)) == (
            "https://archives.nseindia.com/content/historical/DERIVATIVES/"
            "2023/DEC/fo29DEC2023bhav.csv.zip"
        )

    def test_cutover_date_is_jan_1_2024(self):
        # Binary-searched live 2026-07-23 -- see module docstring. Pinned here
        # so an accidental edit to CUTOVER_DATE fails loudly.
        assert CUTOVER_DATE == date(2024, 1, 1)

    def test_url_for_selects_new_format_on_and_after_cutover(self):
        assert url_for(date(2024, 1, 1)) == new_format_url(date(2024, 1, 1))
        assert url_for(date(2024, 7, 5)) == new_format_url(date(2024, 7, 5))

    def test_url_for_selects_legacy_format_before_cutover(self):
        assert url_for(date(2023, 12, 29)) == legacy_format_url(date(2023, 12, 29))


# ─── New-format parsing ──────────────────────────────────────────────────────

NEW_FORMAT_HEADER = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,"
    "FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,"
    "ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,"
    "ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,"
    "Rmks,Rsvd01,Rsvd02,Rsvd03,Rsvd04\n"
)
NEW_FORMAT_ROWS = (
    # A real NIFTY IDO (index option) row.
    "2024-01-01,2024-01-01,FO,NSE,IDO,72884,,NIFTY,,2024-02-29,2024-02-29,21400.00,"
    "CE,NIFTY24FEB21400CE,839.00,955.00,836.10,882.85,836.10,870.55,21741.90,882.85,"
    "20450,-650,160,178251222.50,95,F1,50,,,,,\n"
    # A real NIFTY PE row, different expiry/strike.
    "2024-01-01,2024-01-01,FO,NSE,IDO,67286,,NIFTY,,2024-03-28,2024-03-28,21400.00,"
    "PE,NIFTY24MAR21400PE,350.80,350.80,302.15,322.15,338.30,326.30,21741.90,322.15,"
    "1400,-100,33,35829902.50,28,F1,50,,,,,\n"
    # A real stock-option (STO) row -- must be filtered OUT (wrong FinInstrmTp).
    "2024-01-01,2024-01-01,FO,NSE,STO,154732,,LICHSGFIN,,2024-03-28,2024-03-28,635.00,"
    "PE,LICHSGFIN24MAR635PE,0.00,0.00,0.00,105.40,0.00,105.40,563.00,73.90,0,0,0,"
    "0.00,0,F1,2000,,,,,\n"
)


def _zip_of(text: str, name: str = "bhav.csv") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, text)
    return buf.getvalue()


class TestParseNewFormat:
    def setup_method(self):
        raw_zip = _zip_of(NEW_FORMAT_HEADER + NEW_FORMAT_ROWS)
        self.rows = parse_bhavcopy_zip(raw_zip, date(2024, 1, 1))

    def test_filters_to_nifty_index_options_only(self):
        # 2 NIFTY IDO rows in the fixture, 1 stock-option row dropped.
        assert len(self.rows) == 2
        assert all(r.underlying == "NIFTY" for r in self.rows)

    def test_parses_call_row_fields(self):
        ce = next(r for r in self.rows if r.option_type == OptionType.CALL)
        assert ce.trade_date == date(2024, 1, 1)
        assert ce.expiry == date(2024, 2, 29)
        assert ce.strike == 21400.0
        assert ce.close == 882.85
        assert ce.settle_price == 882.85
        assert ce.open_interest == 20450
        assert ce.volume == 160
        assert ce.underlying_close == 21741.90

    def test_parses_put_row_fields(self):
        pe = next(r for r in self.rows if r.option_type == OptionType.PUT)
        assert pe.expiry == date(2024, 3, 28)
        assert pe.strike == 21400.0
        assert pe.close == 322.15


# ─── Legacy-format parsing ───────────────────────────────────────────────────

LEGACY_FORMAT_HEADER = (
    "INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,"
    "SETTLE_PR,CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP,\n"
)
LEGACY_FORMAT_ROWS = (
    # A real NIFTY OPTIDX row.
    "OPTIDX,NIFTY,04-Jan-2024,18300,CE,0,0,0,1669.65,3451.7,0,0,0,0,29-DEC-2023,\n"
    # A real BANKNIFTY future row -- must be filtered OUT (wrong INSTRUMENT).
    "FUTIDX,BANKNIFTY,25-Jan-2024,0,XX,48750,48805,48404.75,48628.8,48628.8,"
    "129897,946629.41,2077725,-10920,29-DEC-2023,\n"
)


class TestParseLegacyFormat:
    def setup_method(self):
        raw_zip = _zip_of(LEGACY_FORMAT_HEADER + LEGACY_FORMAT_ROWS)
        self.rows = parse_bhavcopy_zip(raw_zip, date(2023, 12, 29))

    def test_filters_to_nifty_optidx_only(self):
        assert len(self.rows) == 1
        assert self.rows[0].underlying == "NIFTY"

    def test_parses_fields(self):
        row = self.rows[0]
        assert row.trade_date == date(2023, 12, 29)
        assert row.expiry == date(2024, 1, 4)
        assert row.strike == 18300.0
        assert row.option_type == OptionType.CALL
        assert row.close == 1669.65
        assert row.settle_price == 3451.7

    def test_legacy_schema_has_no_underlying_close(self):
        # UndrlygPric doesn't exist in the legacy schema -- must be None, not
        # a guessed/defaulted value, so callers know to source spot elsewhere.
        assert self.rows[0].underlying_close is None


# ─── Multi-file zip rejection ────────────────────────────────────────────────

def test_parse_rejects_multi_file_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.csv", NEW_FORMAT_HEADER)
        zf.writestr("b.csv", NEW_FORMAT_HEADER)
    with pytest.raises(ValueError):
        parse_bhavcopy_zip(buf.getvalue(), date(2024, 1, 1))


# ─── fetch_raw caching + 404 handling ────────────────────────────────────────

class _FakeResponse:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content


class _FakeSession:
    """Records requested URLs, returns pre-programmed responses in order."""
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(url)
        return self._responses.pop(0)


class TestFetchRaw:
    def test_raises_not_available_on_404(self, tmp_path):
        session = _FakeSession([_FakeResponse(404)])
        with pytest.raises(BhavcopyNotAvailable):
            fetch_raw(date(2024, 1, 27), tmp_path, session=session)  # a Saturday

    def test_caches_successful_response_to_disk(self, tmp_path):
        session = _FakeSession([_FakeResponse(200, b"zip-bytes")])
        result = fetch_raw(date(2024, 1, 1), tmp_path, session=session)
        assert result == b"zip-bytes"
        assert (tmp_path / "20240101.zip").read_bytes() == b"zip-bytes"

    def test_second_call_serves_from_cache_without_a_network_request(self, tmp_path):
        session = _FakeSession([_FakeResponse(200, b"zip-bytes")])
        fetch_raw(date(2024, 1, 1), tmp_path, session=session)
        # Second call would raise IndexError on session.get() if it hit the
        # network again, since the fake session has no more responses queued.
        result = fetch_raw(date(2024, 1, 1), tmp_path, session=session)
        assert result == b"zip-bytes"
        assert len(session.calls) == 1

    def test_retries_then_succeeds_on_transient_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.options.vrp.bhavcopy.time.sleep", lambda *_: None)
        session = _FakeSession([_FakeResponse(500), _FakeResponse(200, b"zip-bytes")])
        result = fetch_raw(date(2024, 1, 1), tmp_path, session=session, max_retries=3)
        assert result == b"zip-bytes"
        assert len(session.calls) == 2
