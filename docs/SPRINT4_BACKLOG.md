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

## Sprint 7 — Prove (≈20 pts)

Derived from Fable's 2026-07-16 review of the trading rationale. The finding
that reframes this sprint: "unproven" was being treated as a *waiting*
problem (accumulate 30–50 live trades) when it is a *measurement-design*
problem (make the trades interpretable, and bound the answer cheaply first).
These stories insert **before** Sprint 6 rather than after it, because S7-3
is the falsifier Sprint 6's old gate was standing in for — see the corrected
gate below.

**Do not batch.** The sequencing below is explicit dependency, not story
order for convenience: S7-3 is a falsifier that can delete the need for
S7-4 through S7-7. Building the veto instrumentation (the single biggest
story here) before running the backtest risks 8 points of wasted work if
the thesis doesn't survive contact with costs.

### S7-1 · Deploy the breadth/universe fix to the VM + startup assertion — **2 pts**
As an operator, I want proof at boot that both universes actually loaded,
so a repeat of the Chartink-breadth bug (regime measured from a 128-name
momentum list instead of a market cross-section) is caught immediately
instead of discovered by hand weeks later.
- Hand-set both `scanner.universe_file` and `regime.breadth_universe_file`
  on the VM's `agent/config.yaml` — it's gitignored, so `git pull` delivers
  `agent/universe_nifty500.txt` but not the config keys pointing at it; the
  old `scanner.universe_file` value plus the backward-compat fallback would
  otherwise silently keep routing breadth back to the stale 128-name list.
- Add a startup log line per universe consumer (Stage A scanner, regime
  breadth) showing resolved file path, symbol count, and a checksum —
  nothing today detects deployed-config drift from repo intent.
- **AC:** `/regime/status` advance+decline+unchanged sums to ~500, not ~128;
  restart logs show two distinct universe loads with matching counts.
- ✅ **DONE 2026-07-16** — VM config carried both keys since the prior day's
  restart; verified live: `/regime/status` returns `advance_count: 250,
  decline_count: 250` (sums to 500). Startup log confirms both consumers:
  `Regime breadth universe: 500 symbols from agent/universe_nifty500.txt` and
  `Stage A: scanning 500 symbols from agent/universe_nifty500.txt`. Note: the
  first post-restart breadth fetch hit a Fyers 429 (500-symbol quote fetch
  colliding with Stage A's own quote burst at market open) and fell back to
  neutral (hence the exact 250/250 split) — a transient rate-limit collision,
  not a config bug; next `REGIME_CACHE_TTL` refresh should pull real data.

### S7-2 · Expectancy arithmetic: plausible edge vs plausible cost — **1 pt** (zero code)
As the person whose capital is at risk, I want to know whether the
strategy's plausible edge can even clear its own cost model before anyone
spends engineering time on a return that's mathematically dead on arrival.
- One page: sketch plausible win-rate/R distributions for the Darvas setup
  (e.g., ~40% win rate, ~2R average winner ≈ 0.2R gross expectancy) against
  the S5-1 cost model's round-trip range for NSE small/mid-cap (STT +
  brokerage + breakout-entry impact + stop slippage, plausibly 0.3–0.8%).
- State plainly whether the hypothesized edge sits inside or outside the
  cost model's error bars.
- **AC:** a one-page doc exists with an explicit verdict — "edge clears
  costs" or "edge does not clear costs at plausible parameters" — and the
  assumptions used to get there.
- ✅ **DONE 2026-07-16** — `docs/EXPECTANCY_CHECK.md`. Verdict: inconclusive
  by arithmetic alone (plausible net expectancy spans −0.26R to +0.13R
  depending on box width and fill slippage) — not dead on arrival, not
  clearly positive either. Hands off to S7-3.

### S7-3 · Pine strategy + sample backtest over 30–50 names — **5 pts** — THE GATE (gated on S7-1, S7-2)
As the person deciding whether to keep building on Darvas, I want an actual
backtest result before investing in veto instrumentation, sizing, and exit
rules that would be wasted work if the edge doesn't exist.
- Convert `pine/darvas_breakout_alert.pine` from indicator to strategy,
  matching `core/darvas/box.py`'s multi-timeframe confluence logic for
  entry/stop/exit.
