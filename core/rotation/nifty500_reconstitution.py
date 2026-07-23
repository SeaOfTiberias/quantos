"""
QuantOS — Nifty 500 point-in-time membership reconstruction
─────────────────────────────────────────────────────────────
S8-3's original equity-curve run ranked every backtest week against
agent/universe_nifty500.txt — TODAY's constituent list applied retroactively
across the whole ~3-year window. That's survivorship bias: a stock NSE has
since dropped from the Nifty 500 never gets a chance to be ranked/entered
even in the weeks it WAS a constituent, and a recently-added stock competes
in weeks before it actually joined. Fable flagged this against the original
+8pt-alpha-vs-Nifty finding (see memory: quantos-equity-curve-and-fable-review).

This module walks the semi-annual broad-market reviews (plus the ad-hoc
merger/suspension replacements NSE issues between them) BACKWARD from
TODAY's list (agent/universe_nifty500.txt) to reconstruct what the true
point-in-time Nifty 500 membership was at each date in the backtest window,
so backtest_equity_curve.py can rank each week only against symbols that
were actually constituents that week.

Source: press releases from niftyindices.com/press-release, user-supplied
since niftyindices.com is unfetchable by this environment's web tools (see
memory: quantos-s8-3-survivorship-fix-status). EVENTS below covers only the
Nifty 500 broad-index section of each release (other Nifty variants in the
same PDF are out of scope) and nets same-cycle corrections into the base
semi-annual figures (e.g. Mar 2024's IREDA/V-Guard SEBI-concentration
revocation, Sept 2024's Vodafone Idea revocation) rather than listing them
as separate events, since both landed before the cycle's own effective date.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# Floor earlier than any realistic backtest window start, so the earliest
# reconstructed snapshot always covers "from the beginning of time" rather
# than needing to match runtime --years arithmetic.
_EPOCH = datetime(2015, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class ReconstitutionEvent:
    effective_date: datetime      # first trading day the change applies
    added: frozenset              # symbols entering Nifty 500 on this date
    removed: frozenset            # symbols leaving Nifty 500 on this date
    source: str                   # press-release filename, for auditability


def _d(y: int, m: int, day: int) -> datetime:
    return datetime(y, m, day, tzinfo=timezone.utc)


# Chronological order matters — build_point_in_time_universe() walks this
# list backward (newest first) from today's live universe file.
EVENTS: list[ReconstitutionEvent] = [
    ReconstitutionEvent(
        effective_date=_d(2023, 9, 29),
        added=frozenset({
            "ALLCARGO", "ALOKINDS", "GILLETTE", "GLS", "GPIL", "IRCON", "JINDALSAW",
            "KAYNES", "KIRLFER", "MINDACORP", "PGHL", "SAFARI", "SAREGAMA", "SFL",
            "SYMPHONY", "SYRMA", "UJJIVANSFB", "USHAMART",
        }),
        removed=frozenset({
            "BASF", "GARFIBRES", "GODREJAGRO", "GREENPANEL", "HIKAL", "HGS", "IFBIND",
            "IBREALEST", "JINDWORLD", "KENNAMET", "RUSTOMJEE", "MAHLOG", "NOCIL", "TMB",
            "TCIEXP", "TCNSBRANDS", "TCI", "UFLEX",
        }),
        source="ind_prs17082023.pdf",
    ),
    ReconstitutionEvent(
        effective_date=_d(2023, 10, 26),
        added=frozenset({"CONCORDBIO"}),
        removed=frozenset({"KIRLFER"}),
        source="ind_prs17102023.pdf",
    ),
    ReconstitutionEvent(
        # Base ind_prs28022024.pdf netted with ind_prs19032024.pdf's correction:
        # IREDA's inclusion was revoked (SEBI portfolio-concentration breach) and
        # V-Guard's exclusion was revoked in the same stroke, so neither appears
        # as an actual membership change on this date.
        effective_date=_d(2024, 3, 28),
        added=frozenset({
            "ACE", "ANANDRATHI", "ASTRAZEN", "CAPLIPOINT", "CELLO", "CHENNPETRO",
            "DOMS", "ELECON", "GRSE", "GMDCLTD", "HAPPYFORGE", "HBLPOWER", "HSCL",
            "HONASA", "INOXWIND", "JAIBALAJI", "J&KBANK", "JIOFIN", "JSWINFRA", "JWL",
            "LLOYDSME", "MAHSEAMLES", "NUVAMA", "RRKABEL", "RAILTEL", "RKFORGE",
            "SBFC", "SCHNEIDER", "SIGNATURE", "TMB", "TATATECH", "TITAGARH", "TVSSCS",
        }),
        removed=frozenset({
            "AARTIDRUGS", "BCG", "DELTACORP", "EPIGRAL", "GRINFRA", "GALAXYSURF",
            "GOCOLORS", "GUJALKALI", "HLEGLAS", "INFIBEAM", "INGERRAND", "JAMNAAUTO",
            "LAXMIMACH", "LUXIND", "NAZARA", "ORIENTELEC", "PFIZER", "POLYPLEX",
            "PGHL", "RAIN", "RALLIS", "RELAXO", "ROSSARI", "SHARDACROP", "SFL",
            "SHOPERSTOP", "SUPRAJIT", "SYMPHONY", "TEAMLEASE", "TTKPRESTIG",
            "VINATIORGA", "VMART", "ZYDUSWELL",
        }),
        source="ind_prs28022024.pdf+ind_prs19032024.pdf",
    ),
    ReconstitutionEvent(
        # Base ind_prs23082024.pdf netted with ind_prs25092024.pdf's correction:
        # Vodafone Idea's exclusion was revoked and Prism Johnson excluded instead.
        effective_date=_d(2024, 9, 30),
        added=frozenset({
            "AADHARHFC", "ABSLAMC", "ANANTRAJ", "BASF", "BHARTIHEXA", "GRINFRA",
            "GET&D", "GODIGIT", "GODREJAGRO", "IFCI", "INDGN", "IREDA", "INOXINDIA",
            "JPPOWER", "JKTYRE", "JYOTICNC", "KIRLOSBROS", "KIRLOSENG", "NETWEB",
            "NEWGEN", "PFIZER", "PTCIL", "SCI", "TBOTEK", "TECHNOE", "DBREALTY",
            "VINATIORGA",
        }),
        removed=frozenset({
            "AETHER", "ALLCARGO", "ANURAS", "BORORENEW", "CSBBANK", "DCMSHRIRAM",
            "EPL", "FDC", "GLS", "GMMPFAUDLR", "HAPPYFORGE", "INDIGOPNTS", "JAIBALAJI",
            "JKPAPER", "KRBL", "LXCHEM", "MHRIL", "MEDPLUS", "MTARTECH", "PRINCEPIPE",
            "RBA", "SAFARI", "STLTECH", "SUNTECK", "TMB", "VAIBHAVGBL", "PRSMJOHNSN",
        }),
        source="ind_prs23082024.pdf+ind_prs25092024.pdf",
    ),
    ReconstitutionEvent(
        effective_date=_d(2024, 10, 16),
        added=frozenset({"AKUMS"}),
        removed=frozenset({"TV18BRDCST"}),
        source="ind_prs10102024.pdf",
    ),
    ReconstitutionEvent(
        effective_date=_d(2025, 3, 21),
        added=frozenset({"RAYMONDLSL"}),
        removed=frozenset({"ISEC"}),
        source="ind_prs17032025.pdf",
    ),
    ReconstitutionEvent(
        effective_date=_d(2025, 3, 28),
        added=frozenset({
            "ACMESOLAR", "AFCONS", "ALIVUS", "AIIL", "BAJAJHFL", "FIRSTCRY",
            "DCMSHRIRAM", "GRAVITA", "HYUNDAI", "IGIL", "IKS", "JSWHL", "LTFOODS",
            "NAVA", "NEULANDLAB", "NIVABUPA", "NTPCGREEN", "OLAELEC", "PGEL",
            "PREMIERENE", "RPOWER", "SAGILITY", "SAILIFE", "SARDAEN", "SWIGGY",
            "TARIL", "VMM", "WAAREEENER", "WOCKPHARMA", "ZENTEC",
        }),
        removed=frozenset({
            "ACI", "AVANTIFEED", "BALAMINES", "BIRLACORPN", "CELLO", "CHEMPLASTS",
            "CIEINDIA", "EASEMYTRIP", "EQUITASBNK", "FINEORG", "GRINFRA", "GRINDWELL",
            "GAEL", "GSFC", "JKLAKSHMI", "KSB", "MAHLIFE", "METROBRAND", "NUVOCO",
            "PGHH", "RAJESHEXPO", "RATNAMANI", "SANOFI", "SPARC", "SUNDRMFAST",
            "TVSSCS", "UJJIVANSFB", "VIPIND", "VARROC", "VINATIORGA",
        }),
        source="ind_prs21022025.pdf",
    ),
    ReconstitutionEvent(
        effective_date=_d(2025, 9, 23),
        added=frozenset({"RELINFRA"}),
        removed=frozenset({"PEL"}),
        source="ind_prs15092025_1.pdf",
    ),
    ReconstitutionEvent(
        effective_date=_d(2025, 9, 30),
        added=frozenset({
            "ABLBL", "AEGISVOPAK", "AKZOINDIA", "ATHERENERG", "BLUEJET", "CHOICEIN",
            "AGARWALEYE", "FORCEMOT", "HEXT", "ITCHOTELS", "KSB", "MAHSCOOTER",
            "NUVOCO", "ONESOURCE", "PGHH", "THELEELA", "ENRIN", "VENTIVE",
        }),
        removed=frozenset({
            "ALIVUS", "GNFC", "GPPL", "JSWHL", "JUSTDIAL", "KANSAINER", "KNRCON",
            "MASTEK", "NETWORK18", "PNCINFRA", "RTNINDIA", "RAYMONDLSL", "RAYMOND",
            "ROUTE", "RENUKA", "SWSOLAR", "TANLA", "WESTLIFE",
        }),
        source="ind_prs22082025.pdf",
    ),
    ReconstitutionEvent(
        effective_date=_d(2026, 3, 30),
        added=frozenset({
            "ACUTAAS", "CPPLUS", "ABDL", "ANTHEM", "ANURAS", "BELRISE", "GROWW",
            "CANHLIFE", "CARTRADE", "CEMPRO", "EMMVEE", "GABRIEL", "GALLANTT",
            "HDBFS", "ICICIAMC", "JAINREC", "LENSKART", "LGEINDIA", "MEESHO",
            "PARADEEP", "PWL", "PINELABS", "PIRAMALFIN", "SPLPETRO", "TATACAP",
            "TMCV", "TEGA", "TENNIND", "TRAVELFOOD", "URBANCO", "ZYDUSWELL",
        }),
        removed=frozenset({
            "AKUMS", "APLLTD", "ALKYLAMINE", "ALOKINDS", "ASTRAZEN", "BASF",
            "CAMPUS", "CENTURYPLY", "CERA", "AGARWALEYE", "FINPIPE", "GODREJAGRO",
            "GUJGASLTD", "HAPPSTMNDS", "INOXINDIA", "JYOTHYLAB", "KIRLOSBROS",
            "KSB", "MAHSCOOTER", "MAHSEAMLES", "METROPOLIS", "PRAJIND", "PGHH",
            "RCF", "RELINFRA", "SUNDRMFAST", "TRIVENI", "DBREALTY", "MANYAVAR",
            "VENTIVE", "VGUARD",
        }),
        source="ind_prs23022026.pdf",
    ),
    ReconstitutionEvent(
        effective_date=_d(2026, 5, 12),
        added=frozenset({"CIEINDIA"}),
        removed=frozenset({"GSPL"}),
        source="ind_prs04052026.pdf",
    ),
]


@dataclass(frozen=True)
class UniverseSnapshot:
    valid_from:  datetime               # inclusive
    valid_until: Optional[datetime]     # exclusive; None means "still current"
    symbols:     frozenset


def build_point_in_time_universe(
    current_universe: frozenset, window_start: datetime = _EPOCH,
) -> list[UniverseSnapshot]:
    """Reconstructs Nifty 500 membership snapshots covering [window_start, now],
    by walking EVENTS backward from current_universe (today's live list) and
    undoing each one in turn: what an event added gets removed to recover the
    state just before it, what it removed gets added back.

    Returns snapshots oldest-first, each valid over a contiguous date range.
    """
    events_desc = sorted(EVENTS, key=lambda e: e.effective_date, reverse=True)
    universe = set(current_universe)
    snapshots: list[UniverseSnapshot] = []
    valid_until: Optional[datetime] = None

    for event in events_desc:
        snapshots.append(UniverseSnapshot(
            valid_from=event.effective_date, valid_until=valid_until,
            symbols=frozenset(universe),
        ))
        universe = (universe - event.added) | event.removed
        valid_until = event.effective_date

    snapshots.append(UniverseSnapshot(
        valid_from=window_start, valid_until=valid_until, symbols=frozenset(universe),
    ))
    snapshots.reverse()
    return snapshots


def eligible_symbols_asof(snapshots: list[UniverseSnapshot], as_of_date: datetime) -> frozenset:
    """The Nifty 500 membership in effect on as_of_date. Dates before the
    first snapshot or after the last both clamp to the nearest snapshot
    rather than raising, since a backtest's first/last trading day can fall
    right at a window boundary."""
    for snap in snapshots:
        if snap.valid_from <= as_of_date and (snap.valid_until is None or as_of_date < snap.valid_until):
            return snap.symbols
    return snapshots[-1].symbols if as_of_date >= snapshots[-1].valid_from else snapshots[0].symbols
