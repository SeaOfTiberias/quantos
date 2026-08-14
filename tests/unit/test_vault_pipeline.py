"""
core/vault/ingest.py, compile.py and lint.py — the raw -> wiki pipeline.

Karpathy's three LLM-wiki operations. The properties worth protecting are the
ones that make a compiled wiki trustworthy rather than merely present:

  • an ingested source is identified by its bytes, so dragging the same
    article in twice does not double its weight in retrieval;
  • `raw/` is append-only, so a wiki page's citation still points at what it
    cited;
  • `compile` cannot write outside `wiki/`, and cannot emit executable rules.

The compile tests use a stub client. This module is never allowed to reach a
real model in a unit test — that would make the suite cost money and depend on
a network.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from core.vault.compile import (
    CompileError, _split_pages, _strip_rule_blocks, compile_vault, write_index,
)
from core.vault.index import VaultIndex
from core.vault.ingest import (
    IngestError, html_to_text, ingest_file, ingest_inbox, slugify,
)
from core.vault.layers import Layer, VaultPaths
from core.vault.lint import Severity, lint_vault

SOURCE = """# Minervini on the pivot

The pivot is the point of least resistance. Volume dries up to below 40% of
its fifty day average before the move.
"""


@pytest.fixture
def vault(tmp_path):
    return VaultPaths(tmp_path).ensure()


def drop(vault, name, text=SOURCE):
    path = vault.inbox / name
    path.write_text(text, encoding="utf-8")
    return path


class TestSlugify:

    def test_lowercases_and_hyphenates(self):
        assert slugify("Minervini on the Pivot") == "minervini-on-the-pivot"

    def test_folds_unicode_so_smart_quotes_do_not_fork_a_page(self):
        """"Minervini's" with a curly apostrophe and with a straight one are
        the same article and must not become two pages."""
        assert slugify("Minervini\u2019s Template") == slugify("Minervini's Template")

    def test_truncates_without_a_trailing_hyphen(self):
        assert not slugify("word " * 40).endswith("-")

    def test_empty_input_still_yields_a_name(self):
        assert slugify("!!!") == "untitled"


class TestHtmlToText:

    def test_strips_tags_and_entities(self):
        assert html_to_text("<p>a &amp; b</p>") == "a & b"

    def test_drops_script_and_style_contents(self):
        text = html_to_text("<style>p{color:red}</style><p>keep</p><script>x=1</script>")
        assert text == "keep"


class TestIngest:

    def test_files_under_topic_and_date(self, vault):
        drop(vault, "notes.md")
        result = ingest_file(vault.inbox / "notes.md", vault, topic="minervini",
                             on_date=date(2026, 8, 14))
        assert result.vault_path.parent == vault.raw / "minervini"
        assert result.vault_path.name.startswith("2026-08-14-")

    def test_body_is_preserved_verbatim(self, vault):
        """Sources are evidence. Rewriting them on the way in defeats the
        point of citing them."""
        drop(vault, "notes.md")
        result = ingest_file(vault.inbox / "notes.md", vault)
        assert "point of least resistance" in result.vault_path.read_text(encoding="utf-8")

    def test_records_provenance(self, vault):
        drop(vault, "notes.md")
        text = ingest_file(vault.inbox / "notes.md", vault).vault_path.read_text(encoding="utf-8")
        assert "origin:" in text and "checksum:" in text and "layer: raw" in text

    def test_windows_path_origin_stays_parseable_yaml(self, vault):
        r"""A double-quoted YAML scalar would treat D:\Exodus as escapes and
        fail to parse, silently costing the note its tags."""
        drop(vault, "notes.md")
        result = ingest_file(vault.inbox / "notes.md", vault,
                             origin=r"D:\Exodus_14_14\QuantOS\raw\notes.md")
        note = VaultIndex.load(vault.root).get(result.vault_path.stem)
        assert note.frontmatter.get("origin") == r"D:\Exodus_14_14\QuantOS\raw\notes.md"
        assert note.tags                     # frontmatter parsed, tags survived

    def test_identical_content_is_not_ingested_twice(self, vault):
        """Dragging the same article in again is a normal accident, and a
        duplicate would double its weight in BM25 and in compile."""
        drop(vault, "a.md")
        first = ingest_file(vault.inbox / "a.md", vault, move=False)
        drop(vault, "b.md")                  # same bytes, different filename
        second = ingest_file(vault.inbox / "b.md", vault, move=False)
        assert second.skipped is True
        assert second.vault_path == first.vault_path

    def test_different_content_same_title_lands_beside_it(self, vault):
        """raw/ is append-only: a revised source never overwrites the version
        earlier pages were compiled from."""
        drop(vault, "a.md")
        first = ingest_file(vault.inbox / "a.md", vault, on_date=date(2026, 8, 14), move=False)
        drop(vault, "b.md", SOURCE + "\nAn added paragraph.\n")
        second = ingest_file(vault.inbox / "b.md", vault, on_date=date(2026, 8, 14), move=False)
        assert second.skipped is False
        assert second.vault_path != first.vault_path
        assert first.vault_path.exists()

    def test_unsupported_extension_raises(self, vault):
        (vault.inbox / "paper.pdf").write_bytes(b"%PDF-1.4 binary")
        with pytest.raises(IngestError, match="not ingestible"):
            ingest_file(vault.inbox / "paper.pdf", vault)

    def test_missing_file_raises(self, vault):
        with pytest.raises(IngestError, match="no such file"):
            ingest_file(vault.inbox / "nope.md", vault)

    def test_html_is_converted(self, vault):
        drop(vault, "clip.html", "<h1>Clipped</h1><p>Body text</p>")
        result = ingest_file(vault.inbox / "clip.html", vault)
        assert "Body text" in result.vault_path.read_text(encoding="utf-8")


class TestIngestInbox:

    def test_processes_and_empties_the_inbox(self, vault):
        drop(vault, "a.md")
        drop(vault, "b.md", SOURCE + "\ndifferent\n")
        results = ingest_inbox(vault, topic="test", move=True)
        assert len([r for r in results if not r.skipped]) == 2
        assert list(vault.inbox.iterdir()) == []

    def test_a_bad_file_is_left_in_the_inbox_as_an_error_queue(self, vault):
        drop(vault, "good.md")
        (vault.inbox / "bad.pdf").write_bytes(b"binary")
        results = ingest_inbox(vault, move=True)
        assert (vault.inbox / "bad.pdf").exists()
        assert any(r.skipped and "not ingestible" in r.reason for r in results)

    def test_empty_inbox_is_not_an_error(self, vault):
        assert ingest_inbox(vault) == []

    def test_hidden_files_are_ignored(self, vault):
        (vault.inbox / ".DS_Store").write_text("junk", encoding="utf-8")
        assert ingest_inbox(vault) == []


class TestCompileSafety:
    """The compile step is the one an agent drives. These are the limits on it."""

    def _client(self, text):
        client = MagicMock()
        block = MagicMock()
        block.type, block.text = "text", text
        client.messages.create.return_value = MagicMock(content=[block])
        return client

    def _with_raw(self, vault):
        drop(vault, "src.md")
        ingest_file(vault.inbox / "src.md", vault, topic="t")
        return VaultIndex.load(vault.root)

    def test_writes_pages_into_wiki_concepts(self, vault):
        index = self._with_raw(vault)
        result = compile_vault(vault, index.by_layer(Layer.RAW),
                               client=self._client("===PAGE: Pivot Point===\n\n## What\n\nText."))
        assert len(result.pages_written) == 1
        assert result.pages_written[0].parent == vault.wiki_concepts.resolve()

    def test_generated_rule_blocks_are_stripped(self, vault):
        """A model summarising Minervini will happily produce a rule block.
        It must not land in the vault looking like a gate."""
        index = self._with_raw(vault)
        result = compile_vault(vault, index.by_layer(Layer.RAW), client=self._client(
            "===PAGE: Pivot===\n\n## What\n\n```quantos-rules\nclose > sma(50)\n```\n\nMore."))
        written = result.pages_written[0].read_text(encoding="utf-8")
        assert "quantos-rules" not in written
        assert "More." in written

    def test_compiled_page_is_never_auditable_even_with_rules(self, vault):
        """Belt and braces: even if a rule block somehow survived, the layer
        forbids executing it."""
        (vault.wiki_concepts / "sneaky.md").write_text(
            "# Sneaky\n\n```quantos-rules\nclose > sma(50)\n```\n", encoding="utf-8")
        index = VaultIndex.load(vault.root)
        assert index.get("sneaky").is_auditable is False
        assert index.auditable_notes == []

    def test_refuses_to_write_outside_wiki(self, vault):
        """A model-supplied page title containing path traversal must not be
        able to reach brain/."""
        index = self._with_raw(vault)
        result = compile_vault(vault, index.by_layer(Layer.RAW),
                               client=self._client("===PAGE: ../../brain/evil===\n\nbody"))
        # slugify neutralises the separators, so the page lands safely inside
        # wiki/ rather than escaping.
        for path in result.pages_written:
            assert vault.wiki.resolve() in path.parents

    def test_brain_notes_are_never_compiled(self, vault):
        """Feeding hand-written canon back through a model risks it returning
        as a wiki page."""
        (vault.brain / "Canon.md").write_text("# Canon\n\nMine.\n", encoding="utf-8")
        index = VaultIndex.load(vault.root)
        result = compile_vault(vault, index.notes, client=self._client("===PAGE: X===\n\nbody"))
        assert "Canon" not in result.sources_read

    def test_already_compiled_sources_are_skipped(self, vault):
        index = self._with_raw(vault)
        raw = index.by_layer(Layer.RAW)
        client = self._client("===PAGE: Pivot===\n\nbody")
        compile_vault(vault, raw, client=client)
        again = compile_vault(vault, raw, client=client)
        assert again.sources_read == []
        assert len(again.sources_skipped) == 1

    def test_force_recompiles(self, vault):
        index = self._with_raw(vault)
        raw = index.by_layer(Layer.RAW)
        client = self._client("===PAGE: Pivot===\n\nbody")
        compile_vault(vault, raw, client=client)
        again = compile_vault(vault, raw, client=client, force=True)
        assert len(again.sources_read) == 1

    def test_no_client_raises_rather_than_silently_doing_nothing(self, vault):
        index = self._with_raw(vault)
        with pytest.raises(CompileError, match="ANTHROPIC_API_KEY"):
            compile_vault(vault, index.by_layer(Layer.RAW), client=None)

    def test_a_failing_source_does_not_abort_the_run(self, vault):
        drop(vault, "a.md")
        ingest_file(vault.inbox / "a.md", vault, topic="t", move=False)
        drop(vault, "b.md", SOURCE + "\nsecond\n")
        ingest_file(vault.inbox / "b.md", vault, topic="t", move=False)

        client = MagicMock()
        good = MagicMock()
        good.type, good.text = "text", "===PAGE: Fine===\n\nbody"
        client.messages.create.side_effect = [RuntimeError("rate limited"),
                                              MagicMock(content=[good])]
        result = compile_vault(vault, VaultIndex.load(vault.root).by_layer(Layer.RAW),
                               client=client)
        assert len(result.errors) == 1
        assert len(result.sources_read) == 1


class TestSplitPages:

    def test_splits_multiple_pages(self):
        pages = _split_pages("===PAGE: A===\n\nbody a\n\n===PAGE: B===\n\nbody b")
        assert [t for t, _ in pages] == ["A", "B"]

    def test_response_without_a_delimiter_is_kept_not_discarded(self):
        assert _split_pages("just prose")[0][0] == "Untitled Concept"

    def test_empty_response_yields_nothing(self):
        assert _split_pages("") == []

    def test_strip_rule_blocks_counts_what_it_removed(self):
        cleaned, removed = _strip_rule_blocks(
            "a\n```quantos-rules\nx > y\n```\nb\n```quantos-rules\np > q\n```\n")
        assert removed == 2
        assert "quantos-rules" not in cleaned


class TestWriteIndex:

    def test_lists_notes_grouped_by_layer(self, vault):
        (vault.brain / "A.md").write_text("# A\n", encoding="utf-8")
        (vault.wiki_concepts / "B.md").write_text("# B\n", encoding="utf-8")
        index = VaultIndex.load(vault.root)
        text = write_index(vault, index.notes).read_text(encoding="utf-8")
        assert "brain/" in text and "wiki/" in text
        assert "[[A]]" in text and "[[B]]" in text

    def test_marks_which_layers_execute(self, vault):
        (vault.brain / "A.md").write_text("# A\n", encoding="utf-8")
        text = write_index(vault, VaultIndex.load(vault.root).notes).read_text(encoding="utf-8")
        assert "executable" in text


class TestLint:

    def test_clean_vault_has_no_errors(self, vault):
        (vault.brain / "A.md").write_text(
            "# A\n\n```quantos-rules\nclose > sma(50)\n```\n", encoding="utf-8")
        report = lint_vault(VaultIndex.load(vault.root))
        assert report.ok is True

    def test_rules_outside_brain_are_an_error(self, vault):
        (vault.wiki_concepts / "Gen.md").write_text(
            "# Gen\n\n```quantos-rules\nclose > sma(50)\n```\n", encoding="utf-8")
        report = lint_vault(VaultIndex.load(vault.root))
        assert not report.ok
        assert any(f.code == "rules-outside-brain" for f in report.errors)

    def test_unparseable_rule_is_an_error(self, vault):
        (vault.brain / "A.md").write_text(
            "# A\n\n```quantos-rules\nrsi > 70\n```\n", encoding="utf-8")
        report = lint_vault(VaultIndex.load(vault.root))
        assert any(f.code == "rule-syntax" for f in report.errors)

    def test_edited_raw_source_is_an_error(self, vault):
        """raw/ is immutable so a wiki citation keeps meaning something."""
        drop(vault, "src.md")
        result = ingest_file(vault.inbox / "src.md", vault, topic="t")
        text = result.vault_path.read_text(encoding="utf-8")
        result.vault_path.write_text(text + "\nsomeone edited this\n", encoding="utf-8")

        report = lint_vault(VaultIndex.load(vault.root))
        assert any(f.code == "raw-modified" for f in report.errors)

    def test_untouched_raw_source_passes(self, vault):
        drop(vault, "src.md")
        ingest_file(vault.inbox / "src.md", vault, topic="t")
        report = lint_vault(VaultIndex.load(vault.root))
        assert not any(f.code == "raw-modified" for f in report.findings)

    def test_duplicate_stems_are_a_warning(self, vault):
        (vault.brain / "Dup.md").write_text("# One\n", encoding="utf-8")
        (vault.wiki_concepts / "Dup.md").write_text("# Two\n", encoding="utf-8")
        report = lint_vault(VaultIndex.load(vault.root))
        assert any(f.code == "duplicate-stem" for f in report.warnings)

    def test_unresolved_link_is_info_not_an_error(self, vault):
        """In Obsidian this means 'page worth writing'."""
        (vault.brain / "A.md").write_text("# A\n\nsee [[Nonexistent]]\n", encoding="utf-8")
        report = lint_vault(VaultIndex.load(vault.root))
        assert report.ok is True
        assert any(f.code == "unresolved-link" for f in report.infos)

    def test_loose_note_with_rules_is_an_error(self, vault):
        (vault.root / "Stray.md").write_text(
            "# Stray\n\n```quantos-rules\nclose > sma(50)\n```\n", encoding="utf-8")
        report = lint_vault(VaultIndex.load(vault.root))
        assert any(f.code in ("unlayered-note", "rules-outside-brain") for f in report.errors)

    def test_loose_note_without_rules_is_only_a_warning(self, vault):
        (vault.root / "Stray.md").write_text("# Stray\n\njust notes\n", encoding="utf-8")
        report = lint_vault(VaultIndex.load(vault.root))
        assert report.ok is True
        assert any(f.code == "unlayered-note" for f in report.warnings)

    def test_stale_index_is_a_warning(self, vault):
        (vault.brain / "A.md").write_text("# A\n", encoding="utf-8")
        write_index(vault, VaultIndex.load(vault.root).notes)
        (vault.brain / "B.md").write_text("# B\n", encoding="utf-8")
        report = lint_vault(VaultIndex.load(vault.root))
        assert any(f.code == "index-stale" for f in report.warnings)