- Run TradingView Strategy Tester across 30–50 names pre-sampled across the
  cap spectrum (sampling method fixed in advance, not cherry-picked after
  seeing results) — current Nifty 500 constituents, so results are a
  survivorship-biased upper bound. That bias is acceptable here: it works
  *for* the strategy, so if Darvas can't beat costs even with the bias
  helping, the thesis is dead for a week's work instead of a year's capital.
- Export CSVs into the existing `core/backtest/parser.py` + `analyst.py`
  ingest path (built for exactly this in Sprint 4/US-11).
- **AC:** a documented go/no-go verdict on whether net-of-cost expectancy is
  positive across the sample. This verdict gates Sprint 6 and S7-4–S7-7.
- ✅ **DONE 2026-07-19 — VERDICT: NO demonstrated edge. `docs/S7_3_BACKTEST_RESULTS.md`.**
  39 of 40 pre-committed symbols (DOMS excluded — exported in SEK, not INR;
  effect on the pooled verdict is negligible at n=690), 690 pooled trades,
  28.7% win rate, profit factor **0.75**, Sharpe **-1.25**, net **-241%** at
  realistic cost (NSE stack + 20bps slippage/leg). Sensitivity-checked at
  0bps slippage (most generous case possible, no real execution achieves
  this): profit factor only reaches 1.11, Sharpe 0.22 — still fails
  `has_positive_edge`'s 0.5 Sharpe bar. **No cost assumption in a defensible
  range clears a genuine edge for this specification.** This is the S7-2
  expectancy check's "inside the cost model's error bars" finding, now
  confirmed empirically rather than sketched — and since the sample is
  survivorship-biased (current Nifty 500 constituents, an upper bound), the
  real answer is likely worse, not better.
  **Consequence: Sprint 6 stays gated (verdict is negative). S7-4 through
  S7-7 do NOT proceed** — instrumenting an 8-point veto-logging system for a
  strategy that doesn't clear its own costs is exactly the wasted work the
  sequencing was designed to avoid. Also found+fixed en route: a real Pine
  bug (`darvasBox()` reset `boxReady` before checking `breakoutNow`,
  suppressing nearly every real breakout — commit `a74521a`; live Python
  trading engine was never affected, verified structurally immune) and a
  TradingView export-format mismatch in `core/backtest/parser.py` (actual
  columns are `Date and time`/`Price <CCY>`/`Size (qty)`/`Net PnL <CCY>`
  etc., not what US-11 assumed; also handles the per-chart currency-suffix
  variance TradingView leaks into the export).

### S7-4 · Instrument the veto — **8 pts** (gated on S7-3 surviving)
As the person whose discretion sits in the execution loop, I want to know
whether my vetoes make the system better or worse — right now a skipped
signal is persisted (`cloud/api/main.py:402`) but its counterfactual is not,
so the record can't distinguish good judgment from bias toward skipping the
uncomfortable (and disproportionately winning) signals.
- Log every Stage-B signal fired — entry/stop/size — whether executed,
  skipped, or rejected.
- For every skip, paper-track a hypothetical exit under the same entry/stop
  rules used for real trades.
- Pre-commit written veto criteria (data errors, corporate events, known
  news) — "feels toppy" is explicitly excluded as a logged reason.
- Fold Claude's pre-trade opinion into the same log — it's a third,
  unversioned author of the record.
- **AC:** a report shows skip rate plus the P&L delta between the executed
  curve and the hypothetical-all-signals curve; skip rate >15% is flagged.

### S7-5 · Pre-committed kill criterion — **1 pt** (gated on S7-3 surviving)
As the operator, I want a written stop-trading threshold in place before
live data arrives, so a losing streak can't get rationalized in real time
after the fact.
- Document the specific expectancy/drawdown/win-rate threshold and sample
  size at which Darvas trading pauses pending re-review.
- **AC:** doc exists, dated, referenced from the daily runbook.

### S7-6 · Sizing: fixed-fractional until ~100 trades — **2 pts** (gated on S7-3 surviving)
As the risk owner, I want position size to come from a stable rule instead
of Kelly noise on tiny samples, and the full stack of multipliers to
resolve to one auditable rupee number.
- Force fixed-fractional sizing (bypass `core/risk/kelly_calculator.py`'s
  Kelly path) until real trade count reaches ~100 — Kelly on 10–50 trades is
  noise, not signal.
