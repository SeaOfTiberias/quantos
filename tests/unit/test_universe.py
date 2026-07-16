"""
Universe file loading + generation (2026-07-16 de-link).

Covers the committed Nifty 500 universe that now feeds BOTH Stage A discovery
and the regime advance/decline sample, and the NSE-CSV generator that builds it.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from agent.main import _load_universe

REPO_ROOT = Path(__file__).resolve().parents[2]
NIFTY500 = REPO_ROOT / "agent" / "universe_nifty500.txt"


def _load_build_universe():
    """Import scripts/build_universe.py — not a package, so load it by path."""
    spec = importlib.util.spec_from_file_location(
        "build_universe", REPO_ROOT / "scripts" / "build_universe.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_universe"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestLoadUniverse:
    def test_parses_comma_and_newline_separated(self, tmp_path):
        f = tmp_path / "u.txt"
        f.write_text("AAA,BBB\nCCC\n", encoding="utf-8")
        assert _load_universe(str(f)) == ["AAA", "BBB", "CCC"]

    def test_ignores_full_line_and_inline_comments(self, tmp_path):
        f = tmp_path / "u.txt"
        f.write_text("# header\nAAA  # trailing\n\nBBB\n", encoding="utf-8")
        assert _load_universe(str(f)) == ["AAA", "BBB"]

    def test_dedupes_and_uppercases(self, tmp_path):
        f = tmp_path / "u.txt"
        f.write_text("aaa,AAA\nbbb\n", encoding="utf-8")
        assert _load_universe(str(f)) == ["AAA", "BBB"]

    def test_missing_file_returns_empty_not_raise(self, tmp_path):
        # Breadth degrades to a neutral placeholder on an empty universe rather
        # than taking the agent down — see core/regime/fetcher.MIN_BREADTH_SAMPLE.
        assert _load_universe(str(tmp_path / "nope.txt")) == []

    def test_utf8_content_round_trips(self, tmp_path):
        f = tmp_path / "u.txt"
        f.write_bytes("# hdr — dash\nAAA\n".encode("utf-8"))
        assert _load_universe(str(f)) == ["AAA"]

    def test_locale_encoded_file_fails_the_same_on_every_platform(self, tmp_path):
        """Universe files are generated on Windows and read on the Linux VM.

        _load_universe reads UTF-8 explicitly rather than deferring to the
        ambient locale. That matters because the failure it prevents is
        platform-split: a header written in cp1252 (em-dash -> 0x97) used to
        parse silently on the Windows laptop and raise UnicodeDecodeError only
        on the Linux VM, crash-looping the service at startup. Failing
        identically everywhere is the point — the laptop now reproduces the VM.
        """
        f = tmp_path / "u.txt"
        f.write_bytes("# hdr — dash\nAAA\n".encode("cp1252"))
        with pytest.raises(UnicodeDecodeError):
            _load_universe(str(f))


class TestCommittedNifty500:
    def test_exists_and_has_500_symbols(self):
        assert NIFTY500.exists(), f"{NIFTY500} missing — regenerate with scripts/build_universe.py"
        assert len(_load_universe(str(NIFTY500))) == 500

    def test_no_duplicates(self):
        syms = _load_universe(str(NIFTY500))
        assert len(syms) == len(set(syms))

    def test_is_ascii_only(self):
        """Regression guard.

        The generator originally wrote this file with the Windows locale
        encoding (cp1252), which encoded an em-dash in the header comment to
        byte 0x97 — not valid UTF-8. The agent reads it on Linux, so the VM
        crash-looped on UnicodeDecodeError at startup. Keep the file ASCII.
        """
        raw = NIFTY500.read_bytes()
        assert all(b < 128 for b in raw), (
            "universe file has non-ASCII bytes: "
            f"{sorted({hex(b) for b in raw if b > 127})}"
        )
        raw.decode("utf-8")  # must not raise

    def test_symbols_are_fyers_safe(self):
        """Broker adapters build NSE:{symbol}-EQ unconditionally."""
        import re
        for s in _load_universe(str(NIFTY500)):
            assert re.fullmatch(r"[A-Z0-9&-]+", s), f"unexpected characters in symbol: {s!r}"


class TestBuildUniverse:
    def test_drops_non_eq_series(self, tmp_path):
        csv = tmp_path / "idx.csv"
        csv.write_text(
            "Company Name,Industry,Symbol,Series,ISIN Code\n"
            "Alpha Ltd.,IT,ALPHA,EQ,INE001A01001\n"
            "Beta Ltd.,IT,BETA,BE,INE002A01002\n",
            encoding="utf-8",
        )
        mod = _load_build_universe()
        symbols, skipped = mod.read_constituents(csv)
        assert symbols == ["ALPHA"]
        assert skipped == ["BETA"]

    def test_handles_bom_from_nse_csv(self, tmp_path):
        """NSE ships these CSVs with a UTF-8 BOM, which would otherwise attach
        itself to the first header and break the 'Symbol' lookup."""
        csv = tmp_path / "idx.csv"
        csv.write_bytes(
            "﻿Company Name,Industry,Symbol,Series,ISIN Code\n"
            "Alpha Ltd.,IT,ALPHA,EQ,INE001A01001\n".encode("utf-8")
        )
        mod = _load_build_universe()
        symbols, _ = mod.read_constituents(csv)
        assert symbols == ["ALPHA"]

    def test_rejects_csv_without_symbol_column(self, tmp_path):
        csv = tmp_path / "bad.csv"
        csv.write_text("Name,Sector\nAlpha,IT\n", encoding="utf-8")
        mod = _load_build_universe()
        with pytest.raises(SystemExit, match="no 'Symbol' column"):
            mod.read_constituents(csv)

    def test_written_file_is_utf8_and_round_trips(self, tmp_path):
        mod = _load_build_universe()
        out = tmp_path / "u.txt"
        mod.write_universe(["AAA", "BBB"], out, "src.csv", "Test Index")
        out.read_bytes().decode("utf-8")  # must not raise
        assert _load_universe(str(out)) == ["AAA", "BBB"]
