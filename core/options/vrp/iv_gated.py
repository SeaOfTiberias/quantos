"""
QuantOS — IV-Gated Short Premium (strangle / straddle / iron condor)
─────────────────────────────────────────────────────────────────────
Implements docs/VRP_IV_GATED_METHODOLOGY.md (pre-committed 2026-10-06,
before any result existed). Reuses the original VRP pipeline wherever
the methodology says "unchanged": entry cycles and the 0.20-delta
strangle legs (strikes.py), the put-call-parity forward, and the
expiry-day settlement lookup (simulator.py). New here: the ATM straddle
and iron-condor wings, the trailing-percentile IV gate, the corrected
cost schedule, and return-on-margin stats with idle weeks zero-filled.

Pure functions only -- no I/O. scripts/backtest_vrp_iv_gated.py drives it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Optional

from core.options.greeks import ImpliedVolatilityError, compute_greeks, implied_volatility
from core.options.models import OptionType
from core.options.vrp.bhavcopy import BhavcopyOptionRow
from core.options.vrp.strikes import StrangleSelection, synthetic_forward

# ─── Pre-committed parameters (docs/VRP_IV_GATED_METHODOLOGY.md) ─────────
GATE_PERCENTILE = 0.67
GATE_LOOKBACK = 52
GATE_MIN_HISTORY = 40
WING_DELTA = 0.05
WING_DELTA_TOLERANCE = 0.04
WING_FALLBACK_PCT = 0.02
NAKED_MARGIN_PCT = 0.12
WEEKLY_ANNUALIZATION = 52

SEGMENT_A_END = date(2023, 7, 21)
SEGMENT_B_START, SEGMENT_B_END = date(2023, 7, 24), date(2026, 7, 22)
SEGMENT_C_START = date(2026, 7, 23)

ARMS = ("strangle", "straddle", "iron_condor")
PRIMARY_ARM = "strangle"

SHORT, LONG = -1, 1


# ─── Costs (corrected schedule -- see the methodology's "Costs") ─────────
BROKERAGE_PCT = 0.0003
SEBI_PCT = 0.000001
GST_PCT = 0.18
STAMP_BUY_PCT = 0.00003
_STT_SELL = [(date(2000, 1, 1), 0.0005), (date(2023, 4, 1), 0.000625),
             (date(2024, 10, 1), 0.001), (date(2026, 4, 1), 0.0015)]
_STT_EXERCISE = [(date(2000, 1, 1), 0.00125), (date(2026, 4, 1), 0.0015)]
_EXCHANGE = [(date(2000, 1, 1), 0.00053), (date(2024, 10, 1), 0.0003503)]


def _rate_asof(schedule: list, d: date) -> float:
    rate = schedule[0][1]
    for effective_from, r in schedule:
        if effective_from <= d:
            rate = r
    return rate


@dataclass(frozen=True)
class Leg:
    option_type:   OptionType
    strike:        float
    side:          int      # SHORT (-1) or LONG (+1)
    entry_premium: float
    method:        str      # how the strike was chosen: delta / atm / fallback_pct_otm

    def exit_value(self, settlement: float) -> float:
        if self.option_type == OptionType.CALL:
            return max(0.0, settlement - self.strike)
        return max(0.0, self.strike - settlement)


def leg_cost_points(leg: Leg, entry_date: date, expiry_date: date, settlement: float) -> float:
    """Round-trip cost of one leg in index points. Entry: brokerage +
    exchange + SEBI + GST, plus STT if sold or stamp duty if bought.
    Expiry: only exercise STT, and only on a LONG leg that finishes ITM --
    STT on exercise is the holder's charge, not the writer's."""
    p = leg.entry_premium
    brokerage = BROKERAGE_PCT * p
    exchange = _rate_asof(_EXCHANGE, entry_date) * p
    sebi = SEBI_PCT * p
    cost = brokerage + exchange + sebi + GST_PCT * (brokerage + exchange + sebi)
    cost += _rate_asof(_STT_SELL, entry_date) * p if leg.side == SHORT else STAMP_BUY_PCT * p
    if leg.side == LONG:
        cost += _rate_asof(_STT_EXERCISE, expiry_date) * leg.exit_value(settlement)
    return cost


# ─── Trades ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StructureTrade:
    arm:           str
    entry_date:    date
    expiry_date:   date
    forward:       float
    legs:          tuple
    margin_points: float
    settlement:    Optional[float]

    @property
    def entry_credit(self) -> float:
        return -sum(l.side * l.entry_premium for l in self.legs)

    @property
    def gross_pnl_points(self) -> Optional[float]:
        if self.settlement is None:
            return None
        return sum(l.side * (l.exit_value(self.settlement) - l.entry_premium) for l in self.legs)

    @property
    def net_pnl_points(self) -> Optional[float]:
        gross = self.gross_pnl_points
        if gross is None:
            return None
        return gross - sum(leg_cost_points(l, self.entry_date, self.expiry_date, self.settlement)
                           for l in self.legs)

    @property
    def return_on_margin(self) -> Optional[float]:
        net = self.net_pnl_points
        if net is None or self.margin_points <= 0:
            return None
        return net / self.margin_points

    @property
    def pct_of_credit(self) -> Optional[float]:
        net = self.net_pnl_points
        if net is None or self.entry_credit <= 0:
            return None
        return net / self.entry_credit * 100.0


@dataclass(frozen=True)
class AtmSelection:
    strike: float
    call:   BhavcopyOptionRow
    put:    BhavcopyOptionRow
    forward: float
    iv:     float           # mean of CE/PE implied vol, decimal


def select_atm(rows: list[BhavcopyOptionRow], expiry: date, dte: int) -> Optional[AtmSelection]:
    """ATM = the listed strike nearest the put-call-parity forward with
    both legs priced. IV is solved strictly: an un-invertible price makes
    the whole cycle's ATM IV unavailable rather than silently 18%."""
    expiry_rows = [r for r in rows if r.expiry == expiry]
    forward = synthetic_forward(expiry_rows)
    if forward is None:
        return None
    by_strike: dict[float, dict] = {}
    for r in expiry_rows:
        if r.close > 0:
            by_strike.setdefault(r.strike, {})[r.option_type] = r
    paired = [k for k, legs in by_strike.items() if len(legs) == 2]
    if not paired:
        return None
    strike = min(paired, key=lambda k: abs(k - forward))
    ce, pe = by_strike[strike][OptionType.CALL], by_strike[strike][OptionType.PUT]
    try:
        iv_c = implied_volatility(ce.close, forward, strike, dte, OptionType.CALL, strict=True)
        iv_p = implied_volatility(pe.close, forward, strike, dte, OptionType.PUT, strict=True)
    except ImpliedVolatilityError:
        return None
    return AtmSelection(strike=strike, call=ce, put=pe, forward=forward, iv=(iv_c + iv_p) / 2)


