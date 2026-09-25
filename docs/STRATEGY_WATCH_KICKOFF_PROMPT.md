# Kickoff prompt: watch the three live paper strategies (18, 18b, Darvas ATR-stop)

Written 2026-09-26 after two sessions (09-24, 09-25/26) that took candidate 18,
candidate 18b and the Darvas ATR-stop candidate from "backtest passed" to
running on the VM in paper mode with real-capital sizing wired in. Paste the
block below into a new session.

---

```
This session is for WATCHING our three live paper strategies, not building
new ones. Everything below is in paper mode (dry_run: true). Do not change
capital, sizing or dry_run without asking me first
(feedback_confirm_before_scaling_capital).

## 0. Load context first
Read these memory files before anything else:
- quantos_orb_options_scalping_status, quantos_orb_entry_filter_status,
  quantos_orb_scalping_golive_decision            (candidates 18 / 18b)
- quantos_darvas_atr_stop_status,
  quantos_darvas_atr_stop_live_executor            (Darvas ATR-stop)
- quantos_sharpe_sweep_equity_curve_plan, quantos_pine_breakout_bug
- quantos_vm_deploy_pipeline, quantos_health_signals_mask_dead_broker
Then docs: ORB_SCALPING_EQUITY_CURVE_RESULTS.md,
ORB_SCALPING_CAPITAL_ALLOCATION_RESULTS.md,
DARVAS_ATR_STOP_EQUITY_CURVE_RESULTS.md, ORB_ENTRY_FILTER_METHODOLOGY.md,
ORB_STOPOUT_SPREAD_PROBE_METHODOLOGY.md.

VM access: ssh -i "D:/Exodus_14_14/QuantOS/Oracle SSH/ssh-key-2026-07-14.key" ubuntu@161.118.189.29
(allowed without prompting via .claude/settings.local.json). The VM runs UTC.
journalctl is SLOW on this box: always pass --since and wrap in `timeout 100`,
and query several units in ONE pass (never loop per day).

## 1. What is running (state as of 2026-09-26)

Candidate 18 -- ORB options scalping, NIFTY + BankNifty
- quantos-orb-scalping-live.timer, every minute in market hours.
- VM config orb_scalping: enabled, dry_run true, dynamic_sizing true
  (rolling half-Kelly, f619b43), starting_capital 70000, min_capital_floor 60000.
- In paper mode Kelly history stays EMPTY (dry-run exits record no
  ClosedTrade) -> sizing uses the 2% fallback -> expect 1 lot via the floor.
  Real half-Kelly starts only after 20 REAL closed trades.
- Gate: stop-out spread probe, N>=20 per index AND >=4 weeks since 09-03.
  As of 09-25: NIFTY 7/20, BankNifty 8/20, 3.1 weeks. Time condition met ~10-01.
  Check: .venv/bin/python scripts/check_orb_stopout_probe_gate.py (ON the VM).

Candidate 18b -- same signal, entry filter (NIFTY Mon/Fri only, BankNifty
|gap| > 0.3%)
- quantos-orb-scalping-filtered-live.timer, separate position store + dry-run log.
- VM config orb_scalping_filtered: same sizing keys as 18 (70000 / 60000).
- Gate: N>=20 per index AND >=8 weeks since 09-22 -> earliest 2026-11-17.
  As of 09-25: 1/20 each. Rs50k equity narrative also reported only on 11-17.
  Check: .venv/bin/python scripts/check_orb_18b_gate.py (ON the VM).
- NEVER compute running P&L from the .jsonl logs by hand -- no peeking.

Darvas ATR-stop, Bucket B (35-50% box width) on the Nifty 500
- Split 09-25 (ce71d0b):
  * quantos-darvas-atr-stop-scan.timer, 18:00 IST: fetches ~500 daily
    histories, writes ~/.quantos/darvas_atr_stop_plan.json. No orders.
    Entries tagged Alpha50 / Mom30 (informational only).
  * quantos-darvas-atr-stop-live.timer, 09:45 IST: places ONLY the plan's
    orders. Refuses a missing, already-executed or >4-day-old plan.
- VM config darvas_atr_stop: enabled, dry_run true, equity_fraction 0.09,
  starting_capital 250000 (paper ledger).
- First plan (bars 09-25): ONE entry, ZYDUSLIFE, ceiling 1181.5, floor 835.5,
  width 41.4%, stop 1124.27, target 1527.50. First execute: Mon 09-28 09:45 IST.
- Gate: a weeks-long supervised paper run, then my explicit capital go-ahead.
  Fable's caution stands: both Sharpes sit near the 0.5 bar (±0.3).
- Real-money context: at the 9% portfolio-Kelly fraction the equity curve is
  thin -- full window ~1.4% CAGR, Sharpe 0.28 at Rs250k; holdout +0.7%
  total. The per-trade edge passed; the portfolio curve is modest. Keep
  that in view when judging the paper run.

Pine (TradingView, my own validation of stocks OUTSIDE the universe)
- darvas_breakout_strategy.pine, darvas_breakout_alert.pine,
  darvas_breakout_indicator_v6.pine: validated Bucket B rule, shared engine
  (verified: 0 mismatches / 6,867 days; 69/69 trades vs _simulate_exit_atr).
- darvas_breakout_indicator_v7.pine is MY original indicator -- leave it alone.
- Still pending on my side: pasting them into TradingView to confirm they
  compile, and checking ZYDUSLIFE shows the 09-25 breakout with the values above.

## 2. What to do this session

A. Health (every session): for each of the five timers above, show last run,
   result and next run (systemctl list-timers --all + systemctl show -p
   Result). Confirm the Fyers token is valid -- all-green timers have
   masked a dead broker before (quantos_health_signals_mask_dead_broker).

B. Darvas: read the latest plan (bars_as_of, entries with tags, position
   actions, failures) and the 09:45 execute log. Confirm: the plan was
   consumed exactly once (executed_on set), ZYDUSLIFE was entered in paper
   mode at a sane price (not below its stop), and each later scan is
   managing it -- trail/exit actions appear only when the rule says so.
   Show ~/.quantos/darvas_atr_stop_open_positions.json and the dry-run log.

C. Candidates 18/18b: run both gate scripts on the VM and report only what
   they print. Confirm the new sizing path runs: journal lines
   "Kelly sizing for ..." with the lot count and fallback note, and no
   "LOW CAPITAL WARNING". Count trades so far per variant and index.

D. Fyers rate limits: count "limit exceeded" / "request limit" lines per day
   across the ORB units since 09-21 in ONE journalctl pass. Baseline before
   the Darvas move: 3, 0, 2, 2, 5 (09-21..09-25). Did moving Darvas off 09:20
   help? Any day where a 429 cost an 18b exit record (look for "could not
   fetch exit quote")? That silently removes trades from 18b's gate data.

E. Report as one table per strategy: running? / trades so far / gate progress
   / earliest verdict date / anything abnormal. Then a short list of issues,
   most important first.

## 3. Known open issues (don't rediscover these -- decide whether to act)
1. ORB processes need retry/backoff on Fyers 429/-353 instead of losing the
   data point. Real code fix, affects 18b's evidence -- highest priority if
   rate-limit hits continue.
2. Rs70k per ORB strategy vs the capital-allocation research: half Kelly at
   Rs100k skipped 165/471 trades for cash, and Rs500k was the tier that
   cleared the ~Rs55k lockout cliff. The live code is risk-to-stop sizing,
   not the research's notional-fraction sizing, so reconcile the two before
   any real capital. Raise this with me; don't change it.
3. core/reference/calendar.py ends 2026-08-18 -> no job detects weekday NSE
   holidays. Re-running scripts/derive_nse_calendar.py extends it (past
   dates only).
4. Nifty 500 universe has 3 dead tickers (HEG, HFCL, JBCHEPHARM) that fail
   every scan -- rebuild from a fresh NSE CSV (scripts/build_universe.py).
5. The VM's agent/config.yaml is NOT in git. Backups: on the VM
   agent/config.yaml.bak-20260925*; on the laptop
   D:/Exodus_14_14/QuantOS/vm_config_backups/config.yaml.2026-09-26.
   Edit it the safe way: scp down -> edit -> diff -> back up on VM -> upload
   as .new -> yaml-parse -> mv. Refresh the laptop backup after any change.

## 4. If a review of the 09-24..09-26 work is needed
29 commits: `git log --oneline d976152^..9f0cb07`. Only three touch live
execution and are worth a real code review before any capital:
f619b43 (ORB halt-check + Kelly sizing), a72cdd5 (Darvas live executor),
ce71d0b (Darvas scan/execute split). The rest are research, docs or Pine.
Use /code-review on those three if we decide to.

## 5. Rules
- Deploy only with scripts/deploy-vm.ps1 (VM pulls from origin; push first).
- Commit and push results before reporting (feedback_commit_results_before_reporting).
- Update the memory files above in place rather than creating duplicates.
```
