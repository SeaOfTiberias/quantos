"""
core/vault/layers.py and core/vault/wikilinks.py.

The layer tests exist for one reason: `Layer.is_executable` is the boundary
between "an agent can describe a strategy" and "an agent can author the
condition that releases a real order". The wiki/ layer is written by a model;
brain/ is written by a human and reviewed in a diff. Everything here pins that
apart, including the routes by which it could quietly stop holding — an
un-migrated vault, a note at the root, a rule block appearing in a compiled
page.
"""

import pytest

from core.vault.index import VaultIndex
from core.vault.layers import Layer, VaultPaths, layer_of
from core.vault.wikilinks import NoteGraph, WikiLink, normalise, parse_links

RULE_NOTE = """---
quantos:
  id: trend
---
# Trend

```quantos-rules
close > sma(50)
```
"""


class TestLayerExecutability:

    def test_only_brain_executes(self):
        assert Layer.BRAIN.is_executable is True
        assert Layer.RAW.is_executable is False
        assert Layer.WIKI.is_executable is False
        assert Layer.LOOSE.is_executable is False

    def test_only_wiki_is_agent_writable(self):
        """raw/ is append-only and brain/ is hand-authored, so wiki/ is the
        only place a compile step may create files."""
        assert Layer.WIKI.is_agent_written is True
        assert Layer.BRAIN.is_agent_written is False
        assert Layer.RAW.is_agent_written is False

    def test_no_layer_is_both_executable_and_agent_written(self):
        """The property that actually matters, stated directly. If this ever
        holds for some layer, a model can author a live trading gate."""
        for layer in Layer:
            assert not (layer.is_executable and layer.is_agent_written)


class TestLayerOf:

    def test_resolves_each_layer(self, tmp_path):
        for layer in (Layer.BRAIN, Layer.RAW, Layer.WIKI):
            path = tmp_path / layer.value / "note.md"
            assert layer_of(path, tmp_path) is layer

    def test_nested_subdirectories_keep_their_layer(self, tmp_path):
        assert layer_of(tmp_path / "raw" / "minervini" / "a.md", tmp_path) is Layer.RAW
        assert layer_of(tmp_path / "wiki" / "concepts" / "a.md", tmp_path) is Layer.WIKI

    def test_note_at_the_vault_root_is_loose(self, tmp_path):
        """What a pre-migration single-folder vault looks like."""
        assert layer_of(tmp_path / "note.md", tmp_path) is Layer.LOOSE

    def test_path_outside_the_vault_is_loose(self, tmp_path):
        assert layer_of(tmp_path.parent / "elsewhere.md", tmp_path) is Layer.LOOSE

    def test_layer_directory_match_is_case_insensitive(self, tmp_path):
        assert layer_of(tmp_path / "Brain" / "note.md", tmp_path) is Layer.BRAIN


class TestUnmigratedVaultFailsSafe:
    """An existing flat vault must degrade to 'nothing executes', never to
    'everything executes'."""

    def test_rules_at_the_root_do_not_execute(self, tmp_path):
        (tmp_path / "Trend.md").write_text(RULE_NOTE, encoding="utf-8")
        index = VaultIndex.load(tmp_path)
        note = index.get("Trend")
        assert note.layer is Layer.LOOSE
        assert note.rules                      # they parsed
        assert note.is_auditable is False      # but they will never run
        assert note.has_unexecutable_rules is True

    def test_the_same_note_in_brain_does_execute(self, tmp_path):
        (tmp_path / "brain").mkdir()
        (tmp_path / "brain" / "Trend.md").write_text(RULE_NOTE, encoding="utf-8")
        assert VaultIndex.load(tmp_path).get("Trend").is_auditable is True

    def test_rules_in_a_compiled_wiki_page_never_execute(self, tmp_path):
        """The scenario this whole boundary exists for: a model writes a page
        that happens to contain a rule block."""
        (tmp_path / "wiki").mkdir()
        (tmp_path / "wiki" / "Generated.md").write_text(RULE_NOTE, encoding="utf-8")
        index = VaultIndex.load(tmp_path)
        assert index.get("Generated").is_auditable is False
        assert index.auditable_notes == []

    def test_auditable_notes_excludes_every_non_brain_layer(self, tmp_path):
        for layer in ("brain", "raw", "wiki"):
            (tmp_path / layer).mkdir()
            (tmp_path / layer / f"{layer}_note.md").write_text(RULE_NOTE, encoding="utf-8")
        auditable = VaultIndex.load(tmp_path).auditable_notes
        assert [n.name for n in auditable] == ["brain_note"]


class TestVaultPaths:

    def test_ensure_creates_the_layout_idempotently(self, tmp_path):
        paths = VaultPaths(tmp_path).ensure()
        assert paths.brain.is_dir() and paths.raw.is_dir() and paths.wiki.is_dir()
        assert paths.inbox.is_dir()
        paths.ensure()                        # second call must not raise

    def test_ensure_does_not_touch_existing_files(self, tmp_path):
        brain = tmp_path / "brain"
        brain.mkdir()
        note = brain / "keep.md"
        note.write_text("original", encoding="utf-8")
        VaultPaths(tmp_path).ensure()
        assert note.read_text(encoding="utf-8") == "original"