def select_wing(rows: list[BhavcopyOptionRow], expiry: date, forward: float, dte: int,
                short_strike: float, option_type: OptionType) -> Optional[tuple[float, BhavcopyOptionRow, str]]:
    """Long wing ~0.05 delta strictly beyond the short strike; else the
    listed strike nearest 2% beyond it. None if nothing is listed beyond."""
    is_call = option_type == OptionType.CALL
    beyond = {r.strike: r for r in rows
              if r.expiry == expiry and r.option_type == option_type and r.close > 0
              and (r.strike > short_strike if is_call else r.strike < short_strike)}
    if not beyond:
        return None
    target = WING_DELTA if is_call else -WING_DELTA
    best = None
    for k, r in beyond.items():
        try:
            iv = implied_volatility(r.close, forward, k, dte, option_type, strict=True)
        except ImpliedVolatilityError:
            continue
        gap = abs(compute_greeks(forward, k, dte, iv, option_type).delta - target)
        if best is None or gap < best[0]:
            best = (gap, k, r)
    if best is not None and best[0] <= WING_DELTA_TOLERANCE:
        return best[1], best[2], "delta"
    goal = short_strike * (1 + WING_FALLBACK_PCT) if is_call else short_strike * (1 - WING_FALLBACK_PCT)
    k = min(beyond, key=lambda s: abs(s - goal))
    return k, beyond[k], "fallback_pct_otm"


