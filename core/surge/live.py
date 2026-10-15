"""
QuantOS — Candidate 23b: forward paper test of L2W4 bull call spreads (pure part)
──────────────────────────────────────────────────────────────────────────────────
docs/SURGE_23B_METHODOLOGY.md. Expiry and strike choice, quote-based paper
fills, the exit rule, the JSONL position store and the verdict maths. No
broker calls here; scripts/run_surge_23b.py does the fetching. Read-only:
nothing in this package can place an order.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

from core.backtest.parser import BacktestTrade, _compute_metrics
from core.surge.spreads import statutory_cost

SURGE_PCT = 5.0
LONG_OFFSET = 2          # L2
WIDTH_STRIKES = 4        # W4
MIN_WEEKDAYS_TO_EXPIRY = 5
HOLD_SESSIONS = 8
COOLDOWN_SESSIONS = 10
HISTORY_SESSIONS = 252
MIN_CLOSED = 60
STRUCTURE = f"L{LONG_OFFSET}W{WIDTH_STRIKES}"


def store_dir() -> Path:
    return Path.home() / ".quantos" / "surge_23b"


# ─── Selection ──────────────────────────────────────────────────────────────

def weekdays_after(today: date, end: date) -> int:
    """Weekdays in (today, end], counting `end` itself."""
    n, d = 0, today
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def choose_expiry(expiries: list[tuple[date, str]], today: date) -> Optional[tuple[date, str]]:
    for exp, epoch in sorted(expiries):
        if weekdays_after(today, exp) >= MIN_WEEKDAYS_TO_EXPIRY:
            return exp, epoch
    return None


def is_fresh_52w_high(prior_closes: list[float], price: float) -> bool:
    """True when `price` is at or above the max of the prior 252 daily
    closes. Fewer than 252 closes -> True (not enough history: skip)."""
    window = prior_closes[-HISTORY_SESSIONS:]
    return len(window) < HISTORY_SESSIONS or price >= max(window)


@dataclass(frozen=True)
class Leg:
    symbol: str
    strike: float
    bid: float
    ask: float
    ltp: float
    volume: float = 0.0
    oi: float = 0.0

    @property
    def two_sided(self) -> bool:
        return self.bid > 0 and self.ask > 0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2 if self.two_sided else self.ltp


def pick_legs(calls: list[Leg], spot: float) -> tuple[Optional[Leg], Optional[Leg], str]:
    """(long, short, reason). ATM = the listed strike nearest `spot` (ties
    to the lower strike); long = ATM + 2 strikes, short = long + 4."""
    calls = sorted(calls, key=lambda c: c.strike)
    if not calls:
        return None, None, "no call strikes in chain"
    atm = min(range(len(calls)), key=lambda i: (abs(calls[i].strike - spot), calls[i].strike))
    il, ish = atm + LONG_OFFSET, atm + LONG_OFFSET + WIDTH_STRIKES
    if ish >= len(calls):
        return None, None, "short strike beyond the strikes returned"
    long_, short = calls[il], calls[ish]
    if not (long_.two_sided and short.two_sided):
        return long_, short, "a leg has no two-sided quote"
    debit = long_.ask - short.bid
    if not 0 < debit < short.strike - long_.strike:
        return long_, short, f"real debit {debit:.2f} outside (0, width)"
    return long_, short, ""


# ─── Position store ─────────────────────────────────────────────────────────

@dataclass
class Position:
    symbol: str
    entry_date: str
    expiry: str
    expiry_epoch: str
    lot: int
    spot_entry: float
    long: dict
    short: dict
    debit_real: float
    debit_mid: float
    market: dict = field(default_factory=dict)
    sessions_held: int = 0
    last_session: str = ""
    exit_date: str = ""
    spot_exit: float = 0.0
    long_exit: dict = field(default_factory=dict)
    short_exit: dict = field(default_factory=dict)
    exit_flag: str = ""          # "" | "ltp_fallback" | "missing_quote"

    @property
    def open(self) -> bool:
        return not self.exit_date

    @property
    def width(self) -> float:
        return self.short["strike"] - self.long["strike"]


def load_positions(path: Path) -> list[Position]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(Position(**json.loads(line)))
    return out


def save_positions(path: Path, positions: list[Position]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(asdict(p)) + "\n" for p in positions), encoding="utf-8")
    tmp.replace(path)


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def in_cooldown(positions: list[Position], symbol: str, sessions_since: dict[str, int]) -> bool:
    """sessions_since: {entry_date: sessions elapsed since that date}."""
    return any(p.symbol == symbol and sessions_since.get(p.entry_date, 10**6) <= COOLDOWN_SESSIONS
               for p in positions)


def exit_due(p: Position, today: date) -> bool:
    return p.sessions_held >= HOLD_SESSIONS or weekdays_after(today, date.fromisoformat(p.expiry)) <= 1


def exit_value(leg: Optional[Leg], side: str) -> tuple[float, str]:
    """Paper exit at the quote: long legs sell at the bid, short legs buy
    back at the ask; with no two-sided quote, the last traded price."""
    if leg is None:
        return float("nan"), "missing_quote"
    if leg.two_sided:
        return (leg.bid if side == "long" else leg.ask), ""
    return leg.ltp, "ltp_fallback"


# ─── Verdict ────────────────────────────────────────────────────────────────

def trade_return(p: Position) -> Optional[tuple[float, float, float]]:
    """(gross, costs, return on risk) per share, real fills; None if open/unpriced."""
    if p.open or not p.long_exit or not p.short_exit:
        return None
    vl, vs = p.long_exit.get("value"), p.short_exit.get("value")
    if vl is None or vs is None or (isinstance(vl, float) and math.isnan(vl)) or \
            (isinstance(vs, float) and math.isnan(vs)):
        return None
    gross = (vl - vs) - p.debit_real
    costs = statutory_cost(p.long["ask"], p.short["bid"], vl, vs, p.lot,
                           date.fromisoformat(p.entry_date), date.fromisoformat(p.exit_date))
    return gross, costs, (gross - costs) / p.debit_real


@dataclass
class Verdict:
    closed: int
    open: int
    ready: bool
    passed: Optional[bool]
    profit_factor: float = 0.0
    sharpe: float = 0.0
    mean_ret: float = 0.0
    t_stat: float = 0.0
    lines: list[str] = field(default_factory=list)


def evaluate(positions: list[Position]) -> Verdict:
    priced = [(p, r) for p in positions if (r := trade_return(p)) is not None]
    n_open = sum(1 for p in positions if p.open)
    if len(priced) < MIN_CLOSED:
        return Verdict(len(priced), n_open, False, None,
                       lines=[f"{len(priced)} of {MIN_CLOSED} closed trades -- no verdict, no P&L reported."])
    bt = []
    for i, (p, (gross, costs, _)) in enumerate(sorted(priced, key=lambda x: x[0].entry_date)):
        bt.append(BacktestTrade(
            trade_num=i + 1, direction="Long", qty=1,
            entry_date=datetime.fromisoformat(p.entry_date), entry_price=100.0,
            exit_date=datetime.fromisoformat(p.exit_date), exit_price=100.0 * (1 + gross / p.debit_real),
            profit=100.0 * gross / p.debit_real, profit_pct=100.0 * gross / p.debit_real, cum_profit=0.0,
            bars_held=max(p.sessions_held, 1), costs=100.0 * costs / p.debit_real))
    m = _compute_metrics(bt)
    by_date: dict[str, list[float]] = {}
    for p, (_, _, r) in priced:
        by_date.setdefault(p.entry_date, []).append(r)
    dm = np.array([np.mean(v) for v in by_date.values()])
    t = float(dm.mean() / (dm.std(ddof=1) / math.sqrt(len(dm)))) if len(dm) > 1 and dm.std(ddof=1) > 0 else 0.0
    mean_ret = float(np.mean([r for _, (_, _, r) in priced]))
    checks = {"PF > 1.0": m.profit_factor > 1.0, "Sharpe > 0.5": m.sharpe_ratio > 0.5,
              "mean return on risk > 0 with t >= 1.5": mean_ret > 0 and t >= 1.5}
    return Verdict(len(priced), n_open, True, all(checks.values()), m.profit_factor, m.sharpe_ratio,
                   mean_ret, t, [f"{k}: {'pass' if v else 'FAIL'}" for k, v in checks.items()])
