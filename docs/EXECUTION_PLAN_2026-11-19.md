# Execution plan: use what is built (2026-11-19)

From the fresh review of 2026-11-18 (user: "how can we leverage this repository for systems trading and for everyday discretionary calls"). It replaces strategy hunting with two tracks that use what is built, and a short list of things to stop. The standing rules in `CLAUDE.md` still apply: trading is paused; capital, size and `dry_run` change only with the user's go-ahead; orders go through the gateway; the user releases them.

**Kickoff prompt** (the user pastes this to start or resume):

> Continue the execution plan. Read docs/EXECUTION_PLAN_2026-11-19.md and do the next unchecked session. Before you build anything, tell me which session it is and what "done" means for it.

**Each session ends** by ticking the tracker with one line of outcome and the commit hash, committing and pushing, deploying with `scripts/deploy-vm.ps1` outside 09:15–15:30 IST if code changed (`powershell -ExecutionPolicy Bypass -File .\scripts\deploy-vm.ps1`), and updating memory.

---

## 1. What the review found

**What five months of tests say.** About 25 candidates and roughly 40 tests show that, on NSE large caps, rules that time entries from daily price levels and indicators don't beat costs. The list covers pivots, CPR, R3/S3, SMC zones, CCI, ORB filters, pairs, vol-conditioning, the S3 flush, the overnight rebound and Pivot Compression. Short sides fail almost every time: stocks drift up. Two things survive, and both are slow and long-biased:

| Survivor | Evidence | Status |
|---|---|---|
| Darvas ATR-stop, Bucket B | OOS 2016-23 PF 1.46, 991 trades; CI only just above 0 | Paper since 2026-09-28: **5 closed trades, 3 open** (2026-11-19) |
| Momentum, candidate 11 | Walk-forward | Paper on the VM; no verdict before ~2027-Q3 |

**What the map is good for.** It is risk geometry and a way to say no, not a signal:
- On the Darvas-8, the map's gain came from not trading (ZYDUS, CYIENT, PERSISTENT).
- Over 2016-23, map entries rescued the pullback picks (+1.13% vs −4.14%) but entered only about 12% of picks. Per pick that was +0.13% against +0.74% as traded, so the map entry must not replace the Darvas trade (45c4cdb).
- The F&O call plan failed its history replay: −0.19R / −0.32R over 870 picks.

**Assets worth keeping:**
- **Data:** the L1 store (3,793 adjusted stocks from 2010, 5-minute bars from 2017 for 500) and the index bars.
- **Map engine:** v3, one version since cebfb5b.
- **Order stack:** gateway, checks, GTT OCO exits, position manager, release page.
- **Research harness:** pre-registration, placebos, bootstrap, replay.

**Gaps:**
1. **Unwatched jobs.** ORB 18, 18b and the stop-out probe sat in "activating" from 2026-10-07 to 11-17 (41 days) and nobody noticed (cf1c518). 18b's verdict, planned for about 11-17, rests on missing data.
2. **Five separate call records:** `trade_ideas.py`, the forward book, `call_plans`, the book job and the Telegram calls. No single record scores discretion.
3. **Research churn.** On 2026-11-17 alone there were six or more pre-registrations, each spun from the previous failure's "lead". Each test is clean, but across about 40 tests one or two passes should turn up by chance.

---

## 2. Standing rules for this plan

- **No new pick-source or signal pre-registration** until sessions E1–E3 are ticked. Work already pre-registered may run (the Darvas second chance, 47833c9).
- **Any future pass must also pass a held-out confirmation period** written into its pre-registration. A discovery pass alone is reported as "lead", not "pass".
- **The map stays frozen at definitions v3.** No v4 until a signal test of v3 has run.
- **Deploy or delete within a week.** Code that is not deployed seven days after its commit is either deployed or reverted, so tests and the live system describe the same thing.
- **No paid API runs** without asking (credit is at 0; the book job runs code-only, e5823be). Daily reasoning happens in Claude Code sessions.

---

## 3. Sessions

### E0. One map: v3 everywhere (DONE)

The old 100-day map is retired from every path. Indices read v3 from the index bars, and the position manager uses v3. cebfb5b; deployed 2026-11-19 and the `quantos-price-maps` timer removed (VM checked: HEAD cebfb5b, 0 price-maps units).

### E1. Job watchdog, and the ORB data gap

**Problem:** a stuck or missed job is silent. The health signals have hidden a dead feed before (2026-07-16, Fyers auth) and missed this one for 41 days.

