# QuantOS — Scope Contract

**Adopted 2026-08-18.** This file exists to make scope creep require a
deliberate act rather than a quiet afternoon. Everything QuantOS does is
bounded by what follows.

The reasoning behind it is in the *What OpenBB Gave Up* and *The NSE-Only
Contract* review artifacts. The short version: OpenBB Terminal — the funded,
staffed, open-source Bloomberg terminal — was sunset because the maintenance
of breadth was unsustainable at 7–10k monthly users. The lesson taken here is
not "be smaller" but "be narrow and be correct about the narrow thing".

---

## The contract

| Dimension | Commitment |
|---|---|
| **Operator** | **One.** No multi-user support, no installer, no onboarding surface, no backwards-compatibility obligation to anyone else. |
| **Venue** | **NSE only.** No BSE, no MCX, no currency, no global venue. |
| **Source of record** | **Fyers** for live quotes, history and broker state. **NSE bhavcopy** for settlement and EOD truth. Nothing else is supported. |
| **Instruments** | In build order, each earning the next: **1.** NSE cash equities · **2.** NSE index options (NIFTY, BANKNIFTY) · **3.** NSE stock F&O |
| **Out of scope** | Macro and global context, mutual funds, commodities, crypto, fundamentals beyond the PEAD cache, and any second broker as a *supported* path. |

### Amendment rule

Adding a provider, venue or asset class requires editing this file **in its own
commit**, naming what it costs to maintain. Not a code change with a doc
footnote.

---

## Consequences worth stating

**Scoping macro out scopes OpenBB out.** Their packages earned their keep in
exactly one place — `openbb-fred` / `openbb-oecd` for global series — because
they ship no NSE or BSE provider at all. With macro excluded there is no
remaining reason to take the dependency, and the AGPL-3.0 network-copyleft
question goes away with it. What was worth taking was the *shape* of their
provider model, adopted without the package.

**Narrowness is only worth it if it buys correctness.** India is roughly one
percent of a global vendor's attention and one hundred percent of ours. That
asymmetry pays only when spent on rules a global tool must average away: the
exact charge stack, expiry conventions and their cutovers, point-in-time index
membership, ban lists, lot-size revisions, and the trading calendar. Being
right about those is the entire content of "smarter". It is not more data than
Bloomberg — it is correctness where Bloomberg is careless.

---

## Architecture decisions taken

### ADR-S1 · Strategies are declarations, and the harness consumes them first

A strategy is data, not a Python file. `core/vault/` already implements the
mechanism — frontmatter plus a fenced ` ```quantos-rules ` block, parsed by
`core/vault/parser.py` and evaluated by `core/vault/rules.py`'s AST evaluator.
Today it declares *screening* criteria ("is this symbol a valid setup?"). The
schema extends to *strategy* by adding exit and stop rules, sizing, cadence,
universe, cost model and pass bar.

**Why it matters:** RS momentum is currently defined twice — once in
`scripts/backtest_rs_momentum.py`, once in `core/rotation/executor.py`.
`core/rotation/ranker.py` was extracted to stop the *signal* drifting, and it
works, but cost model, position size, cadence, `top_n` and universe are still
specified separately in each. The clearest evidence of the cost is
`scripts/ablate_momentum_turnover.py`: testing weekly-versus-quarterly
rebalancing, a single parameter, required an entire separate script, because
cadence is control flow rather than a value the strategy holds.

**The ordering is a safety property, not a preference.** The falsification
harness consumes declarations *before* any execution path does. Declarations
feeding the harness make "what you backtested is what you ran" mechanically
checkable. Declarations feeding execution directly would be the thing the
vault was explicitly built not to do — see `core/vault/__init__.py`, where the
rule block is audited *before* a signal reaches an execution path, and
`docs/OBSIDIAN_VAULT_INTEGRATION.md` on why both money gates ship off.

### Still open

- **SQLite or JSON for the consolidated portfolio store.** SQLite is already on
  the VM and would make the portfolio queryable from MCP directly; JSON is
  inspectable with `cat` and has never failed.
- **Whether the mothballed Darvas agent is harvested or deleted.** It holds the
  correlation gate and the only human-confirm flow — both wanted; the loop
  around them is not.

---

## Build order

The dependency order is forced: reference sits beneath data, data beneath the
harness, the harness is what makes execution's strategies trustworthy,
execution writes to the portfolio, and MCP surfaces all of it.

| # | Work | Status |
|---|---|---|
| 1 | `core/reference/` — trading calendar, then the scattered reference data folded in | **in progress** |
| 2 | `core/data/` — `DataProvider` split; bhavcopy's two parallel stacks collapse into one | |
| 3 | Portfolio consolidation — cheapest now, while three of five stores are inert | |
| 4 | Execution path unification — slicer wired, gates uniform, one `dry_run` | |
| 5 | Falsification harness + machine-readable ledger, consuming declarations | |
| 6 | MCP over the consolidated surface | |