def build_trades(strangle: Optional[StrangleSelection], atm: Optional[AtmSelection],
                 rows: list[BhavcopyOptionRow], entry_date: date, expiry_date: date, dte: int,
                 settlement: Optional[float]) -> dict[str, StructureTrade]:
    """All three arms for one cycle -- whichever can be built that day."""
    out: dict[str, StructureTrade] = {}
    if strangle is not None:
        c, p = strangle.call, strangle.put
        short_legs = (Leg(OptionType.CALL, c.strike, SHORT, c.row.close, c.method),
                      Leg(OptionType.PUT, p.strike, SHORT, p.row.close, p.method))
        out["strangle"] = StructureTrade("strangle", entry_date, expiry_date, strangle.spot_estimate,
                                         short_legs, NAKED_MARGIN_PCT * strangle.spot_estimate, settlement)
        cw = select_wing(rows, expiry_date, strangle.spot_estimate, dte, c.strike, OptionType.CALL)
        pw = select_wing(rows, expiry_date, strangle.spot_estimate, dte, p.strike, OptionType.PUT)
        if cw and pw:
            legs = short_legs + (Leg(OptionType.CALL, cw[0], LONG, cw[1].close, cw[2]),
                                 Leg(OptionType.PUT, pw[0], LONG, pw[1].close, pw[2]))
            margin = max(cw[0] - c.strike, p.strike - pw[0])
            out["iron_condor"] = StructureTrade("iron_condor", entry_date, expiry_date,
                                                strangle.spot_estimate, legs, margin, settlement)
    if atm is not None:
        legs = (Leg(OptionType.CALL, atm.strike, SHORT, atm.call.close, "atm"),
                Leg(OptionType.PUT, atm.strike, SHORT, atm.put.close, "atm"))
        out["straddle"] = StructureTrade("straddle", entry_date, expiry_date, atm.forward,
                                         legs, NAKED_MARGIN_PCT * atm.forward, settlement)
    return out


# ─── The gate ────────────────────────────────────────────────────────────

def gate_states(ivs: list[Optional[float]]) -> list[Optional[bool]]:
    """Per cycle, in date order: None = warm-up / no IV that day (no trade
    in any arm), True = gate open, False = closed. Each cycle compares its
    own ATM IV only against the last GATE_LOOKBACK valid IVs from cycles
    strictly BEFORE it -- never itself, never anything later."""
    states: list[Optional[bool]] = []
    history: list[float] = []
    for iv in ivs:
        if iv is None or len(history) < GATE_MIN_HISTORY:
            states.append(None)
        else:
            window = history[-GATE_LOOKBACK:]
            pct = sum(1 for h in window if h < iv) / len(window)
            states.append(pct >= GATE_PERCENTILE)
        if iv is not None:
            history.append(iv)
    return states


def segment_of(d: date) -> str:
    if d <= SEGMENT_A_END:
        return "A"
    if SEGMENT_B_START <= d <= SEGMENT_B_END:
        return "B"
    return "C"


# ─── Stats ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ArmStats:
    eligible_cycles:   int
    trades:            int
    skipped_open:      int      # gate open but the arm couldn't be built / settled
    gate_runs:         int
    win_rate:          float
    profit_factor:     float
    sharpe:            float    # zero-filled weekly return-on-margin, annualized
    annual_return_pct: float    # mean weekly return * 52, as % of margin
    max_drawdown_pct:  float    # cumulative return-on-margin, % points
    worst_trade_pct:   float
    avg_pct_credit:    float
    top_quarter_share: Optional[float]   # largest quarter's share of total net return; None if total <= 0


