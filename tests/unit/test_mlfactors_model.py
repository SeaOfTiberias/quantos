"""
ML Multi-Factor Stock Ranking — Model Unit Tests

Covers core/mlfactors/model.py: time-based (never random) train/test
splitting, that hyperparameter selection and fitting only ever touch rows
handed to them (no leakage across a split boundary the caller controls),
and that the target_basket_fn closure produced for backtest integration
actually ranks by the model's predicted probability.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.mlfactors.dataset import FeatureRow, build_symbol_precomputed  # noqa: E402
from core.mlfactors.model import (  # noqa: E402
    evaluate_auc,
    fit_model,
    make_target_basket_fn,
    predict_scores,
    time_based_split,
)
from core.brokers.base import OHLCV  # noqa: E402

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _synthetic_row(day_offset: int, symbol: str, signal: float, label: int) -> FeatureRow:
    """A FeatureRow with `signal` standing in for momentum (the feature
    with the most direct, easy-to-learn relationship to the label in this
    synthetic set) and every other feature held constant, so a fitted
    model's predicted probability should track `signal` monotonically."""
    return FeatureRow(
        symbol=symbol, date=START + timedelta(days=day_offset),
        momentum=signal, dual_momentum_score=0.0, dual_momentum_trend_up=True,
        mr_rsi=50.0, mr_band_position=0.5, mr_sector_trend_up=True, mr_sector_mapped=True,
        recon_days_since_added=3650.0, recon_recently_added=False, recon_data_known=True,
        label=label,
    )


def _synthetic_dataset(n_days: int, symbols_per_day: int = 6) -> list[FeatureRow]:
    """A dataset where higher `momentum` deterministically means label=1
    for the top 20% each day -- learnable by construction, so a fitted
    model's AUC should be meaningfully above 0.5."""
    rows = []
    for day in range(n_days):
        for i in range(symbols_per_day):
            signal = float(i) / symbols_per_day + 0.01 * (day % 3)   # small day-to-day jitter
            label = 1 if i == symbols_per_day - 1 else 0   # highest-signal symbol each day is the winner
            rows.append(_synthetic_row(day, f"SYM{i}", signal, label))
    return rows


# ─── time_based_split ─────────────────────────────────────────────────────

def test_time_based_split_is_strictly_chronological():
    rows = _synthetic_dataset(n_days=30)
    split_date = START + timedelta(days=20)
    train, test = time_based_split(rows, split_date)
    assert all(r.date < split_date for r in train)
    assert all(r.date >= split_date for r in test)
    assert len(train) + len(test) == len(rows)


def test_time_based_split_excludes_a_train_row_whose_label_peeks_past_the_split():
    """Regression: Fable's review of candidate 16's first cut found a row
    dated just before split_date whose LABEL came from a price on/after
    split_date still counted as train -- a real, if tiny, test-period leak."""
    split_date = START + timedelta(days=20)
    leaking_row = _synthetic_row(19, "LEAK", signal=0.5, label=1)
    leaking_row.label_date = split_date + timedelta(days=2)   # label price is IN the test period
    clean_row = _synthetic_row(19, "CLEAN", signal=0.5, label=1)
    clean_row.label_date = split_date - timedelta(days=1)     # label price is still pre-test

    train, test = time_based_split([leaking_row, clean_row], split_date)

    assert leaking_row not in train
    assert clean_row in train


def test_time_based_split_no_overlap():
    rows = _synthetic_dataset(n_days=30)
    split_date = START + timedelta(days=15)
    train, test = time_based_split(rows, split_date)
    assert set(id(r) for r in train).isdisjoint(set(id(r) for r in test))


# ─── fit_model / evaluate_auc ──────────────────────────────────────────────

def test_fit_model_learns_the_synthetic_signal():
    rows = _synthetic_dataset(n_days=60)
    train, test = time_based_split(rows, START + timedelta(days=45))
    model = fit_model(train, c=1.0)   # fixed C, bypass CV for a fast/deterministic test
    auc = evaluate_auc(model, test)
    assert auc > 0.7   # should comfortably beat random (0.5) on a learnable-by-construction signal


def test_evaluate_auc_nan_when_test_set_has_one_class():
    rows = [_synthetic_row(0, "A", 1.0, 1), _synthetic_row(0, "B", 0.0, 1)]  # both label=1
    train = _synthetic_dataset(n_days=30)
    model = fit_model(train, c=1.0)
    import math
    assert math.isnan(evaluate_auc(model, rows))


# ─── predict_scores / make_target_basket_fn ────────────────────────────────

def daily(prices: list) -> list:
    return [
        OHLCV(timestamp=START + timedelta(days=i), open=p, high=p * 1.01, low=p * 0.99,
              close=p, volume=1000)
        for i, p in enumerate(prices)
    ]


def _trending(base: float, daily_pct: float, n: int) -> list:
    prices = [base]
    for _ in range(n - 1):
        prices.append(prices[-1] * (1 + daily_pct))
    return prices


def test_target_basket_fn_ranks_by_predicted_probability():
    n = 420
    sector = daily(_trending(100.0, 0.001, n))
    precomputed = {
        "STRONG": build_symbol_precomputed(daily(_trending(100.0, 0.01, n)), sector, True),
        "WEAK": build_symbol_precomputed(daily(_trending(100.0, -0.005, n)), sector, True),
        "MID": build_symbol_precomputed(daily(_trending(100.0, 0.002, n)), sector, True),
    }
    rows = _synthetic_dataset(n_days=60)
    train, _ = time_based_split(rows, START + timedelta(days=60))
    model = fit_model(train, c=1.0)

    target_basket_fn = make_target_basket_fn(model, precomputed, reconstitution_events=[])
    as_of = START + timedelta(days=400)
    basket = target_basket_fn(symbol_series=None, as_of_date=as_of, top_n=2, eligible=set(precomputed.keys()))

    assert len(basket) == 2
    scores = predict_scores(model, precomputed, as_of, set(precomputed.keys()), reconstitution_events=[])
    assert scores[basket[0]] >= scores[basket[1]]   # basket order matches descending predicted probability
