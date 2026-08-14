# Obsidian Vault Integration

Uses a local Obsidian note vault as QuantOS's qualitative memory. A strategy
note carries both the prose a human reads and a machine-readable rule block a
signal can be audited against before it reaches an execution path.

Built 2026-08-14. **Nothing in this vault has been backtested.** A `PASS` means
"this symbol satisfies the conditions written in the note", which is a statement
about structure — never evidence of an edge. See the closing section.

---

## Layout

```
obsidian_vault/QuantOS/            # the vault. Notes tracked; .obsidian/ ignored
  Mark_Minervini_VCP_Strategy.md   # id: minervini_vcp
  Stan_Weinstein_Stage_Analysis.md # id: weinstein_stage2

core/vault/
  models.py          # Verdict, Rule, RuleResult, AuditReport, GateDecision
  parser.py          # markdown + YAML frontmatter -> StrategyNote
  index.py           # VaultIndex: load, tag filter, BM25 retrieval, mtime reload
  facts.py           # MarketFacts: the numbers a rule may reference
  rules.py           # the rule DSL: whitelist AST parse + evaluate
  auditor.py         # StrategyAuditor: note + bars -> AuditReport
  narrator.py        # optional Claude prose over an ALREADY-DECIDED verdict
  gates.py           # audit_gate(): the fail-closed entry point
  shortlist_audit.py # momentum shortlist annotator

prompts/
  vault_audit_narrator_system.md
  vault_audit_narrator_user.md

scripts/audit_symbol.py            # CLI: audit, search, list
```

---

## Note format

An ordinary Obsidian document. Frontmatter tags still drive Obsidian's search
and graph view; the rule block renders as a plain code block. No plugin needed.

````markdown
---
tags:
  - strategy/momentum
  - trading/vcp
quantos:
  id: minervini_vcp
---

# Mark Minervini's VCP

Prose, diagrams, links — anything at all.

```quantos-rules
# Stage 2 uptrend — the SEPA trend template
close > sma(50) > sma(150) > sma(200)
sma(200) > sma(200)[20]        # 200-day sloping up over a month
```
````

- `quantos.id` is a stable handle for gates; without it the filename stem is used.
  `VaultIndex.get()` accepts either.
- Multiple `quantos-rules` blocks per note are concatenated — put rules next to
  the prose that explains them.
- A note with no rule block is still indexed and searchable. It just cannot
  produce a verdict.
- **All rules in a note are conjunctive.** All notes passed to a gate are also
  conjunctive.

---

## The rule DSL

| | |
|---|---|
| **Scalars** | `close`, `bar_open`, `bar_high`, `bar_low`, `volume`, `rs_rating` |
| **Windows** | `sma(n)`, `ema(n)`, `high(n)`, `low(n)`, `volume_sma(n)` |
| **Lag** | any term `[n]` = n bars ago, e.g. `sma(200)[20]` |
| **Operators** | `> >= < <= == !=`, `+ - * /`, unary `-`, `and`, `or` |
| **Comments** | `# ...` on its own line or trailing a rule |

Chained comparisons work, so a note reads the way its author writes it:
`close > sma(50) > sma(150) > sma(200)`.

Every rule must be a comparison. A bare `sma(50)` is rejected at parse time —
treating its truthiness as a verdict would pass for any non-zero average.

### Safety

Rules are parsed with `ast.parse(mode="eval")` and walked against a whitelist
of node types, function names, and variable names. Nothing from the vault
reaches an interpreter. Attribute access, comprehensions, lambdas, string
literals, and calls to anything outside the table above are all rejected when
the vault loads — not when a signal fires.

This matters because the vault is a directory of markdown that syncs through
Obsidian and arrives on the VM via `git pull`. Without the whitelist, "can
write to the vault" would equal "can run code as the user holding the broker
keys".

---

## The fail-closed contract

`Verdict` has four values, and **only `PASS` clears**:

| Verdict | Meaning | Clears? |
|---|---|---|
| `PASS` | every rule evaluated and held | **yes** |
| `FAIL` | a rule was evaluated and rejected | no |
| `INSUFFICIENT_DATA` | a rule could not be computed | no |
| `UNAVAILABLE` | the audit could not be attempted | no |

`INSUFFICIENT_DATA` deliberately outranks `FAIL`. They mean opposite things:
`FAIL` says the market rejected the setup, `INSUFFICIENT_DATA` says the audit
did not happen. Collapsing them would hide a broken data feed inside a stream
of plausible-looking rejections — this project's canonical failure mode, where
systemd, the heartbeat and `/regime/status` all read green for 70 minutes while
the broker connection was dead.

