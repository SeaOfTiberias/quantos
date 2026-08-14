"""
core/vault/parser.py and core/vault/index.py — reading an Obsidian vault.

The vault is a directory of ordinary markdown a human edits in Obsidian, so
these tests lean on what actually goes wrong with such a directory: broken
YAML, notes with no rules, Obsidian's own churning config files, and edits
landing while a long-running agent already holds an index.
"""

import pytest

from core.vault.index import (
    NoteNotFoundError, VaultIndex, VaultNotFoundError, tokenize,
)
from core.vault.parser import parse_note

VCP_NOTE = """---
tags:
  - strategy/momentum
  - trading/vcp
quantos:
  id: minervini_vcp
---

# Volatility Contraction Pattern

Progressive reduction of price volatility as supply is absorbed.

```quantos-rules
# the Stage 2 stack
close > sma(50) > sma(150)
sma(200) > sma(200)[20]    # 200-day sloping up
```
"""

WEINSTEIN_NOTE = """---
tags: [strategy/momentum, trading/stage-analysis]
quantos:
  id: weinstein_stage2
---

# Stage Analysis

Never buy below a flat or falling thirty week moving average.

```quantos-rules
close > sma(150)
```
"""

CONTEXT_NOTE = """---
tags:
  - journal
---

# Trading journal

No rules here, just notes about position sizing discipline.
"""


@pytest.fixture
def vault(tmp_path):
    (tmp_path / "Minervini.md").write_text(VCP_NOTE, encoding="utf-8")
    (tmp_path / "Weinstein.md").write_text(WEINSTEIN_NOTE, encoding="utf-8")
    (tmp_path / "Journal.md").write_text(CONTEXT_NOTE, encoding="utf-8")
    return tmp_path


class TestParseNote:

    def test_extracts_frontmatter_tags(self, vault):
        note = parse_note(vault / "Minervini.md")
        assert note.tags == ("strategy/momentum", "trading/vcp")

    def test_accepts_inline_tag_list_form(self, vault):
        """Obsidian writes `tags: [a, b]` as readily as a YAML block list."""
        note = parse_note(vault / "Weinstein.md")
        assert note.tags == ("strategy/momentum", "trading/stage-analysis")

    def test_title_comes_from_the_h1(self, vault):
        assert parse_note(vault / "Minervini.md").title == "Volatility Contraction Pattern"

    def test_strategy_id_prefers_frontmatter_over_filename(self, vault):
        note = parse_note(vault / "Minervini.md")
        assert note.name == "Minervini"
        assert note.strategy_id == "minervini_vcp"

    def test_strategy_id_falls_back_to_filename(self, vault):
        assert parse_note(vault / "Journal.md").strategy_id == "Journal"

    def test_extracts_rules_ignoring_comments_and_blanks(self, vault):
        rules = parse_note(vault / "Minervini.md").rules
        assert [r.expression for r in rules] == [
            "close > sma(50) > sma(150)",
            "sma(200) > sma(200)[20]",
        ]

    def test_captures_trailing_comment_on_a_rule(self, vault):
        rules = parse_note(vault / "Minervini.md").rules
        assert rules[1].comment == "200-day sloping up"

    def test_note_without_a_rule_block_is_not_auditable(self, vault):
        note = parse_note(vault / "Journal.md")
        assert note.rules == ()
        assert note.is_auditable is False

    def test_multiple_rule_blocks_are_concatenated(self, tmp_path):
        """Rules read better next to the prose that explains them than
        collected at the bottom of the note."""
        path = tmp_path / "Split.md"
        path.write_text(
            "# Split\n\n```quantos-rules\nclose > sma(50)\n```\n\n"
            "Some prose.\n\n```quantos-rules\nvolume > volume_sma(50)\n```\n",
            encoding="utf-8")
        assert len(parse_note(path).rules) == 2

    def test_broken_frontmatter_degrades_to_untagged_not_an_error(self, tmp_path):
        """One unreadable note must not be able to take the whole vault — and
        therefore every gate — down with it."""
        path = tmp_path / "Broken.md"
        path.write_text("---\ntags: [unclosed\n---\n\n# Broken\n", encoding="utf-8")
        note = parse_note(path)
        assert note.tags == ()
        assert note.title == "Broken"

    def test_note_with_no_frontmatter_at_all(self, tmp_path):
        path = tmp_path / "Plain.md"
        path.write_text("# Plain\n\nJust text.\n", encoding="utf-8")
        assert parse_note(path).tags == ()


