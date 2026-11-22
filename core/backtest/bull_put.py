"""Bull put credit spread arithmetic for docs/NIFTY_SMC_OB_1H_BULLPUT_PREREG_2026-11-22.md (§3, §8).

Pure and deterministic: no pricing model, no data. The research script prices the legs and passes
the numbers in. Everything is per unit (index points); rupees = points x lot.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date

SHORT_OFFSET = -50          # short put = ATM - 50
WIDTH = 250                 # scored wing
WIDTH_ALT = 300             # reported wing
COST_PTS = 3.0              # scored round-trip cost for the whole spread (4 fills)
PROFIT_TAKE = 0.70          # reported: exit once 70% of the credit is captured


def atm(spot: float, step: int = 50) -> int:
    """round(spot / 50) x 50, half away from zero (Python's round is banker's rounding)."""
    q = spot / step
    n = int(q + 0.5) if q >= 0 else -int(-q + 0.5)
    return n * step


def strikes(spot: float, width: int = WIDTH) -> tuple[int, int]:
    s = atm(spot) + SHORT_OFFSET
    return s, s - width


@dataclass(frozen=True)
class SpreadResult:
    credit: float       # short - long at entry
    debit: float        # short - long at exit (cost to close)
    cost: float
    net: float          # credit - debit - cost
    max_risk: float     # width - credit
    r: float            # net / max_risk


def spread_result(short_in: float, long_in: float, short_out: float, long_out: float,
                  width: float = WIDTH, cost: float = COST_PTS) -> SpreadResult:
    credit = short_in - long_in
    debit = short_out - long_out
    max_risk = width - credit
    if not (0 < credit < width):
        raise ValueError(f"credit {credit:.2f} outside (0, {width})")
    net = credit - debit - cost
    return SpreadResult(credit, debit, cost, net, max_risk, net / max_risk)


def profit_take_hit(value: float, credit: float, frac: float = PROFIT_TAKE) -> bool:
    """True once the spread can be bought back for <= (1 - frac) of the credit."""
    return value <= (1.0 - frac) * credit


# ─── NIFTY lot size by contract (NSE circulars; rupees only, never in R) ──────
# A contract keeps the lot it was listed with until it expires, and monthlies changed on a different
# expiry from weeklies, so the lookup is by expiry date and contract kind.
#   75 -> 50: monthly from the Jul-2021 expiry (2021-07-29), weeklies from Aug-2021 (first 2021-08-05).
#   50 -> 25: effective 2024-04-26; first weekly 2024-05-02, first monthly 2024-05-30.
#   25 -> 75: first weekly 2025-01-02; last monthly at 25 = 2025-01-30, first monthly at 75 = 2025-02-27.
#   75 -> 65: last weekly at 75 = 2025-12-23, last monthly 2025-12-30; first weekly 2026-01-06.

def nifty_lot(expiry: date, monthly: bool) -> int:
    if expiry >= date(2026, 1, 6):
        return 65
    if expiry >= date(2025, 1, 2):
        return 25 if monthly and expiry <= date(2025, 1, 30) else 75
    if expiry >= date(2024, 5, 2):
        return 25
    if expiry >= date(2021, 7, 29):
        return 50
    return 75


# ─── put skew multiplier s(z) ─────────────────────────────────────────────────

@dataclass(frozen=True)
class Skew:
    """s(z) at bucket midpoints; linear between them, flat beyond the ends. z ascending."""
    z: tuple
    s: tuple

    def at(self, z: float) -> float:
        if z <= self.z[0]:
            return self.s[0]
        if z >= self.z[-1]:
            return self.s[-1]
        i = bisect_left(self.z, z)
        z0, z1, s0, s1 = self.z[i - 1], self.z[i], self.s[i - 1], self.s[i]
        return s0 + (s1 - s0) * (z - z0) / (z1 - z0)


FLAT = Skew((0.0,), (1.0,))
