"""
QuantOS — ML Multi-Factor Stock Ranking: Model (candidate 16)
──────────────────────────────────────────────────────────────
Time-based train/test split, train-only hyperparameter selection, a single
fixed model class (logistic regression — no post-hoc model-shopping, per
docs/ML_FACTOR_COMBINATION_METHODOLOGY.md), and a `target_basket_fn`
matching core/rotation/ranker.py's `rank_universe` signature so it plugs
directly into core/rotation/equity_curve.py's `simulate_portfolio`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from core.mlfactors.dataset import FEATURE_NAMES, FeatureRow, SymbolPrecomputed, _row_at, to_feature_vector
from core.rotation.nifty500_reconstitution import ReconstitutionEvent

# Grid searched via train-only TimeSeriesSplit CV -- fixed set, not tuned
# after seeing any test-period result (see methodology doc).
C_GRID = [0.01, 0.1, 1.0, 10.0]
CV_FOLDS = 5


def time_based_split(rows: list[FeatureRow], split_date: datetime) -> tuple[list[FeatureRow], list[FeatureRow]]:
    """TEST = every row whose OWN rebalance date is on/after split_date.
    TRAIN = every remaining row whose LABEL price (drawn from the row's
    label_date, the next rebalance date) is also strictly before
    split_date -- gating on `r.date` alone would leak one rebalance week's
    worth of test-period closing prices into the last training row(s)'
    labels (confirmed live 2026-07-27, Fable's review of the first cut of
    this candidate: ~1% of train rows, immaterial to the fit, but a real,
    avoidable violation of "never touch the test period more than once").
    The test set itself is touched only once, by the caller's final
    evaluation -- never inside this module."""
    test = [r for r in rows if r.date >= split_date]
    train = [r for r in rows if r.date < split_date
             and (r.label_date is None or r.label_date < split_date)]
    return train, test


def _to_arrays(rows: list[FeatureRow]) -> tuple[np.ndarray, np.ndarray]:
    X = np.array([to_feature_vector(r) for r in rows])
    y = np.array([r.label for r in rows])
    return X, y


def select_hyperparameter(train_rows: list[FeatureRow]) -> float:
    """Picks C via time-ordered cross-validation WITHIN train_rows only
    (sklearn's TimeSeriesSplit on rows pre-sorted by date) -- the test set
    this module's caller holds out is never touched here."""
    sorted_rows = sorted(train_rows, key=lambda r: r.date)
    X, y = _to_arrays(sorted_rows)
    tscv = TimeSeriesSplit(n_splits=CV_FOLDS)

    best_c, best_auc = C_GRID[0], -1.0
    for c in C_GRID:
        aucs = []
        for train_idx, val_idx in tscv.split(X):
            if len(set(y[train_idx])) < 2 or len(set(y[val_idx])) < 2:
                continue   # a fold with only one class can't score AUC
            pipe = Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression(C=c, max_iter=1000))])
            pipe.fit(X[train_idx], y[train_idx])
            proba = pipe.predict_proba(X[val_idx])[:, 1]
            aucs.append(roc_auc_score(y[val_idx], proba))
        if aucs:
            avg_auc = sum(aucs) / len(aucs)
            if avg_auc > best_auc:
                best_auc, best_c = avg_auc, c
    return best_c


@dataclass
class TrainedModel:
    pipeline: Pipeline
    c: float
    feature_names: list[str]


def fit_model(train_rows: list[FeatureRow], c: Optional[float] = None) -> TrainedModel:
    """Fits the one pre-registered model class (StandardScaler +
    L2-regularized LogisticRegression) on train_rows. `c`, if not given, is
    selected via select_hyperparameter (train-only CV)."""
    if c is None:
        c = select_hyperparameter(train_rows)
    X, y = _to_arrays(train_rows)
    pipeline = Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression(C=c, max_iter=1000))])
    pipeline.fit(X, y)
    return TrainedModel(pipeline=pipeline, c=c, feature_names=list(FEATURE_NAMES))


def evaluate_auc(model: TrainedModel, rows: list[FeatureRow]) -> float:
    X, y = _to_arrays(rows)
    if len(set(y)) < 2:
        return float("nan")
    proba = model.pipeline.predict_proba(X)[:, 1]
    return roc_auc_score(y, proba)


def predict_scores(
    model: TrainedModel,
    symbol_precomputed: dict[str, SymbolPrecomputed],
    as_of: datetime,
    eligible,
    reconstitution_events: list[ReconstitutionEvent],
) -> dict[str, float]:
    """Predicted top-quintile probability per eligible, warmed-up symbol at
    `as_of` -- the model's actual ranking score."""
    scores: dict[str, float] = {}
    for symbol in eligible:
        precomputed = symbol_precomputed.get(symbol)
        if precomputed is None:
            continue
        row = _row_at(symbol, precomputed, as_of, reconstitution_events)
        if row is None:
            continue
        X = np.array([to_feature_vector(row)])
        scores[symbol] = float(model.pipeline.predict_proba(X)[0, 1])
    return scores


def make_target_basket_fn(
    model: TrainedModel,
    symbol_precomputed: dict[str, SymbolPrecomputed],
    reconstitution_events: list[ReconstitutionEvent],
):
    """Returns a function matching core/rotation/ranker.py's rank_universe
    signature -- (symbol_series, as_of_date, top_n, eligible=None) -> list[str]
    -- so it plugs directly into equity_curve.py's simulate_portfolio via
    its target_basket_fn parameter. `symbol_series` is accepted (for
    signature compatibility with the caller) but unused: this closure
    ranks off symbol_precomputed/model instead, captured at construction
    time from the SAME underlying daily candles the caller's symbol_series
    was built from."""

    def target_basket_fn(symbol_series, as_of_date: datetime, top_n: int, eligible=None) -> list[str]:
        universe = eligible if eligible is not None else symbol_precomputed.keys()
        scores = predict_scores(model, symbol_precomputed, as_of_date, universe, reconstitution_events)
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        return [symbol for symbol, _ in ranked[:top_n]]

    return target_basket_fn
