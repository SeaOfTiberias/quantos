"""
NSE's daily files from the archive host, which the VM can reach (NSE's main site and its
API answer the VM with 403 or a timeout; probed 2026-11-07):

  - the CM bhavcopy (prices), parsed by `core.techno_funda.prices.read_bhavcopy`;
  - the PR bundle (PRddmmyy.zip), whose bcDDMMYYYY.csv lists every corporate action with
    its ex-date and purpose, a few days before the ex-date;
  - symbolchange.csv (renames).

The PR file abbreviates splits ("FVSPLT FRM RS 10 TO RE 1", "FV SPLT FRM RS 5 TO RE 1");
bonuses read as "BONUS 1:3". Both are mapped to the wording `prices.action_factor` reads,
so the factor rule is the one the techno-funda panel used.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests

from core.fundamentals.pead.eq_bhavcopy import url_for as bhavcopy_url
from core.techno_funda import prices as pr
from core.techno_funda.symbols import SymbolChain

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
PR_URL = "https://nsearchives.nseindia.com/archives/equities/bhavcopy/pr/PR{d:%d%m%y}.zip"
SYMBOLCHANGE_URL = "https://nsearchives.nseindia.com/content/equities/symbolchange.csv"
ACTION_SERIES = ("EQ", "BE", "BZ")


def fetch(url: str, timeout: int = 30) -> Optional[bytes]:
    """The file, or None on 404 (a holiday, or not published yet)."""
    r = requests.get(url, headers=UA, timeout=timeout)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.content


def fetch_to(url: str, path: Path) -> Optional[Path]:
    if path.exists() and path.stat().st_size > 0:
        return path
    body = fetch(url)
    if body is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def bhavcopy_day(raw_dir: Path, d: date, chain: SymbolChain):
    """One session's rows (sym, series, o, h, l, c, vol, val) under canonical symbols, or
    None when NSE has no file for `d`."""
    p = fetch_to(bhavcopy_url(d), raw_dir / "cm" / f"{d:%Y%m%d}.zip")
    if p is None:
        return None
    df = pr.read_bhavcopy(p, d)
    df["sym"] = [chain.canonical(s, d) for s in df["sym"]]
    df["eq"] = df["series"] == "EQ"
    df = df.sort_values(["sym", "eq"]).drop_duplicates("sym", keep="last")
    return df.drop(columns=["eq", "date"]).reset_index(drop=True)


def normalise_purpose(purpose: str) -> str:
    t = purpose.upper()
    t = re.sub(r"\bFV\s*SPLT\b|\bFVSPLT\b|\bFV\s*SPLIT\b", "FACE VALUE SPLIT", t)
    t = re.sub(r"\bSPLT\b", "SPLIT", t)
    t = re.sub(r"\bFRM\b", "FROM", t)
    return t


def purpose_factor(purpose: str) -> Optional[float]:
    return pr.action_factor(normalise_purpose(purpose))


def _ex_date(s: str) -> Optional[date]:
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%b-%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def parse_pr_actions(pr_zip: bytes, chain: SymbolChain) -> list[dict]:
    """Splits and bonuses from a PR bundle's bc file: {sym, ex, factor, purpose, source}."""
    with zipfile.ZipFile(io.BytesIO(pr_zip)) as zf:
        names = [n for n in zf.namelist() if n.lower().startswith("bc") and n.lower().endswith(".csv")]
        if not names:
            return []
        text = zf.read(names[0]).decode("latin1")
    out, seen = [], set()
    rd = csv.reader(io.StringIO(text))
    head = [h.strip().upper() for h in next(rd, [])]
    if not {"SERIES", "SYMBOL", "EX_DT", "PURPOSE"} <= set(head):
        raise ValueError(f"unexpected bc header: {head}")
    ix = {h: i for i, h in enumerate(head)}
    for r in rd:
        if len(r) < len(head) or r[ix["SERIES"]].strip() not in ACTION_SERIES:
            continue
        ex = _ex_date(r[ix["EX_DT"]])
        purpose = r[ix["PURPOSE"]].strip()
        f = purpose_factor(purpose)
        if ex is None or not f:
            continue
        sym = chain.canonical(r[ix["SYMBOL"]].strip(), ex)
        key = (sym, ex, round(f, 6))
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(sym=sym, ex=ex.isoformat(), factor=f, purpose=purpose, source="nse_pr"))
    return out


def parse_pr_etfs(pr_zip: bytes) -> set[str]:
    """Symbols on the PR bundle's ETF list (etfDDMMYYYY.csv, column SYMBOL)."""
    with zipfile.ZipFile(io.BytesIO(pr_zip)) as zf:
        names = [n for n in zf.namelist() if n.lower().startswith("etf") and n.lower().endswith(".csv")]
        if not names:
            return set()
        text = zf.read(names[0]).decode("latin1")
    rd = csv.reader(io.StringIO(text))
    head = [h.strip().upper() for h in next(rd, [])]
    if "SYMBOL" not in head:
        raise ValueError(f"unexpected etf header: {head}")
    i = head.index("SYMBOL")
    return {r[i].strip() for r in rd if len(r) > i and r[i].strip()}


def pr_day(raw_dir: Path, d: date, chain: SymbolChain) -> Optional[tuple[list[dict], set[str]]]:
    """(splits and bonuses, ETF symbols) from day `d`'s PR bundle, or None if there is none."""
    p = fetch_to(PR_URL.format(d=d), raw_dir / "pr" / f"PR{d:%d%m%y}.zip")
    if p is None:
        return None
    body = p.read_bytes()
    return parse_pr_actions(body, chain), parse_pr_etfs(body)
