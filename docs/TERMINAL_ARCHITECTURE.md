# QuantOS Terminal: Target Architecture

**Status:** APPROVED 2026-10-23 with the user's answers in §9 and the reordered roadmap in §8. Progress, and what's deferred, is tracked in §8. Proposed 2026-10-16. The ADRs in §6 move into `docs/ADR.md` as v2.0.
**Supersedes, if approved:** the SaaS direction of ADR-01 (deployment), ADR-03 (multi-tenancy) and ADR-06 (pricing).
**Organised by:** the seven domains of the Claude Certified Architect – Professional (CCAR-P) blueprint. Appendix A maps each domain to the sections here.

---

## 1. Purpose

QuantOS started as a research and paper-trading stack aimed at a possible SaaS product. The goal is now different: a **bespoke trading and portfolio terminal for one household**, running on hardware the user owns, with a local LLM/SLM. It should:

1. Show **account-level dashboards** for every family brokerage account.
2. **View and manage trades across accounts**, with multi-leg option positions understood as single strategies.
3. **Track mutual fund holdings.**
4. Show a **consolidated portfolio and net worth** per person and for the household.
5. Keep running the research and paper-trading jobs it already runs: 23b, the screeners, the trade watcher and the vault.

It should do this while keeping household financial data on household hardware, and without weakening the rules that protect real money.

## 2. Context

### 2.1 What exists today

