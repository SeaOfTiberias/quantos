# QuantOS Audit Findings — 2026-07-08

Read-only audit of `main` @ `f2e403b`. Scope: verify actual behavior vs. backlog
claims across the webhook→Telegram critical path, Darvas/risk math, Claude
integration, secrets hygiene, and test quality. Method: every finding cites
`file:line` evidence read during the audit; anything not verifiable in code is
marked **unverified**.

**Corrected claims:** test count is 461 (not 402), all unit-level —
`tests/integration/` is empty. 13 routers mounted (not 12). "Multi-tenancy
with user_id on every table" is schema decoration only (see P2-7).

---

## P0 — Capital / security risk

### P0-1 · Webhook is fail-open when `WEBHOOK_SECRET` is unset
- **Evidence:** `cloud/api/main.py:174` — `if os.getenv("WEBHOOK_SECRET", "") and alert.secret != ...`. If the env var is missing/renamed/typo'd on Railway, the check is silently skipped and the endpoint accepts unauthenticated trade signals.
- **Why it matters:** one config mistake away from an open signal-injection endpoint on a system that places real orders (behind one human tap).
- **Fix:** fail closed — refuse startup (or 503 the route) when unset in production; use `hmac.compare_digest` for the comparison.
- **Effort:** S

### P0-2 · No kill switch: risk limits exist in config but are enforced nowhere
- **Evidence:** `max_daily_loss_pct` / `max_open_positions` exist only as dataclass fields in `core/config/settings.py:66-67` — a module `agent/main.py` never imports. The sizing path (`agent/main.py:137-163`) checks available funds and stop distance only. No daily-loss halt, no consecutive-loss halt, no position-count cap, no global halt flag, no trading-hours gate on execution.
- **Why it matters:** the config file promises a 5% daily circuit breaker that does not exist. A bad day has no floor other than per-trade stops and human attention.
- **Fix:** enforce both limits in `_size_and_place_order`; add a persistent halt flag (`~/.quantos/halt`) checked every poll tick, settable via Telegram command; dead-man behavior on repeated cloud-poll failures.
- **Effort:** M