def _quarter(d: date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def arm_stats(cycles: list[tuple[date, Optional[bool], Optional[StructureTrade]]], gated: bool) -> ArmStats:
    """`cycles`: (entry_date, gate_state, trade-or-None) for eligible cycles
    (gate_state is not None). Gated: trade only where the gate is open.
    Ungated: trade every eligible cycle. Untraded weeks contribute 0."""
    weekly: list[float] = []
    traded: list[StructureTrade] = []
    skipped = runs = 0
    prev_open = False
    for _, state, trade in cycles:
        take = state if gated else True
        if take and not prev_open:
            runs += 1
        prev_open = bool(take)
        r = trade.return_on_margin if (take and trade is not None) else None
        if take and r is None:
            skipped += 1
        if r is None:
            weekly.append(0.0)
        else:
            weekly.append(r)
            traded.append(trade)

    rets = [t.return_on_margin for t in traded]
    n = len(weekly)
    mean = sum(weekly) / n if n else 0.0
    std = math.sqrt(sum((w - mean) ** 2 for w in weekly) / (n - 1)) if n >= 2 else 0.0
    sharpe = mean / std * math.sqrt(WEEKLY_ANNUALIZATION) if std > 0 else 0.0
    wins, losses = sum(r for r in rets if r > 0), -sum(r for r in rets if r <= 0)
    pf = wins / losses if losses > 0 else (float("inf") if wins > 0 else 0.0)
    cum = peak = dd = 0.0
    for w in weekly:
        cum += w
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    total = sum(rets)
    share = None
    if total > 0:
        by_q: dict[str, float] = {}
        for t in traded:
            by_q[_quarter(t.entry_date)] = by_q.get(_quarter(t.entry_date), 0.0) + t.return_on_margin
        share = max(by_q.values()) / total
    pcts = [t.pct_of_credit for t in traded if t.pct_of_credit is not None]
    return ArmStats(
        eligible_cycles=n, trades=len(traded), skipped_open=skipped, gate_runs=runs,
        win_rate=sum(1 for r in rets if r > 0) / len(rets) if rets else 0.0,
        profit_factor=pf, sharpe=sharpe, annual_return_pct=mean * WEEKLY_ANNUALIZATION * 100,
        max_drawdown_pct=dd * 100, worst_trade_pct=min(rets) * 100 if rets else 0.0,
        avg_pct_credit=sum(pcts) / len(pcts) if pcts else 0.0, top_quarter_share=share,
    )


MIN_TRADES = 30


def verdict(gated: ArmStats, ungated: ArmStats) -> tuple[str, list[str]]:
    """The methodology's four criteria. Returns (PASS|FAIL|INCONCLUSIVE, reasons)."""
    checks = [
        (gated.profit_factor > 1.0 and gated.sharpe > 0.5,
         f"edge: PF {gated.profit_factor:.3f} > 1.0 and Sharpe {gated.sharpe:.3f} > 0.5"),
        (gated.sharpe > ungated.sharpe,
         f"gate beats always-on: gated Sharpe {gated.sharpe:.3f} > ungated {ungated.sharpe:.3f}"),
        (gated.top_quarter_share is not None and gated.top_quarter_share <= 0.5,
         "concentration: top quarter's share of net return "
         + ("n/a (total <= 0)" if gated.top_quarter_share is None else f"{gated.top_quarter_share:.0%}")
         + " <= 50%"),
    ]
    reasons = [("ok   " if ok else "FAIL ") + text for ok, text in checks]
    if gated.trades < MIN_TRADES:
        reasons.append(f"FAIL sample: {gated.trades} gated trades < {MIN_TRADES}")
        return "INCONCLUSIVE", reasons
    reasons.append(f"ok   sample: {gated.trades} gated trades >= {MIN_TRADES}")
    return ("PASS" if all(ok for ok, _ in checks) else "FAIL"), reasons
