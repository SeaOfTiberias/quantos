# Sprint 4 Backlog — Capital Preservation & Measurement

Derived from `docs/AUDIT_FINDINGS.md` (2026-07-08). Sequenced by **risk
reduction per point**. Sprint 4 = survive; Sprint 5 = measure; Sprint 6 =
expand. Candidate features from the audit brief were only included where the
audit confirmed they're actually missing; partial-existing items are written
as deltas.

Constraints honored throughout: Telegram stays plain text (no parse_mode);
human-in-loop confirm-before-execute stays the default; Railway remains the
deploy target; all broker access goes through `BrokerAdapter` — no direct
Fyers calls.

---

## Sprint 4 — Survive (≈24 pts)

### S4-1 · Postgres persistence for SignalDB — **5 pts** (P0-3, enables P1-9 calibration)
As an operator, I want signals to survive Railway redeploys so a confirmed
trade can never target a signal that no longer exists.
- Implement the six `_pg_*` stubs (`cloud/api/db.py:130-149`) with asyncpg (already in requirements; `DATABASE_URL` already set).
- Gate on a startup connectivity check, NOT env-var presence (that gating bug already broke production once). Fallback: in-memory + loud warning log.
- `CREATE TABLE IF NOT EXISTS` on boot; keep `user_id='system'`.
- Dedup guard becomes an indexed query (also fixes the 200-signal scan window, `cloud/api/main.py:411`).
- **AC:** redeploy mid-`PENDING_CONFIRMATION` → Telegram "execute" reply still executes. `/signals` returns pre-deploy signals. Verify Railway Postgres plan actually persists volumes (dashboard check).

