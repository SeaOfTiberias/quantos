"""
QuantOS — StatArb (BankNifty test bed): Factor Residuals and OU s-Score
───────────────────────────────────────────────────────────────────────
docs/STATARB_BANKNIFTY_METHODOLOGY.md "Model". Pure numpy, no I/O.

For each stock on each day: a leave-one-out family factor (M1 equal-
weighted peers, or M2 top-2 PCA eigenportfolios of the peers), a 60-day
regression of the stock on it, an AR(1)/Ornstein-Uhlenbeck fit of the
cumulative residual, and the Avellaneda-Lee s-score.

Every hedge is expressed as rupee weights h on the peer stocks, so hedge
P&L and forward residual returns are one dot product for both models.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Optional

import numpy as np

from core.pairs.backtest import FuturesDay

REG_WINDOW = 60
PCA_WINDOW = 252
N_PCA_FACTORS = 2
MAX_REVERSION_DAYS = 30.0   # speed filter: 1/(-ln b) < half the 60-day window
JUMP_BAND = (0.5, 2.0)      # core/rotation/reconstitution_gutcheck.py's corporate-action band

# HDFC Ltd merger: announced 2022-04-04, effective 2023-07-01 (+1 month buffer).
STRUCTURAL_BREAKS: dict[str, tuple[date, date]] = {
    "HDFCBANK": (date(2022, 4, 4), date(2023, 7, 31)),
}

PCA_FACTORS = {"M2": N_PCA_FACTORS, "PCA5": 5}


@dataclass(frozen=True)
class Panel:
    """Dense date x symbol arrays built from per-symbol FuturesDay series.
    NaN where a symbol has no near-month row that day."""
    dates:    list[date]
    symbols:  list[str]
    adj:      np.ndarray   # roll-adjusted close
    raw:      np.ndarray   # raw near-month close
    expiry:   np.ndarray   # object array of near-month expiry dates (None if missing)
    returns:  np.ndarray   # daily log return of adj; row 0 all NaN
    jump:     np.ndarray   # bool, raw close ratio vs previous row outside JUMP_BAND


def build_panel(series: dict[str, list[FuturesDay]]) -> Panel:
    symbols = sorted(series)
    dates = sorted({d.trade_date for s in series.values() for d in s})
    idx = {d: i for i, d in enumerate(dates)}
    T, N = len(dates), len(symbols)
    adj = np.full((T, N), np.nan)
    raw = np.full((T, N), np.nan)
    expiry = np.full((T, N), None, dtype=object)
    for j, sym in enumerate(symbols):
        for d in series[sym]:
            i = idx[d.trade_date]
            raw[i, j] = d.close
            adj[i, j] = d.adj_close if d.adj_close is not None else d.close
            expiry[i, j] = d.expiry
    with np.errstate(invalid="ignore", divide="ignore"):
        returns = np.full((T, N), np.nan)
        returns[1:] = np.log(adj[1:] / adj[:-1])
        ratio = np.full((T, N), np.nan)
        ratio[1:] = raw[1:] / raw[:-1]
    jump = (ratio < JUMP_BAND[0]) | (ratio > JUMP_BAND[1])
    return Panel(dates, symbols, adj, raw, expiry, returns, jump)


@dataclass(frozen=True)
class OUFit:
    b:          float
    m:          float
    sigma_eq:   float
    s:          float
    tau_days:   float   # 1/(-ln b), mean-reversion time in trading days

    @property
    def half_life_days(self) -> float:
        return math.log(2) * self.tau_days

    @property
    def speed_ok(self) -> bool:
        return self.tau_days < MAX_REVERSION_DAYS


def ou_fit(residuals: np.ndarray) -> Optional[OUFit]:
    """Avellaneda-Lee: AR(1) on the cumulative residual X; s = (X_end - m)/σ_eq.
    None when b is outside (0, 1) -- no mean reversion to measure."""
    x = np.cumsum(residuals)
    x0, x1 = x[:-1], x[1:]
    b, a = np.polyfit(x0, x1, 1)
    if not 0.0 < b < 1.0 - 1e-9:  # b numerically 1 = pure trend, tau meaningless
        return None
    zeta = x1 - (a + b * x0)
    sigma_eq = math.sqrt(float(np.var(zeta)) / (1.0 - b * b))
    if sigma_eq <= 0:
        return None
    m = a / (1.0 - b)
    return OUFit(b=float(b), m=float(m), sigma_eq=sigma_eq,
                 s=float((x[-1] - m) / sigma_eq), tau_days=-1.0 / math.log(b))


def regress(y: np.ndarray, factors: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """OLS of y (n,) on factors (n, k) with intercept -> (alpha, betas, residuals)."""
    X = np.column_stack([np.ones(len(y)), factors])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return float(coef[0]), coef[1:], y - X @ coef


def pca_weights(peer_returns: np.ndarray, n_factors: int = N_PCA_FACTORS) -> np.ndarray:
    """(n_peers, n_factors) eigenportfolio weights v_kj / σ_j from the
    correlation matrix of the peers' returns (paper's construction). Each
    eigenvector's sign is fixed so its weights sum positive -- otherwise the
    sign is arbitrary and a factor's beta would flip day to day."""
    sd = peer_returns.std(axis=0, ddof=1)
    corr = np.corrcoef(peer_returns, rowvar=False)
    vals, vecs = np.linalg.eigh(corr)
    w = vecs[:, np.argsort(vals)[::-1][:n_factors]] / sd[:, None]
    return w * np.where(w.sum(axis=0) < 0, -1.0, 1.0)


