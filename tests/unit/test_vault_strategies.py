"""
core/vault/strategies.py — strategy records, their lint check, and `vault report`.

The vault is the record of every strategy; reports are only as good as the
properties on each page, so these tests cover what goes wrong with
hand-compiled frontmatter: missing keys, off-vocabulary values, a mismatched
id, dates YAML did not parse. Plus the two wikilink edge cases the report
itself depends on.
"""

from datetime import date

import pytest

from core.vault.index import VaultIndex
from core.vault.layers import VaultPaths
from core.vault.lint import lint_vault
from core.vault.strategies import (
    filter_records, load_records, render_report, validate, write_report,
)
from core.vault.wikilinks import NoteGraph, parse_links


def _page(name, *, status="closed", verdict="FAIL", family="breakout", instrument="equity-cash",
          verdict_date="2026-09-22", extra="", strategy_id=None):
    return f"""---
title: {name}
tags:
  - wiki/concept
  - wiki/strategy
strategy_id: {strategy_id or name}
candidate: "1"
family: {family}
instrument: {instrument}
status: {status}
verdict: {verdict}
first_tested: 2026-09-20
verdict_date: {verdict_date}
profit_factor: 0.9
sharpe: -0.5
trades: 100
headline: "{name} headline."
{extra}quantos:
  layer: wiki
  generated: true
---

# {name}

Body.
"""


@pytest.fixture
def vault(tmp_path):
    paths = VaultPaths(tmp_path).ensure()
    concepts = paths.wiki_concepts
    (concepts / "alpha.md").write_text(_page("alpha"), encoding="utf-8")
    (concepts / "beta.md").write_text(
        _page("beta", status="live-paper", verdict="PASS", family="momentum",
              verdict_date="2026-10-05", extra='capital: "₹5L paper"\nnext_gate: "go-ahead"\n'),
        encoding="utf-8")
    (concepts / "gamma.md").write_text(
        _page("gamma", status="live-tool", verdict="N/A", family="discretionary-aid",
              instrument="stock-options", verdict_date=""), encoding="utf-8")
    (concepts / "not-a-strategy.md").write_text(
        "---\ntags:\n  - wiki/concept\nquantos:\n  layer: wiki\n---\n\n# Concept\n", encoding="utf-8")
    return paths


def _index(paths):
    return VaultIndex.load(paths.root)


class TestValidate:
    def test_complete_records_are_clean(self, vault):
        index = _index(vault)
        assert all(validate(index.get(n)) == [] for n in ("alpha", "beta", "gamma"))

    def test_missing_and_off_vocabulary(self, vault):
        (vault.wiki_concepts / "bad.md").write_text(
            _page("bad", status="dead", family="").replace('headline: "bad headline."\n', ""),
            encoding="utf-8")
        problems = " ".join(validate(_index(vault).get("bad")))
        assert "missing `family`" in problems
        assert "missing `headline`" in problems
        assert "`status: dead` is not one of" in problems

    def test_verdict_date_required_unless_open(self, vault):
        (vault.wiki_concepts / "nodate.md").write_text(_page("nodate", verdict_date=""), encoding="utf-8")
        (vault.wiki_concepts / "open.md").write_text(
            _page("open", verdict="OPEN", verdict_date=""), encoding="utf-8")
        index = _index(vault)
        assert any("verdict_date" in p for p in validate(index.get("nodate")))
        assert validate(index.get("open")) == []

    def test_strategy_id_must_match_file(self, vault):
        (vault.wiki_concepts / "delta.md").write_text(_page("delta", strategy_id="other"), encoding="utf-8")
        assert any("does not match" in p for p in validate(_index(vault).get("delta")))

    def test_lint_reports_strategy_record_warnings(self, vault):
        (vault.wiki_concepts / "bad.md").write_text(_page("bad", status="dead"), encoding="utf-8")
        report = lint_vault(_index(vault))
        codes = [(f.code, f.note) for f in report.warnings]
        assert ("strategy-record", "bad") in codes
        assert report.ok  # warnings only: an incomplete record cannot release money


class TestRecordsAndFilters:
    def test_only_tagged_wiki_pages_load(self, vault):
        names = {r.name for r in load_records(_index(vault).notes)}
        assert names == {"alpha", "beta", "gamma"}

    def test_types(self, vault):
        beta = next(r for r in load_records(_index(vault).notes) if r.name == "beta")
        assert beta.verdict_date == date(2026, 10, 5)
        assert beta.profit_factor == 0.9 and beta.trades == 100
        assert beta.is_live and beta.capital == "₹5L paper"

    def test_filters(self, vault):
        records = load_records(_index(vault).notes)
        assert {r.name for r in filter_records(records, live_only=True)} == {"beta", "gamma"}
        assert {r.name for r in filter_records(records, verdict=["FAIL"])} == {"alpha"}
        assert {r.name for r in filter_records(records, family=["momentum", "breakout"])} == {"alpha", "beta"}
        assert {r.name for r in filter_records(records, since=date(2026, 10, 1))} == {"beta"}


class TestReport:
    def test_render_and_write(self, vault):
        records = load_records(_index(vault).notes)
        text = render_report(records, today=date(2026, 10, 13))
        assert "**3** strategy records: 1 PASS, 1 FAIL, 1 N/A." in text
        assert "**Real capital deployed:** none." in text
        assert "[[beta\\|beta]]" in text  # escaped pipe inside tables
        reg = text.split("## Register")[1]
        assert reg.index("[[beta") < reg.index("[[alpha")  # newest verdict first
        path = write_report(vault, text, today=date(2026, 10, 13))
        assert path == vault.wiki / "reports" / "strategy-register-2026-10-13.md"

    def test_report_links_resolve_and_lint_stays_clean(self, vault):
        text = render_report(load_records(_index(vault).notes), today=date(2026, 10, 13))
        write_report(vault, text, today=date(2026, 10, 13))
        index = _index(vault)
        unresolved = index.graph.unresolved_links()
        assert not any(t.startswith(("alpha", "beta", "gamma")) for t in unresolved)


class TestWikilinkEdgeCases:
    def test_table_escaped_alias_pipe(self):
        (link,) = parse_links("| [[darvas-atr-stop\\|Darvas]] |")
        assert link.target == "darvas-atr-stop" and link.alias == "Darvas"

    def test_base_embed_not_reported_unresolved(self):
        from types import SimpleNamespace
        hub = SimpleNamespace(name="hub", links=parse_links("![[Strategy Register.base]] and [[missing-page]]"))
        graph = NoteGraph.build([hub])
        assert set(graph.unresolved_links()) == {"missing-page"}