`GateDecision.allowed` is True in exactly two cases: everything passed, or the
gate was explicitly disabled in config (`skipped=True`). A missing vault,
missing note, empty note list, unparseable rule, or any unexpected exception
returns False. There is no path that returns True with a caveat attached.

---

## Integration points

| Where | Default | Effect |
|---|---|---|
| Momentum shortlist | **on** | Adds a `vault_verdict` / `vault_detail` column. No execution path — annotation only. |
| `scripts/audit_symbol.py` | on demand | Full rule-by-rule breakdown, vault search, note listing. |
| Options webhook `open` | **off** | Hard veto before the chain is built. `vault.gate_options_webhook` |
| Rotation pilot buys | **off** | Filters new entrants before sizing. `vault.gate_rotation_pilot` |

Both execution gates ship **off**. Each adds a veto to a path that spends
money, so enabling one is a deliberate act. Watch the shortlist's vault column
for a few sessions first — it is free and it shows you exactly what the rules
reject before an order depends on it.

The rotation pilot **never filters sells**. A rule audit is an entry criterion;
refusing to exit because the vault could not be read would turn a research aid
into a risk. Same "refuse entries, keep managing exits" philosophy as the kill
switch.

### CLI

```bash
python scripts/audit_symbol.py TVSMOTOR                    # all auditable notes
python scripts/audit_symbol.py TVSMOTOR --note minervini_vcp
python scripts/audit_symbol.py TVSMOTOR --rs-rating 85     # supply the RS input
python scripts/audit_symbol.py TVSMOTOR --universe agent/universe_nifty500.txt
python scripts/audit_symbol.py --search "volume dry up before a pivot"
python scripts/audit_symbol.py --list
```

---

## Retrieval

`VaultIndex.search()` is BM25 over frontmatter-tag-filtered notes. Tag
filtering happens before scoring, so narrowing to `strategy/momentum` cannot be
overridden by a high-scoring note from another discipline.

Lexical, not vector. At tens of notes this is the better tool, not a
compromise: exact, reproducible, no model download, no API key, no network. And
notes are written in the vocabulary they get queried in. The cost is real —
BM25 will not connect "shrinking pullback depth" to "volatility contraction"
without a shared word. `VaultIndex.search()` is the one seam where that trade
is made, so swapping in a vector store later means replacing one method, not
rewriting callers.

---

## The `rs_rating` caveat

Both bundled notes ask for `rs_rating`, which **cannot be derived from one
symbol's bars** — it is cross-sectional. It must be injected, and if it isn't,
any rule referencing it is unevaluable and the audit returns
`INSUFFICIENT_DATA` rather than passing.

The shortlist annotator supplies one via `rs_rating_from_rank()`: a percentile
of *this universe's* ranking by 52-week-high proximity. **This is not IBD's RS
Rating**, which is what Minervini's `>= 70` threshold was written against —
different measure, different population. Treat a pass on that line as
directional, not equivalent.

---

## What this does not do

- **No backtest.** Nothing here has been tested for edge. The repo's research
  ledger has nineteen candidates and zero validated edges; a rule audit is a
  consistency check against something you wrote down, which is a different and
  much weaker claim.
- **No pattern matching.** Minervini's actual VCP — "2 to 6 contractions, each
  roughly half the last" — is not encoded. The DSL evaluates scalars, not swing
  structure. What the note checks is the *context* a VCP forms in.
- **No verdict from the model.** `narrator.py` writes prose over a settled
  result and cannot change it. `core/options/recommender.py` was stripped of
  exactly this capability on 2026-07-25 after review found that fluent
  model-written rationale wrapped around a weak label "reads as grounded
  analysis when it isn't — a stronger over-trust trigger than a bare unlabeled
  number, not a weaker one."

Both bundled strategies are trend-following breakout methods, and every
trend-following breakout candidate tested in this repo has failed on turnover
and cost grounds — Darvas S7-3, Dow theory, the 10:10 breakout. If you intend to
act on a `PASS`, cost it through `core/risk/costs.py` first.

---

## Deployment

Notes are git-tracked, so the VM receives them through the existing
`scripts/deploy-vm.ps1` pull. The VM therefore audits against **committed**
rules only — an uncommitted local edit cannot change live behaviour, which is
the property you want.

`.obsidian/` is gitignored: `workspace.json` rewrites itself whenever a pane
moves and would make every session a dirty tree.

Override the vault location with `QUANTOS_VAULT_DIR` or `vault.dir` in
`agent/config.yaml`.
