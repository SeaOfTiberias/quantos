"""
Adjusted daily prices + all-time highs for the techno-funda candidate
──────────────────────────────────────────────────────────────────────
Rules from docs/TECHNO_FUNDA_PREREG_2026-11-01.md:

  - NSE equity bhavcopies 2010-01-01 .. 2026-10-23; series EQ, BE, BZ kept
    (only EQ days are tradable, but every series' highs count toward the ATH);
    ETFs dropped; symbols chained through NSE's symbol-change file.
  - Splits/bonuses back-adjusted from NSE's corporate-action lists 2010-2026.
  - An overnight move of -35% or worse that the list does not explain is
    adjusted only if the company's filings show the share count changing by
    the same ratio (within 4%). Otherwise the stock's record restarts there:
    a new SEGMENT, whose indicators and running high start afresh.
  - ATH: the running max of adjusted highs within the segment. Everything
    before the segment (raw 2000-2009 highs, earlier segments) sets an upper
    BOUND on the older adjusted high, since unknown splits/bonuses only scale
    old prices down. The ATH is known once the segment's running high reaches
    the bound; until then it is unknown and the stock is not eligible.

Prices stay continuous across segment breaks (P&L must see a real drop);
only indicators and the running high restart.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from core.fundamentals.pead.eq_bhavcopy import CUTOVER_DATE, DEFAULT_RAW_CACHE_DIR
from core.techno_funda.symbols import SymbolChain

SERIES = ("EQ", "BE", "BZ")
ACTION_FILES = (Path("data_cache/nse_corporate_actions_2010_2015.json"),
                Path("data_cache/nse_corporate_actions_2016_2023.json"),
                Path("data_cache/nse_corporate_actions_2024_2026.json"))
PRICES_FROM, PRICES_TO = date(2010, 1, 1), date(2026, 10, 23)
GAP, CONFIRM_TOL = 0.65, 0.04


def _is_etf(sym: pd.Series) -> pd.Series:
    return sym.str.endswith("BEES") | sym.str.contains("ETF")


def read_bhavcopy(path: Path, d: date) -> pd.DataFrame:
    """One day's EQ/BE/BZ rows: sym, series, o, h, l, c, vol, val (raw)."""
    with zipfile.ZipFile(path) as zf:
        df = pd.read_csv(io.BytesIO(zf.read(zf.namelist()[0])), dtype=str)
    if d >= CUTOVER_DATE:
        df = df[df["FinInstrmTp"] == "STK"]
        cols = {"TckrSymb": "sym", "SctySrs": "series", "OpnPric": "o", "HghPric": "h",
                "LwPric": "l", "ClsPric": "c", "TtlTradgVol": "vol", "TtlTrfVal": "val"}
    else:
        cols = {"SYMBOL": "sym", "SERIES": "series", "OPEN": "o", "HIGH": "h", "LOW": "l",
                "CLOSE": "c", "TOTTRDQTY": "vol", "TOTTRDVAL": "val"}
    df = df[list(cols)].rename(columns=cols)
    df["sym"], df["series"] = df["sym"].str.strip(), df["series"].str.strip()
    df = df[df["series"].isin(SERIES) & ~_is_etf(df["sym"])]
    for k in ("o", "h", "l", "c", "vol", "val"):
        df[k] = pd.to_numeric(df[k], errors="coerce")
    df = df.dropna()
    df = df[(df["c"] > 0) & (df["o"] > 0) & (df["h"] > 0)]
    df["date"] = pd.Timestamp(d)
    return df


def _canonicalise(df: pd.DataFrame, chain: SymbolChain) -> pd.DataFrame:
    renamed = df["sym"].isin(chain.renamed())
    if renamed.any():
        sub = df.loc[renamed, ["sym", "date"]]
        df.loc[renamed, "sym"] = [chain.canonical(s, d.date()) for s, d in zip(sub["sym"], sub["date"])]
    return df


def load_bars(chain: SymbolChain, raw_dir: Path = DEFAULT_RAW_CACHE_DIR,
              start: date = PRICES_FROM, end: date = PRICES_TO) -> pd.DataFrame:
    frames = []
    for p in sorted(raw_dir.glob("*.zip")):
        d = datetime.strptime(p.stem, "%Y%m%d").date()
        if start <= d <= end:
            frames.append(read_bhavcopy(p, d))
    df = _canonicalise(pd.concat(frames, ignore_index=True), chain)
    # EQ wins if a rename ever leaves two rows for one company-day
    df["eq"] = df["series"] == "EQ"
    df = df.sort_values(["sym", "date", "eq"]).drop_duplicates(["sym", "date"], keep="last")
    return df.drop(columns="eq").reset_index(drop=True)


def pre2010_highs(chain: SymbolChain, raw_dir: Path = DEFAULT_RAW_CACHE_DIR,
                  before: date = PRICES_FROM) -> dict[str, float]:
    """Max raw high per canonical symbol over every 2000-2009 bhavcopy, all series."""
    best: dict[str, float] = {}
    for p in sorted(raw_dir.glob("*.zip")):
        d = datetime.strptime(p.stem, "%Y%m%d").date()
        if d >= before:
            break
        with zipfile.ZipFile(p) as zf:
            df = pd.read_csv(io.BytesIO(zf.read(zf.namelist()[0])), dtype=str)
        df = df.rename(columns=str.strip)
        if "SYMBOL" not in df or "HIGH" not in df:
            continue
        h = pd.to_numeric(df["HIGH"], errors="coerce")
        for s, v in zip(df["SYMBOL"].str.strip(), h):
            if v == v and v > 0:
                s = chain.canonical(s, d)
                if v > best.get(s, 0.0):
                    best[s] = v
    return best