- Specify how `size_multiplier` × Kelly (once eligible) × kill-switch caps
  compose — currently unspecified.
- **AC:** one test walks a signal through every multiplier and asserts the
  final rupee amount matches the documented formula.

### S7-7 · Exit rule specification — **1–3 pts** (gated on S7-3 surviving)
As the person who inherits P&L dominated by exits, I want the trail,
time-stop, and regime-flip-mid-trade behavior written down properly, since
exits — not entries — dominate breakout system P&L and today's spec is six
words.
- Document (and align code to) the trailing-stop rule, any time-based stop,
  and explicit behavior when regime flips mid-trade (tighten stop? exit
  immediately? hold to original rule?).
- **AC:** doc exists with a scenario table covering a TRENDING→RANGING flip
  mid-trade and a time-stop expiry.

---

## Sprint 6 — Expand (BLOCKED 2026-07-19 — S7-3's verdict came back negative)

**Gate corrected 2026-07-16** (was: "gated on Sprint 4 + 30–50 recorded
Darvas trades"). That gate was statistically void: live trades validate
*execution* (fills, slippage, infra) not *edge*, and at plausible win rates
30 trades can't distinguish a good breakout system from a losing one (±18pt
CI on win rate alone). Worse, until S7-4 lands, executed trades aren't even
a clean sample — the human veto means what got recorded is a biased subset
of what the system generated. Sprint 6 waited on **S7-3's backtest verdict**
instead — and that verdict is **NO demonstrated edge** (`docs/S7_3_BACKTEST_RESULTS.md`:
profit factor 0.75 at realistic cost, still fails the Sharpe bar even at an
unrealistic zero-slippage best case). Sprint 6 stays blocked: building
strategies to expand a system that doesn't clear its own costs isn't the
next step — revisiting the Darvas specification (or the thesis itself) is.
See Sprint 7 above for what's next.

