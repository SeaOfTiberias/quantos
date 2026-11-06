"""
Daily snapshot of the user's own screener.in screen (the techno-funda momentum query).

Record only (user, 2026-11-06): one fetch of one public page after the close, kept on
the VM, never shared or mirrored (screener.in's terms allow personal, non-commercial
viewing). No paper trades and no Darvas-cycle hookup until the 2021-26 techno-funda
backtest (its own pre-registration) passes. The snapshots are the forward record that
backtest's rebuild of the query is later checked against.

Parsing uses only the standard library. Only page 1 is read: screener.in's robots.txt
disallows the paging parameters, so a list longer than one page is recorded as
truncated rather than fetched further.
"""

from __future__ import annotations

import html
import json
import os
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

SCREEN_URL = "https://www.screener.in/screens/1018464/momentum_scan_milind_upasani/"
USER_AGENT = "Mozilla/5.0 (QuantOS personal daily snapshot)"


class _TableParser(HTMLParser):
    """Collects the results table: header labels, and per row the cells and company link."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.headers: list[str] = []
        self.rows: list[dict] = []
        self._th: Optional[dict] = None
        self._row: Optional[dict] = None
        self._cell: Optional[list[str]] = None
        self._href: Optional[str] = None
        self.query: Optional[str] = None
        self._in_query = False
        self._query_buf: list[str] = []
        self.results_text: Optional[str] = None
        self._text_buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table" and "data-table" in (a.get("class") or ""):
            self.in_table = True
        elif tag == "textarea" and a.get("id") == "query-builder":
            self._in_query = True
        elif self.in_table and tag == "th":
            self._th = {"tooltip": a.get("data-tooltip"), "text": []}
        elif self.in_table and tag == "tr" and "data-row-company-id" in a:
            self._row = {"cells": [], "href": None, "name": None}
        elif self._row is not None and tag == "td":
            self._cell = []
        elif self._row is not None and tag == "a" and self._cell is not None:
            self._href = a.get("href")

    def handle_endtag(self, tag):
        if tag == "table" and self.in_table:
            self.in_table = False
        elif tag == "textarea" and self._in_query:
            self._in_query = False
            self.query = "".join(self._query_buf).strip()
        elif tag == "th" and self._th is not None:
            label = self._th["tooltip"] or " ".join("".join(self._th["text"]).split())
            self.headers.append(label)
            self._th = None
        elif tag == "td" and self._cell is not None and self._row is not None:
            text = " ".join("".join(self._cell).split())
            if self._href:
                self._row["href"], self._row["name"] = self._href, text
                self._href = None
            self._row["cells"].append(text)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._in_query:
            self._query_buf.append(data)
        elif self._th is not None:
            self._th["text"].append(data)
        elif self._cell is not None:
            self._cell.append(data)
        if "results found" in data:
            self.results_text = " ".join(data.split())


def _number(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def tradingview_url(nse_symbol: Optional[str]) -> Optional[str]:
    """TradingView chart link for an NSE symbol; TradingView writes '&' and '-' as '_' (M&M -> M_M)."""
    if not nse_symbol:
        return None
    return f"https://www.tradingview.com/chart/?symbol=NSE:{re.sub(r'[&-]', '_', nse_symbol)}"


def _company(href: str) -> tuple[Optional[str], Optional[str]]:
    """(NSE symbol, BSE code) from a screener.in company link. A numeric slug is a BSE code:
    the stock has no NSE listing on screener.in (often an SME or BSE-only name)."""
    m = re.match(r"^/company/([^/]+)/", href or "")
    if not m:
        return None, None
    slug = html.unescape(m.group(1))
    return (None, slug) if slug.isdigit() else (slug, None)


def parse(page: str) -> dict:
    """The screen page -> {query, results_text, total, pages, truncated, columns, rows}."""
    p = _TableParser()
    p.feed(page)
    if not p.headers:
        raise ValueError("no results table on the page (layout changed, or not a screen page)")
    columns = p.headers[2:]                      # after "S.No." and "Company"
    rows = []
    for r in p.rows:
        nse, bse = _company(r["href"])
        values = r["cells"][2:]
        rows.append({
            "name": r["name"],
            "screener_url": f"https://www.screener.in{r['href']}" if r["href"] else None,
            "nse_symbol": nse,
            "bse_code": bse,
            "tradingview_url": tradingview_url(nse),
            "values": {c: _number(v) for c, v in zip(columns, values)},
        })
    total = pages = None
    if p.results_text:
        m = re.search(r"(\d+)\s+results? found", p.results_text)
        total = int(m.group(1)) if m else None
        m = re.search(r"page\s+\d+\s+of\s+(\d+)", p.results_text)
        pages = int(m.group(1)) if m else None
    return {
        "query": p.query,
        "results_text": p.results_text,
        "total": total,
        "pages": pages,
        "truncated": bool(pages and pages > 1),
        "columns": columns,
        "rows": rows,
    }


# ─── Storage: one JSON file per session in ~/.quantos/screen_snapshots/ ──────

def store_dir() -> Path:
    override = os.getenv("QUANTOS_SCREEN_SNAPSHOTS")
    return Path(override) if override else Path.home() / ".quantos" / "screen_snapshots"


def save(snapshot: dict, session: date) -> Path:
    d = store_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{session.isoformat()}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(snapshot, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def load_all() -> list[dict]:
    """Every saved snapshot, oldest first. Unreadable files are skipped."""
    d = store_dir()
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("????-??-??.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def _key(row: dict) -> str:
    return row.get("nse_symbol") or row.get("bse_code") or row.get("name") or "?"


def latest_view(snapshots: list[dict], lookback: int = 20) -> Optional[dict]:
    """The newest snapshot, each row annotated with when it first appeared and how many
    of the last `lookback` snapshots it was in; plus which names dropped off since the one before."""
    if not snapshots:
        return None
    last = snapshots[-1]
    window = snapshots[-lookback:]
    first_seen: dict[str, str] = {}
    for s in snapshots:
        for r in s.get("rows", []):
            first_seen.setdefault(_key(r), s["session"])
    rows = []
    for r in last.get("rows", []):
        k = _key(r)
        rows.append({**r,
                     "first_seen": first_seen.get(k),
                     "days_in_window": sum(any(_key(x) == k for x in s.get("rows", [])) for s in window)})
    prev = snapshots[-2] if len(snapshots) > 1 else None
    now_keys = {_key(r) for r in last.get("rows", [])}
    dropped = [{"name": r.get("name"), "nse_symbol": r.get("nse_symbol"),
                "tradingview_url": r.get("tradingview_url"), "screener_url": r.get("screener_url")}
               for r in (prev or {}).get("rows", []) if _key(r) not in now_keys]
    return {**last, "rows": rows, "dropped": dropped, "lookback": len(window),
            "previous_session": prev["session"] if prev else None,
            "sessions_recorded": len(snapshots)}