| Component | State |
|---|---|
| Strategy research | About 35 strategies tested under pre-registration, recorded in the Obsidian vault (`wiki/Strategy Register.base`). |
| Scheduled jobs | Oracle VM, around 20 systemd timers: 23b logger, F&O screener, trade watcher, Darvas, option-chain recorder, vault watch. |
| Brokers | `BrokerAdapter` (ADR-02). Fyers is live. A Zerodha adapter is written. |
| Backend | FastAPI (`cloud/api/`, about 25 routers) on the VM behind nginx basic auth. HTTPS since 2026-10-21 (Let's Encrypt on an sslip.io name); plain HTTP on the bare IP still serves webhooks. |
| Frontend | `cockpit/`, React + Vite + recharts. |
| LLM use | About 10 single-shot calls (morning brief, screener ranker, vault compile and narrator, analyst chat, pre-trade score, alpha attribution, versioning). `claude-sonnet-4-6` is **hard-coded in each file**. Prompts are versioned files in `prompts/`. `pre_trade.py` uses a forced tool call for structured output. |
| Claude Code | One project skill (`vault-compile`). |
| Trading loop (as of 2026-10-23) | F&O screener (evening Telegram + cockpit `#/picks`; spread sized to the 5-session move; calls labelled "no measured edge", puts carry the backtested retest plan); structure picker (`pick_structure.py`); trade-idea log scored daily; spread watcher on ICICI spreads with daily-close stops; **position manager** reading ICICI futures by itself (daily-close stop, 1R target, 10 sessions). All alerts only. |
| Accounts connected | Fyers (spouse, API trading account) and the spouse's ICICI Direct via Breeze (daily login from the cockpit; the session connects automatically). The static IP (161.118.189.29) is registered with the Breeze app, which fixed the 2026-10-22 mismatch. API orders go through the order gateway (§8, phase 6). |

### 2.2 Stakeholders and accounts

| Person | Accounts | Role |
|---|---|---|
| The user | Zerodha | Builder, decision-maker, main trader |
| Spouse | Fyers (QuantOS API account), ICICI Direct (the user's discretionary option trades), all mutual funds (her PAN) | Account owner |
| Son | ICICI Direct | Account owner |

Account owners are stakeholders, not just data sources. They need to consent to API access on their accounts, and the spouse and son may want their own views (CCAR-P D6).

### 2.3 Hard constraints

| # | Constraint | Source |
|---|---|---|
| C1 | **API orders only from a whitelisted static IP** tied to the broker App ID. | SEBI retail-algo framework, live 1 Apr 2026 (`docs/SEBI_COMPLIANCE.md`) |
| C2 | Self-developed algos may be used **only within family** (self, spouse, dependent children or parents), with 2FA consent. **The son is not a dependent (user, 2026-10-23): no algo may ever trade his account.** Read-only tracking is unaffected. The user operates the spouse's accounts, and her 2FA goes to the user's phone. | Same |
| C3 | No change to capital or `dry_run` without the user's explicit go-ahead. | Standing project rule |
| C4 | `brain/` and `raw/` in the vault are never written by an agent. Executable rules come only from the user. | `obsidian_vault/QuantOS/SCHEMA.md` |
| C5 | Household financial data (holdings, net worth, PAN, account numbers) is personal data under India's **DPDP Act 2023**. | Law |
| C6 | Every broker needs its own daily login per account: Fyers, Zerodha (Kite Connect), ICICI Direct (Breeze). The son's ICICI Direct account is deferred: he's away, so its OTP can't be completed. | Broker APIs |

## 3. Requirements

**Functional**
- F1: Read-only sync of funds, holdings, positions and orders for all four brokerage accounts. Statement import as a fallback.
- F2: Trades view across accounts. Legs are grouped into strategies (spread, straddle, covered call) with debit/credit, max loss, max profit, breakeven, days to expiry and live P&L.
- F3: Mutual funds from the CAMS/KFintech consolidated account statement (CAS), valued daily from the AMFI NAV file. Shows XIRR and category mix.
- F4: Manual assets: FDs, EPF/PPF, gold, and any other holdings. **No property, and the household has no loans** (user, 2026-10-23), so no liabilities module.
- F5: Net worth per person and for the household, with a daily history, asset allocation and concentration (e.g. one bank across all accounts).
- F6: Alerts on positions (trade watcher) extended to spreads and all accounts.
- F7: Order actions, such as squaring off a spread as one action. Gated (§5.5) and built last.

**Non-functional**
- N1, privacy: household data stays on household hardware unless it has been stripped of personal details (§5.5).
- N2, availability: scheduled market jobs must not depend on the home machine being up.
- N3, cost: LLM spend is visible per feature and month.
- N4, auditability: every LLM call, alert and order action is logged with its inputs.
- N5, correctness: anything that computes money (P&L, max loss, net worth) is deterministic code with unit tests, never LLM output.

## 4. Target topology

```
                ┌──────────────────────── HOME (private) ────────────────────────┐
  phone /       │  QuantOS Terminal (GPU desktop)                                 │
  laptop  ──────┼─▶ Cockpit (React)  ──▶  Terminal API (FastAPI)                  │
  via Tailscale │                          │                                       │
                │        ┌─────────────────┼───────────────────┐                   │
                │        ▼                 ▼                   ▼                   │
                │  Portfolio store    QuantOS MCP server    Model router           │
                │  (SQLite, encrypted)  (tools, tiers)      ├─▶ local LLM/SLM (GPU)│
                │  household/person/                         └─▶ Claude API ──────┼──▶ Anthropic
                │  account/holdings/MF                          (redacted only)    │
                │        ▲   vault (Obsidian) + local embeddings                   │
                └────────┼─────────────────────────────────────────────────────────┘
                         │ Tailscale (encrypted, no public port)
                ┌────────┼──────────── ORACLE VM (static IP) ────────────────────┐
                │  Scheduled jobs: 23b, screeners, recorder, trade watcher        │
                │  Broker sessions (Fyers today; others as added)                 │
                │  ORDER GATEWAY (only path for API orders; C1)                   │──▶ Brokers
                │  Telegram alerts                                                │
                └─────────────────────────────────────────────────────────────────┘
```

Why two nodes and not one:
- **C1:** home broadband usually has a dynamic IP, and API orders must come from a whitelisted static IP. The VM already has one.
- **N2:** a power cut or Windows update at home must not cost a 23b entry or a trade-watcher alert.
- **N1:** the private data and the local model sit at home, where the hardware is under the household's control.

## 5. Design by CCAR-P domain

### 5.1 D1: Solution design and architecture

Each feature gets the *least autonomous* pattern that does the job:

| Pattern | Use it for | QuantOS examples |
|---|---|---|
| **Deterministic code** | Anything that computes money, places or gates orders, or decides a test verdict | P&L, spread grouping, max loss, net worth, 23b rules, kill switch, backtests |
| **Workflow** (fixed steps, LLM inside one step) | Repeatable reports | Morning brief, vault compile, screener notes, monthly portfolio letter |
| **Augmented LLM** (one call with tools or retrieval) | Questions with a clear answer path | "Price TechM 1740/1800 for 27-Oct", "What does the vault say about wide spreads?" |
| **Agent** (model chooses tools in a loop) | Open-ended household questions | "How exposed are we to private banks across all accounts, and what changed this month?" |
| **Multi-agent** | **Not used** until an eval (§5.4) shows a single agent failing for lack of specialisation | — |

The rule: **LLMs explain, retrieve and draft; code computes and decides.** An agent may read anything it is allowed to, but every number it shows comes from a tool that computed it.

### 5.2 D2: Models, prompting and context

- **One model registry** (`config/models.yaml`) replaces the ten hard-coded model strings. Each feature names a *role* (`reasoning`, `summary`, `private_chat`, `embed`), never a model ID. Upgrading a model is a one-line change, checked by the eval suite (§5.4).
- **The router** picks a model by **data class × task difficulty**:

  | | Public or research data (P0/P1) | Household data (P2) |
  |---|---|---|
  | Routine (summarise, label, search) | Local model | Local model |
  | Hard reasoning (option analysis, test design, code) | Claude | Claude **after redaction**, otherwise local |
  | Credentials (P3) | Never sent to any model | Never sent to any model |

- **Prompt caching** for long, stable system prompts and vault context sent to Claude. ADR-04 already wanted aggressive caching, but the code doesn't do it.
- **Structured output** through forced tool calls everywhere a result is parsed. `pre_trade.py` already does this; extend it to the ranker and the narrator.
- **Context engineering:** the agent gets tools and fetches data on demand (progressive discovery), not a whole portfolio dump in every prompt.
- **Skills** (Claude Code, see §5.7) hold repeated procedures.

### 5.3 D3: Integration

**The QuantOS MCP server is the centre of the design.** One tool layer is used by the cockpit's analyst, Claude Code, the local model and Claude Desktop. The ad-hoc scripts written on 2026-10-16 to price ICICI, Persistent, Kotak and TechM spreads are what these tools replace.

| Tier | Tools (initial) | Who may call | Side effects |
|---|---|---|---|
| **T0 read: market** | `quote`, `option_chain`, `price_spread(symbol, legs, expiry)`, `results_date`, `history` | Any model | None |
| **T0 read: research** | `search_vault`, `strategy_record`, `surge_23b_status` (counts only before 60 closed) | Any model | None |
| **T1 read: household** | `accounts`, `holdings(person?)`, `positions(account?)`, `strategies()` (grouped legs), `mf_holdings`, `net_worth(person?, date?)` | Local model, or Claude through the redaction layer | None |
| **T2 alert** | `set_alert(position, rule)`, `send_telegram` | Any model, but the **user confirms** each rule in the cockpit | Messages only |
| **T3 order** | `square_off_strategy(id)`, `place_order(...)` | **A model may draft; code checks; the user releases.** Only `core/orders/gateway.py` calls Breeze's order methods, after `core/orders/checks.py`. User-released orders: `scripts/qorder.py --yes`. Rule-driven exits: the position manager, by code. A model never sends an order or decides an exit. Runs on the VM (C1). | Real money |

Other integration decisions:
- **Broker connectors:** read-only sync jobs per account, writing snapshots to the portfolio store. Breeze is needed for both ICICI Direct accounts. If an API is unavailable or too much daily-login friction, a holdings CSV or PDF import is the fallback. The son's quiet account may be fine on weekly statements.
- **Auth:** each account's credentials stay in its own encrypted store on the node that uses it. The MCP server checks the caller's tier before every tool call.
- **RAG over the vault:** local embeddings of `wiki/` (and `raw/` read-only), so strategy history is searchable by any model without being sent to the cloud wholesale.
- **Observability:** one **LLM call log** (feature, route, model, tokens, cost, latency, data class, tool calls, outcome). Tool-call logs go into the same audit trail as alerts and orders (N4). The existing job-health routes carry on for systemd jobs.

### 5.4 D4: Evaluation, testing and optimisation

Strategy research already has strict discipline: pre-registration, holdouts, no peeking. **The AI features get the same treatment.**

| Eval set | Contents | Pass bar |
|---|---|---|
| `spread_math` | About 50 spread questions with real quotes. Expected numbers come from deterministic code. | 100% of numbers taken from tools. Any number the model makes up is a failure. |
| `portfolio_qa` | About 40 household questions on a **synthetic** household | Correct tool choice and correct answer ≥ 95% |
| `vault_retrieval` | About 30 questions with known source pages | Correct source cited ≥ 90% |
| `redaction` | Prompts full of PAN, account numbers, names and amounts | Zero leaks |
| `brief_quality` | 20 past morning briefs with expected key points | Rubric score, compared against the current prompt |
| Feature baselines | Screener ranker against plain rank order; pre-trade score against no gate | The AI feature must beat its baseline, or it's removed |

- Evals run on **every model, prompt or router change**. A regression blocks the change, just as failing unit tests do.
- **Local model qualification** (ADR-20): the same suites run against candidate open-weight models **before any hardware is bought**, on rented GPU time if needed. The result decides model size, and model size decides hardware.
- **Production monitoring:** the LLM call log is sampled weekly into the eval sets so they track real usage.

### 5.5 D5: Governance, safety and risk

**Data classes**

| Class | Examples | Where it may go |
|---|---|---|
| P0 public | Quotes, option chains, bhavcopy, NSE results dates | Anywhere |
| P1 research | Strategy code, test results, vault | Claude, local model, git |
| P2 household | Holdings, positions, net worth, MF folios, PAN, names, account IDs | Home node and the encrypted store. Claude only after redaction (names → "Person A", IDs dropped, amounts optionally scaled). **Never in git, logs, test fixtures or Claude Code sessions.** |
| P3 secrets | Broker tokens, TOTP seeds, API keys | Their node's secret store only. Never sent to any model. |

**Safety rules**
- Permission tiers as in §5.3. T3 is never exposed to a model.
- Human in the loop for every alert rule and every order (ADR-05 continues).
- Existing protections carry on unchanged: the kill switch and dead-man (ADR-10), read-only loggers, the `brain/` rule (C4) and pre-registration.
- **Failure modes to design against:**
  - Hallucinated numbers (N5 plus the `spread_math` eval).
  - Stale quotes shown as live (every number shows its timestamp, as today's spread checks did).
  - A wrong account receiving an order (T3 shows owner and account in large type and needs a typed confirmation).
  - Prompt injection through vault or web content (tool results are data; T2 and T3 are never model-initiated).
- **DPDP Act:** the household is both data principal and fiduciary, so the obligations are light. In practice: written consent from each account owner for API access (also needed for C2), a deletion path per person, and encryption at rest (full-disk BitLocker or LUKS, plus an encrypted SQLite file).
- **Regulatory:** the family-only rule (C2) and static-IP orders (C1). The son counts as family for algo purposes only if he's a dependent; read-only portfolio tracking is unaffected either way.

### 5.6 D6: Stakeholder communication and lifecycle

- **This document plus ADRs** are the architecture record. Each future change updates an ADR before code.
- **Stakeholder views:** the user sees everything. The spouse and son each get a **person-scoped view** of their own accounts if they want it. A short consent note is recorded per account owner.
- **Lifecycle:**
  - Model upgrades go through the registry plus evals (§5.2, §5.4).
  - Broker API changes are caught by daily sync health checks.
  - The hardware refresh is judged by eval latency and quality, not specs.
  - Every strategy keeps its vault record (existing rule).
- **Feedback loop:** a monthly household portfolio letter (workflow pattern) doubles as the review of whether the terminal is useful.

### 5.7 D7: Developer productivity and operational enablement

- **Claude Code skills** for repeated tasks:
  - `price-spread`: live chain, fills at bid/ask, the table we built by hand five times today.
  - `trade-check`: owner, account, legs, P&L, exit plan.
  - `vault-compile`: exists.
  - `deploy-vm`.
  - `new-strategy-test`: the pre-registration template.
- **Hooks:**
  - Block commits that contain P2/P3 patterns (PAN regex, account numbers, tokens).
  - Run evals when `prompts/` or `config/models.yaml` changes.
- **`CLAUDE.md`** at the repo root holds the standing rules, which today live only in memory and chat: C3, C4, no P&L before the 23b gate, and the files that must never be committed.
- **Synthetic household fixture** for all development and tests, so real P2 data never enters a Claude Code session.
- **Runbook:** the morning login sequence (four accounts), what to do when a sync fails, and how to restore from backup.

## 6. Decisions (proposed ADRs)

| ADR | Decision | Notes |
|---|---|---|
| **ADR-11 Personal terminal** | QuantOS is a single-household terminal. Drop the SaaS path: per-user tenancy, pricing tiers, vendor empanelment. Keep a `person_id` on household data. | Amends ADR-01, ADR-03, ADR-06. Removes the SEBI vendor-regime risk entirely. |
| **ADR-12 Two-node topology** | Home terminal for private data, local model and cockpit. Oracle VM for scheduled jobs, broker sessions and the order gateway. Linked by Tailscale. No public ports. | C1, N1, N2. The plain-HTTP cockpit retires. |
| **ADR-13 Pattern selection** | Deterministic code for money and verdicts. Workflows for reports. One agent for household Q&A. No multi-agent until evals justify it. | §5.1 |
| **ADR-14 Model registry and router** | Features name roles, not models. The router routes by data class × difficulty. Redaction is required before P2 reaches Claude. | §5.2. Replaces ten hard-coded model IDs. |
| **ADR-15 MCP tool layer with tiers** | One QuantOS MCP server, tiers T0–T3. T3 is never callable by a model. | §5.3 |
| **ADR-16 Data classification** | Classes P0–P3 with the handling rules in §5.5. Encryption at rest. No P2 in git, logs or dev sessions. | C5 |
| **ADR-17 Portfolio data model** | household → person → account → {funds, holdings, positions, orders} snapshots. `strategy` groups legs. MF from CAS plus AMFI NAV. Manual assets. Daily net-worth snapshot. | F1–F5 |
| **ADR-18 Evaluation harness** | Eval suites in §5.4 gate model, prompt and router changes. Every AI feature must beat a baseline. | D4 |
| **ADR-19 LLM observability** | One call log with feature, route, model, tokens, cost, latency, data class and tools. Weekly sampling into the evals. | N3, N4 |
| **ADR-20 Hardware sized from evals** | Buy only after local-model qualification. Size the GPU memory to the smallest model that passes the evals, plus room for context and an embedding model. | §7 |

## 7. Hardware

**Approach:** pick the model first, then the hardware. Hardware is the last decision, not the first.

| Tier | GPU memory | Comfortable model class (quantised) | Fits if the evals show… |
|---|---|---|---|
| A | 16–24 GB, one GPU | Up to about 14B models, plus embeddings | Local work is summarising, labelling and retrieval. Hard reasoning goes to Claude. |
| B | About 32 GB, one high-end GPU | About 30B-class models with long context | The local model must also handle household Q&A with tools well. |
| C | 48–128 GB (two GPUs, a workstation card, or a large unified-memory machine) | About 70B-class models | The evals show 30B-class models failing on private reasoning that can't be redacted. |

Also needed at every tier:
- A **UPS**.
- **64 GB+ system RAM.**
- **2 TB NVMe** for market data caches, option rows and the vault.
- Backups to an encrypted external drive plus one off-site copy.
- Linux, or Windows with WSL2, for the model server. Model and hardware specifics should be checked at purchase time; they change quarterly.

My expectation, to be confirmed by evals: **tier B** covers this household's private work, and Claude keeps the hard reasoning.

## 7b. Options picks: dashboard, log and spreads (added 2026-10-16)

The F&O screener's evening picks (5 calls, 5 puts) get three additions:
- **Cockpit panel and history.**
- **Outcome log:** stock move and option value after 1, 3 and 5 sessions from bhavcopy closes, plus a "taken" flag once account sync exists.
- **Spread alternative per pick:** a bull call spread for calls, a bear put spread for puts, 2–3 strike pairs priced at bid/ask, with bid-ask cost as a % of debit and a flag above 10%.

Rules pick the strike pairs; a model only explains them. This uses public data only, so it ships as phase 2b on the existing VM cockpit. Its verdict compares the single option and the spread on the same picks after about 30 picks per side. Bear call spreads (credit) are optional, not the default, because the surge study found no reversal.

## 7c. ICICI Direct spreads and trailing exits (added 2026-10-19)

The user trades spreads in the spouse's ICICI Direct account, so it is the first account connected (phase 2) and the first one the trade watcher manages for spreads (phase 3).

- **Connection:** ICICI's Breeze API (`breeze-connect`).
  - API key and secret from her ICICI Direct login.
  - Daily session token from `api.icicidirect.com/apiuser/login?api_key=…`, then `generate_session`.
  - Read-only use: `get_portfolio_positions()` and `get_quotes(..., exchange_code="NFO", product_type="options")`.
  - Register the VM static IP (161.118.189.29) now: Breeze accepts orders only from the registered IP, which can change once a week.
  - ICICI uses its own stock codes (e.g. TECMAH), mapped through its security master.
- **Spreads:** the two legs are grouped into one position with entry debit, max loss, max profit and breakeven. The live value is the long leg's bid minus the short leg's ask.
- **Trails (alerts only):**
  - (A) A stock-price trail 0.8% below the high since entry, once in profit, or a per-trade level.
  - (B) Profit give-back: once the spread reaches 20% of max profit, alert if it gives back half of the best profit.
  - Fixed alerts for breakeven and exit day (one session before expiry).
  - The Telegram alert spells out both closing orders.
  - The parameters are starting guesses, to be re-tuned on 20–30 of the user's own spreads.
- **Automatic exits** via Breeze are tier T3. Stage 2 approved by the user (2026-10-22 API orders, 2026-10-24 automated exits); built for futures in the position manager (§8, phase 6).

## 7d. Edge and product strategy (added 2026-10-21)

The edge QuantOS can prove today is a process edge (structure, exits, honest measurement); its analysis is plausible but unmeasured. Build and pitch it in two layers:

| Layer | For the household now | As a product |
|---|---|---|
| View: screener, levels, news, Claude's read, the user's judgement | Comes from QuantOS | Needs a measured edge per setup, and likely SEBI Research Analyst registration to offer as calls |
| Execution: structure engine, exit watcher, idea journal | Built | Sellable now; no licence, no edge claim |

Regulation is a working assumption, not legal advice; confirm with a SEBI compliance professional before any external pitch.

**The loop:** idea with target, stop, horizon and setup tag -> structure engine (lowest needed hit rate, only if clearly below the no-skill rate) -> watcher and zone alerts manage the exit (discretionary exits record a reason) -> idea log scores paper vs actual per tag -> measured hit rate per tag feeds structure choice and sizing; tags with no edge after ~30 ideas are dropped.

**Data to ingest, by edge per effort:** event calendar; IV history and rank per stock (option-chain recorder); 5-minute data around marked levels; OI by strike and NSE participant-wise OI; results surprise and news classified by the local LLM; actual fills and charges from the trade books; the user's entry/exit reasons.

**Pitch (draft):** a co-pilot for serious retail F&O traders that turns a view into the best-priced trade, watches the exit and keeps an honest scoreboard. A SEBI study (2024) found about 9 in 10 individual F&O traders lose money; structure, exits, sizing and self-deception are what it addresses. Evidence needed: 3-6 months of timestamped logged ideas with paper and actual P&L (started 2026-10-21).

**Built 2026-10-21:** idea log (core/ideas/log.py, scripts/trade_ideas.py, 15:25 IST timer, cockpit #/ideas); structure engine (core/ideas/structure.py, scripts/pick_structure.py, POST /ideas/structure, research mode); earnings-gap drift study (docs/EARNINGS_GAP_DRIFT_GUTCHECK.md).

**Roadmap addition (after phase 3):** Edge loop: setup tags, no-skill hit-rate column, event calendar and IV rank, zone-entry alerts, exit reasons. Exit check: 60 logged ideas with hit rate per tag; one tag with a measured edge traded small.

**Open questions added:** household-only or outside users (and then analysis vs execution layer); the starting setup-tag list; futures allowed for proven setups with a stop order at entry and the gap worst case accepted?

## 7e. Measured edge and the exit fix (added 2026-10-23)

- **Backtest:** a year of the screener's own signals (`scripts/backtest_fno_screener.py`, `backtest_fno_exits.py`, and the pre-registered `backtest_fno_entries.py`; `docs/FNO_ENTRY_SEARCH_PREREG_2026-10-23.md`).
  - **Call breakouts** had no edge under any exit or entry rule tested.
  - **Put breakdowns** had one: sell the retest 0.25 ATR under the broken floor; stop on a daily close 0.75 ATR beyond the fill; 1R resting target; out by session 10. Result: +0.31% per trade, 69% won, positive in both halves.
  - **Buying options** on these signals lost before costs.
  - **Stop timescale** (15-minute, hourly, daily close) barely mattered on average. A **1R take-profit** helped consistently.
- **Exit tooling:**
  - The position manager reads ICICI futures by itself and holds them to that plan.
  - The spread watcher takes per-trade **daily-close** stops, with a touch emergency stop and a target. This replaces §7c's 0.8% touch trail, which is noise on a stock with a ~2.3% daily range (TCS, 22 Oct).
- **The view layer stays unmeasured until the idea log has enough entries.** The live record so far: discretionary calls mostly right (about 8 in a week), and the losses came from structure and exits, which this section addresses.

## 8. Roadmap

Reordered 2026-10-23: the trading loop works now, so foundations and the market tools that serve it come before accounts. Nothing touches the VM's live jobs during market hours; every change ships through the tested deploy.

| Phase | Delivers | Exit check | Status (2026-10-23) |
|---|---|---|---|
| **0 Foundations** | `CLAUDE.md` with the standing rules; model registry; LLM call log; P2/P3 commit hook; synthetic household fixture; Tailscale on the VM, the laptop and the user's phone, with nginx bound to the tailnet | Cockpit unreachable from the public internet; every LLM call goes through the registry and is logged | **Partly done.** Registry, call log, `CLAUDE.md` and hook shipped. The synthetic fixture moves to phase 1. **Tailscale deferred** by the user, so the cockpit stays on HTTPS + basic auth. |
| **0b Market tools (MCP T0)** | `quote`, `option_chain`, `price_spread`, `pick_structure`, levels and ATR, screener state, idea log, as one MCP server used by Claude Code and the cockpit | A "what about <stock>?" question is answered from tools with no ad-hoc script (six were written by hand on 2026-10-23) | **Done** for Claude Code. The cockpit doesn't use the tools yet. |
| **1 Accounts (read-only)** | Portfolio store (ADR-17); synthetic household fixture; sync for Fyers, Breeze (spouse) and Kite Connect (user's Zerodha); T1 MCP tools; account dashboards | The connected accounts reconcile with each broker's own holdings and funds screens | **Next.** Fyers and the spouse's Breeze are already connected. **Kite Connect deferred** by the user. The son's account is deferred (OTP unavailable). |
| **2 Trades view** | Strategies across accounts as one view: spreads grouped, futures with their managed plans; per-strategy P&L, max loss and breakeven | A spread and a managed future show as one line each with correct numbers | Not started. The spread watcher and position manager already do the per-position maths. |
| **3 Mutual funds** | CAS import, AMFI NAV job, XIRR and category mix | Values match the CAS to the rupee on statement date | Not started |
| **4 Net worth** | All holdings: demat, MFs, FDs, EPF/PPF, gold (no property, no loans); person and household views, history and allocation | Monthly letter generated | Not started |
| **5 Local model** | Eval suites first, so a later hardware choice is sized from evals (ADR-20) | — | **Deferred** by the user: stay on the laptop and the VM |
| **6 Order actions** | Order gateway + checks + journal (`core/orders/`), `qorder` for user-released orders and spreads (long leg first, short bought back first), position manager exits: resting GTT OCO target + emergency stop, 15:20 daily-close exit. | Approved 2026-10-22 / 2026-10-24. Switched on by `orders.live` and `position_manager.orders: auto` in the VM config; kill switch `~/.quantos/ORDERS_OFF` | Built 2026-10-24. The first live GTT OCO's payload is checked against the broker's GTT book. Spread-watcher exits and strike management (rolling to keep moneyness) are next, the rolling rule after a pre-registered test |

### What shipped on 2026-10-23

| Area | Shipped | Commits |
|---|---|---|
| Phase 0 | `config/models.yaml` + `core/llm` (`model_for`, `log_call` → `~/.quantos/llm_calls.jsonl`, metadata only). All 10 Claude call sites migrated with **no model change**. `CLAUDE.md`. `.githooks/pre-commit` (enable per clone: `git config core.hooksPath .githooks`). | 9b1bba9 |
| Phase 0b | `mcp_server/quantos_mcp.py` (mcp 2.3.0) with 8 read-only tools from `core/mcp_tools/market.py`, live adapter `core/mcp_tools/live.py`. Runs on the VM over SSH via `scripts/quantos-mcp.sh` and `.mcp.json`. | a243f6d, 9d76377, f125da6 |
| Trading loop | Screener: up to 12 picks per side, edge labels, retest plan per pick, spread sized to the 5-session move, bid-ask gate, watchlist, Nifty label. Position manager for ICICI futures. Daily-close stops in the spread watcher; Breeze retry. | 6143246 … d8a3939 |
| Research | Year backtest of the screener's signals, exit grid, and the pre-registered entry search (puts' retest entry passes; calls have no edge). | 6a53794, 37c3aab |
| Trade-event explainer | When a watcher rule fires, or a held stock opens ≥ 1 ATR away, the alert goes out unchanged; then one Claude call (Opus 5.5, effort low, web search) adds 2–3 sentences on *why* the stock is moving. Code decides, the model explains. It sends symbol, structure and levels only; quantity, P&L and account are stripped. Capped at 12 a day. Live test: about $0.11 and 29 s per explanation. | 88073c8 |

### Deferred, and what each needs

| Item | Needs | Unblocks |
|---|---|---|
| Tailscale | The user installs it on the laptop and phone; an auth key or `tailscale up` on the VM | Taking the cockpit off the public internet (phase 0 exit check) |
| Kite Connect | The user's Kite Connect app (paid), key and secret in `~/.quantos/`, redirect `https://161-118-189-29.sslip.io/auth/kite/callback` | The user's Zerodha account in phase 1 |
| Son's ICICI Direct | His OTP, when he's back. Read-only, never algo-traded. | His account in the household view |
| Local model and hardware | A user decision; evals first | Phase 5 |
| Model upgrades (Sonnet 4.6 → current) | A deliberate migration per feature. `pre_trade` forces `tool_choice`, which Opus/Sonnet 5.5 reject. | Lower cost and newer models |
| Spread exits by code; rolling strikes | Spread-watcher executor on the gateway; a pre-registered rolling rule | Phase 6b |

## 9. The user's answers (2026-10-23)

1. **Son:** not a dependent. No algo trading in his account, ever (C2). He's away, so his ICICI Direct OTP can't be completed: integration deferred.
2. **Breeze on the son's account:** not applicable for now.
3. **Zerodha:** connect via **Kite Connect**. Needs the user's Kite Connect app key and secret, and a daily login.
4. **Consent:** the user operates the spouse's accounts, and her 2FA is mapped to the user's phone.
5. **Hardware:** stay on the current setup (this laptop plus the Oracle VM). Phase 5 is deferred.
6. **Net worth:** list every holding (demat, mutual funds, FDs, EPF/PPF, gold). Skip property. The household has no loans.

---

## Appendix A: CCAR-P domain map

| Domain (weight*) | Sections | Today → target |
|---|---|---|
| D1 Solution design (17%) | §4, §5.1, ADR-12/13 | Implicit choices → recorded pattern policy |
| D2 Models, prompting, context (13%) | §5.2, ADR-14 | Ten hard-coded model IDs → registry, router, caching, structured output |
| D3 Integration (19%) | §5.3, ADR-15/17/19 | No MCP, ad-hoc scripts → one tiered MCP server, vault RAG, call log |
| D4 Evaluation (16%) | §5.4, ADR-18 | Strategies only → AI features evaluated and baseline-gated |
| D5 Governance, safety, risk (14%) | §5.5, ADR-16 | Strong but informal → data classes, tiers, DPDP and SEBI handling |
| D6 Stakeholders, lifecycle (14%) | §2.2, §5.6, §9 | One user → household stakeholders, ADR-first changes, model lifecycle |
| D7 Developer enablement (7%) | §5.7 | One skill → skills, hooks, `CLAUDE.md`, synthetic fixtures |

\*Weights are from third-party CCAR-P prep sites (claudearchitectcertification.com, claudecertificationguide.com). Check them against Anthropic's official exam guide.
