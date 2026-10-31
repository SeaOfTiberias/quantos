"""
Symbol-change chaining (NSE's symbolchange.csv).

A bhavcopy row or a filing carries the symbol in force on its own date. To
join a company's whole history under one key, each (symbol, date) is mapped
forward through every rename whose effective date is AFTER that date. Dates
matter: NSE reuses retired symbols, and a row dated after a rename belongs to
whoever holds the symbol then, so it is not renamed.
"""

from __future__ import annotations

import csv
import io
from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

SYMBOL_CHANGES = Path("data_cache/nse_symbolchange.csv")


class SymbolChain:
    def __init__(self, changes: list[tuple[str, str, date]]) -> None:
        by_old: dict[str, list[tuple[date, str]]] = defaultdict(list)
        for old, new, eff in changes:
            if old != new:
                by_old[old].append((eff, new))
        self._by_old = {k: sorted(v) for k, v in by_old.items()}
        self._eff = {k: [e for e, _ in v] for k, v in self._by_old.items()}

    @classmethod
    def load(cls, path: Path = SYMBOL_CHANGES) -> "SymbolChain":
        text = path.read_bytes().decode("utf-8", errors="replace")
        rows = []
        for r in csv.reader(io.StringIO(text)):
            if len(r) < 4 or r[1].strip() == "OLD SYMBOL":
                continue
            try:
                eff = datetime.strptime(r[3].strip(), "%d-%b-%Y").date()
            except ValueError:
                continue
            rows.append((r[1].strip(), r[2].strip(), eff))
        return cls(rows)

    def canonical(self, symbol: str, on: date) -> str:
        """The symbol this company trades under after every later rename."""
        seen = set()
        while symbol in self._by_old and symbol not in seen:
            seen.add(symbol)
            i = bisect_right(self._eff[symbol], on)       # first rename effective after `on`
            if i == len(self._eff[symbol]):
                break
            symbol = self._by_old[symbol][i][1]
        return symbol

    def renamed(self) -> frozenset[str]:
        return frozenset(self._by_old)