class TestVaultIndex:

    def test_missing_directory_raises(self, tmp_path):
        with pytest.raises(VaultNotFoundError):
            VaultIndex.load(tmp_path / "nope")

    def test_indexes_every_markdown_file(self, vault):
        index = VaultIndex.load(vault)
        assert len(index.notes) == 3
        assert len(index.auditable_notes) == 2

    def test_get_by_filename_stem(self, vault):
        assert VaultIndex.load(vault).get("Minervini").strategy_id == "minervini_vcp"

    def test_get_by_strategy_id(self, vault):
        """Gates pin to a stable id; humans think in filenames. Both resolve,
        because a lookup that silently missed would be a gate blocking
        forever for an invisible reason."""
        assert VaultIndex.load(vault).get("minervini_vcp").name == "Minervini"

    def test_get_unknown_raises_and_names_what_it_knows(self, vault):
        with pytest.raises(NoteNotFoundError, match="Minervini"):
            VaultIndex.load(vault).get("nonexistent")

    def test_skips_obsidian_config_directory(self, vault):
        """.obsidian/workspace.json rewrites itself whenever a pane moves."""
        obsidian = vault / ".obsidian"
        obsidian.mkdir()
        (obsidian / "workspace.md").write_text("# not a strategy\n", encoding="utf-8")
        assert len(VaultIndex.load(vault).notes) == 3

    def test_indexes_notes_in_subdirectories(self, vault):
        sub = vault / "Strategies"
        sub.mkdir()
        (sub / "Nested.md").write_text("# Nested\n", encoding="utf-8")
        assert len(VaultIndex.load(vault).notes) == 4


class TestTagFiltering:

    def test_by_tag_exact(self, vault):
        names = {n.name for n in VaultIndex.load(vault).by_tag("trading/vcp")}
        assert names == {"Minervini"}

    def test_by_tag_matches_nested_tags(self, vault):
        """`strategy` should match `strategy/momentum`, as Obsidian's own tag
        pane does."""
        names = {n.name for n in VaultIndex.load(vault).by_tag("strategy")}
        assert names == {"Minervini", "Weinstein"}

    def test_by_tag_tolerates_a_leading_hash(self, vault):
        assert len(VaultIndex.load(vault).by_tag("#journal")) == 1


class TestSearch:

    def test_finds_by_body_term(self, vault):
        hits = VaultIndex.load(vault).search("supply absorbed")
        assert hits[0].note.name == "Minervini"

    def test_ranks_a_title_match_above_a_passing_mention(self, vault):
        hits = VaultIndex.load(vault).search("stage analysis")
        assert hits[0].note.name == "Weinstein"

    def test_tag_filter_applies_before_scoring(self, vault):
        """Narrowing to a tag must not be overridable by a higher-scoring
        note from another discipline."""
        hits = VaultIndex.load(vault).search("moving average", tags=["journal"])
        assert hits == []

    def test_no_match_returns_empty(self, vault):
        assert VaultIndex.load(vault).search("cointegration residual") == []

    def test_empty_query_returns_empty(self, vault):
        assert VaultIndex.load(vault).search("") == []

    def test_reports_which_terms_matched(self, vault):
        hits = VaultIndex.load(vault).search("thirty week moving average")
        assert "thirty" in hits[0].matched_terms

    def test_respects_limit(self, vault):
        assert len(VaultIndex.load(vault).search("a", limit=1)) <= 1


class TestReload:

    def test_no_change_is_a_noop(self, vault):
        index = VaultIndex.load(vault)
        assert index.reload_if_changed() is False

    def test_picks_up_an_edited_note(self, vault):
        """A long-running agent holds one index. Without this it would serve
        whatever rules were on disk at boot, indefinitely."""
        index = VaultIndex.load(vault)
        assert len(index.get("Weinstein").rules) == 1

        (vault / "Weinstein.md").write_text(
            WEINSTEIN_NOTE.replace(
                "close > sma(150)",
                "close > sma(150)\nvolume > volume_sma(50) * 2.0"),
            encoding="utf-8")
        # Force a distinct stamp — same-second writes can share an mtime.
        import os
        os.utime(vault / "Weinstein.md", (0, 0))

        assert index.reload_if_changed() is True
        assert len(index.get("Weinstein").rules) == 2

    def test_picks_up_a_new_note(self, vault):
        index = VaultIndex.load(vault)
        (vault / "New.md").write_text("# New\n", encoding="utf-8")
        assert index.reload_if_changed() is True
        assert index.has("New")


class TestTokenize:

    def test_lowercases_and_splits_on_punctuation(self):
        assert tokenize("SMA(200) > SMA(200)[20]!") == ["sma", "200", "sma", "200", "20"]
