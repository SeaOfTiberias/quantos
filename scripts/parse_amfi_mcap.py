#!/usr/bin/env python3
"""
Parse an AMFI half-yearly "Average Market Capitalisation of listed companies" PDF to CSV
(Alpha 50 rebuild round 2, docs/ALPHA50_REBUILD_V2_PREREG_2026-11-27.md).

    pip install pypdf            # only this script needs it
    python scripts/parse_amfi_mcap.py data_cache/amfi_mcap/amfi_2019H1.pdf data_cache/amfi_mcap/amfi_2019H1.csv

Columns: rank, isin, name, symbols (every exchange symbol printed, BSE first), nse_symbol,
avg_mcap_cr, category. Public data, kept in data_cache/ (gitignored).

A row reads "rank name ISIN BSE-sym BSE-mcap NSE-sym NSE-mcap [MSEI-sym MSEI-mcap] avg category";
empty cells vanish in the PDF text. The NSE symbol is the second symbol printed; a row with one
symbol printed the same symbol for both exchanges (or one exchange only), so that one is used.
The text is split at the LAST ISIN on the line, because wrapped company names can leak an
earlier fragment (and ISIN) into the line.
"""

from __future__ import annotations

import csv
import re
import sys

NUM = re.compile(r"^\d{1,3}(,\d{2,3})*(\.\d+)?$|^\d+(\.\d+)?$")
ISIN = re.compile(r"(IN[A-Z0-9]{9,10}|(?<=[A-Z. ])NA(?= ))")
LINE = re.compile(r"^(\d{1,4}) (.+?) (Large|Mid|Small) Cap$")


def parse_line(line: str):
    """One PDF text line -> (rank, isin, name, symbols, nse_symbol, avg_mcap_cr, category), or None."""
    m = LINE.match(line.strip())
    if not m:
        return None
    rank, body, cat = int(m.group(1)), m.group(2), m.group(3)
    hits = list(ISIN.finditer(body))
    if not hits:
        return None
    last = hits[-1]
    name = body[:hits[0].start()].strip()
    rest = body[last.end():].split()
    nums = [t for t in rest if NUM.match(t)]
    syms = [t.strip("*$") for t in rest if not NUM.match(t) and t != "-"]
    syms = [s for s in syms if s]
    if not nums:
        return None
    nse = syms[1] if len(syms) >= 2 else (syms[0] if syms else "")
    return rank, last.group(1), name, " ".join(syms), nse, float(nums[-1].replace(",", "")), cat


def main(argv=None) -> int:
    from pypdf import PdfReader
    src, out = (argv or sys.argv[1:])[:2]
    rows, bad = [], []
    for page in PdfReader(src).pages:
        for line in page.extract_text().splitlines():
            r = parse_line(line)
            if r:
                rows.append(r)
            elif LINE.match(line.strip()):
                bad.append(line)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "isin", "name", "symbols", "nse_symbol", "avg_mcap_cr", "category"])
        w.writerows(rows)
    ranks = [r[0] for r in rows]
    missing = sorted(set(range(1, max(ranks) + 1)) - set(ranks))
    r300 = [r for r in rows if r[0] == 300]
    print(f"{src}: {len(rows)} rows, last rank {max(ranks)}, missing ranks {len(missing)} {missing[:10]}, "
          f"unparsed {len(bad)}; rank 300 = {r300[0][4] if r300 else '?'} {r300[0][5] if r300 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