- ❌ **EMA 9/20 crossover strategy (equity)** — **DROPPED 2026-07-19** per Fable's review: "Darvas in a different costume" — same single-name trend-following entries, same trail-dominated exits, same turnover profile that just failed S7-3, no distinct documented anomaly behind it beyond generic trend-following (which the literature supports at asset-class/futures level, not fast EMA crosses on individual equities net of retail costs). Not worth the manual backtest session it would cost to confirm what's already predictable.
- **Mean-reversion strategy for RANGING** (5 pts): RSI(2)/Bollinger snap-back, Nifty-100 universe only; hard regime gate mandatory (counter-trend). Deprioritized behind Sprint 8 (below) — Fable's read: cheap to test via the existing Pine pipeline but expect a negative result (same high-turnover family as Darvas, and conditioned on the regime classifier's RANGING output, which is itself unvalidated per S8-1).
- **52-week-high RS momentum** — promoted to **Sprint 8, S8-3** below (Fable's top-ranked candidate — the actual documented cross-sectional momentum anomaly, weekly cadence attacks the turnover-vs-cost problem that killed Darvas directly).
- ✅ **Fill reconciliation** (2 pts) — **DONE 2026-07-08** (the one Sprint 6 item with no live-data gate; done early). `core/risk/fill_reconciliation.py` compares intended entry (`price`) vs actual fill (`execution_price`) per trade, direction-aware, signed bps (+ = adverse). `GET /reconciliation/slippage` surfaces per-trade deltas + aggregate; `suggested_slippage_bps` = `max(0, mean_bps)` feeds the S5-1 cost model's per-leg `slippage_bps` for backtests. Entry leg only (no intended-exit stored). 17 tests. Empty-but-valid until fills accrue.
- **Options execution path** (L, separate epic): options order support in `BrokerAdapter`/Fyers adapter — prerequisite for the already-built condor/spread advisor to become tradeable.

---

## Sprint 8 — Shortlist (≈13 pts + 1 zero-code)

Derived from Fable's 2026-07-19 post-S7-3 review (`docs/S7_3_BACKTEST_RESULTS.md`
killed Darvas; the same review ranked what's left) plus a second, independently
track-recorded candidate the user has been running manually. Same discipline
as Sprint 7: pre-commit before running, sequence don't batch, a negative
verdict is a valid and useful outcome.

**VM ops note (2026-07-19):** the live Darvas loop was mothballed —
`quantos-agent.service` and `quantos-agent-daily-restart.timer` both
`systemctl stop`ped and `disable`d on the VM — since Sprint 6 stays blocked
and zero validated strategies are running through it. No daily token-refresh
ritual needed until something in this sprint validates. Restarting later is
a one-line `systemctl enable --now quantos-agent`.

**Why regime validation goes first:** two later stories (S8-3's optional
regime gate, S8-4's regime-filtered NIFTY entries) want to condition on
`Regime.TRENDING_BULL`/`TRENDING_BEAR`, and Fable's review flagged that
classifier as itself unvalidated — hand-picked thresholds with no test that
they correlate with anything real. Wiring either strategy to an unvalidated
gate would just be Darvas's mistake one level up. S8-1 removes that
uncertainty for both stories at once instead of assuming the gate works.

### S8-1 · Regime classifier validation harness — **3 pts**
As the person about to gate two new strategies on this classifier's output,
I want to know whether TRENDING_BULL/TRENDING_BEAR/RANGING/UNCERTAIN
actually separates real forward outcomes before anything depends on it.
- Replay `core/regime/classifier.py`'s `classify()` day-by-day over
  historical NIFTY + VIX data (`core/regime/fetcher.py`'s `_fetch_nifty`/
  `_fetch_vix` logic is fully reconstructable from historical daily OHLCV —
  live-tick breadth is not, so the replay accepts breadth as UNCERTAIN and
  notes that limitation rather than faking a breadth history).
- Correlate the resulting regime time series against forward NIFTY returns
  and realized volatility over the following N days.
- **AC:** `docs/REGIME_VALIDATION.md` with an explicit verdict — does
  TRENDING_BULL precede positive forward drift more than UNCERTAIN does,
  does RANGING precede lower realized vol — using the same go/no-go framing
  as `docs/S7_3_BACKTEST_RESULTS.md`.
- ✅ **DONE 2026-07-19 — VERDICT: classifier does NOT reliably separate forward
  outcomes; several results run backwards from the label.** `docs/REGIME_VALIDATION.md`.
  1254 trading days replayed (2021-06-28 to 2026-07-17), real breadth from 99
  universe symbols (not a placeholder). Findings:
  1. **TRENDING_BEAR precedes HIGHER forward returns than TRENDING_BULL**
     (+1.43% vs +0.89% at 20d, n=106 vs n=334) — backwards from the label.
     Most likely reading: this classifier's "bear" catches short pullbacks
     inside the mostly-rising 2021-2026 sample, which bounced.
  2. **RANGING does not precede calmer markets** — its realized vol (0.83) is
     tied with UNCERTAIN/BEAR and higher than TRENDING_BULL's (0.63), despite
     RANGING supposedly meaning "choppy, avoid breakouts."
  3. **VOLATILE precedes the BEST forward returns of any regime** (+3.64% at
     20d, ~4x TRENDING_BULL) while the live system's actual response to
     VOLATILE is to cut position size 50% — the design pulls back exactly
     when, historically, the best average outcomes followed. n=39 here is the
     smallest bucket (likely a few sharp V-shaped recoveries dominating the
     mean) — least confidence in this one, but not reassuring either way.
  4. **UNCERTAIN fired on 603/1254 days (48%)** — even setting aside whether
     the other four labels are predictive, a gate that abstains on half of
     all trading days is a large standing cost by itself.
  **Consequence for S8-3/S8-4 below: do not gate either on this classifier's
  output as a headline result.** Report both regime-split and unfiltered
  variants where the story already allows for that, but the unfiltered
  number is the one to trust. This also weakens in advance the "Darvas would
  have worked gated to TRENDING_BULL" argument Fable's review anticipated
  someone would eventually make — TRENDING_BULL wasn't strongly better than
  UNCERTAIN here either, so that rescue looks unlikely to have worked.

### S8-2 · Fyers automation trade-history retrospective — **zero code** (ended up small-code)
As the person who already has real (not backtested) results for the NIFTY
EMA9/21 options strategy below, I want a free analysis of the actual exit
distribution before designing any replacement exit rule.
- User exports whatever trade/execution log Fyers' built-in automation
  provides for the strategy described in S8-4.
- Analyse (no code, mirrors `docs/EXPECTANCY_CHECK.md`'s style): how often
  would a trailing stop have captured more than the fixed ₹2000 cap did; how
  often the position ran to -₹2000 after the crossover had already reversed
  (i.e. a faster invalidation exit would have cut the loss earlier).
- **AC:** short written analysis grounding S8-4's exit-rule design in real
  trade data instead of guessed parameters. Runs in parallel with S8-1/S8-3
  — needs the user's export, not more code.
- ✅ **DONE 2026-07-19.** `docs/S8_2_TRADE_HISTORY_ANALYSIS.md` +
  `scripts/analyze_s82_trade_history.py`. Scope grew slightly beyond "zero
  code": answering the trailing-stop/invalidation questions properly needs
  to know what the underlying was doing WHILE each trade was open, which the
  raw tradebook doesn't carry (entry/exit fills only) — so the script fetches
  real NIFTY 5-min candles for each trade's window (small, fast fetch, ~21
  trades of a few hours each — unlike S8-1's multi-year pull) and computes
  EMA9/21 on them, same as S8-1's "deliver more than scoped when the data
  turns out to be cheap" pattern.
  - Real tradebook: `backtest_results/nifty_ema_options_tradebook.csv`
    (committed, matching S7-3's raw-data-as-audit-trail precedent — but with
    Fyers' Client Name/Client ID/PAN header stripped before committing; this
    repo pushes to a public-ish GitHub remote and that header is real PII,
    not something to put in git history). 21 same-day round trips
    reconstructed (46 fills, FIFO-paired per option contract) + 2 Overnight
    trades reported separately as manual overrides.
  - **Win rate 48% (10/21), total gross P&L +₹2,633 — roughly breakeven
    before real costs**, over a small sample.
  - **Confirms the user's stated concern directly: 18/21 trades (86%) exit
    via the P&L cap, not the 3:10pm time-stop, and cap-exits cluster tightly
    at ±₹2000-2200 on BOTH sides** — the cap is doing almost all the work,
    consistent with "why stop at 2000."
  - **Question 1 (faster invalidation):** 5/21 trades had the EMA9/21
    crossover reverse against the position before the actual exit — one
    case rode 335 minutes past invalidation to a small loss, several rode
    150-210 minutes past invalidation into the ±₹2000 cap.
  - **Question 2 (trailing stop):** 3/21 trades gave back >20% of the
    underlying's peak favourable move by the actual exit (one gave back
    105% — moved favourably, then reversed past entry before exiting).
  - Caveats carried into S8-4: gross P&L only (no cost model applied here);
    underlying-move analysis approximates option premium path from NIFTY's
    own 5-min move, not real option tick data (none exists in this repo);
    small sample — this grounds S8-4's design, it is not itself a verdict.

### S8-3 · 52-week-high RS momentum backtest — **5 pts** (unblocked — S8-1 done, verdict negative)
As the person deciding what to build next, I want the one candidate with an
actual documented edge (unlike Darvas's borrowed citation) tested with the
same rigor before any more infrastructure gets built around it.
- New harness (e.g. `scripts/backtest_rs_momentum.py`), modeled on
  `core/darvas/weekly_discovery.py`'s fetch/throttle/gather structure over
  `agent/universe_nifty500.txt`: 52-week-high-proximity/RS score per symbol,
  weekly rebalance into a pre-committed top-N.
- Constructs `BacktestTrade` objects directly (bypassing the TradingView CSV
  parser entirely — no TradingView export exists for a cross-sectional
  strategy; follow `tests/unit/test_backtest.py`'s `make_trades()` pattern)
  and feeds the existing `_compute_metrics`. Cost model: `core/risk/costs.py`'s
  `CostModel` with delivery-style STT/stamp rates (weekly hold, not intraday).
- Pre-commit universe, ranking rule, holding-period rule, rebalance cadence,
  and pass/fail bar to a doc BEFORE running — same discipline as S7-3's
  `docs/S7_3_BACKTEST_SAMPLE.md`.
- **AC:** documented go/no-go verdict, matching `docs/S7_3_BACKTEST_RESULTS.md`'s
  format. **S8-1 came back negative — report the UNFILTERED result as the
  headline number.** A regime-split variant is optional/informational only,
  not a basis for the go/no-go call.

### S8-4 · NIFTY EMA9/21 options strategy backtest — **5 pts** (unblocked — S8-1 done, verdict negative; informed by S8-2)
As the person who has been running this manually via Fyers' built-in
automation (5-min EMA9/EMA21 crossover on NIFTY → buy ATM/near-ATM CE on
bullish cross, PE on bearish cross; currently exits at ±₹2000 P&L or 3:10pm,
"has worked ok"), I want the three specific improvements I asked about
tested against history before any of them get automated.
- New harness (e.g. `scripts/backtest_nifty_ema_options.py`): fetch NIFTY
  5-min historical bars (`FyersBroker.get_historical_data(..., "5m", ...)` —
  confirmed already supported by the broker adapter's `_TF_MAP`), detect
  EMA9/EMA21 crossovers, approximate option P&L from the underlying's point
  move (flagged simplification — full options pricing needs historical
  IV/chain data this repo doesn't have yet; delta-approximated P&L is the
  cheap first pass, sufficient to compare exit rules against each other even
  if absolute P&L needs a pinch of salt).
- Test three separable questions against the same historical crossover set:
  1. Trailing stop (premium high-water-mark minus a buffer, or
     underlying-ATR-based) vs the fixed ±₹2000 baseline.
  2. Faster invalidation exit — exit when the crossover itself reverses
     within N candles, instead of riding to -₹2000 regardless.
  3. Regime-filtered entries — **S8-1 came back negative (TRENDING_BEAR
     precedes HIGHER forward returns than TRENDING_BULL in-sample, RANGING
     doesn't precede lower vol), so this is now a lower-priority,
     informational-only variant, not an expected win.** Still worth
     including in the comparison table (cheap, and it's a different sample
     — daily NIFTY regime vs 5-min NIFTY crosses — so it's not strictly the
     same test), but do not expect it to raise the win rate, and don't
     gate the go/no-go verdict on it.
- New cost model variant needed: options STT is 0.1% on sell premium (not
  equity's 0.025% sell-only), different exchange/SEBI rates — `core/risk/costs.py`'s
  own docstring already cites the right numbers; instantiate a second
  `CostModel` with those parameters rather than reusing `DEFAULT_COST_MODEL`.
- **AC:** documented comparison of baseline vs each candidate exit rule vs
  regime-filtered, net of the options cost model, using S8-2's retrospective
  as a sanity check on the harness's realism.

### Live execution engineering — deferred, not started
Not scoped as a story yet — only begins if S8-3 or S8-4 validates. If/when
it does, the blockers found 2026-07-19 become the task list: `fyers.py`'s
`place_order`/`get_ltp`/`get_quotes` each independently hardcode `NSE:{symbol}-EQ`
(3 separate call sites, not unified); no option-symbol constructor exists
(strike+expiry+CE/PE → Fyers convention); no NIFTY lot-size/strike-interval
constant exists anywhere (`core/options/strategy_builder.py:226`'s lot size
75 is a generic placeholder, not NIFTY-specific); `get_option_chain()`
(`fyers.py:358`) is a real, working, currently-unused pass-through — a
starting point, not a finished path. Wiring in either validated strategy
also inherits the still-unresolved human-veto contamination problem
(Fable's original review) — that gets fixed once, not per-strategy.

### Also fixed this sprint (no live-data gate, done immediately)
- ✅ **Negative-Kelly floor bug** — **DONE 2026-07-19.** `core/risk/kelly_calculator.py`'s
  negative-edge branch floored sizing at `MIN_SIZE_PCT` (0.5%) even when the
  last `lookback` trades measured a losing system — guaranteeing continued
  exposure to a measured negative edge rather than refusing to trade it.
  Now sizes to 0 (`size_pct=0.0`, `risk_amount=0.0`), which flows through to
  `qty=0` and `agent/main.py`'s existing `quantity <= 0` guard (raises
  `BrokerError`) — a loud refusal, not a silent skip. The floor still
  applies correctly for a small POSITIVE edge (that's what it's for).

## Explicitly deferred (with reasons)
- Multi-tenancy (P2-7): single-user in practice; revisit as P0 the day a second user signs up.
- Morning-brief scheduler (P2-6): decide wire-or-delete after Sprint 5 observability lands.
- Zerodha live parity (P2-10): verify only when a Zerodha account is actually available.
- ORB/earnings-gap strategies: structurally misfit (latency / event-filter conflict) — documented in audit conversation.
