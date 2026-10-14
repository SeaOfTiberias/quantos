"""
QuantOS — Obsidian Vault: strategy records and reports
───────────────────────────────────────────────────────
The vault is the record of every strategy the project has tested or run.
Each one is a `wiki/` page tagged `wiki/strategy` carrying the flat
properties defined in SCHEMA.md ("Strategy records"). This module reads
those properties back out, validates them for `vault lint`, and renders the
deterministic strategy register `vault report` writes.

Deterministic on purpose, same reasoning as `write_index`: a report is a
listing of recorded facts, and having a model write it invites invented
entries. Interpretation lives on the strategy pages themselves, where every
claim cites a raw source.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from core.vault.layers import Layer, VaultPaths

STRATEGY_TAG = "wiki/strategy"

STATUSES = ("live-capital", "live-paper", "live-tool", "open", "closed", "retired", "shelved")
VERDICTS = ("PASS", "FAIL", "MIXED", "INCONCLUSIVE", "OPEN", "N/A")
FAMILIES = ("breakout", "momentum", "trend", "mean-reversion", "stat-arb", "volatility-premium",
            "vol-conditioning", "intraday-options", "calendar-effect", "event-drift", "ml-factor",
            "discretionary-aid")
INSTRUMENTS = ("equity-cash", "stock-futures", "index-futures", "index-options", "stock-options", "mixed")
REQUIRED = ("strategy_id", "family", "instrument", "status", "verdict", "headline")
NO_DATE_VERDICTS = ("OPEN", "N/A")

LIVE_STATUSES = ("live-capital", "live-paper", "live-tool")
_STATUS_ORDER = {s: i for i, s in enumerate(STATUSES)}


@dataclass(frozen=True)
class StrategyRecord:
    name: str                  # note stem, the [[link]] target
    title: str
    path: Path
    strategy_id: str
    candidate: str
    family: str
    instrument: str
    status: str
    verdict: str
    headline: str
    first_tested: Optional[date] = None
    verdict_date: Optional[date] = None
    profit_factor: Optional[float] = None
    sharpe: Optional[float] = None
    trades: Optional[int] = None
    bar: str = ""
    capital: str = ""
    next_gate: str = ""
    next_gate_date: Optional[date] = None

    @property
    def is_live(self) -> bool:
        return self.status in LIVE_STATUSES


def _as_date(value: Any) -> Optional[date]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _as_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    f = _as_float(value)
    return int(f) if f is not None else None


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def is_strategy_note(note) -> bool:
    return STRATEGY_TAG in note.tags and note.layer is Layer.WIKI


def validate(note) -> list[str]:
    """Problems with a strategy page's properties, as plain sentences.
    Empty list = the page is a complete record."""
    fm = note.frontmatter or {}
    problems = [f"missing `{key}`" for key in REQUIRED if _text(fm.get(key)) == ""]
    for key, allowed in (("status", STATUSES), ("verdict", VERDICTS),
                         ("family", FAMILIES), ("instrument", INSTRUMENTS)):
        value = _text(fm.get(key))
        if value and value not in allowed:
            problems.append(f"`{key}: {value}` is not one of {', '.join(allowed)}")
    if _text(fm.get("verdict")) not in NO_DATE_VERDICTS and "verdict" in fm:
        if _as_date(fm.get("verdict_date")) is None:
            problems.append("missing or unparseable `verdict_date` (required unless verdict is OPEN or N/A)")
    for key in ("first_tested", "verdict_date", "next_gate_date"):
        if _text(fm.get(key)) and _as_date(fm.get(key)) is None:
            problems.append(f"`{key}` is not a YYYY-MM-DD date")
    for key in ("profit_factor", "sharpe", "trades"):
        if _text(fm.get(key)) and _as_float(fm.get(key)) is None:
            problems.append(f"`{key}` is not a number")
    sid = _text(fm.get("strategy_id"))
    if sid and sid != note.name:
        problems.append(f"`strategy_id: {sid}` does not match the file name `{note.name}`")
    return problems


def record_from_note(note) -> StrategyRecord:
    fm = note.frontmatter or {}
    return StrategyRecord(
        name=note.name, title=note.title, path=note.path,
        strategy_id=_text(fm.get("strategy_id")) or note.name,
        candidate=_text(fm.get("candidate")),
        family=_text(fm.get("family")), instrument=_text(fm.get("instrument")),
        status=_text(fm.get("status")), verdict=_text(fm.get("verdict")),
        headline=_text(fm.get("headline")),
        first_tested=_as_date(fm.get("first_tested")),
        verdict_date=_as_date(fm.get("verdict_date")),
        profit_factor=_as_float(fm.get("profit_factor")),
        sharpe=_as_float(fm.get("sharpe")),
        trades=_as_int(fm.get("trades")),
        bar=_text(fm.get("bar")), capital=_text(fm.get("capital")),
        next_gate=_text(fm.get("next_gate")),
        next_gate_date=_as_date(fm.get("next_gate_date")),
    )


def load_records(notes: Iterable) -> list[StrategyRecord]:
    return [record_from_note(n) for n in notes if is_strategy_note(n)]


def filter_records(
    records: Iterable[StrategyRecord], *,
    status: Optional[Iterable[str]] = None, verdict: Optional[Iterable[str]] = None,
    family: Optional[Iterable[str]] = None, instrument: Optional[Iterable[str]] = None,
    since: Optional[date] = None, live_only: bool = False,
) -> list[StrategyRecord]:
    """Each filter is an allow-list; None means no filter. `since` keeps
    records whose verdict_date or first_tested is on/after that date."""
    def ok(value: str, allowed) -> bool:
        return allowed is None or value in set(allowed)

    out = []
    for r in records:
        if not (ok(r.status, status) and ok(r.verdict, verdict)
                and ok(r.family, family) and ok(r.instrument, instrument)):
            continue
        if live_only and not r.is_live:
            continue
        if since is not None:
            latest = max((d for d in (r.verdict_date, r.first_tested) if d), default=None)
            if latest is None or latest < since:
                continue
        out.append(r)
    return out


# ─── Rendering ──────────────────────────────────────────────────────────────

def _num(value: Optional[float], fmt: str = "{:.2f}") -> str:
    return "" if value is None else fmt.format(value)


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _date(d: Optional[date]) -> str:
    return d.isoformat() if d else ""


def _register_rows(records: list[StrategyRecord]) -> list[str]:
    rows = ["| Strategy | Cand. | Family | Instrument | Status | Verdict | Verdict date | PF | Sharpe | Trades | Headline |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    ordered = sorted(records, key=lambda r: (r.verdict_date or r.first_tested or date.min), reverse=True)
    for r in ordered:
        rows.append(
            f"| [[{r.name}\\|{_cell(r.title)}]] | {_cell(r.candidate)} | {r.family} | {r.instrument} | "
            f"{r.status} | **{r.verdict}** | {_date(r.verdict_date)} | {_num(r.profit_factor)} | "
            f"{_num(r.sharpe)} | {'' if r.trades is None else r.trades} | {_cell(r.headline)} |")
    return rows


def _counts_table(records: list[StrategyRecord], key: str, order: tuple[str, ...]) -> list[str]:
    counts = Counter(getattr(r, key) for r in records)
    verdicts = Counter((getattr(r, key), r.verdict) for r in records)
    head = "| " + key.capitalize() + " | Total | " + " | ".join(VERDICTS) + " |"
    rows = [head, "|" + "---|" * (len(VERDICTS) + 2)]
    for value in [v for v in order if counts[v]] + sorted(set(counts) - set(order)):
        cells = " | ".join(str(verdicts[(value, v)] or "") for v in VERDICTS)
        rows.append(f"| {value} | {counts[value]} | {cells} |")
    return rows


def render_report(records: list[StrategyRecord], *, today: date, title: str = "Strategy register",
                  filters: str = "") -> str:
    """Markdown report: summary counts, what is running, the full register.
    Every row links its strategy page, where the cited evidence lives."""
    by_verdict = Counter(r.verdict for r in records)
    live = sorted((r for r in records if r.is_live), key=lambda r: _STATUS_ORDER.get(r.status, 99))
    real_capital = [r for r in records if r.status == "live-capital"]

    lines = [
        "---",
        f"title: {title} — {today.isoformat()}",
        f"compiled: {today.isoformat()}",
        "tags:",
        "  - wiki/report",
        "quantos:",
        "  layer: wiki",
        "  generated: true",
        "---",
        "",
        f"# {title} — {today.isoformat()}",
        "",
        "> [!abstract] Generated report",
        "> Written by `python scripts/vault.py report` from the strategy-record properties on each "
        "`wiki/strategy` page (SCHEMA.md, \"Strategy records\"). Regenerate rather than edit. "
        "Numbers are each test's headline as recorded on its page; the page holds the evidence and "
        "its sources. Nothing here is a claim that a strategy is profitable.",
        "",
    ]
    if filters:
        lines += [f"**Filter:** {filters}", ""]

    lines += [
        "## Summary",
        "",
        f"- **{len(records)}** strategy records: "
        + ", ".join(f"{by_verdict[v]} {v}" for v in VERDICTS if by_verdict[v]) + ".",
        f"- **Running now:** {len(live)} "
        f"({', '.join(f'[[{r.name}]]' for r in live) or 'none'}).",
        f"- **Real capital deployed:** "
        + (", ".join(f"[[{r.name}]]" for r in real_capital) if real_capital else "none") + ".",
        "",
    ]

    if live:
        lines += ["## Running now", "",
                  "| Strategy | Status | Verdict | Capital | Next gate | Gate date |",
                  "|---|---|---|---|---|---|"]
        for r in live:
            lines.append(f"| [[{r.name}\\|{_cell(r.title)}]] | {r.status} | **{r.verdict}** | "
                         f"{_cell(r.capital)} | {_cell(r.next_gate)} | {_date(r.next_gate_date)} |")
        lines.append("")

    lines += ["## By status", ""] + _counts_table(records, "status", STATUSES) + [""]
    lines += ["## By family", ""] + _counts_table(records, "family", FAMILIES) + [""]
    lines += ["## By instrument", ""] + _counts_table(records, "instrument", INSTRUMENTS) + [""]
    lines += ["## Register (newest verdict first)", ""] + _register_rows(records) + [""]
    return "\n".join(lines)


def write_report(vault: VaultPaths, text: str, *, today: date, slug: str = "strategy-register",
                 out: Optional[Path] = None) -> Path:
    """Default location: `wiki/reports/<slug>-YYYY-MM-DD.md` — inside the
    agent-written layer, so it is regenerable and never executable."""
    path = out or (vault.wiki / "reports" / f"{slug}-{today.isoformat()}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
