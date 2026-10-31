#!/usr/bin/env python3
"""
QuantOS — Techno-Funda momentum: data fetch (2026-11-01)
──────────────────────────────────────────────────────────
Downloads the real NSE data docs/TECHNO_FUNDA_PREREG_2026-11-01.md needs, into
the existing caches. Resumable: every file is written as it arrives and skipped
on a re-run, so an interrupted run is restarted with the same command.
Throttled (~1 request/second) because NSE's Akamai front blocks fast clients.

Stages, in order:
  1. symbols   NSE's symbol-change file           -> data_cache/nse_symbolchange.csv
  2. actions   corporate actions 2010-2015, monthly -> data_cache/corp_actions_raw/,
               merged into data_cache/nse_corporate_actions_2010_2015.json
  3. metadata  results-filing metadata 2018-04..2026-10, monthly (pipeline cache)
  4. bhav      equity bhavcopies 2000-01-01..2015-12-31 (eq_bhavcopy raw cache)
  5. ifmeta    "Integrated Filing - Financials" metadata 2024-10..2026-10, monthly
               -> data_cache/pead_nse/if_metadata_raw/. From the quarter to
               Mar 2025 companies file results here; the old results feed
               (stage 3) is nearly empty from Apr 2025 on.
  6. xbrl      XBRL of every non-financial filing from both feeds, consolidated
               where filed, otherwise standalone; all revisions (each is used
               point-in-time). Integrated filings are cached as if_{seq_Id}.xml.

Financial-format filings are not downloaded: the pre-registration excludes
them. Old feed: bank B/F, NBFC-IND, Non-Ind-AS. Integrated feed (which has no
bank/indAs fields): any XBRL other than INTEGRATED_FILING_INDAS_* (NBFC_INDAS,
NONINDAS, GI, LI). Old-feed filings whose classification fields are missing
ARE downloaded, so gate D5 can see them.

Progress: logs/techno_funda_fetch.log. A 404 is recorded in
data_cache/techno_funda_404.txt and not retried.

Usage: python scripts/fetch_techno_funda_data.py [--stages symbols,actions,metadata,ifmeta,bhav,xbrl]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.fundamentals.pead.eq_bhavcopy import EqBhavcopyNotAvailable, fetch_raw  # noqa: E402
from core.fundamentals.pead.eq_bhavcopy import DEFAULT_RAW_CACHE_DIR as BHAV_DIR  # noqa: E402
from core.fundamentals.pead.nse_client import (  # noqa: E402
    _API_HEADERS, NseNotFoundError, NseSession, _get_json, fetch_bytes, fetch_xbrl)
from core.fundamentals.pead.pipeline import (  # noqa: E402
    DEFAULT_METADATA_CACHE_DIR as META_DIR, DEFAULT_XBRL_CACHE_DIR as XBRL_DIR,
    _month_chunks, fetch_metadata_month)

PAUSE = 1.0
SYMBOLS_URL = "https://nsearchives.nseindia.com/content/equities/symbolchange.csv"
SYMBOLS_OUT = Path("data_cache/nse_symbolchange.csv")
ACTIONS_API = "https://www.nseindia.com/api/corporates-corporateActions"
ACTIONS_RAW = Path("data_cache/corp_actions_raw")
ACTIONS_OUT = Path("data_cache/nse_corporate_actions_2010_2015.json")
META_FROM, META_TO = date(2018, 4, 1), date(2026, 10, 31)
IF_API = "https://www.nseindia.com/api/integrated-filing-results"
IF_REFERER = "https://www.nseindia.com/companies-listing/corporate-integrated-filing"
IF_TYPE = "Integrated Filing- Financials"
IF_META = Path("data_cache/pead_nse/if_metadata_raw")
IF_FROM, IF_PAGE = date(2024, 10, 1), 1000
IF_STANDARD_PREFIX = "INTEGRATED_FILING_INDAS_"
BHAV_FROM, BHAV_TO = date(2000, 1, 1), date(2015, 12, 31)
NOT_FOUND = Path("data_cache/techno_funda_404.txt")
LOG = Path("logs/techno_funda_fetch.log")
FINANCIAL = {"bank": {"B", "F"}, "indAs": {"NBFC-IND", "Non-Ind-AS"}}

log = logging.getLogger("techno_funda_fetch")


def _not_found() -> set[str]:
    return set(NOT_FOUND.read_text().split()) if NOT_FOUND.exists() else set()


def _mark_not_found(key: str) -> None:
    with NOT_FOUND.open("a") as f:
        f.write(key + "\n")


class Backoff:
    """After 25 failures in a row (likely an Akamai block), wait 10 minutes."""
    def __init__(self) -> None:
        self.streak = 0

    def ok(self) -> None:
        self.streak = 0

    def fail(self, what: str, e: Exception) -> None:
        self.streak += 1
        log.warning("fail %s: %s", what, str(e)[:160])
        if self.streak >= 25:
            log.warning("25 failures in a row; pausing 10 minutes")
            time.sleep(600)
            self.streak = 0


def stage_symbols(nse: NseSession) -> None:
    if SYMBOLS_OUT.exists():
        log.info("symbols: cached")
        return
    SYMBOLS_OUT.write_bytes(fetch_bytes(nse, SYMBOLS_URL))
    log.info("symbols: saved %s", SYMBOLS_OUT)


def stage_actions(nse: NseSession) -> None:
    ACTIONS_RAW.mkdir(parents=True, exist_ok=True)
    rows = []
    for a, b in _month_chunks(date(2010, 1, 1), date(2015, 12, 31)):
        p = ACTIONS_RAW / f"{a:%Y%m}.json"
        if not p.exists():
            r = _get_json(nse, ACTIONS_API, {"index": "equities", "from_date": f"{a:%d-%m-%Y}",
                                             "to_date": f"{b:%d-%m-%Y}"})
            p.write_text(json.dumps(r if isinstance(r, list) else r.get("data", [])), encoding="utf-8")
            time.sleep(PAUSE)
        rows += json.loads(p.read_text(encoding="utf-8"))
    ACTIONS_OUT.write_text(json.dumps(rows), encoding="utf-8")
    log.info("actions: %d rows 2010-2015 -> %s", len(rows), ACTIONS_OUT)


def stage_metadata(nse: NseSession) -> list[dict]:
    rows = []
    for a, b in _month_chunks(META_FROM, META_TO):
        p = META_DIR / f"{a:%Y%m}.json"
        # a month cached before it was over (plus a week for late filers) is incomplete
        if p.exists() and datetime.fromtimestamp(p.stat().st_mtime).date() < b + timedelta(days=7):
            p.unlink()
        fresh = not p.exists()
        rows += fetch_metadata_month(nse, a, b)
        if fresh:
            log.info("metadata: %s fetched", f"{a:%Y-%m}")
            time.sleep(PAUSE)
    log.info("metadata: %d filing rows 2018-04..2026-10", len(rows))
    return rows


def _if_page(nse: NseSession, a: date, b: date, page: int) -> dict:
    headers = dict(_API_HEADERS, Referer=IF_REFERER)
    params = {"index": "equities", "period_ended": "all", "type": IF_TYPE,
              "from_date": f"{a:%d-%m-%Y}", "to_date": f"{b:%d-%m-%Y}", "page": page, "size": IF_PAGE}
    for attempt in range(3):
        resp = nse.get().get(IF_API, params=params, headers=headers, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (401, 403):
            nse.force_refresh()
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"integrated filings {a}..{b} page {page} -> HTTP {resp.status_code}")


def stage_ifmeta(nse: NseSession) -> list[dict]:
    IF_META.mkdir(parents=True, exist_ok=True)
    rows = []
    for a, b in _month_chunks(IF_FROM, META_TO):
        p = IF_META / f"{a:%Y%m}.json"
        if p.exists() and datetime.fromtimestamp(p.stat().st_mtime).date() < b + timedelta(days=7):
            p.unlink()
        if not p.exists():
            month, page = [], 1
            while True:
                j = _if_page(nse, a, b, page)
                month += j.get("data") or []
                time.sleep(PAUSE)
                if len(month) >= int(j.get("totalCount") or 0) or not j.get("data"):
                    break
                page += 1
            if len(month) != int(j.get("totalCount") or len(month)):
                raise RuntimeError(f"integrated filings {a:%Y-%m}: got {len(month)} of {j.get('totalCount')}")
            p.write_text(json.dumps(month), encoding="utf-8")
            log.info("ifmeta: %s fetched, %d filings", f"{a:%Y-%m}", len(month))
        rows += json.loads(p.read_text(encoding="utf-8"))
    log.info("ifmeta: %d integrated filings 2024-10..2026-10", len(rows))
    return rows


def stage_bhav(nse: NseSession) -> None:
    missing, bo, n = _not_found(), Backoff(), 0
    d = BHAV_FROM
    while d <= BHAV_TO:
        key = f"bhav:{d:%Y%m%d}"
        if d.weekday() < 5 and key not in missing and not (BHAV_DIR / f"{d:%Y%m%d}.zip").exists():
            try:
                fetch_raw(nse, d)
                bo.ok()
                n += 1
            except EqBhavcopyNotAvailable:
                _mark_not_found(key)
            except Exception as e:  # one bad day must not stop the run
                bo.fail(key, e)
            time.sleep(PAUSE)
            if n and n % 200 == 0:
                log.info("bhav: %d new files, at %s", n, d)
        d += timedelta(days=1)
    log.info("bhav: done, %d new files", n)


def _is_financial(r: dict) -> bool:
    return r.get("bank") in FINANCIAL["bank"] or r.get("indAs") in FINANCIAL["indAs"]


def xbrl_targets(rows: list[dict]) -> list[dict]:
    """Every revision of the consolidated filing for each (symbol, period),
    or of the standalone one where no consolidated filing exists."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if _is_financial(r) or not str(r.get("xbrl", "")).endswith(".xml"):
            continue
        groups[(r["symbol"], r["fromDate"], r["toDate"])].append(r)
    out = []
    for g in groups.values():
        cons = [r for r in g if r.get("consolidated") == "Consolidated"]
        out += cons or g
    return [dict(name=f"{r['seqNumber']}.xml", url=r["xbrl"], when=r["broadCastDate"]) for r in out]