# ─── Corporate actions ────────────────────────────────────────────────────────

def action_factor(subject: str) -> Optional[float]:
    """Price factor for an equity bonus and/or face-value split, else None.
    Same rule as scripts/backtest_darvas_atr_stop_oos.py: bonus a:b -> b/(a+b),
    split Rs X to Rs Y -> Y/X, both -> the product. Debenture / preference-share
    bonuses do not touch the share price."""
    t = subject.lower()
    if "debenture" in t or "ncrps" in t or "preference" in t:
        return None
    f = 1.0
    m = re.search(r"bonus\W*(\d+)\s*:\s*(\d+)", t)
    if m:
        f *= int(m.group(2)) / (int(m.group(1)) + int(m.group(2)))
    m = re.search(r"rs\.?\s*(\d+(?:\.\d+)?)\D+?to\s*(?:rs|re)\.?\s*(\d+(?:\.\d+)?)", t)
    if m and ("split" in t or "sub" in t):
        f *= float(m.group(2)) / float(m.group(1))
    return None if f == 1.0 else f


def load_actions(chain: SymbolChain, files=ACTION_FILES) -> dict[str, list[tuple[pd.Timestamp, float]]]:
    seen, out = set(), defaultdict(list)
    for path in files:
        for a in json.loads(path.read_text(encoding="utf-8")):
            f = action_factor(a.get("subject", ""))
            if not f:
                continue
            ex = datetime.strptime(a["exDate"], "%d-%b-%Y").date()
            key = (a["symbol"].strip(), ex, a["subject"].strip().lower())
            if key in seen:
                continue
            seen.add(key)
            out[chain.canonical(a["symbol"].strip(), ex)].append((pd.Timestamp(ex), f))
    return out


# ─── Per-symbol adjustment, segments, ATH ─────────────────────────────────────

ShareRatio = Callable[[str, pd.Timestamp], Optional[float]]


def adjust_symbol(g: pd.DataFrame, actions: list[tuple[pd.Timestamp, float]],
                  share_ratio: ShareRatio, pre_high: float) -> tuple[pd.DataFrame, list[dict]]:
    """Adjust one symbol's bars (sorted by date). Returns the adjusted frame
    (adds mult, seg, ath, ath_known) and a log of every unexplained gap."""
    g = g.sort_values("date").reset_index(drop=True)
    dates = g["date"].to_numpy()
    n = len(g)
    mult = np.ones(n)
    for ex, f in actions:
        mult[dates < np.datetime64(ex)] *= f
    o_raw, c_raw = g["o"].to_numpy(), g["c"].to_numpy()

    gaps, breaks = [], []
    # scaling bars [:i] by a confirmed ratio leaves every other overnight ratio
    # unchanged, so the candidate gaps can be found once, up front
    ratios = (o_raw[1:] * mult[1:]) / (c_raw[:-1] * mult[:-1])
    for i in np.nonzero(ratios <= GAP)[0] + 1:
        g_ratio = ratios[i - 1]
        r = share_ratio(g["sym"].iat[0], pd.Timestamp(dates[i]))
        confirmed = bool(r is not None and abs(g_ratio / r - 1) < CONFIRM_TOL)
        gaps.append(dict(sym=g["sym"].iat[0], date=pd.Timestamp(dates[i]).date(),
                         move=round(float(g_ratio) - 1, 4), share_ratio=r, confirmed=confirmed))
        if confirmed:
            mult[:i] *= r
        else:
            breaks.append(i)

    g = g.copy()
    g["raw_c"] = c_raw
    for k in ("o", "h", "l", "c"):
        g[k] = g[k].to_numpy() * mult
    g["vol"] = g["vol"].to_numpy() / mult
    g["mult"] = mult

    seg = np.zeros(n, dtype=int)
    for b in breaks:
        seg[b:] += 1
    g["seg"] = seg
    h = g["h"].to_numpy()
    ath, known = np.empty(n), np.empty(n, dtype=bool)
    bound = pre_high * mult[0] if pre_high else 0.0      # 2000-2009 raw highs on this scale
    for s in range(seg[-1] + 1 if n else 0):
        idx = np.nonzero(seg == s)[0]
        if s > 0:
            bound = max(bound, h[:idx[0]].max())          # earlier segments: an upper bound only
        run = np.maximum.accumulate(h[idx])
        ath[idx], known[idx] = run, run >= bound
    g["ath"], g["ath_known"] = ath, known
    return g, gaps


def wilder_rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + gain / loss)


def indicators(g: pd.DataFrame) -> pd.DataFrame:
    """RSI14, EMA20, SMA5 volume, SMA50 traded value, previous close -- each
    restarted at every segment break."""
    parts = []
    for _, s in g.groupby("seg", sort=True):
        s = s.copy()
        c = s["c"]
        s["rsi"] = wilder_rsi(c)
        s["ema20"] = c.ewm(span=20, adjust=False, min_periods=20).mean()
        s["vol5"] = s["vol"].rolling(5).mean()
        s["val50"] = s["val"].rolling(50).mean()
        s["prev_c"] = c.shift(1)
        parts.append(s)
    return pd.concat(parts)