- **Watchdog:** `scripts/job_watchdog.py` on a VM timer.
  - Runs every 15 minutes from 09:00 to 16:00 IST, and once at 21:45 IST.
  - For each enabled QuantOS timer it knows the expected cadence (from the unit's `OnCalendar`) and the journal file the job writes, if any.
  - **Alert (Telegram, once per fault per day)** when a unit is:
    - `activating` for longer than its `TimeoutStartSec`, or for 30 minutes when that is unset;
    - past its last expected fire with no run;
    - finished with result `failed`;
    - running, but its journal file wasn't written that day.
  - Pure logic in `core/ops/watchdog.py`, with unit tests on synthetic `systemctl show` output. The script only gathers and sends.
- **ORB gap report.** Count the sessions ORB 18, 18b and the probe missed between 10-07 and 11-17. State 18b's new earliest verdict date under its own gate (8 weeks and N ≥ 20 of *recorded* sessions). Count sessions only, with no P&L (18b's no-peeking rule).
- **Done when:** on the VM, a deliberately stuck test unit raises a Telegram alert within 15 minutes and is cleared; the ORB gap report and 18b's new verdict date are committed.

### E2. Darvas Bucket B: the go/no-go rule, written before any further look at the paper P&L

**Why first:** Darvas is the only survivor with an out-of-sample pass and a complete live chain (scan 18:00, pre-open, execute, exits). At about 0.7 closed trades a week, waiting for significance takes more than a year. So the rule compares the paper trades with the backtest instead.

