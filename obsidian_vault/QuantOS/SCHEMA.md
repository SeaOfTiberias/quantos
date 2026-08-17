---
tags:
  - meta/schema
quantos:
  layer: meta
---

# Vault schema

Conventions for this vault. Karpathy's LLM-wiki pattern puts this in a
`CLAUDE.md`; here it lives inside the vault so it travels with the notes and is
readable in Obsidian beside them.

**If you are an agent working on this vault, read this first.**

---

## The three layers

| Layer | Written by | Executable | Mutable |
|---|---|---|---|
| `brain/` | **you, by hand** | **yes** | yes |
| `raw/` | `vault ingest` | no | **no — append only** |
| `wiki/` | `vault compile` (an agent) | no | yes, freely |

### `brain/` — canon

Hand-authored strategy notes. This is the **only** layer whose
```` ```quantos-rules ```` blocks are ever evaluated, and therefore the only
layer that can gate a trade.

An agent must never create or edit a file here. That is not a style
preference: a rule in `brain/` can veto a real order, and the boundary between
"a model can describe a strategy" and "a model can author the condition that
releases money" is this directory. Propose changes in prose; a human writes
them.

### `raw/` — sources

Immutable evidence. Files land here via `python scripts/vault.py ingest`, which
stamps each with its origin, ingest date, and two SHA-256 hashes.

Never edit a file in `raw/`. Wiki pages cite these bytes, and `vault lint`
re-hashes the body to check. A newer version of a source is a **new ingest**,
filed under its own date — not an overwrite.

Layout: `raw/<topic>/YYYY-MM-DD-slug.md`

### `wiki/` — compiled pages

Agent-written entity pages, one concept per page, interlinked with
`[[wiki-links]]` and citing `raw/` sources. Freely editable and freely
regenerable — a recompile may overwrite anything here, so nothing irreplaceable
belongs in this layer.

Two special pages:
- `wiki/index.md` — generated table of contents. Do not hand-edit; run
  `vault index`.
- `wiki/log.md` — append-only record of what has been compiled. `compile` reads
  it to skip sources it has already seen.

---

## Note frontmatter

```yaml
---
tags:
  - strategy/momentum        # nested tags work; `strategy` matches all children
  - trading/vcp
quantos:
  id: minervini_vcp          # stable handle for gates; defaults to the filename
  timeframe: daily
---
```

Only `tags` and `quantos.id` are load-bearing. Everything else is yours.

---

## Rule blocks

Only meaningful in `brain/`. A rule block anywhere else is a **lint error** —
it does nothing, and its author probably believes otherwise.

````markdown
```quantos-rules
# comments and blank lines are ignored
close > sma(50) > sma(150) > sma(200)
sma(200) > sma(200)[20]        # trailing comments work too
volume_sma(5) / volume_sma(50) < 0.40
```
````

| | |
|---|---|
| Scalars | `close` `bar_open` `bar_high` `bar_low` `volume` `rs_rating` |
| Windows | `sma(n)` `ema(n)` `high(n)` `low(n)` `volume_sma(n)` |
| Lag | `term[n]` — n bars ago |
| Operators | `> >= < <= == !=` · `+ - * /` · unary `-` · `and` `or` |

Every rule must be a comparison. All rules in a note are conjunctive. Anything
outside this vocabulary is rejected when the vault loads.

Full reference: `docs/OBSIDIAN_VAULT_INTEGRATION.md`.

---

## Stage blocks

The other kind of machine-readable block, and the difference is the whole
point of having two. A rule block is **conjunctive** and answers one
PASS/FAIL. A stage block is a **classifier**: the stages are mutually
exclusive, so it is evaluated **first match wins**, top to bottom, and line
order is load-bearing.

````markdown
```quantos-stages
stage 4 when sma(150) < sma(150)[25] * 0.99
stage 2 pivot when sma(150) > sma(150)[25] * 1.01 and volume_sma(5) / volume_sma(50) < 0.40
stage 2 when sma(150) > sma(150)[25] * 1.01
stage 3 when sma(150)[25] > sma(150)[125]
stage 1                       # terminal default — must be last
```
````

`stage <1-4> [phase] [when <expression>]`. The expression is the same DSL as a
rule block, with the same vocabulary and the same validation. The optional
`phase` is a free sub-label (`pivot`, `pullback`) that refines the display
without creating a new stage.

**A stage is not a verdict and never gates anything.** A verdict has a safe
default — block — and fails closed. A stage has no safe default, so when a
clause cannot be evaluated the classifier **stops** and reports *unclassified*
rather than falling through to a later clause. Nothing in `core/vault/gates.py`
reads a stage, and a test enforces that.

See `core/vault/stages.py`, and `Stan_Weinstein_Stage_Analysis` for the
worked example.

---

## Writing wiki pages

For agents running `compile`, in addition to `prompts/vault_compile_system.md`:

- **One page per concept**, not per source. Three articles about volatility
  contraction update one page.
- **Link with a reason.** `A stricter form of [[Stage Analysis]]'s Stage 2 test`
  beats `Related: [[Stage Analysis]]`.
- **Cite every substantive claim** as `[[source-note-name]]`.
- **Only what the source supports.** No filling gaps from general knowledge, and
  say so where a source is vague.
- **Never claim profitability.** Write "Minervini requires X", never "X
  produces returns". Nothing in this vault is backtested, and the owner has
  tested nineteen strategies with no validated edge.
- **Never emit a rule block.** It gets stripped and flagged.

---

## Commands

```bash
python scripts/vault.py init                 # create the layout
python scripts/vault.py ingest --topic X     # file raw/_inbox -> raw/X/
python scripts/vault.py compile              # raw/ -> wiki/  (unattended; needs a key)
python scripts/vault.py query "..."          # BM25 + graph expansion
python scripts/vault.py lint                 # integrity + safety
python scripts/vault.py index                # regenerate wiki/index.md
python scripts/vault.py status               # what is where
python scripts/vault.py graph <note>         # links in and out

python scripts/audit_symbol.py TVSMOTOR      # audit a symbol against brain/
```

Only `compile` needs an API key, and only in its unattended form. The better
route is to ask your coding agent to **"compile the vault"** — it loads
`.claude/skills/vault-compile/SKILL.md`, reads the existing pages properly
before linking to them, and needs no key.

---

## What lives outside this vault

- `.obsidian/` is gitignored — `workspace.json` rewrites itself constantly.
- The notes themselves **are** tracked, and reach the production VM through
  `git pull`. The VM therefore audits against committed rules only; an
  uncommitted local edit cannot change live behaviour.
