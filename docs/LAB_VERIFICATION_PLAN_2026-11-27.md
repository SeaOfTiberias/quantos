# Strategy Lab: verifying old results (triage and method, 2026-11-27)

Most tested strategies saved only summary numbers, not their trades. This plan backs each result with data in two steps:

1. **Reproduce** the published result from the code as it was.
2. **Export** its trades into the Lab (`research/lab/trades/`).

## Method

1. Check out the result's commit into a separate git worktree. Main is never touched, and almost every script rewrites its own results doc when run.
2. Copy in the gitignored data the script reads.
3. Run the script unchanged.
4. Compare the regenerated results doc with the committed one (`git diff`):
   - **Reproduced exactly:** no diff.
   - **Reproduced with differences:** the diff and its cause are recorded (usually data refreshed since).
   - **Can't reproduce:** the reason is recorded (data gone, API limit).
5. Only then add a trade export, run from current code, and check its totals against the reproduced summary, so the Lab's trades are shown to belong to the published result.
6. Spot-check 3–5 trades per strategy against raw exchange prices.

Each registry entry gets a `verification` field shown on the Lab page.

**Pilot, 2026-11-27: ORB candidate 18** (`scripts/backtest_orb_time_convention.py` at d78cfd0, cached candles). The regenerated `docs/ORB_TIME_CONVENTION_RESULTS.md` is byte-identical to the committed one. **Reproduced exactly.**

## Triage (no re-runs except the pilot)

| Group | Strategies | What it needs |
|---|---|---|
| **A. Trades already on disk** | S7-3 Darvas (TradingView exports, 40 symbols in `backtest_results/`) | Convert only. |
| **B. Cached data, local re-run** | ORB 18 (done), trend-day filter, CCI/CPR (`data_cache/cci_cpr`), VRP strangle and IV-gated (F&O bhavcopy), vol skew and term structure, event proximity, expiry-day effect, earnings-gap drift, CCI/SMA cross, F&O indicator filter, SMC order block (1H) and bull put, Darvas ATR-stop OOS / re-entry / structural stop (equity bhavcopy), pairs v2, RS-momentum family (S8-3, S1, candidate 11), Alpha 50 rebuild, surge 23b | Re-run in a worktree; confirm each one's cache is complete when it runs. |
| **C. Needs Fyers data again (VM)** | Darvas box-width and trailing stop, EMT VWAP, goodnight scalper, Dow theory, pairs v1, vol spread, candle confirm, S8-4 EMA options | Daily history is deep and re-fetchable. Old intraday history may no longer be served (Fyers serves ~100 days per call); any that can't be fetched are marked "can't reproduce" with the reason. |
| **D. Nothing to verify** | MA cross and techno-funda (never run), E1 (pending), ORB 18b | 18b's protocol forbids looking at its P&L before its gate. |
| **E. No producing script found** | PCA stat-arb (code in `core/statarb`; how it was run is unclear) | Find the entry point first. |

## Order

1. Group A.
2. Group B, newest first.
3. Group C on the VM.

Results are committed as they land. The Lab shows each strategy's verification status.

Household data: `FyersBackTestResults/` (untracked) is a real broker tradebook. It is not research data and stays out of the Lab and git.

## Progress

| Date | Strategy | Outcome |
|---|---|---|
| 2026-11-27 | ORB candidate 18 | **Reproduced** byte for byte (d78cfd0). Trade export still to add. |
| 2026-11-27 | S7-3 Darvas | **Reproduced**, then **corrected**: a spot-check found the TradingView row-pairing bug in `core/backtest/parser.py` (fixed, 6050691). 729 trades instead of 690, PF 0.77 instead of 0.75; verdict unchanged. Trades in the Lab; 6 of 6 spot-checks match NSE prices after adjustment. |
| 2026-11-28 | CCI/CPR, CCI/SMA cross, F&O indicator filter | **Reproduced** byte for byte (8c2beb5, 89c8cf1, 6a5a51b). |
| 2026-11-28 | SMC order block 1H, SMC bull put | **Reproduced**: input files match their pinned SHA-256 hashes, and every table matches the doc (bull put: only typeset minus signs differ). |
| 2026-11-28 | Alpha 50 rebuild (both rounds) | **Reproduced**: every reported line identical. |
| 2026-11-28 | Trend-day filter, vol term structure, event proximity, surge 23b | **Reproduced** byte for byte (end dates pinned to the original runs). |
| 2026-11-28 | Vol skew | **Reproduced** byte for byte, but only with a helper module committed two days after the result: the published run used code not yet in git. |
| 2026-11-28 | VRP IV-gated | **Reproduced**: all generated figures identical; only hand-written commentary isn't regenerated. |
| 2026-11-28 | VRP strangle | **Reproduced** with the data that existed on the run date. With today's data one more cycle settles (expiry after the run): net PF 1.044, Sharpe 0.117. Verdict unchanged. |
| 2026-11-28 | Earnings-gap drift | **Reproduced** exactly on the original 2,586 sessions. 10 special weekend sessions added to the cache later shift the counts slightly; verdict unchanged. |
| 2026-11-28 | PCA stat-arb | **Reproduced with differences**: the script always runs to today. 2020-2025 rows identical, verdict unchanged. |
| 2026-11-28 | Expiry-day effect, pairs v1, pairs v2 | **Reproduced** byte for byte on the F&O files and sector lists as of their run dates. (Pairs fetches NSE sector constituents live when they aren't cached; FMCG membership changed since July.) |
| 2026-11-28 | Darvas ATR-stop OOS 2016-23 | **Reproduced**: recomputed from scratch at 67de055 (cache set aside) on the 2,586 equity sessions as of 2026-10-05. Every generated line identical: 991 trades, PF 1.46, +0.70% vs the equal-weight universe. Only the hand-written post-run notes aren't regenerated. 21 of 38 verified. |

Lessons for the remaining runs:
- Spot-check trades against exchange prices, not only totals: S7-3's totals reproduced while its pairing was wrong.
- Compare prices adjusted for corporate actions **up to the test date** (what the backtest saw).
- `data_cache/` has tracked files, so a worktree already has the folder: link each needed subfolder inside it (PowerShell `New-Item -ItemType Junction`), and check the link before trusting a run.
- Research scripts can silently skip missing inputs. The SMC pricing check printed "0 trades" instead of failing when its folder was absent. A missing input should stop the run; new scripts should assert their data.
- Several scripts print tables that were pasted into the doc. Compare printed output to the doc, not just `git diff`.
- Set `PYTHONIOENCODING=utf-8` (≥ and − signs crash a cp1252 console).
- Pin every date a script takes from "today" (end dates, rolling windows) to the original run's date.
- Data caches grow. When a re-run differs, rebuild the input as it stood on the run date (hard-link only the files older than the run) before calling it a difference.
- Special weekend sessions (Muhurat, Budget, DR drills) now sit in the equity cache. Any script that treats every file as a trading day picks them up. New tests should exclude them explicitly.
- Some scripts fetch reference data live (NSE sector constituents) when it isn't cached. Supply the cached copy as of the run date, or the universe silently changes.
