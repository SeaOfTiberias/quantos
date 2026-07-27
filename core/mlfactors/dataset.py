"""
QuantOS — ML Multi-Factor Stock Ranking: Dataset Assembly (candidate 16)
──────────────────────────────────────────────────────────────────────────
Assembles the (symbol, rebalance_date) x feature matrix + top-quintile
forward-return label per docs/ML_FACTOR_COMBINATION_METHODOLOGY.md's
"Label" section. Point-in-time throughout: a row's features use only data
at/before its rebalance date; its label uses only the price at the NEXT
rebalance date (never used as a feature for that same row).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.brokers.base import OHLCV
from core.mlfactors.features import (
    MeanReversionIndicators,
    build_mean_reversion_indicators,
    dual_momentum_feature,
    mean_reversion_feature,
    momentum_feature,
    reconstitution_feature,
)
from core.rotation.dual_momentum import SymbolIndicators, build_indicators
from core.rotation.nifty500_reconstitution import ReconstitutionEvent, UniverseSnapshot, eligible_symbols_asof
from core.rotation.ranker import SymbolSeries, build_symbol_series, value_as_of

TOP_QUINTILE_PCT = 0.20   # per the pre-registered label definition


@dataclass
class SymbolPrecomputed:
    """Every per-symbol indicator structure needed to answer feature
    queries at any as_of date, built ONCE per symbol rather than
    recomputed at every rebalance date."""
    series:     SymbolSeries               # momentum
    indicators: SymbolIndicators           # dual-momentum
    mr:         MeanReversionIndicators    # mean-reversion


def build_symbol_precomputed(
    daily_candles: list[OHLCV], sector_candles: list[OHLCV], sector_mapped: bool,
) -> SymbolPrecomputed:
    return SymbolPrecomputed(
        series=build_symbol_series(daily_candles),
        indicators=build_indicators(daily_candles),
        mr=build_mean_reversion_indicators(daily_candles, sector_candles, sector_mapped),
    )


@dataclass
class FeatureRow:
    symbol: str
    date:   datetime
    momentum:              float
    dual_momentum_score:   float
    dual_momentum_trend_up: bool
    mr_rsi:                float
    mr_band_position:      float
    mr_sector_trend_up:    bool
    mr_sector_mapped:      bool
    recon_days_since_added: float
    recon_recently_added:  bool
    recon_data_known:      bool
    label:                 Optional[int] = None   # set once the next rebalance date's forward return is known


FEATURE_NAMES = [
    "momentum", "dual_momentum_score", "dual_momentum_trend_up",
    "mr_rsi", "mr_band_position", "mr_sector_trend_up", "mr_sector_mapped",
    "recon_days_since_added", "recon_recently_added", "recon_data_known",
]


def to_feature_vector(row: FeatureRow) -> list[float]:
    """Booleans as 0.0/1.0, in FEATURE_NAMES order — the exact input shape
    core/mlfactors/model.py's sklearn pipeline expects."""
    return [
        row.momentum, row.dual_momentum_score, float(row.dual_momentum_trend_up),
        row.mr_rsi, row.mr_band_position, float(row.mr_sector_trend_up), float(row.mr_sector_mapped),
        row.recon_days_since_added, float(row.recon_recently_added), float(row.recon_data_known),
    ]


def _row_at(
    symbol: str, precomputed: SymbolPrecomputed, as_of: datetime,
    reconstitution_events: list[ReconstitutionEvent],
) -> Optional[FeatureRow]:
    """None if any REQUIRED (non-optional-by-design) feature isn't warmed
    up yet as of this date — a symbol too young to rank shouldn't get a
    row with fabricated values."""
    mom = momentum_feature(precomputed.series, as_of)
    dm = dual_momentum_feature(precomputed.indicators, as_of)
    mr = mean_reversion_feature(precomputed.mr, as_of)
    recon = reconstitution_feature(symbol, as_of, reconstitution_events)

    if mom is None or dm.score is None or dm.trend_up is None:
        return None
    if mr.rsi is None or mr.band_position is None or mr.sector_trend_up is None:
        return None

    return FeatureRow(
        symbol=symbol, date=as_of,
        momentum=mom, dual_momentum_score=dm.score, dual_momentum_trend_up=dm.trend_up,
        mr_rsi=mr.rsi, mr_band_position=mr.band_position, mr_sector_trend_up=mr.sector_trend_up,
        mr_sector_mapped=mr.sector_mapped,
        recon_days_since_added=recon.days_since_added, recon_recently_added=recon.recently_added,
        recon_data_known=recon.data_known,
    )


def build_dataset(
    symbol_precomputed: dict[str, SymbolPrecomputed],
    rebal_dates: list[datetime],
    universe_snapshots: list[UniverseSnapshot],
    reconstitution_events: list[ReconstitutionEvent],
) -> list[FeatureRow]:
    """One row per (eligible symbol, rebalance date) with enough warmed-up
    history, for every rebalance date EXCEPT THE LAST (which has no next
    date to compute a forward-return label from). Labels: top
    TOP_QUINTILE_PCT of that date's eligible universe by forward return to
    the NEXT rebalance date -> 1, else 0."""
    rows: list[FeatureRow] = []

    for i in range(len(rebal_dates) - 1):
        as_of = rebal_dates[i]
        next_date = rebal_dates[i + 1]
        eligible = eligible_symbols_asof(universe_snapshots, as_of)

        date_rows: list[FeatureRow] = []
        fwd_returns: list[float] = []
        for symbol in eligible:
            precomputed = symbol_precomputed.get(symbol)
            if precomputed is None:
                continue
            row = _row_at(symbol, precomputed, as_of, reconstitution_events)
            if row is None:
                continue
            entry = value_as_of(precomputed.series, as_of)
            exit_ = value_as_of(precomputed.series, next_date)
            if entry is None or exit_ is None or entry[0] <= 0:
                continue
            fwd_return = exit_[0] / entry[0] - 1.0
            date_rows.append(row)
            fwd_returns.append(fwd_return)

        if len(date_rows) < 5:   # too few eligible symbols this week to define a meaningful quintile
            continue

        sorted_returns = sorted(fwd_returns, reverse=True)
        cutoff_idx = max(0, int(len(sorted_returns) * TOP_QUINTILE_PCT) - 1)
        threshold = sorted_returns[cutoff_idx]
        for row, fwd_return in zip(date_rows, fwd_returns):
            row.label = 1 if fwd_return >= threshold else 0
            rows.append(row)

    return rows