- **From the OOS trade list (2016-23)**, bootstrap the distribution of mean net R (or return per trade, as the backtest reports it) for samples of 10, 20 and 30 trades.
- **Rule, frozen in `docs/DARVAS_GO_NO_GO_2026-11.md`:**
  - **Health:** every scan, pre-open and execute ran (from E1). Fills against the planned entry: slippage per trade under the cost the backtest assumed. No trade missed or doubled by a fault.
  - **Consistent with the backtest:** at 20 closed paper trades, the mean is above the 10th percentile of the backtest's 20-trade distribution, and the worst drawdown is inside the backtest's 90th-percentile drawdown for 20 trades.
  - **Outcomes:**
    - pass both → the user is offered a real-money pilot (size is the user's call; nothing changes without the go-ahead);
    - fail health → fix and restart the count;
    - fail consistency → Darvas goes back to research, reported as a fail.
- **Done when:** the rule doc, with its numbers computed from the backtest, is committed before the paper P&L is next opened. A one-line count of closed paper trades is fine; their returns are not looked at.

### E3. Two narrow tests on the strategy that has an edge (zero API)

Both use the map where the evidence says it helps (stops and exits), on Darvas trades only:

1. **Run the Darvas second chance as pre-registered** (47833c9: Bucket B losing stop-outs become map-planned CE picks on the stop-out day). Discovery 2016-23, confirmation 2024-26. Report pass or fail as written.
2. **Pre-register, then run, stop placement:** on the same Bucket B entries, the ATR stop against a stop beyond the nearest structural liquidity (v3: D/W protected low, or an EQL/sweep low, 0.1 ATR under it).
   - The metric is net R per trade and the share of trades stopped and then reaching the backtest's exit within 15 sessions (the GLAND pattern).
   - Discovery 2016-23, confirmation 2024-26, both halves > 0.
   - Worked cases first (4–5 trades drawn by hand) before the full run (lesson 11-14: check the design against the newest lessons before long runs).
- **Done when:** both results docs are committed and reported. A pass changes nothing live until E2's rule has run its course and the user agrees.

### E4. A benchmark the systems must beat

- **Data:** add the NIFTY200 Momentum 30 and NIFTY 50 indices to `core/market_map/index_bars.py` (NSE's index close file carries them; check the names and the earliest year). Total-return series are better if NSE publishes them; otherwise use price, labelled.
- **Report** (monthly, code-only, to Telegram and `#/reports`): the Darvas paper record and the candidate 11 walk-forward, against both indices over the same dates, after costs.
- **The household rule this gives:** a system that can't beat a NIFTY200 Momentum 30 index fund after costs and tax doesn't get capital; the fund does.
- **Done when:** the indices are in the store and the first report has run on the VM.

### E5. One call ledger for discretionary calls

**Goal:** every call, from whatever source, is written down before its outcome and scored in R. Within 60 calls it shows whether discretion (the user's or Claude's) adds anything over the mechanical baselines.

- **Store:** `~/.quantos/ledger/calls.jsonl` on the VM; `core/ledger/` (pure: schema, scoring) and `scripts/ledger.py` (add, list, score).
- **A call records:**
  - date and time;
  - who called it (screener, Darvas, user, Claude);
  - symbol, side, entry rule, stop, target and size in R;
  - the salvage plan;
  - the frozen v3 map read (`map_read`, required, as `trade_ideas.py` already enforces);
  - "taken" or "avoided", and why.
- **Sources:** `trade_ideas.py` becomes a thin writer to the ledger. `call_plans` and the book job write their mechanical plans as **baselines** for the same symbol and day, not as separate records.
- **Scoring (deterministic code, unit-tested):**
  - R per call from daily bars, walked forward like `call_plan.step`;
  - for each discretionary call, the same score for the call as the screener sent it and for the mechanical map plan;
  - "avoided" calls are scored too, to show what avoiding saved or cost.
- **Cockpit:** `#/ledger` lists the calls and the running comparison (n, mean R, against both baselines). It needs the nginx allowlist entry by hand.
- **Done when:** a call can be added from the CLI and from a Claude Code session, the evening job scores open calls, and `#/ledger` shows them.

### E6. The evening routine (code-only)

At about 20:15 IST, after the call plans, one Telegram brief and a cockpit page:
1. **Index:** NIFTY and BANKNIFTY v3 reads (W and D structure, nearest strong zones, protected and weak levels).
2. **Breadth:** from `playbook_scan` (W up against W down, sweeps of the day).
3. **Candidates:** the day's Darvas and F&O picks, each with its context card and the mechanical plan.
4. **Vetoes**, flagged by code (markers, not orders):
   - stop inside a strong zone;
   - R:R under 1 to the first obstacle;
   - a long into a W/M supply zone, or a short into a W/M demand zone (the HDFCBANK lesson, 2026-11-02);
   - results within 5 sessions.

The user, or Claude in a Claude Code session, turns the brief into ledger calls following `docs/TRADE_REASONING.md`. No model runs in the job.

- **Done when:** the brief has arrived on three evenings in a row and at least one call has been entered from it into the ledger.

### E7. Review at 60 ledger calls

- Report discretion against both baselines: mean R, its spread, the bootstrap CI, and the user's calls and Claude's calls separately.
- Decide with the user what changes: more weight on the calls, or the mechanical plan, or neither.
- **Done when:** the review is committed and the user has the result.

---

## 4. Parked (not in this plan)

- Map v4, golden-set scoring, and sprint sessions S6 (market backdrop), S6b (fundamentals) and S7 (situations). They return only after a signal test of v3.
- New strategy candidates and pick sources (rule 1 above).
- Model-judged (A2) runs while API credit is 0.

---

## Tracker

- [x] E0 One map, v3 everywhere: cebfb5b, deployed 2026-11-19, price-maps timer removed
- [ ] E1 Job watchdog + ORB gap report. **Built, not yet deployed (2026-11-19):**
  - `core/ops/watchdog.py` + `scripts/job_watchdog.py` + timer; 12 tests. A read-only dry run on the VM found exactly the two real faults: the option-chain recorder STUCK since 10-07 14:33 IST, and the NSE calendar stale since 08-18.
  - Start timeouts added to the 5 units that had none.
  - Gap report `docs/ORB_GAP_REPORT_2026-11-19.md`: 27 sessions lost; 18b at 6 entries (4 BN, 2 NIFTY) in 11 recorded sessions; proposed amendment "8 weeks = 40 recorded sessions" (≈ 2026-12-30), awaiting the user.
  - **Tick when:** deployed, the timer enabled, and `scripts/ops/watchdog_selftest.sh` FAILED and then cleared alerts seen on Telegram.
- [ ] E2 Darvas go/no-go rule (before the next look at paper P&L)
- [ ] E3 Darvas second chance run + stop-placement test
- [ ] E4 Momentum benchmark indices + monthly report
- [ ] E5 One call ledger
- [ ] E6 Evening routine
- [ ] E7 Review at 60 calls

## Changes to the plan

_Dated notes on anything a session changed for later sessions._

- **2026-11-19 (E1):** the derived NSE calendar ends 2026-08-18. Anything that needs trading days after that date falls back to weekdays. Re-deriving it (`scripts/derive_nse_calendar.py`) is a small task to do before E2, which counts sessions.
