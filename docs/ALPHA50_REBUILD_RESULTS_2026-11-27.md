# NIFTY Alpha 50 rebuild: results (2026-11-27)

Pre-registered in `docs/ALPHA50_REBUILD_PREREG_2026-11-27.md` (0a01741, amendment 1 d7434c6). Run once with `python scripts/backtest_alpha50.py --step1`.

## Step 1: tracking check (gate)

The base version (the index's own rules, turnover-ranked universe), before costs, against the NIFTY Alpha 50 price index, 2018-03-14 to 2023-12-29, 1,430 daily returns:

- Correlation of daily returns: **0.944** (need ≥ 0.90): holds.
- CAGR: rebuild **+25.75%** vs index **+22.40%**, a difference of **+3.35 pp** (need within 3.0): **FAILS**.

**Step 1 FAIL.** As pre-registered, the test stops here: step 2 (skip-month and market-filter grid) is **not run**, and this round is not re-tuned.

## Reading

- The rebuild moves with the index day to day, but over six years it compounded 3.35 points a year faster. The likely cause is the universe proxy. Without free-float market-cap history, the 300 were ranked on turnover alone, which lets heavily traded smaller companies in (review 1's top names included UPERGANGES, TIRUMALCHM, DWARKESH, KIRIINDUS). Smaller momentum names did well over 2020-23.
- The rebuild's higher CAGR is **not a result**. It is before costs, it was not the pre-registered question, and it comes from a universe that differs from the index's. It must not be read as "the rebuild beats Alpha 50".

## Next round (needs its own pre-registration)

Rebuild the universe with real market capitalisation (NSE's per-stock market-cap data, if its history back to 2016 can be obtained), then re-run step 1 and, only if it passes, step 2 as already specified.