### S4-2 · Portfolio kill switch + halt flag — **5 pts** (P0-2)
As the human in the loop, I want the agent to refuse to trade past defined
loss/exposure limits even if I'd confirm the signal.
- Enforce `max_open_positions` and `max_daily_loss` (realized, from today's closed trades + open-position MTM) in `_size_and_place_order`; halt = refuse all new entries, keep managing exits.
- Persistent halt flag `~/.quantos/halt`: set automatically on daily-loss breach or 3 consecutive losses; clearable only manually. Checked every poll tick.
- Telegram notification on any halt trigger (plain text).
- Dead-man's switch: if the agent can't reach the cloud for N minutes with positions open, send one Telegram alert via a direct fallback? **No** — agent has no Telegram token (ADR-01). Instead: cloud-side sweep flags agents that stopped reporting (see S5-6 observability); agent-side, log loudly and keep managing stops (stops are broker-resident SL-M orders — they survive agent death; document this as the actual dead-man protection).
- **AC:** simulated 5% daily loss → next confirmed signal is refused with a logged+notified reason; SL-M management continues.

### S4-3 · Webhook hardening — **3 pts** (P0-1, P1-3, P1-11, P2-1)
- Fail closed when `WEBHOOK_SECRET` unset (startup refusal in production mode).
- `hmac.compare_digest` for the comparison.
- Add `EXECUTED` (and `BLOCKED_EVENT_RISK`) to the same-day dedup set (`cloud/api/main.py:414`).
- Add `timestamp` to the Pine alert JSON + reject payloads older than 2 minutes (replay guard). Delta: Pine script change + one webhook check.
- **AC:** unset secret → all webhooks 503; replayed 10-minute-old payload → 401; re-fired alert after execution → `REJECTED_DUPLICATE`.

### S4-4 · Persist agent trade history locally — **2 pts** (P1-1)
- `TradeHistoryService` load/save at `~/.quantos/trade_history.json` (pattern: `agent/positions.py`).
- **AC:** restart agent → history intact; 20th closed trade flips sizing method from `FIXED_FALLBACK` to `KELLY` across restarts.

### S4-5 · Telegram delivery reliability + token-safe logging — **3 pts** (P1-4, P1-5)
- Retry sends ×3 with backoff; on final failure persist `notify_failed` on the signal.
- Startup + periodic sweep: re-notify `PENDING_CONFIRMATION` signals >5 min old without a successful send.
- Sanitize exception logging in `notifier.py` (no URLs in log output).
- **AC:** with Telegram unreachable, a signal is re-notified after recovery; grep of logs during failure shows no `/bot` substring.

### S4-6 · Stage B confirmed-candle fix — **2 pts** (P1-2)
- Drop the forming candle per timeframe before `detect_breakout` in the internal scanner path; volume ratio computed on closed candles only.
- **AC:** regression test: a synthetic series whose final (forming) candle ticks above the box top does NOT fire; the same series with a *closed* breakout candle does.

### S4-7 · Claude call hygiene: timeout + structured outputs — **2 pts** (P1-9, P2-3)
- `timeout=30` on both `AsyncAnthropic` constructions.
- Convert pre-trade scoring to structured output (tool-use/JSON schema); remove the silent 50.0 fallback — parse failure now surfaces as "unscored" (existing `None` path).
- **AC:** malformed-response test asserts "unscored", not 50.0; webhook latency bounded under simulated slow Claude.

### S4-8 · First integration test harness — **2 pts** (P2-4, partial)
- One end-to-end test: webhook → (real in-memory or test-Postgres) persist → mocked-transport Telegram, with failure injection for: duplicate delivery, Claude exception, Telegram outage.
- **AC:** the three named scenarios from the audit each have a failing-then-fixed test.

---

## Sprint 5 — Measure (≈21 pts)

**Status (2026-07-08): 7 of 8 stories DONE + pushed; 619 tests green.**
✅ S5-1 costs (reconciles Fyers note to the paisa) · ✅ S5-3 corp-action spike
(Fyers daily OHLC is split-adjusted → 5-pt conditional store dropped) ·
✅ S5-4 real breadth (+ cockpit A/D panel; live market-hours quote check pending)
· ✅ S5-5 correlation gate · ✅ S5-6 observability · ✅ S5-7 SEBI compliance doc
(QuantOS ≪10 OPS → no algo registration) · ✅ S5-8 prompt files.
⏳ **S5-2 Claude calibration — the only story left; hard-gated on S4-1 Postgres
+ 30 recorded closed trades, so it cannot start until live-trade data accrues.**
The 5-pt conditional half of S5-3 was dropped by the spike, so the codeable
sprint is effectively complete. See `docs/CORP_ACTION_SPIKE.md`,
`docs/SEBI_COMPLIANCE.md`, and the per-story commit trail for evidence.

### S5-1 · Transaction cost & slippage model — **3 pts** (P1-7)
- `core/risk/costs.py`: NSE intraday stack (brokerage, STT, exchange txn, SEBI, stamp, GST) + configurable slippage bps.
- Wire into `ClosedTrade` net-P&L and the backtest module. All expectancy/Kelly inputs become net-of-cost.
- **AC:** a known round-trip reproduces Fyers' contract-note total within ₹1.

### S5-2 · Claude calibration query — **2 pts** (P1-9 payoff; requires S4-1)
- Bucket `confidence_score` vs. realized `pnl` from the signals table; monthly summary via Telegram or endpoint. Include REJECTED/SKIPPED counts (outcome tracking for rejects = deferred shadow-tracking note).
- **AC:** after 30 closed trades, one query answers "do >80-confidence signals outperform 70–80?"

### S5-3 · Corporate-action verification, then (conditional) adjusted OHLC store — **1 pt spike + 5 pts conditional** (P1-8)
- Spike: fetch a recently split NSE symbol via `get_historical_data`; compare around the split date.
- Only if unadjusted: DuckDB+parquet OHLC store with adjustment factors, consumed by Stage A/B fetch path.
- **AC (spike):** documented verdict with evidence in `docs/`.

### S5-4 · Real breadth data for regime — **3 pts** (P1-10)
- Replace the neutral placeholder (`core/regime/fetcher.py:157-169`) with NSE bhavcopy or Nifty-500 LTP sample.
- **AC:** classifier inputs show live advance/decline; UNCERTAIN rate drops from artificial neutrality.

### S5-5 · Wire correlation gate — **3 pts** (P1-6)
- Agent-side: at sizing time, check candidate vs. open positions (r>0.75 → refuse/downsize); sync result to cloud for display (ADR-09 pattern).
- **AC:** second highly-correlated bank stock signal gets refused with a logged reason while the first is open.

### S5-6 · Observability panel (cockpit, real data) — **3 pts** (P2-8)
- Wire existing mock panels to: signal counts by status/day (from S4-1 Postgres), webhook + Claude latency (log-derived or middleware timer), Claude spend/day estimate, last-agent-heartbeat (from watchlist/regime sync timestamps — doubles as the S4-2 dead-man display).
- **AC:** cockpit shows live values with the agent running; heartbeat goes stale visibly when agent stops.

### S5-7 · SEBI retail algo compliance spike — **2 pts**
- Verify current Fyers/exchange requirements against the post-April-2026 registration regime the project already hit once (new app + static-IP whitelist). Document what auto-execution (vs. current human-in-loop) would additionally require.
- **AC:** one-page `docs/SEBI_COMPLIANCE.md` with citations.

### S5-8 · Prompt files + versioning — **1 pt** (P2-5)
- Move inline prompts to `prompts/*.md`, loaded at startup; git history becomes the prompt changelog.

---

## Sprint 6 — Expand (gated on Sprint 4 + 30–50 recorded Darvas trades)

- **EMA 9/20 crossover strategy** (3 pts): sibling of Stage B scanner; hard-gated to TRENDING regimes via synced regime; tagged `strategy="ema_crossover"` for segmented expectancy.
- **Mean-reversion strategy for RANGING** (5 pts): RSI(2)/Bollinger snap-back, Nifty-100 universe only; hard regime gate mandatory (counter-trend).
- **52-week-high RS momentum** (3 pts): weekly cadence, reuses Stage A discovery pattern.
- ✅ **Fill reconciliation** (2 pts) — **DONE 2026-07-08** (the one Sprint 6 item with no live-data gate; done early). `core/risk/fill_reconciliation.py` compares intended entry (`price`) vs actual fill (`execution_price`) per trade, direction-aware, signed bps (+ = adverse). `GET /reconciliation/slippage` surfaces per-trade deltas + aggregate; `suggested_slippage_bps` = `max(0, mean_bps)` feeds the S5-1 cost model's per-leg `slippage_bps` for backtests. Entry leg only (no intended-exit stored). 17 tests. Empty-but-valid until fills accrue.
- **Options execution path** (L, separate epic): options order support in `BrokerAdapter`/Fyers adapter — prerequisite for the already-built condor/spread advisor to become tradeable.

## Explicitly deferred (with reasons)
- Multi-tenancy (P2-7): single-user in practice; revisit as P0 the day a second user signs up.
- Morning-brief scheduler (P2-6): decide wire-or-delete after Sprint 5 observability lands.
- Zerodha live parity (P2-10): verify only when a Zerodha account is actually available.
- ORB/earnings-gap strategies: structurally misfit (latency / event-filter conflict) — documented in audit conversation.
