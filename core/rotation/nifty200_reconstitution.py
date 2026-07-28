"""
QuantOS — Nifty 200 point-in-time membership reconstruction
─────────────────────────────────────────────────────────────
Strategy 1's original backtest (docs/S1_DUAL_MOMENTUM_BACKTEST_RESULTS.md,
2026-07-24) ranked every week against agent/universe_nifty200.txt — TODAY's
constituent list applied retroactively across the whole ~3-year window.
That's the exact survivorship bias S8-3 already hit once (see
core/rotation/nifty500_reconstitution.py's own docstring and memory
quantos-s8-3-survivorship-fix-status) — arguably worse here, since Nifty
200 membership is itself largely a record of "which stocks already won"
for a MOMENTUM strategy specifically.

This module mirrors nifty500_reconstitution.py's exact approach (same
ReconstitutionEvent/UniverseSnapshot shape, same backward-walk algorithm)
but for the Nifty 200 section of each NSE semi-annual broad-market review
— a DIFFERENT list from the Nifty 500 section of the same press releases
(Nifty 200 is a strict subset, with its own separate exclude/include
tables, not derivable from the Nifty 500 events alone).

Source: same real NSE press-release PDFs already gathered in
backtest_results/helper_docs/ for the Nifty 500 module — re-read for their
separate "Nifty 200" section instead. Five of the ten PDFs in that
directory are narrow ad-hoc single/few-stock corrections that never touch
Nifty 200 at all (confirmed by reading each one in full, not assumed):
ind_prs17102023.pdf, ind_prs10102024.pdf, ind_prs17032025.pdf,
ind_prs15092025_1.pdf, ind_prs04052026.pdf. Real Nifty 200 events exist in
five: ind_prs17082023.pdf, ind_prs28022024.pdf (+ind_prs19032024.pdf's
correction), ind_prs23082024.pdf (+ind_prs25092024.pdf's correction),
ind_prs21022025.pdf, ind_prs22082025.pdf, ind_prs23022026.pdf.

**Coverage limitation, same as the Nifty 500 module**: real events only
go back to 2023-09-29 (NIFTY200_RECONSTITUTION_COVERAGE_START below).
Dates before that collapse to one static backward-projected snapshot —
not true point-in-time. A backtest window starting earlier than this
(e.g. Strategy 1's own 3-year default, ~2022-06 with warmup) will have
its early warmup period fall in this uncovered zone; only the actual
ranking/trading period (which starts after warmup, typically well into
2023) benefits from true point-in-time correction throughout.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

_EPOCH = datetime(2015, 1, 1, tzinfo=timezone.utc)

NIFTY200_RECONSTITUTION_COVERAGE_START = datetime(2023, 9, 29, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Nifty200ReconstitutionEvent:
    effective_date: datetime
    added: frozenset
    removed: frozenset
    source: str


def _d(y: int, m: int, day: int) -> datetime:
    return datetime(y, m, day, tzinfo=timezone.utc)


EVENTS200: list[Nifty200ReconstitutionEvent] = [
    Nifty200ReconstitutionEvent(
        effective_date=_d(2023, 9, 29),
        added=frozenset({
            "APLAPOLLO", "BDL", "FACT", "KPITTECH", "LODHA", "MAZDOCK", "RVNL", "TATAMTRDVR",
        }),
        removed=frozenset({
            "ABBOTINDIA", "HINDZINC", "HONAUT", "OFSS", "TTML", "TRIDENT", "WHIRLPOOL",
        }),
        source="ind_prs17082023.pdf",
    ),
    Nifty200ReconstitutionEvent(
        # Base ind_prs28022024.pdf netted with ind_prs19032024.pdf's correction:
        # IREDA's inclusion was revoked (same SEBI portfolio-concentration
        # breach that hit the Nifty 500 event this same date), BSE Ltd.
        # substituted in as the replacement.
        effective_date=_d(2024, 3, 28),
        added=frozenset({
            "MAHABANK", "GMRINFRA", "IDBI", "BSE", "JIOFIN", "JSWINFRA",
            "KALYANKJIL", "OFSS", "SJVN", "SUPREMEIND", "SUZLON", "TATATECH",
        }),
        removed=frozenset({
            "AWL", "BATAINDIA", "COROMANDEL", "CROMPTON", "DEVYANI", "FLUOROCHEM",
            "MSUMI", "MUTHOOTFIN", "NAVINFLUOR", "PGHH", "RAMCOCEM", "UBL",
        }),
        source="ind_prs28022024.pdf+ind_prs19032024.pdf",
    ),
    Nifty200ReconstitutionEvent(
        # Base ind_prs23082024.pdf netted with ind_prs25092024.pdf's correction:
        # IDEA's exclusion was revoked (stays in) and CENTRALBK's inclusion
        # was revoked (never entered) -- same Vodafone-Idea-adjacent revocation
        # cycle that hit the Nifty 500 event this same date.
        effective_date=_d(2024, 9, 30),
        added=frozenset({
            "BHARTIHEXA", "COCHINSHIP", "EXIDEIND", "HINDZINC", "HUDCO", "IOB",
            "IREDA", "IRB", "MRPL", "MUTHOOTFIN", "NLCINDIA", "PHOENIXLTD",
            "SOLARINDS", "SUNDARMFIN",
        }),
        removed=frozenset({
            "BERGEPAINT", "DALBHARAT", "DEEPAKNTR", "LALPATHLAB", "FORTIS", "GLAND",
            "GUJGASLTD", "IPCALAB", "LTTS", "LAURUSLABS", "PEL", "SUNTV", "SYNGENE", "ZEEL",
        }),
        source="ind_prs23082024.pdf+ind_prs25092024.pdf",
    ),
    Nifty200ReconstitutionEvent(
        effective_date=_d(2025, 3, 28),
        added=frozenset({
            "BAJAJHFL", "GLENMARK", "HYUNDAI", "MOTILALOFS", "NATIONALUM",
            "NTPCGREEN", "OLAELEC", "PREMIERENE", "SWIGGY", "VMM", "WAAREEENER",
        }),
        removed=frozenset({
            "BALKRISIND", "DELHIVERY", "FACT", "IDBI", "IOB", "JSWINFRA", "MRPL",
            "NLCINDIA", "POONAWALLA", "SUNDARMFIN", "TATACHEM",
        }),
        source="ind_prs21022025.pdf",
    ),
    Nifty200ReconstitutionEvent(
        effective_date=_d(2025, 9, 30),
        added=frozenset({
            "360ONE", "BLUESTARCO", "COROMANDEL", "FORTIS", "GODFRYPHLP",
            "POWERINDIA", "ITCHOTELS", "KEI", "ENRIN",
        }),
        removed=frozenset({
            "ABFRL", "APOLLOTYRE", "BANDHANBNK", "MAHABANK", "ESCORTS", "ICICIPRULI",
            "OLAELEC", "PETRONET", "SJVN",
        }),
        source="ind_prs22082025.pdf",
    ),
    Nifty200ReconstitutionEvent(
        effective_date=_d(2026, 3, 30),
        added=frozenset({
            "GROWW", "GVT&D", "ICICIAMC", "LAURUSLABS", "LENSKART", "LGEINDIA",
            "MCX", "RADICO", "TATACAP", "TATAINVEST", "TMCV",
        }),
        removed=frozenset({
            "ACC", "BAJAJHFL", "BHARTIHEXA", "IGL", "IRB", "ITCHOTELS", "LICI",
            "NTPCGREEN", "SONACOMS", "TATATECH", "TORNTPOWER",
        }),
        source="ind_prs23022026.pdf",
    ),
]


@dataclass(frozen=True)
class Nifty200UniverseSnapshot:
    valid_from:  datetime
    valid_until: Optional[datetime]
    symbols:     frozenset


def build_point_in_time_nifty200(
    current_universe: frozenset, window_start: datetime = _EPOCH,
) -> list[Nifty200UniverseSnapshot]:
    """Same backward-walk algorithm as nifty500_reconstitution.py's
    build_point_in_time_universe, applied to EVENTS200 instead."""
    events_desc = sorted(EVENTS200, key=lambda e: e.effective_date, reverse=True)
    universe = set(current_universe)
    snapshots: list[Nifty200UniverseSnapshot] = []
    valid_until: Optional[datetime] = None

    for event in events_desc:
        snapshots.append(Nifty200UniverseSnapshot(
            valid_from=event.effective_date, valid_until=valid_until,
            symbols=frozenset(universe),
        ))
        universe = (universe - event.added) | event.removed
        valid_until = event.effective_date

    snapshots.append(Nifty200UniverseSnapshot(
        valid_from=window_start, valid_until=valid_until, symbols=frozenset(universe),
    ))
    snapshots.reverse()
    return snapshots


def nifty200_eligible_asof(
    snapshots: list[Nifty200UniverseSnapshot], as_of_date: datetime,
) -> frozenset:
    """Same clamp-to-nearest-snapshot semantics as
    nifty500_reconstitution.py's eligible_symbols_asof."""
    for snap in snapshots:
        if snap.valid_from <= as_of_date and (snap.valid_until is None or as_of_date < snap.valid_until):
            return snap.symbols
    return snapshots[-1].symbols if as_of_date >= snapshots[-1].valid_from else snapshots[0].symbols
