"""
Fyers Options Symbol Master — resolves (underlying, expiry, strike, CE/PE)
against Fyers' own published symbol master rather than hand-built strings.
Sample rows below are copied verbatim from a real download of
https://public.fyers.in/sym_details/NSE_FO.csv on 2026-07-21.
"""

import pytest
from datetime import date
from unittest.mock import patch

from core.options import fyers_symbol_master as sm
from core.options.models import OptionType

# Real rows: NIFTY weekly option (numeric month+day format), a NIFTY future
# (should be excluded from option lookups), and a stock monthly option
# (3-letter month format) — proves the module handles both symbol styles.
_SAMPLE_CSV = (
    "101126072861088,BANKNIFTY 28 Jul 26 FUT,11,30,0.2,,0915-1530|1815-1915:,"
    "2026-07-20,1785232800,NSE:BANKNIFTY26JULFUT,10,11,61088,BANKNIFTY,26009,-1.0,XX,"
    "101000000026009,None,0,0.0\n"
    "101126072135426,NIFTY 21 Jul 26 29450 CE,14,65,0.05,,0915-1530|1815-1915:,"
    "2026-07-20,1784628000,NSE:NIFTY2672129450CE,10,11,35426,NIFTY,26000,29450.0,CE,"
    "101000000026000,None,0,0.0\n"
    "101126072135427,NIFTY 21 Jul 26 29450 PE,14,65,0.05,,0915-1530|1815-1915:,"
    "2026-07-20,1784628000,NSE:NIFTY2672129450PE,10,11,35427,NIFTY,26000,29450.0,PE,"
    "101000000026000,None,0,0.0\n"
    "1011260728138926,SBIN 28 Jul 26 600 CE,15,750,0.05,,0915-1530|1815-1915:,"
    "2026-07-20,1785232800,NSE:SBIN26JUL600CE,10,11,138926,SBIN,3045,600.0,CE,"
    "10100000003045,None,0,0.0\n"
)


@pytest.fixture(autouse=True)
def _mock_master_download(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "_CACHE_DIR", str(tmp_path))
    with patch.object(sm, "_download_master", return_value=_SAMPLE_CSV) as m:
        yield m


class TestResolveOptionSymbol:

    def test_resolves_nifty_weekly_symbol(self):
        resolved = sm.resolve_option_symbol(
            "NIFTY", date(2026, 7, 21), 29450.0, OptionType.CALL,
        )
        assert resolved.symbol == "NSE:NIFTY2672129450CE"
        assert resolved.lot_size == 65

    def test_resolves_stock_monthly_symbol(self):
        resolved = sm.resolve_option_symbol(
            "SBIN", date(2026, 7, 28), 600.0, OptionType.CALL,
        )
        assert resolved.symbol == "NSE:SBIN26JUL600CE"
        assert resolved.lot_size == 750

    def test_put_resolves_independently_of_call(self):
        resolved = sm.resolve_option_symbol(
            "NIFTY", date(2026, 7, 21), 29450.0, OptionType.PUT,
        )
        assert resolved.symbol == "NSE:NIFTY2672129450PE"

    def test_unlisted_strike_raises(self):
        with pytest.raises(sm.SymbolMasterError):
            sm.resolve_option_symbol(
                "NIFTY", date(2026, 7, 21), 99999.0, OptionType.CALL,
            )

    def test_unknown_underlying_raises(self):
        with pytest.raises(sm.SymbolMasterError):
            sm.resolve_option_symbol(
                "NOTAREALSYMBOL", date(2026, 7, 21), 100.0, OptionType.CALL,
            )

    def test_futures_row_never_matches_an_option_lookup(self):
        """BANKNIFTY's only row in the sample is a future (strike=-1, type=XX)
        — an option lookup for BANKNIFTY must not accidentally match it."""
        with pytest.raises(sm.SymbolMasterError):
            sm.resolve_option_symbol(
                "BANKNIFTY", date(2026, 7, 28), 50000.0, OptionType.CALL,
            )


class TestGetExpiryEpoch:

    def test_returns_epoch_string_for_nifty_weekly(self):
        epoch = sm.get_expiry_epoch("NIFTY", date(2026, 7, 21))
        assert epoch == "1784628000"

    def test_returns_epoch_string_for_stock_monthly(self):
        epoch = sm.get_expiry_epoch("SBIN", date(2026, 7, 28))
        assert epoch == "1785232800"

    def test_unlisted_expiry_raises(self):
        with pytest.raises(sm.SymbolMasterError):
            sm.get_expiry_epoch("NIFTY", date(2099, 1, 1))


class TestGetLotSize:

    def test_nifty_lot_size(self):
        assert sm.get_lot_size("NIFTY") == 65

    def test_stock_lot_size_differs_from_index(self):
        assert sm.get_lot_size("SBIN") == 750

    def test_unknown_underlying_raises(self):
        with pytest.raises(sm.SymbolMasterError):
            sm.get_lot_size("NOTAREALSYMBOL")


class TestListExpiries:

    def test_lists_only_future_or_today_expiries(self):
        expiries = sm.list_expiries("NIFTY")
        assert date(2026, 7, 21) in expiries

    def test_unknown_underlying_raises(self):
        with pytest.raises(sm.SymbolMasterError):
            sm.list_expiries("NOTAREALSYMBOL")


class TestCaching:

    def test_second_call_uses_cache_not_network(self, _mock_master_download):
        sm.resolve_option_symbol("NIFTY", date(2026, 7, 21), 29450.0, OptionType.CALL)
        sm.resolve_option_symbol("SBIN", date(2026, 7, 28), 600.0, OptionType.CALL)
        assert _mock_master_download.call_count == 1

    def test_force_refresh_bypasses_cache(self, _mock_master_download):
        sm.resolve_option_symbol("NIFTY", date(2026, 7, 21), 29450.0, OptionType.CALL)
        sm.resolve_option_symbol(
            "NIFTY", date(2026, 7, 21), 29450.0, OptionType.CALL, force_refresh=True,
        )
        assert _mock_master_download.call_count == 2