class TestParseLinks:

    def test_plain_link(self):
        assert parse_links("see [[Stage Analysis]]") == (WikiLink(target="Stage Analysis"),)

    def test_alias(self):
        link = parse_links("see [[Stage Analysis|Weinstein]]")[0]
        assert link.target == "Stage Analysis"
        assert link.alias == "Weinstein"

    def test_heading(self):
        link = parse_links("see [[Notes#The pivot]]")[0]
        assert link.target == "Notes"
        assert link.heading == "The pivot"

    def test_heading_and_alias(self):
        link = parse_links("[[Notes#Pivot|the pivot point]]")[0]
        assert (link.target, link.heading, link.alias) == ("Notes", "Pivot", "the pivot point")

    def test_embed(self):
        assert parse_links("![[Chart]]")[0].is_embed is True

    def test_multiple_in_order(self):
        links = parse_links("[[A]] then [[B]] then [[A]]")
        assert [l.target for l in links] == ["A", "B", "A"]

    def test_links_inside_fenced_code_are_ignored(self):
        """A note documenting link syntax must not create real edges."""
        text = "real [[A]]\n\n```markdown\nexample [[NotReal]]\n```\n"
        assert [l.target for l in parse_links(text)] == ["A"]

    def test_links_inside_inline_code_are_ignored(self):
        assert parse_links("write `[[Target]]` to link") == ()

    def test_empty_target_ignored(self):
        assert parse_links("[[]] and [[  ]]") == ()

    def test_no_links(self):
        assert parse_links("plain prose with [brackets] and [a](link)") == ()

    def test_key_is_case_folded(self):
        assert parse_links("[[Stage ANALYSIS]]")[0].key == normalise("stage analysis")


class TestNoteGraph:

    class _Note:
        def __init__(self, name, links=()):
            self.name = name
            self.links = tuple(WikiLink(target=t) for t in links)

    def _graph(self):
        return NoteGraph.build([
            self._Note("A", ["B", "C"]),
            self._Note("B", ["C"]),
            self._Note("C"),
            self._Note("Island"),
        ])

    def test_forward_links(self):
        assert self._graph().links_from("A") == ["B", "C"]

    def test_backlinks(self):
        assert self._graph().links_to("C") == ["A", "B"]

    def test_neighbours_are_both_directions(self):
        assert self._graph().neighbours("B") == ["A", "C"]

    def test_link_resolution_is_case_insensitive(self):
        graph = NoteGraph.build([self._Note("Stage Analysis"), self._Note("X", ["stage analysis"])])
        assert graph.links_to("Stage Analysis") == ["X"]

    def test_expand_one_hop(self):
        assert self._graph().expand(["A"], hops=1) == ["A", "B", "C"]

    def test_expand_two_hops_reaches_further(self):
        graph = NoteGraph.build([
            self._Note("A", ["B"]), self._Note("B", ["C"]), self._Note("C"),
        ])
        assert graph.expand(["A"], hops=1) == ["A", "B"]
        assert graph.expand(["A"], hops=2) == ["A", "B", "C"]

    def test_expand_terminates_on_a_cycle(self):
        graph = NoteGraph.build([self._Note("A", ["B"]), self._Note("B", ["A"])])
        assert graph.expand(["A"], hops=10) == ["A", "B"]

    def test_expand_zero_hops_is_the_seed(self):
        assert self._graph().expand(["A"], hops=0) == ["A"]

    def test_unresolved_links_are_reported_with_their_sources(self):
        """In Obsidian an unresolved link means 'page worth writing', so this
        is information, not breakage."""
        graph = NoteGraph.build([self._Note("A", ["Missing"]), self._Note("B", ["Missing"])])
        assert graph.unresolved_links() == {"missing": ["A", "B"]}

    def test_expand_never_returns_an_unresolved_target(self):
        graph = NoteGraph.build([self._Note("A", ["Missing"])])
        assert graph.expand(["A"], hops=2) == ["A"]

    def test_orphans(self):
        assert self._graph().orphans() == ["Island"]

    def test_self_link_is_not_a_neighbour(self):
        graph = NoteGraph.build([self._Note("A", ["A"])])
        assert graph.neighbours("A") == []


class TestIndexGraphIntegration:

    def test_index_exposes_related_notes(self, tmp_path):
        brain = tmp_path / "brain"
        brain.mkdir()
        (brain / "A.md").write_text("# A\n\nsee [[B]]\n", encoding="utf-8")
        (brain / "B.md").write_text("# B\n", encoding="utf-8")
        index = VaultIndex.load(tmp_path)
        assert [n.name for n in index.related("A")] == ["B"]

    def test_related_excludes_the_note_itself(self, tmp_path):
        brain = tmp_path / "brain"
        brain.mkdir()
        (brain / "A.md").write_text("# A\n\nsee [[B]]\n", encoding="utf-8")
        (brain / "B.md").write_text("# B\n\nback to [[A]]\n", encoding="utf-8")
        assert "A" not in [n.name for n in VaultIndex.load(tmp_path).related("A")]
