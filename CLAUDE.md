# QuantOS: standing rules

A household trading and portfolio terminal. Architecture: `docs/TERMINAL_ARCHITECTURE.md` (approved 2026-10-23). These rules hold in every session.

## Money and orders
- **No change to capital, position size or `dry_run` without the user's explicit go-ahead in that session.**
- **Stage 2 is approved** (user, 2026-10-22 for API orders; 2026-10-24 for automated exits): orders go to ICICI Direct from the VM's static IP. The order rule is **a model drafts, code checks, the user releases; rule-driven exits are placed by code, never by a model.**
  - Every order goes through `core/orders/gateway.py`, which runs the deterministic checks in `core/orders/checks.py` and journals the attempt. Nothing else calls Breeze's place/modify/cancel/GTT methods.
  - A model may turn the user's words into an order ticket. Only the user's confirmation sends it (`scripts/qorder.py --yes` on the VM).
  - The position manager places and manages exits (resting GTT OCO target + emergency stop, the 15:20 daily-close exit) by itself, only when `position_manager.orders: auto` in the VM config. A model never decides an exit.
  - Switch with `scripts/enable-orders.ps1 -Mode live|paper|off` from this PC. Kill switch: `-Kill on` (the file `~/.quantos/ORDERS_OFF` on the VM) stops every new order.
- The trade watcher (Fyers) and the spread watcher stay alerts only until their own exit code is written and switched on.

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
