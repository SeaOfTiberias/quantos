"""
PEAD Gut-Check — NSE Equity Bhavcopy Fetch/Parse — Unit Tests

Fixture CSV bodies below are trimmed real rows pulled from NSE's live
archive 2026-07-23 (2024-10-15 new-format, 2023-10-16 legacy-format), same
discipline as tests/unit/test_vrp_bhavcopy.py's fixtures -- not invented.
"""

import io
import zipfile
from datetime import date

import pytest

from core.fundamentals.pead.eq_bhavcopy import (
    CUTOVER_DATE,
    EqBhavcopyNotAvailable,
    legacy_format_url,
    new_format_url,
    parse_bhavcopy_zip,
    url_for,
)


class TestUrlSelection:
    def test_new_format_url_shape(self):
        assert new_format_url(date(2024, 10, 15)) == (
            "https://nsearchives.nseindia.com/content/cm/"
            "BhavCopy_NSE_CM_0_0_0_20241015_F_0000.csv.zip"
        )

    def test_legacy_format_url_shape(self):
        assert legacy_format_url(date(2023, 10, 16)) == (
            "https://archives.nseindia.com/content/historical/EQUITIES/"
            "2023/OCT/cm16OCT2023bhav.csv.zip"
        )

    def test_cutover_date_matches_vrp_fo_bhavcopy(self):
        # Confirmed live 2026-07-23 -- not a coincidence with VRP's F&O
        # cutover, both are NSE's unified new-schema rollout.
        assert CUTOVER_DATE == date(2024, 1, 1)

    def test_url_for_selects_new_format_on_and_after_cutover(self):
        assert url_for(date(2024, 1, 1)) == new_format_url(date(2024, 1, 1))

    def test_url_for_selects_legacy_format_before_cutover(self):
        assert url_for(date(2023, 10, 16)) == legacy_format_url(date(2023, 10, 16))


NEW_FORMAT_HEADER = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,"
    "FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,"
    "ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,"
    "TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4\n"
)
NEW_FORMAT_ROWS = (
    # A real main-board equity row (SctySrs == EQ) -- must be kept.
    "2024-10-15,2024-10-15,CM,NSE,STK,20372,INE00Y201027,FLAIR,EQ,,,,,"
    "FLAIR WRITING INDUST LTD,296.15,300.10,293.75,295.95,298.85,296.15,,296.00,,,"
    "34968,10365770.00,1404,F1,1,,,,,\n"
    # A real trade-for-trade row (SctySrs == BE) -- must be filtered OUT.
    "2024-10-15,2024-10-15,CM,NSE,STK,3699,INE287Z01012,GAYAHWS,BE,,,,,"
    "GAYATRI HIGHWAYS LIMITED,1.33,1.39,1.26,1.34,1.39,1.33,,1.00,,,"
    "76350,98860.71,157,F1,1,,,,,\n"
)

LEGACY_HEADER = "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,\n"
LEGACY_ROWS = (
    # A real non-EQ series (T-bill) row -- must be filtered OUT.
    "182D160224,TB,97.55,97.55,97.55,97.55,97.55,97,200,19510,16-OCT-2023,1,IN002023Y219,\n"
)


def _zip_of(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("bhav.csv", text)
    return buf.getvalue()


class TestParseBhavcopyZip:
    def test_new_format_keeps_eq_series_only(self):
        rows = parse_bhavcopy_zip(_zip_of(NEW_FORMAT_HEADER + NEW_FORMAT_ROWS), date(2024, 10, 15))
        assert len(rows) == 1
        assert rows[0].symbol == "FLAIR"
        assert rows[0].close == 295.95
        assert rows[0].trade_date == date(2024, 10, 15)

    def test_legacy_format_drops_non_eq_series(self):
        rows = parse_bhavcopy_zip(_zip_of(LEGACY_HEADER + LEGACY_ROWS), date(2023, 10, 16))
        assert rows == []

    def test_multi_file_zip_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("a.csv", NEW_FORMAT_HEADER)
            zf.writestr("b.csv", NEW_FORMAT_HEADER)
        with pytest.raises(ValueError):
            parse_bhavcopy_zip(buf.getvalue(), date(2024, 10, 15))