### P0-3 · All signal state is in-memory on the cloud; wiped on every deploy
- **Evidence:** `cloud/api/db.py:50` (`_use_postgres = False` hardcoded), `db.py:130-149` (all six `_pg_*` methods are `NotImplementedError` stubs). Railway redeploys on every push to `main`.
- **Why it matters:** pending confirmations vanish mid-flight; a Telegram "execute" reply after a deploy targets a signal that no longer exists; the same-day dedup guard resets; confidence scores are unrecoverable for calibration.
- **Mitigating factors already in place:** Railway Postgres is provisioned (`DATABASE_URL` set), `sqlalchemy`+`asyncpg` are already in `requirements.txt`, the `Signal` schema already carries the full lifecycle (confidence → execution price → exit price → pnl), and the agent already reports closures (`agent/main.py:491`).
- **Fix:** implement the six stubs; gate on a startup connectivity check (not env-var presence — that gating bug already 500'd production once); `CREATE TABLE IF NOT EXISTS` on boot.
- **Effort:** M

---

## P1 — Correctness

### P1-1 · Trade history is in-memory; Kelly can never graduate and expectancy is unmeasurable
- **Evidence:** `core/risk/trade_history.py:27-29` — `self._trades: list = []`, no persistence. The agent restarts daily (Fyers token expiry).
- **Why it matters:** blocks the three questions the system exists to answer: does Kelly ever activate (needs 20 persisted trades), does the strategy have positive expectancy, do Claude's scores correlate with outcomes. Highest leverage-to-effort ratio in this report.
- **Fix:** `~/.quantos/trade_history.json` load/save, same pattern as `agent/positions.py`. Stays local (ADR-01: sizing must work offline); the cloud Postgres copy (P0-3) is the analytics mirror.
- **Effort:** S

### P1-2 · Internal Stage B scanner fires breakouts on the forming (incomplete) candle
- **Evidence:** `core/darvas/box.py:165-188` treats `candles[-1]` as a closed candle; `core/darvas/scanner.py` fetches history to `datetime.now()` mid-session, so the last candle is still forming. Its partial volume also feeds the volume-confirmation ratio. The Pine path is clean (`pine/darvas_breakout_alert.pine:107` uses `alert.freq_once_per_bar_close`).
- **Why it matters:** systematically fires on intrabar wicks that retrace by close — the exact false-breakout class Darvas methodology exists to filter. Internal-scanner signals will look worse than Pine signals for a structural, fixable reason.
- **Fix:** drop `candles[-1]` when its time bucket is still open relative to now (per timeframe).
- **Effort:** S

### P1-3 · Same-day dedup guard ignores `EXECUTED` status
- **Evidence:** `cloud/api/main.py:414` — guard set is `("PENDING_CONFIRMATION", "CONFIRMED")` only. After execution, a re-fired/replayed alert for the same symbol passes clean and generates a second Telegram confirm.
- **Why it matters:** same-day double position on one symbol; human attention is the only remaining guard.
- **Fix:** add `EXECUTED` to the guard set (arguably `BLOCKED_EVENT_RISK` too, else a blocked symbol can be re-attempted until it slips through on an event-calendar refresh).
- **Effort:** S

### P1-4 · Telegram send failure silently strands a live signal
- **Evidence:** `cloud/api/notifier.py:27-58` — 10s timeout, zero retries, returns `False` which `_send_confirmation_request` callers don't act on; signal remains `PENDING_CONFIRMATION` with nobody notified. No dead-letter record.
- **Fix:** retry ×3 with backoff; persist a `notify_failed` marker; startup/periodic sweep re-notifies any `PENDING_CONFIRMATION` older than N minutes without a successful send.
- **Effort:** M

### P1-5 · Telegram bot token can leak into logs via exception messages
- **Evidence:** `cloud/api/notifier.py:57` and `:148` log the raw httpx exception; httpx transport errors embed the request URL, which contains `/bot<token>/`. (Type: Telegram bot token; no values reproduced here.)
- **Fix:** catch and log `type(e).__name__` + sanitized message; never interpolate the URL.
- **Effort:** S

### P1-6 · Correlation check is built, tested, and wired to nothing
- **Evidence:** `cloud/api/main.py:97` — `_correlation_service = None`, never assigned (the same dead pattern the regime service had until `f2e403b`); `cloud/api/correlation_routes.py:36-45` 503s unconditionally; nothing in the signal path calls it. The r>0.75 rejection exists only in unit tests.
- **Fix:** same agent-side-compute + cloud-sync pattern as ADR-09, or run it agent-side at sizing time (it has broker access there).
- **Effort:** M

### P1-7 · No transaction-cost model anywhere
- **Evidence:** zero hits for STT/brokerage/slippage across `core/`, `cloud/`, `agent/`.
- **Why it matters:** intraday NSE round-trip costs (STT, exchange charges, stamp, slippage) routinely consume 30–50% of gross edge on breakout strategies. Every expectancy number the system ever produces will be gross, and therefore optimistic in exactly the direction that loses money.
- **Fix:** single `core/risk/costs.py` with the NSE intraday cost stack; apply in `ClosedTrade.pnl` and any backtest.
- **Effort:** M

### P1-8 · No corporate-action adjustment; upstream adjustment behavior unverified
- **Evidence:** no split/bonus/adjustment logic in-repo. Whether Fyers returns adjusted candles is **unverified**.
- **Why it matters:** an unadjusted 1:5 split inside Stage A's 365-day window reads as an 80% crash — destroys real boxes, fabricates fake ones, corrupts ATR and volume SMA.
- **Fix:** first a 30-minute live verification against a recently split symbol; if unadjusted, that's the trigger for the persistent-OHLC-store story (Sprint 5).
- **Effort:** S (verify) → L (store, only if needed)

### P1-9 · Claude malformed output becomes a fake-neutral 50.0 presented as real
- **Evidence:** `cloud/analyst/pre_trade.py:136-147` — any parse failure returns 50.0; the Telegram message renders it indistinguishably from a genuine score.
- **Fix:** structured outputs (tool-use/JSON schema) so malformed responses become impossible; if the call itself fails, surface "unscored" to the human (the `None` path already does this — reuse it).
- **Effort:** S

### P1-10 · Regime classifier runs with its breadth input hardcoded neutral
- **Evidence:** `core/regime/fetcher.py:157-169` — `_fetch_breadth` returns a 250/250 placeholder with a Sprint-2 TODO.
- **Why it matters:** one of three classification inputs is a constant; RANGING/VOLATILE boundary decisions are made on two signals while appearing to use three.
- **Fix:** NSE bhavcopy or Nifty-500 LTP-vs-prev-close sample at scan time.
- **Effort:** M

### P1-11 · No replay protection on the trade webhook
- **Evidence:** no timestamp/nonce validation anywhere in `cloud/`. A captured payload replays successfully on any later day (dedup only blocks same-day while pending/confirmed/…).
- **Fix:** require a timestamp field in the Pine alert JSON; reject stale (>2 min) payloads. Nonce cache once Postgres exists.
- **Effort:** S–M

---

## P2 — Product debt

| # | Finding | Evidence | Fix / Effort |
|---|---|---|---|
| P2-1 | Secret compared with `!=`, not constant-time | `cloud/api/main.py:174` | `hmac.compare_digest` / S |
| P2-2 | No rate limiting on any endpoint | verified absent | slowapi or per-IP counter / S |
| P2-3 | Anthropic clients use SDK-default (unbounded-ish) timeout inside the webhook request | `cloud/analyst/pre_trade.py:20`, `core/options/recommender.py:28` | `timeout=30` / S |
| P2-4 | Zero integration tests; the 672-line order-placing loop (`agent/main.py`) has zero direct tests; `send_telegram` untested; `_parse_confidence_score` untested; the dedup guard untested | Phase 4 sampling | harness + extraction / M–L |
| P2-5 | Prompts are inline strings — unversioned, undiffable except via git blame | `pre_trade.py:90-133` | move to `prompts/` files / S |
| P2-6 | Morning brief / scheduler never started — `register_jobs()` has no caller | `cloud/scheduler/jobs.py:54` | decide: wire or delete / M |
| P2-7 | Multi-tenancy is aspirational: every row gets `user_id="system"` (`cloud/api/main.py:431`), global webhook secret, single Telegram chat, single global `TradeHistoryService` (`core/risk/trade_history.py:24`) | as cited | defer until second user is real; becomes P0 then / L |
| P2-8 | Cockpit: every panel except Discovery Watchlist renders hardcoded mock data | `cockpit/src/App.jsx` | observability story / M |
| P2-9 | Options strategies are advisory-only — no options order path exists (`place_order` formats `-EQ` only, `core/brokers/fyers.py:122`) | as cited | separate epic, not a bug / L |
| P2-10 | Zerodha adapter exists (301 LOC) but live parity is **unverified** — only Fyers has ever run | `core/brokers/zerodha.py` | verify before claiming broker-agnostic / M |

---

## Phase 4 — Test quality summary

- **461 tests, 100% unit-level.** No test exercises webhook→persist→Telegram, even mocked end-to-end.
- **Coverage is inverted vs. risk:** Kelly (40), regime (44), Darvas math (34), correlation (32) are genuinely well-tested — edge cases, known values, zero-division guards, and several regression tests proven against real live bugs (git-stash verified). Meanwhile: `_size_and_place_order` 0 tests, `_manage_open_positions` 0, `send_telegram` 0, `_parse_confidence_score` 0, dedup guard 0.
- **Named-scenario check:** duplicate webhook — no test; Claude malformed — tested in `test_backtest`/`test_recommender` parsers but *not* `pre_trade`'s; Telegram outage — no test; Fyers rate limit — **yes** (`TestFetchDailyRetry`, `TestDarvasScannerThrottling`).
- **Padding assessment:** minimal — of ~15 weak assertions found, most are `is not None` preconditions followed by real asserts; only `test_screener.py:96` (`assert len(...) >= 0`) is vacuous. The suite isn't padded; it's aimed at the wrong altitude.

## Secrets hygiene (clean)

Full 40-commit history scanned for Telegram-token, Anthropic-key, and hex-secret
patterns: **no hits**. `agent/config.yaml` / `.env` never committed. Tokens read
from env only (`cloud/api/notifier.py:23-24`). Sole leak vector is P1-5.
