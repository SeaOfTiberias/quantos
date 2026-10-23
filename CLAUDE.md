# QuantOS: standing rules

A household trading and portfolio terminal. Architecture: `docs/TERMINAL_ARCHITECTURE.md` (approved 2026-10-23). These rules hold in every session.

## Money and orders
- **No change to capital, position size or `dry_run` without the user's explicit go-ahead in that session.**
- Everything that touches a broker is **alerts only**: the trade watcher, the spread watcher and the position manager. Order code (tier T3) is never callable by a model. Don't write or change order-placing code without an explicit stage-2 go-ahead.
- No algo may ever trade the son's account. He is not a dependent (SEBI family rule).
- Anything that computes money (P&L, max loss, levels, net worth) is deterministic code with unit tests, never model output.

## Research discipline
- **Pre-register** a strategy or filter test (hypotheses and pass criteria committed) before running it. A failed test is reported as failed, not re-tuned in the same round.
- **Surge 23b:** no P&L before 60 closed trades.
- Log every trade idea, including "avoid", with `scripts/trade_ideas.py` on the VM. Pick the structure with `scripts/pick_structure.py`, never by habit.
- The Obsidian vault (`obsidian_vault/QuantOS`) is the strategy record. Agents never write to `brain/` or `raw/`.

## Data
- Household data (P2: holdings, positions, PAN, account IDs, names with amounts) and secrets (P3: tokens, API keys, TOTP) **never go into git, logs, test fixtures or prompts**. Use synthetic fixtures. The pre-commit hook (`.githooks/pre-commit`) blocks the obvious patterns.
- Credentials live in `~/.quantos/` on the machine that uses them. Don't print them.

## Claude calls
- Get a model with `core.llm.model_for("<feature>")` (`config/models.yaml`); never hard-code a model ID. Log every call with `core.llm.log_call(...)` in a `finally`.
- A model change is a migration (thinking, `tool_choice`, prefill rules differ by generation). Run the feature's tests and the evals first.

## Operations
- **VM:** `ssh -i ~/.ssh/oracle.key ubuntu@161.118.189.29`. Deploy only with `scripts/deploy-vm.ps1` from PowerShell (tests, pull, unit sync, verify).
- Don't restart or edit live VM jobs during market hours (09:15–15:30 IST) unless fixing a live fault.
- The VM's `agent/config.yaml` is edited by hand: back it up first (`config.yaml.bak-YYYYMMDD`).
- The VM clock is UTC. Timers are written in UTC with the IST time in a comment.
