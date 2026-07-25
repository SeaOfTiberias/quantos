"""
Pairs Trading — Sector-Tagged Futures Universe Unit Tests

Covers core/pairs/universe.py's pure logic (no network calls) per
docs/PAIRS_TRADING_METHODOLOGY.md's "Universe" section.
"""

import io
import sys
import zipfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.pairs.universe import (  # noqa: E402
    build_pairs_universe, candidate_pairs, parse_stf_near_month, parse_stf_symbols,
    symbol_sector_counts,
)


def _make_raw_zip(rows: list[dict]) -> bytes:
    header = ["TradDt", "FinInstrmTp", "TckrSymb", "XpryDt", "ClsPric", "NewBrdLotQty"]
    lines = [",".join(header)]
    for r in rows:
        lines.append(",".join(str(r.get(h, "")) for h in header))
    csv_text = "\n".join(lines)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("bhav.csv", csv_text)
    return buf.getvalue()


def test_parse_stf_symbols_filters_to_stf_only():
    raw = _make_raw_zip([
        {"FinInstrmTp": "STF", "TckrSymb": "TCS"},
        {"FinInstrmTp": "STF", "TckrSymb": "INFY"},
        {"FinInstrmTp": "STO", "TckrSymb": "TCS"},   # option, not future
        {"FinInstrmTp": "IDF", "TckrSymb": "NIFTY"},  # index future
    ])
    assert parse_stf_symbols(raw) == {"TCS", "INFY"}


def test_parse_stf_symbols_dedupes_across_expiries():
    raw = _make_raw_zip([
        {"FinInstrmTp": "STF", "TckrSymb": "TCS", "XpryDt": "2026-07-28"},
        {"FinInstrmTp": "STF", "TckrSymb": "TCS", "XpryDt": "2026-08-25"},
    ])
    assert parse_stf_symbols(raw) == {"TCS"}


def test_build_pairs_universe_intersects_sector_and_futures():
    sector_map = {
        "auto": ["MARUTI", "TATAMOTORS", "MOTHERSON"],  # MOTHERSON has no futures below
        "bank": ["HDFCBANK"],  # only 1 futures-listed symbol -- should be dropped
    }
    stf_symbols = {"MARUTI", "TATAMOTORS", "HDFCBANK"}
    universe = build_pairs_universe(sector_map, stf_symbols)
    assert universe == {"auto": ["MARUTI", "TATAMOTORS"]}


def test_build_pairs_universe_drops_sectors_with_fewer_than_two():
    universe = build_pairs_universe({"realty": ["DLF"]}, {"DLF"})
    assert universe == {}


def test_candidate_pairs_generates_unordered_combinations():
    universe = {"auto": ["A", "B", "C"]}
    pairs = candidate_pairs(universe)
    assert set(pairs) == {("A", "B", "auto"), ("A", "C", "auto"), ("B", "C", "auto")}


def test_candidate_pairs_no_cross_sector_pairs():
    universe = {"auto": ["A", "B"], "bank": ["C", "D"]}
    pairs = candidate_pairs(universe)
    symbols_paired = {(p[0], p[1]) for p in pairs}
    assert ("A", "C") not in symbols_paired
    assert ("B", "D") not in symbols_paired


def test_candidate_pairs_multi_sector_symbol_contributes_to_each():
    # HDFCBANK tagged under both "bank" and "financials" -- pairs with each sector's peers
    universe = {"bank": ["HDFCBANK", "ICICIBANK"], "financials": ["HDFCBANK", "BAJFINANCE"]}
    pairs = candidate_pairs(universe)
    assert ("HDFCBANK", "ICICIBANK", "bank") in pairs
    assert ("HDFCBANK", "BAJFINANCE", "financials") in pairs


def test_parse_stf_near_month_picks_smallest_future_expiry():
    raw = _make_raw_zip([
        {"FinInstrmTp": "STF", "TckrSymb": "TCS", "XpryDt": "2026-07-28", "ClsPric": "4000.0", "NewBrdLotQty": "150"},
        {"FinInstrmTp": "STF", "TckrSymb": "TCS", "XpryDt": "2026-08-25", "ClsPric": "4010.0", "NewBrdLotQty": "150"},
        {"FinInstrmTp": "STF", "TckrSymb": "TCS", "XpryDt": "2026-09-29", "ClsPric": "4020.0", "NewBrdLotQty": "150"},
    ])
    result = parse_stf_near_month(raw, date(2026, 7, 1))
    assert result["TCS"].expiry == date(2026, 7, 28)
    assert result["TCS"].close == 4000.0
    assert result["TCS"].lot_size == 150


def test_parse_stf_near_month_skips_expired_contracts():
    raw = _make_raw_zip([
        {"FinInstrmTp": "STF", "TckrSymb": "TCS", "XpryDt": "2026-07-01", "ClsPric": "4000.0", "NewBrdLotQty": "150"},
    ])
    # trade_date AFTER the only listed expiry -- a stale/already-expired
    # contract, should be skipped rather than treated as tradeable.
    result = parse_stf_near_month(raw, date(2026, 7, 2))
    assert "TCS" not in result


def test_parse_stf_near_month_ignores_non_stf_rows():
    raw = _make_raw_zip([
        {"FinInstrmTp": "STO", "TckrSymb": "TCS", "XpryDt": "2026-07-28", "ClsPric": "50.0", "NewBrdLotQty": "150"},
    ])
    result = parse_stf_near_month(raw, date(2026, 7, 1))
    assert result == {}


def test_symbol_sector_counts():
    universe = {"bank": ["HDFCBANK", "ICICIBANK"], "financials": ["HDFCBANK", "BAJFINANCE"]}
    counts = symbol_sector_counts(universe)
    assert counts["HDFCBANK"] == 2
    assert counts["ICICIBANK"] == 1