@dataclass(frozen=True)
class Score:
    symbol:     str
    model:      str
    s:          Optional[float]
    betas:      tuple[float, ...]
    fit:        Optional[OUFit]
    peer_idx:   tuple[int, ...]     # panel column indices of the hedge peers
    hedge:      tuple[float, ...]   # rupee weight per peer (same order), per rupee of stock
    excluded:   Optional[str] = None

    @property
    def speed_ok(self) -> bool:
        return self.fit is not None and self.fit.speed_ok

    @property
    def tradeable(self) -> bool:
        return self.excluded is None and self.s is not None and self.speed_ok


def _excluded_reason(panel: Panel, t: int, j: int) -> Optional[str]:
    lo = t - PCA_WINDOW + 1
    if lo < 1:
        return "insufficient_history"
    if np.isnan(panel.returns[lo:t + 1, j]).any():
        return "missing_data"
    if panel.jump[lo:t + 1, j].any():
        return "corp_action_jump"
    brk = STRUCTURAL_BREAKS.get(panel.symbols[j])
    if brk and brk[0] <= panel.dates[t] <= brk[1]:
        return "structural_break"
    return None


def exclusion_reasons(panel: Panel, t: int) -> list[Optional[str]]:
    """_excluded_reason for every column at row t -- computed once per day
    and shared across stocks (a 50-name universe would otherwise redo the
    49 peer checks for every stock)."""
    return [_excluded_reason(panel, t, j) for j in range(len(panel.symbols))]


def score(
    panel: Panel, t: int, j: int, model: str,
    reasons: Optional[list[Optional[str]]] = None,
    sectors: Optional[dict[str, str]] = None,
) -> Score:
    """s-score of panel column j at row t, using rows <= t only.

    Models: M1 (equal-weighted peers), M2 / PCA5 (leave-one-out PCA, 2 / 5
    eigenportfolios), MKT_SECTOR (equal-weighted all peers + equal-weighted
    same-sector peers; needs `sectors` {symbol: sector})."""
    sym = panel.symbols[j]
    if reasons is None:
        reasons = exclusion_reasons(panel, t)
    if reasons[j]:
        return Score(sym, model, None, (), None, (), (), excluded=reasons[j])

    lo_pca, lo_reg = t - PCA_WINDOW + 1, t - REG_WINDOW + 1
    peers = [k for k in range(len(panel.symbols)) if k != j
             and reasons[k] in (None, "structural_break")]
    # ^ A peer in its own structural-break window still moves with the
    # family; only data problems (gaps, jumps) disqualify it as a peer.
    if len(peers) < 3:
        return Score(sym, model, None, (), None, (), (), excluded="too_few_peers")

    y = panel.returns[lo_reg:t + 1, j]
    peer_ret = panel.returns[:, peers]
    if model == "M1":
        F = peer_ret[lo_reg:t + 1].mean(axis=1)[:, None]
        _, betas, resid = regress(y, F)
        hedge = np.full(len(peers), betas[0] / len(peers))
    elif model in PCA_FACTORS:
        W = pca_weights(peer_ret[lo_pca:t + 1], PCA_FACTORS[model])
        F = peer_ret[lo_reg:t + 1] @ W
        _, betas, resid = regress(y, F)
        hedge = W @ betas
    elif model == "MKT_SECTOR":
        sector = (sectors or {}).get(sym)
        same = [n for n, k in enumerate(peers) if sector and (sectors or {}).get(panel.symbols[k]) == sector]
        if len(same) < 2:
            return Score(sym, model, None, (), None, (), (), excluded="no_sector_peers")
        window = peer_ret[lo_reg:t + 1]
        F = np.column_stack([window.mean(axis=1), window[:, same].mean(axis=1)])
        _, betas, resid = regress(y, F)
        hedge = np.full(len(peers), betas[0] / len(peers))
        hedge[same] += betas[1] / len(same)
    else:
        raise ValueError(f"unknown model {model}")

    fit = ou_fit(resid)
    return Score(sym, model, fit.s if fit else None, tuple(float(b) for b in betas),
                 fit, tuple(peers), tuple(float(h) for h in hedge))
