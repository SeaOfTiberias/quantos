"""
Daily panel for the techno-funda candidate: adjusted prices + point-in-time
fundamentals + every pre-registered flag, one row per (symbol, day).

Built once and cached (data_cache/techno_funda/); the gate checks and the
backtest both read the cache. Rebuild with build(refresh=True) after new data.
"""

from __future__ import annotations

import pickle
from bisect import bisect_left
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from core.techno_funda import fundamentals as fu
from core.techno_funda import prices as pr
from core.techno_funda.symbols import SymbolChain

CACHE = Path("data_cache/techno_funda/panel.pkl")
MCAP_LO, MCAP_HI = 100 * 1e7, 20_000 * 1e7          # Rs 100 Cr .. Rs 20,000 Cr
LIQ_RS = 50 * 1e5                                   # Rs 50 lakh
ATH_FRAC, RSI_LO, RSI_HI = 0.85, 50.0, 65.0
GROWTH_MIN, OPM_MIN = 0.15, 0.15
EXIT_RSI, EXIT_ATH = 45.0, 0.75


def share_ratio_fn(filings: list[fu.Filing]):
    """(symbol, gap day) -> shares before / shares after, from the filings for
    the last quarter ending before the gap and the first ending on/after it."""
    by_sym: dict[str, dict] = defaultdict(dict)
    for f in sorted(filings, key=lambda f: f.broadcast):
        if f.financial is False and f.quarter and f.quarter.shares:
            by_sym[f.symbol][f.period_end] = f.quarter.shares     # latest version wins
    index = {s: (sorted(d), d) for s, d in by_sym.items()}

    def ratio(sym: str, day: pd.Timestamp):
        if sym not in index:
            return None
        ends, shares = index[sym]
        i = bisect_left(ends, day.date())
        if i == 0 or i == len(ends):
            return None
        return shares[ends[i - 1]] / shares[ends[i]]
    return ratio


def build(refresh: bool = False) -> dict:
    if CACHE.exists() and not refresh:
        return pickle.loads(CACHE.read_bytes())
    chain = SymbolChain.load()
    filings = fu.load_filings(chain)
    states = fu.all_states(filings)
    ratio = share_ratio_fn(filings)
    actions = pr.load_actions(chain)
    pre = pr.pre2010_highs(chain)
    bars = pr.load_bars(chain)

    parts, gaps = [], []
    for sym, g in bars.groupby("sym", sort=False):
        adj, gl = pr.adjust_symbol(g, actions.get(sym, []), ratio, pre.get(sym, 0.0))
        parts.append(pr.indicators(adj))
        gaps += gl
    df = pd.concat(parts, ignore_index=True)
    df["date"] = df["date"].astype("datetime64[ns]")

    st = pd.DataFrame([dict(sym=s, **asdict(x)) for s, xs in states.items() for x in xs])
    st["effective"] = pd.to_datetime(st["effective"]).astype("datetime64[ns]")
    df = df.sort_values("date")
    df = pd.merge_asof(df, st.sort_values("effective"), left_on="date", right_on="effective",
                       by="sym", direction="backward")

    # market cap: shares x adjusted close / mult at the quarter end, same segment only
    qe = df[["sym", "quarter_end"]].dropna().drop_duplicates()
    qe["qe_ts"] = pd.to_datetime(qe["quarter_end"]).astype("datetime64[ns]")
    ref = df[["sym", "date", "mult", "seg"]].rename(columns={"date": "qe_ts", "mult": "mult_pe", "seg": "seg_pe"})
    qe = pd.merge_asof(qe.sort_values("qe_ts"), ref.sort_values("qe_ts"), on="qe_ts", by="sym",
                       direction="backward")
    df = df.merge(qe[["sym", "quarter_end", "mult_pe", "seg_pe"]], on=["sym", "quarter_end"], how="left")
    same_seg = df["seg_pe"] == df["seg"]
    df["mcap"] = np.where(same_seg, df["shares"] * df["c"] / df["mult_pe"], np.nan)

    df = flags(df)
    last_bar = df.groupby("sym")["date"].max()
    out = dict(panel=df.sort_values(["date", "sym"]).reset_index(drop=True), gaps=pd.DataFrame(gaps),
               last_bar=last_bar, n_filings=len(filings), pre2010=len(pre),
               filings=pd.DataFrame([dict(symbol=f.symbol, broadcast=f.broadcast, period_end=f.period_end,
                                          consolidated=f.consolidated, financial=f.financial, feed=f.feed,
                                          key=f.key, parse_error=f.parse_error, relating=f.relating,
                                          has_quarter=f.quarter is not None,
                                          **{f"q_{k}": v for k, v in (asdict(f.quarter) if f.quarter else {}).items()},
                                          **{f"y_{k}": v for k, v in (asdict(f.ytd) if f.ytd else {}).items()})
                                     for f in filings]))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(pickle.dumps(out))
    return out


def flags(df: pd.DataFrame) -> pd.DataFrame:
    c = df["c"]
    df["univ"] = ((df["series"] == "EQ") & (df["financial"] == False)  # noqa: E712
                  & (df["mcap"] > MCAP_LO) & (df["mcap"] < MCAP_HI) & (df["val50"] > LIQ_RS))
    df["t1"] = df["ath_known"] & (c > ATH_FRAC * df["ath"])
    df["t2"] = (df["rsi"] > RSI_LO) & (df["rsi"] < RSI_HI)
    df["t3"] = c > df["prev_c"]
    df["t4"] = df["vol"] > df["vol5"]
    df["f1"] = df["growth"] > GROWTH_MIN
    df["f2"] = df["opm"] > OPM_MIN
    df["price_sig"] = df["univ"] & df["t1"] & df["t2"] & df["t3"] & df["t4"]
    df["sig_f1"] = df["price_sig"] & df["f1"]
    df["sig"] = df["sig_f1"] & df["f2"]
    df["rank"] = c / df["ath"]
    df["exit_sig"] = (c < df["ema20"]) | (df["rsi"] < EXIT_RSI) | (c < EXIT_ATH * df["ath"])
    return df
