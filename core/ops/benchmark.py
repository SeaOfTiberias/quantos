"""The systems against the index funds (execution plan E4). Pure: data in, dicts out.

Household rule: a system that can't beat a Nifty200 Momentum 30 index fund after costs doesn't get
capital; the fund does.

**No peeking.** Each strategy section is LOCKED until that strategy's own frozen gate opens:
- Darvas: the 20th closed paper trade (docs/DARVAS_GO_NO_GO_2026-11.md).
- Momentum walk-forward: 4 completed quarters (docs/MOMENTUM_TURNOVER_WALKFORWARD_METHODOLOGY.md).
A locked section carries counts and the index returns over the strategy's span, never its returns.

Conventions:
- Index return over a trade: close of the last session before the entry date to the close of the
  exit date (the Darvas executor enters at or near the open and exits intraday or at the close).
- Index prices are NSE price indices, not total return; the report says so.
- The index fund carries an assumed expense ratio, pro rata by calendar days. Tax isn't modelled.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

import pandas as pd

DARVAS_GATE_TRADES = 20
MOMENTUM_GATE_QUARTERS = 4
# Assumed index-fund expense ratios (% a year), labelled as assumptions in every report.
FUND_TER = {"NIFTY": 0.20, "NIFTY200MOM30": 0.40}
INDEX_LABEL = {"NIFTY": "Nifty 50", "NIFTY200MOM30": "Nifty200 Momentum 30"}


def _closes(df: pd.DataFrame) -> pd.Series:
    s = pd.Series(df["c"].astype(float).values, index=pd.to_datetime(df["date"]).dt.date)
    return s[~s.index.duplicated(keep="last")].sort_index()


def close_on_or_before(df: pd.DataFrame, d: date) -> Optional[float]:
    s = _closes(df)
    s = s[s.index <= d]
    return float(s.iloc[-1]) if len(s) else None


def index_return(df: pd.DataFrame, entry: date, exit_: date) -> Optional[float]:
    """Close of the last session before `entry` to the close on or before `exit_`.
    None when the index has no bar on or before either end (e.g. before its history starts)."""
    s = _closes(df)
    before = s[s.index < entry]
    upto = s[s.index <= exit_]
    if not len(before) or not len(upto) or upto.index[-1] < entry:
        return None
    return float(upto.iloc[-1]) / float(before.iloc[-1]) - 1


def fund_return(index_ret: Optional[float], start: date, end: date, ter_pct: float) -> Optional[float]:
    if index_ret is None:
        return None
    return index_ret - ter_pct / 100 * max(0, (end - start).days) / 365


def quarters_completed(start: date, today: date) -> int:
    """Quarter ends (03-31, 06-30, 09-30, 12-31) strictly after `start` and on or before `today`."""
    n, y = 0, start.year
    while True:
        for m, d in ((3, 31), (6, 30), (9, 30), (12, 31)):
            q = date(y, m, d)
            if q > today:
                return n
            if q > start:
                n += 1
        y += 1


@dataclass(frozen=True)
class DarvasTrade:
    symbol: str
    entry: date
    exit: date
    entry_price: float
    exit_price: float


def darvas_section(closed: list[DarvasTrade], n_open: int, idx: dict[str, pd.DataFrame], today: date,
                   net_fn: Callable[[float, float], float], gate: int = DARVAS_GATE_TRADES) -> dict:
    """Per trade: net (net_fn(entry, exit), the backtest's Stressed costs) against each index fund over
    the same dates. LOCKED (no strategy return computed at all) until `gate` closed trades."""
    first = min((t.entry for t in closed), default=None)
    out = dict(name="Darvas ATR-stop, Bucket B (paper)", closed=len(closed), open=n_open, gate=gate,
               locked=len(closed) < gate, since=first.isoformat() if first else None)
    span = {s: fund_return(index_return(df, first, today), first, today, FUND_TER.get(s, 0.0))
            for s, df in idx.items()} if first else {}
    out["index_since_first_entry"] = span
    if out["locked"]:
        out["note"] = (f"{len(closed)} of {gate} closed trades: returns stay unread until the "
                       f"{gate}th closes (docs/DARVAS_GO_NO_GO_2026-11.md).")
        return out
    rows = []
    for t in closed:
        net = net_fn(t.entry_price, t.exit_price)
        r = dict(symbol=t.symbol, entry=t.entry.isoformat(), exit=t.exit.isoformat(), net=net)
        for s, df in idx.items():
            f = fund_return(index_return(df, t.entry, t.exit), t.entry, t.exit, FUND_TER.get(s, 0.0))
            r[s] = f
            r[f"excess_{s}"] = None if f is None else net - f
        rows.append(r)
    out["trades"] = rows
    out["mean_net"] = sum(r["net"] for r in rows) / len(rows)
    for s in idx:
        ex = [r[f"excess_{s}"] for r in rows if r[f"excess_{s}"] is not None]
        out[f"mean_excess_{s}"] = sum(ex) / len(ex) if ex else None
        out[f"beat_{s}"] = sum(x > 0 for x in ex)
        out[f"n_{s}"] = len(ex)
    return out


def momentum_section(state: dict, idx: dict[str, pd.DataFrame], today: date,
                     gate: int = MOMENTUM_GATE_QUARTERS) -> dict:
    """The walk-forward's own quarter-end marks (state["equity_curve"]) against each index fund from
    its first mark. LOCKED until `gate` quarters have completed since the first mark."""
    curve = sorted(state.get("equity_curve") or [], key=lambda p: p["date"])
    out = dict(name="Momentum walk-forward, candidate 11 (paper)", gate=gate,
               positions=len(state.get("positions") or {}), closed=len(state.get("closed_trades") or []))
    if not curve:
        return dict(out, locked=True, quarters=0, note="No equity mark yet.")
    start = date.fromisoformat(curve[0]["date"][:10])
    q = quarters_completed(start, today)
    out.update(since=start.isoformat(), quarters=q, locked=q < gate)
    out["index_since_start"] = {s: fund_return(index_return(df, start, today), start, today,
                                               FUND_TER.get(s, 0.0)) for s, df in idx.items()}
    if out["locked"]:
        out["note"] = (f"{q} of {gate} quarters completed: no verdict and no return read before "
                       f"{gate} (docs/MOMENTUM_TURNOVER_WALKFORWARD_METHODOLOGY.md).")
        return out
    last = curve[-1]
    end = date.fromisoformat(last["date"][:10])
    initial = float(state.get("initial_capital") or curve[0]["equity"])
    ret = float(last["equity"]) / initial - 1
    out.update(marked_to=end.isoformat(), ret=ret)
    for s, df in idx.items():
        f = fund_return(index_return(df, start, end), start, end, FUND_TER.get(s, 0.0))
        out[s] = f
        out[f"excess_{s}"] = None if f is None else ret - f
    return out


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:+.2%}"


def render_text(report: dict) -> str:
    """Telegram text. Locked sections show counts and index returns only."""
    lines = [f"QuantOS benchmark report, {report['as_of']} (E4)",
             "Household rule: no capital for a system that can't beat the Nifty200 Momentum 30 fund after costs.",
             "Index funds: NSE price index (not total return) less an assumed TER "
             + ", ".join(f"{INDEX_LABEL.get(s, s)} {t:.2f}%" for s, t in FUND_TER.items()) + "/yr. Tax not modelled.", ""]
    for sec in (report["darvas"], report["momentum"]):
        lines.append(sec["name"])
        if sec.get("error"):
            lines += [f"  error: {sec['error']}", ""]
            continue
        if sec["name"].startswith("Darvas"):
            lines.append(f"  closed {sec['closed']}, open {sec['open']}, since {sec.get('since') or '-'}")
            span = sec.get("index_since_first_entry") or {}
        else:
            lines.append(f"  quarters {sec.get('quarters', 0)} of {sec['gate']}, holdings {sec['positions']}, "
                         f"since {sec.get('since') or '-'}")
            span = sec.get("index_since_start") or {}
        if span:
            lines.append("  index funds over the same span: "
                         + ", ".join(f"{INDEX_LABEL.get(s, s)} {_pct(v)}" for s, v in span.items()))
        if sec["locked"]:
            lines.append(f"  LOCKED: {sec['note']}")
        elif sec["name"].startswith("Darvas"):
            lines.append(f"  mean net per trade {_pct(sec['mean_net'])}")
            for s in FUND_TER:
                if f"mean_excess_{s}" in sec:
                    lines.append(f"  vs {INDEX_LABEL.get(s, s)} fund: mean excess {_pct(sec[f'mean_excess_{s}'])}, "
                                 f"beat it {sec[f'beat_{s}']} of {sec[f'n_{s}']}")
        else:
            lines.append(f"  return to {sec['marked_to']} {_pct(sec['ret'])}")
            for s in FUND_TER:
                if s in sec:
                    lines.append(f"  vs {INDEX_LABEL.get(s, s)} fund {_pct(sec[s])}: excess {_pct(sec[f'excess_{s}'])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
