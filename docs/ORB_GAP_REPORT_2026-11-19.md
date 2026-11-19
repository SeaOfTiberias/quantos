# Stuck jobs, 2026-10-07 to 2026-11-19: what was lost

Execution plan E1 (`docs/EXECUTION_PLAN_2026-11-19.md`). Sessions and row counts only. **No P&L was read**: 18b's no-peeking rule allows a check that the log is accumulating (row count, no malformed lines) and nothing more.

## What happened

On 2026-10-07 at about 14:30 IST, several oneshot units hung on a Fyers socket read that had no timeout. A oneshot unit with no `TimeoutStartSec` waits forever, and its timer can't start it again:

| Unit | Stuck from | Freed | Sessions lost |
|---|---|---|---|
| ORB 18 (`quantos-orb-scalping-live`) | 2026-10-07 ~14:30 IST | 2026-11-17 23:53 IST (cf1c518 timeouts) | 27 |
| ORB 18b (`quantos-orb-scalping-filtered-live`) | 2026-10-07 14:35 IST | 2026-11-17 23:53 IST | 27 |
| Stop-out probe (`quantos-orb-stopout-probe`) | 2026-10-07 | 2026-11-17 23:53 IST | 27 |
| Option-chain recorder | 2026-10-07 14:33 IST | **still stuck on 2026-11-19 09:30 IST**; no timeout until this session | 28 so far (10-08 to 11-19) |

**Sessions lost:** the trading sessions from 2026-10-08 to 2026-11-17, from the L1 store's bhavcopy dates (the derived NSE calendar ends on 2026-08-18; see below). There were 27. The 10-07 session itself was recorded: the units hung after it.

**Evidence that the logs stopped and restarted:**
- 18's trade log has entries up to 10-07, then 11-18.
- The premium trace has 10-01, 10-06 and 10-07, then 11-18.
- The recorder's last folder is `option_chains/2026-10-07`.

**Why nothing alerted:** `cloud/api/job_health.py`, the cockpit's health panel, watches four jobs (shortlist, paper momentum, rotation pilot, spread probe). It judges them by when they last fired, not by whether a run is stuck. ORB 18/18b, the probe, the recorder and Darvas were not watched at all. The E1 watchdog (`core/ops/watchdog.py`) covers every enabled `quantos-*` timer and the two always-on services.

## 18b: where its gate stands

The pre-registered rule (`docs/ORB_ENTRY_FILTER_METHODOLOGY.md`): **N ≥ 20 new filtered entries per index AND at least 8 calendar weeks** since the flag went on (2026-09-22). The descriptive ₹50,000 equity figure was due "strictly as of 2026-11-17".

**As of 2026-11-19:**
- 18b's log has **6 entry rows: 4 BANKNIFTY, 2 NIFTY**, with no malformed lines.
- They come from **11 recorded sessions** (09-22 to 10-07). The sessions since 11-18 count from there.

**What the gap does to the rule:**
- The **8-week clause** was met on the calendar on 11-17, but 27 of the roughly 40 sessions in those weeks were never recorded. Calendar time no longer means what the rule meant: that much live trading.
- The **N ≥ 20 per index clause** is unaffected in kind, since it counts entries. At the rate seen so far (2 NIFTY entries in 11 sessions) NIFTY needs on the order of 100 more sessions. That's a rough figure from a small count, not a forecast.
- The **11-17 equity figure** would describe 11 sessions, not 8 weeks.

**Proposed amendment (needs the user's OK, because it changes a pre-registered rule):**
- Read "8 calendar weeks" as **40 recorded sessions**. That is about the number of NSE sessions in 8 weeks, and today it means about **2026-12-30**, assuming 11-24 and 12-25 are holidays (the calendar is stale).
- Move the descriptive equity figure to the same point.
- N ≥ 20 per index stays as written and will bind later.
- Proposed before any P&L was read, and for missing data only, so it is not a "stop when favourable" move.

**Candidate 18 and the stop-out probe** lost the same 27 sessions. Their own gates (stop-out probe 4 weeks with an N gate; 18's capital allocation) should be read the same way: count recorded sessions, not calendar weeks.

## Also found

- **The derived NSE trading calendar ends on 2026-08-18** (`core/reference/calendar.py` raises `DateOutOfRange` after it). `job_health.py` and `run_screen_snapshot.py` catch this and fall back; the watchdog now does too and reports it once a day as a CALENDAR fault. **Fix:** re-run `scripts/derive_nse_calendar.py`. Not done in E1.
- **Five units had no start timeout** (option-chain recorder, momentum shortlist, paper momentum, goodnight probe, ORB spread probe). E1 gives each one, with the reason in the unit file.
