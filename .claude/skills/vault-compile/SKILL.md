---
name: vault-compile
description: Compile ingested sources in the QuantOS Obsidian vault's raw/ layer into interlinked wiki/ entity pages (Karpathy LLM-wiki pattern). Use when the user asks to compile the vault, process the inbox, build wiki pages from sources, or update the knowledge base after ingesting something. Also use when they ask what a concept in their notes means and the wiki has no page for it yet.
---

# Compile the vault

Turn sources in `raw/` into durable, interlinked concept pages in `wiki/`.

You are doing this **with file tools**, not through an API call. That is the
point: you can read every existing wiki page before deciding whether a concept
needs a new page or an update to an old one, and you can lint and fix
afterwards. `core/vault/compile.py` exists for unattended runs on the VM and is
strictly worse — it sees only a list of page *names*.

## Before you start

```bash
python scripts/vault.py status     # what is in each layer
python scripts/vault.py lint       # fix errors before adding more
```

Read `obsidian_vault/QuantOS/SCHEMA.md`. It is the vault's own conventions doc
and it governs anything not stated here.

## The layer rule — non-negotiable

| Layer | You may write it? |
|---|---|
| `brain/` | **NO. Never.** Hand-authored canon; its rules gate real orders. |
| `raw/` | **NO.** Immutable once ingested; wiki pages cite these bytes. |
| `wiki/` | Yes. This is your layer. |

**Never emit a ```quantos-rules``` block.** Executable rules live only in
`brain/`, written by the user. If a source describes conditions, write them as
prose or a plain markdown table. A rule block in `wiki/` is a lint ERROR, and
its real cost is that it would let a model author a condition that releases
money — see `core/vault/layers.py`.

If you believe a source justifies a new executable rule, say so in your summary
and let the user write it. Do not write it for them.

## Procedure

1. **Find uncompiled sources.** `wiki/log.md` records what has already been
   compiled. Anything in `raw/` not named there is new.

2. **Read the existing wiki first.** Read `wiki/index.md` and the actual
   contents of `wiki/concepts/*.md`. You need to know what concepts already
   have pages and what those pages say, so you update rather than duplicate.

3. **Read the source in full.**

4. **Decide the concept split.** One page per concept, not per source. A single
   article may yield three pages; three articles may all update one. If a
   concept already has a page, edit that page — add the new material, cite the
   new source, reconcile or mark any contradiction.

5. **Write the pages** into `wiki/concepts/<slug>.md`, kebab-case slug.

6. **Regenerate and check.**
   ```bash
   python scripts/vault.py index
   python scripts/vault.py lint
   ```
   Fix every ERROR. Unresolved links are INFO — they mean "page worth writing"
   and are fine to leave.

7. **Append to `wiki/log.md`**, one line per source, matching the existing
   format so `compile.py` also treats it as done:
   ```
   - 2026-08-14T09:12:00+00:00 — compiled [[source-note-name]] -> [[page-one]], [[page-two]]
   ```

8. **Report** which sources you read, which pages you created vs updated, and
   anything you deliberately did not write.

## Page format

```markdown
---
title: Volatility Contraction
compiled: 2026-08-14
tags:
  - wiki/concept
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-08-14-minervini-on-the-pivot-point
---

# Volatility Contraction

> [!abstract] Compiled page
> Written from `[[2026-08-14-minervini-on-the-pivot-point]]` on 2026-08-14.
> Context and retrieval only — rules in this layer never execute.

## Definition

Two or three sentences. Someone who has not read the source should finish this
section understanding what the concept is.

## Mechanics

How it works. Specific numbers, thresholds, formulas, timeframes — whatever the
source actually gives. This is what makes the page worth more than a bookmark.

## Relation to other concepts

A stricter form of [[Stage Analysis]]'s Stage 2 test, adding two more moving
averages [[2026-08-14-minervini-on-the-pivot-point]].
```

## Writing rules

- **Only what the source supports.** No threshold the source did not give. Do
  not fill gaps from your own knowledge of the topic, and never present your
  knowledge as though it came from the source. Where the source is vague, say
  it is vague.
- **Cite every substantive claim** as `[[raw-source-note-name]]`.
- **Link with a reason.** "Related: [[Stage Analysis]]" is nearly useless. "A
  stricter form of [[Stage Analysis]]'s Stage 2 test" is the page earning its
  place.
- **Never claim profitability.** Sources describe what a method looks for. Write
  "Minervini requires X", never "X produces returns". This user has tested
  nineteen strategies with no validated edge; a page that reads as endorsement
  is actively harmful here.
- **Mark disagreement, do not resolve it.** If a new source contradicts an
  existing page, write both and attribute both.
- **No filler.** No "it is important to note", no "in the world of trading".
- Dense, specific, unhurried. A page that takes ninety seconds to read and
  settles a question is the target.

## If `raw/` is empty

Tell the user to drop files into `obsidian_vault/QuantOS/raw/_inbox/` and run:

```bash
python scripts/vault.py ingest --topic <topic>
```

Do not invent sources, and do not compile from your own knowledge. A wiki page
with no citable source is exactly the failure this vault's provenance tracking
exists to prevent.
