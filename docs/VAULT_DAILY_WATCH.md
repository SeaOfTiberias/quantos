# Vault Daily Watch — Design

## Why this exists

The 2026-09-17 strategy-database request had three parts: (1) a queryable
database of every backtested candidate, (2) a published report, (3) can a
strategy that failed its own daily-run pre-registered backtest still be
traded *discretionarily*, on days conditions look genuinely favorable? Parts
1-2 are `obsidian_vault/QuantOS/wiki/` and the published Strategy Ledger
artifact. This document is part 3's *monitoring* half — deliberately not
its execution half.

## The trap this design avoids

Mining a strategy's own historical trades for "what conditions made it win,"
without a pre-registered mining/holdout split, is a well-established trap in
this project's own history — the same maneuver the regime/vol-conditioning
search's five failures and ORB's own condition-mining exercise were built to
guard against (see `docs/ORB_CONDITION_MINING_METHODOLOGY.md`). This design
sidesteps it structurally rather than re-litigating it: it adds **zero**
new signal-discovery logic of its own. It only ever executes a rule that
already exists in `obsidian_vault/QuantOS/brain/` — a layer the vault's own
`SCHEMA.md` makes **human-authored only**, on pain of a lint error if an
agent ever writes to it. This project cannot propose "ideal conditions" for
a strategy and wire them up in the same breath; a human has to write the
rule and choose to watch it first.

## What was built

- **`agent/config.yaml`'s `vault.watch_enabled` / `vault.watches`** — a
  list of `{note, symbol, label}` entries. Off by default, and empty by
  default (no entries exist as of this writing — none of the 20 backtested
  candidates in the wiki have a `brain/` rule written for them yet).
- **`scripts/run_vault_daily_watch.py`** — for each configured watch,
  fetches `symbol`'s recent daily candles and audits them against `note`
  via `core/vault/gates.py`'s existing `audit_gate()` — the same fail-closed
  machinery that already gates the options webhook and the rotation pilot's
  entries. **PASS sends a Telegram alert. Every other outcome (FAIL,
  INSUFFICIENT_DATA, a missing note, a broker error) is silent** — a
  strategy this project's own backtests show fails most days should not
  page the user most days.
- **No execution path.** This script imports nothing from
  `core/execution/` or any order-placing module. A PASS is a Telegram
  message, never an instruction, and there is no code path from this
  script to a broker order.
- **`deploy/systemd/quantos-vault-watch.{service,timer}`** — built, not
  enabled, same precedent as every other new timer in this project's
  history (ORB scalping, the goodnight probe): copied by the deploy
  script, `systemctl enable --now` is a separate, deliberate step.

## How to actually use this

1. Pick a strategy from the wiki (`[[strategy-search]]`) worth a
   discretionary second look — the two holdout-confirmed leads from ORB's
   own condition-mining exercise (`monday_or_friday` on NIFTY,
   `big_gap` on BankNifty) are the only conditions in this project's
   history that have already cleared a mining/holdout bar, so they are the
   most defensible starting point, not a random pick.
2. Write a `quantos-rules` block for it in `obsidian_vault/QuantOS/brain/`
   by hand — this project can propose the condition in prose (as it did
   above); the note itself has to be authored by a person.
3. Add one entry to `agent/config.yaml`'s `vault.watches`, flip
   `watch_enabled: true`.
4. `systemctl enable --now quantos-vault-watch.timer` on the VM (a
   deliberate step, not automatic on deploy).

None of this authorizes real-money execution on its own — a Telegram PASS
alert is exactly as far as this goes until a *separate*, explicitly
pre-registered execution design exists, gated the same way every other
capital decision in this project has been
(`feedback_confirm_before_scaling_capital`).
