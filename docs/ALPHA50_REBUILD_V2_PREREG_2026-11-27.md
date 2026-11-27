# NIFTY Alpha 50 rebuild, round 2: market-cap universe (pre-registration, 2026-11-27)

**Status: signed off by the user 2026-11-27**, before any code for it exists and before any run. All 12 AMFI lists were on hand at sign-off. Research only: trading is paused, nothing live changes, whatever the result.

## Why a round 2

Round 1 (prereg 0a01741 + amendment d7434c6, result 5595816, `docs/ALPHA50_REBUILD_RESULTS_2026-11-27.md`) **failed** its tracking gate: daily-return correlation 0.944 (≥ 0.90 held) but CAGR +3.35 pp over the index (limit 3.0). That result stands and is not revised.

The diagnosed cause was the universe: round 1 ranked stocks by traded value alone because we had no market-cap history. A check made on 2026-11-27 (eligibility only, no returns) at the 2019-02-28 cut-off found **63 of 278** turnover-eligible stocks outside AMFI's top 300 by average market cap (HDIL rank 777, DREDGECORP 740, JPASSOCIAT, RCOM, JETAIRWAYS, PCJEWELLER, GOACARBON...). NSE's universe is built on market cap and turnover; ours ignored market cap.

This round changes **one thing**, the universe rule, using real market-cap history. Because the change was chosen after seeing round 1 fail, the tracking gate is kept **exactly** as it was (≥ 0.90 correlation, CAGR within 3.0 pp, same window). It is not relaxed, and if this round fails too, the rebuild is closed, not tried a third time with another universe.

## Data

- Everything in round 1's Data section and amendment 1 is unchanged (bhavcopies from 2015-01-01, loaders of `scripts/backtest_darvas_atr_stop_oos.py`, price returns, Fyers index history).
- **New: AMFI half-yearly lists** of average market capitalisation of listed companies (the lists behind SEBI's large/mid/small-cap categorisation): each company's 6-month average total market cap (₹ cr), averaged across BSE, NSE and MSEI, ranked, with ISIN and exchange symbols. Public files from amfiindia.com, kept in `data_cache/amfi_mcap/` (gitignored), parsed to CSV.
- Lists needed: Jul–Dec 2017 through Jan–Jun 2023 (12 lists; Jul–Dec 2023 is not used by any review in the window). **The run waits until all of them are on hand.** There is no fallback to an older list for a missing half-year.
- Known gap, stated up front: AMFI gives **total** market cap, not free-float. Promoter-heavy companies rank higher here than in NSE's free-float ranking.

## The one change: universe rule

At each review cut-off (end Feb/May/Aug/Nov, as in round 1):

1. **Which list:** the latest AMFI list whose period ended at least one full month before the cut-off: Feb and May cut-offs use the Jul–Dec list of the year before, Aug and Nov cut-offs use the Jan–Jun list of the same year. (AMFI publishes in the first week of January and July, so each list was public before the cut-off that uses it.)
2. **Universe:** the **300 highest-ranked** companies on that list (AMFI's own rank, by the average across exchanges) that have bars in our NSE EQ data. A company is matched to our data by its NSE symbol as printed on the list; a listed company with no match is skipped and the next rank fills in. Unmatched names in the top 300 are reported per review.
3. Then round 1's rules, unchanged: bars from at least one year before the cut-off and on **every** session of the year to the cut-off (100% trading frequency). Stocks failing these drop out; they are **not** replaced.

The traded-value ranking of round 1 is not used. Everything after the universe (alpha, buffer selection, alpha weights, effective dates, delistings, costs) is round 1's base version, unchanged.

## Step 1: tracking check (gate) — unchanged

The base version, **before costs**, against the NIFTY Alpha 50 price index over **2018-03-14 to 2023-12-29**:

- correlation of daily returns **≥ 0.90**, and
- CAGR within **3.0 percentage points**.

If either fails: reported as a failed rebuild, the test stops, no step 2, and the Alpha 50 rebuild line is closed.

## Step 2 — unchanged

If step 1 passes, round 1's step 2 runs once as pre-registered there (12 versions: skip 1–2 × lookback 9–12 × market filter none/150/200; median version scored on Sharpe vs the base; all five pass criteria), with this round's universe. Its measurement window is round 1's (2017-03-31 to 2023-12-29) **except** that it starts with the first review that has an AMFI list, i.e. cut-off 2018-02-28, effective from the close of the March 2018 expiry. All windows inside step 2 that started 2017-03-31 start there instead; the halves split stays at 2020-06-30; the walk-forward's first chosen year stays 2019 (fit on data to the end of 2018).

## Before the full run

Shown to the user, mechanics only:
- for the first review (cut-off 2018-02-28): universe size after the listing/frequency rules, unmatched top-300 names, and how many round-1 universe stocks are dropped;
- the same overlap count for every review (a table, no returns);
- the parser's row counts per AMFI file against each file's last rank.

Then step 1 runs once.