def if_targets(rows: list[dict]) -> list[dict]:
    """Same rule for the integrated feed; financial format read from the XBRL file name."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        url = r.get("xbrl") or ""
        if not url.rsplit("/", 1)[-1].startswith(IF_STANDARD_PREFIX):
            continue
        groups[(r["symbol"], r["qe_Date"])].append(r)
    out = []
    for g in groups.values():
        cons = [r for r in g if r.get("consolidated") == "Consolidated"]
        out += [dict(name=f"if_{r['seq_Id']}.xml", url=r["xbrl"], when=r["broadcast_Date"]) for r in cons or g]
    return out


def stage_xbrl(nse: NseSession, rows: list[dict], if_rows: list[dict]) -> None:
    XBRL_DIR.mkdir(parents=True, exist_ok=True)
    targets = sorted(xbrl_targets(rows) + if_targets(if_rows),
                     key=lambda t: datetime.strptime(t["when"], "%d-%b-%Y %H:%M:%S"))
    missing, bo = _not_found(), Backoff()
    todo = [t for t in targets if not (XBRL_DIR / t["name"]).exists() and f"xbrl:{t['name']}" not in missing]
    log.info("xbrl: %d target filings, %d already cached, %d to fetch",
             len(targets), len(targets) - len(todo), len(todo))
    for i, t in enumerate(todo, 1):
        key = f"xbrl:{t['name']}"
        try:
            (XBRL_DIR / t["name"]).write_bytes(fetch_xbrl(nse, t["url"]))
            bo.ok()
        except NseNotFoundError:
            _mark_not_found(key)
        except Exception as e:
            bo.fail(key, e)
        time.sleep(PAUSE)
        if i % 250 == 0:
            log.info("xbrl: %d / %d (broadcast %s)", i, len(todo), t["when"])
    log.info("xbrl: done")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", default="symbols,actions,metadata,ifmeta,bhav,xbrl")
    args = ap.parse_args(argv)
    LOG.parent.mkdir(exist_ok=True)
    logging.basicConfig(filename=LOG, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    stages = args.stages.split(",")
    log.info("start, stages=%s", stages)
    nse = NseSession()
    if "symbols" in stages:
        stage_symbols(nse)
    if "actions" in stages:
        stage_actions(nse)
    rows = stage_metadata(nse) if {"metadata", "xbrl"} & set(stages) else []
    if_rows = stage_ifmeta(nse) if {"ifmeta", "xbrl"} & set(stages) else []
    if "bhav" in stages:
        stage_bhav(nse)
    if "xbrl" in stages:
        stage_xbrl(nse, rows, if_rows)
    log.info("finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
