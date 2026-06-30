"""
QuantOS — TradingView Screener CSV Ingestion
───────────────────────────────────────────────
US-03: Parses TradingView screener exports into structured candidates.

TradingView screener export format (typical columns):
  Symbol, Description, Price, Change %, Volume, Market Cap,
  Relative Volume, 20D SMA, 50D SMA, 200D SMA, RSI, ATR%

Export workflow:
  1. Build a screener in TradingView (e.g. "NSE stocks, volume > 1M, price > 50D SMA")
  2. Export to CSV
  3. Drop the file at the configured path (or POST to /screener/upload)
"""

import csv
import io
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ScreenerCandidate:
    """A single row from the TradingView screener export."""
    symbol:          str
    price:           float
    change_pct:      float
    volume:          int
    market_cap:      Optional[float] = None
    relative_volume: Optional[float] = None
    sma_20:          Optional[float] = None
    sma_50:          Optional[float] = None
    sma_200:         Optional[float] = None
    rsi:             Optional[float] = None
    atr_pct:         Optional[float] = None

    @property
    def above_50_sma(self) -> bool:
        return self.sma_50 is not None and self.price > self.sma_50

    @property
    def above_200_sma(self) -> bool:
        return self.sma_200 is not None and self.price > self.sma_200

    @property
    def is_liquid(self) -> bool:
        """Minimum liquidity filter — avoid illiquid small caps."""
        return self.volume >= 500_000

    @property
    def has_volume_surge(self) -> bool:
        return self.relative_volume is not None and self.relative_volume >= 1.5


# Column name mapping — TradingView exports can vary slightly by screener config.
# Maps possible CSV header variants to our canonical field names.
_COLUMN_MAP = {
    "symbol":            ["Symbol", "Ticker"],
    "price":             ["Price", "Last", "Close"],
    "change_pct":        ["Change %", "Change%", "% Change"],
    "volume":            ["Volume", "Vol"],
    "market_cap":        ["Market Cap", "Market Capitalization"],
    "relative_volume":   ["Relative Volume", "Rel Volume"],
    "sma_20":            ["20D SMA", "SMA20", "Simple Moving Average (20)"],
    "sma_50":            ["50D SMA", "SMA50", "Simple Moving Average (50)"],
    "sma_200":           ["200D SMA", "SMA200", "Simple Moving Average (200)"],
    "rsi":               ["RSI", "Relative Strength Index (14)"],
    "atr_pct":           ["ATR%", "ATRP", "Average True Range %"],
}


def parse_screener_csv(csv_content: str) -> list[ScreenerCandidate]:
    """
    Parse TradingView screener CSV export into ScreenerCandidate objects.

    Args:
        csv_content: raw CSV text (from file upload or read())

    Returns:
        List of ScreenerCandidate, skipping rows that fail to parse.
    """
    reader = csv.DictReader(io.StringIO(csv_content))
    if not reader.fieldnames:
        logger.warning("Empty or malformed CSV — no headers found")
        return []

    column_lookup = _build_column_lookup(reader.fieldnames)
    candidates = []

    for row_num, row in enumerate(reader, start=2):  # row 1 = header
        try:
            candidate = _parse_row(row, column_lookup)
            if candidate:
                candidates.append(candidate)
        except Exception as e:
            logger.warning("Skipping row %d — parse error: %s", row_num, e)
            continue

    logger.info("Parsed %d candidates from screener CSV", len(candidates))
    return candidates


def _build_column_lookup(fieldnames: list[str]) -> dict[str, str]:
    """Map canonical field name → actual CSV column name present in this file."""
    lookup = {}
    for canonical, variants in _COLUMN_MAP.items():
        for variant in variants:
            if variant in fieldnames:
                lookup[canonical] = variant
                break
    return lookup


def _parse_row(row: dict, lookup: dict[str, str]) -> Optional[ScreenerCandidate]:
    """Parse a single CSV row into a ScreenerCandidate."""

    def get(field: str, cast=float, default=None):
        col = lookup.get(field)
        if not col or col not in row:
            return default
        raw = row[col].strip().replace(",", "").replace("%", "")
        if not raw or raw in ("-", "N/A", ""):
            return default
        try:
            return cast(raw)
        except ValueError:
            return default

    symbol = get("symbol", cast=str)
    if not symbol:
        return None

    price = get("price")
    if price is None or price <= 0:
        return None

    return ScreenerCandidate(
        symbol=symbol.upper().strip(),
        price=price,
        change_pct=get("change_pct", default=0.0),
        volume=int(get("volume", cast=int, default=0)),
        market_cap=get("market_cap"),
        relative_volume=get("relative_volume"),
        sma_20=get("sma_20"),
        sma_50=get("sma_50"),
        sma_200=get("sma_200"),
        rsi=get("rsi"),
        atr_pct=get("atr_pct"),
    )


def apply_pre_filters(
    candidates: list[ScreenerCandidate],
    min_volume: int = 500_000,
    require_above_50_sma: bool = True,
) -> list[ScreenerCandidate]:
    """
    Apply cheap, deterministic pre-filters before sending to Claude.
    Saves Claude API costs (ADR-04) by removing obviously bad candidates first.
    """
    filtered = [
        c for c in candidates
        if c.volume >= min_volume
        and (not require_above_50_sma or c.above_50_sma)
    ]
    logger.info(
        "Pre-filter: %d → %d candidates (min_volume=%d, above_50_sma=%s)",
        len(candidates), len(filtered), min_volume, require_above_50_sma,
    )
    return filtered
