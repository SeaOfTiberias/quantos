"""scripts/book_daily.py -> call ledger (E5 follow-up, 2026-11-21). Synthetic symbols and levels only."""
from datetime import datetime

from core.ledger.schema import CallError, make_call
from scripts import book_daily as bd

BOOK = dict(id="2026-11-23", why="index W up; two longs off D demand",
            positions=[dict(id="SYN:p2", sym="SYN", track="p2",
                            setup=dict(setup="P2", side="long", entry=302.8, stop=290.1, target=337.5,
                                       valid=10, half_risk=True, entry_at_open=False)),
                       dict(id="SYM:p1", sym="SYM", track="p1",
                            setup=dict(setup="P1", side="short", entry=50.0, stop=53.0, target=44.0,
                                       entry_at_open=True))])


def test_ledger_raw_limit_and_open_entries():
    a, b = (bd.ledger_raw(BOOK, p) for p in BOOK["positions"])
    assert a["who"] == "book" and a["entry"] == dict(kind="limit", price=302.8, window=10)
    assert a["size_r"] == 0.5 and a["decision"] == "taken" and a["source_ref"] == "book:2026-11-23:SYN:p2"
    assert b["entry"] == dict(kind="open") and b["side"] == "short" and b["size_r"] == 1.0


def test_ledger_raw_passes_the_ledger_schema():
    for p in BOOK["positions"]:
        c = make_call(bd.ledger_raw(BOOK, p), now=datetime(2026, 11, 23, 21, 30), as_of="2026-11-20",
                      ref_close=51.0 if p["sym"] == "SYM" else 310.0, atr=3.0, map_read=dict(sym=p["sym"]), map_plan=None)
        assert c["who"] == "book" and c["stop"] is not None


def test_ledger_book_writes_each_position_and_never_raises():
    seen = []
    out = bd.ledger_book(BOOK, None, ledger_add=lambda raw: seen.append(raw) or dict(id=f"x-{raw['symbol']}"))
    assert [r["symbol"] for r in seen] == ["SYN", "SYM"] and out == ["ledger: x-SYN", "ledger: x-SYM"]

    def refuse(raw):
        raise CallError("no map read")
    assert all("not written: no map read" in o for o in bd.ledger_book(BOOK, None, ledger_add=refuse))

    def boom(raw):
        raise OSError("disk")
    assert bd.ledger_book(BOOK, None, ledger_add=boom)[0].startswith("ledger: book rows failed")
    assert bd.ledger_book(BOOK, None, ledger_add=lambda raw: None) == []          # already in the ledger
