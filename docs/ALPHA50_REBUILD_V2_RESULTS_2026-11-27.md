# NIFTY Alpha 50 rebuild, round 2 (AMFI market-cap universe): results, 2026-11-27

**Verdict: step 1 PASS, step 2 FAIL (0 of 5 criteria).** Neither change (skip-month alpha, NIFTY 500 SMA filter) beats the index rules on risk-adjusted return. Reported as failed; not re-tuned. The Alpha 50 rebuild line is closed for these changes.

Pre-registration: `docs/ALPHA50_REBUILD_V2_PREREG_2026-11-27.md` (cf85c05, amendment 1 in bbf81d8, both before any run). Code: `scripts/backtest_alpha50.py --universe amfi`, parser `scripts/parse_amfi_mcap.py`. Research only; trading stays paused.

## Step 1: tracking check — PASS

Base version (index rules, AMFI top-300 universe), before costs, vs the NIFTY Alpha 50 price index, 2018-03-28 to 2023-12-29, 1,420 daily returns:

| Measure | Result | Gate |
|---|---|---|
| Correlation of daily returns | 0.944 | ≥ 0.90 |
| CAGR rebuild vs index | +25.35% vs +23.50% = **+1.86 pp** | within 3.0 pp |

Largest single-stock weight per review: 3.4% to 8.2%.

### Read with care

- The window starts 2018-03-28 (amendment 1: the rebuild holds nothing before the March 2018 expiry close). Round 1's window started 2018-03-14, where the index CAGR was 22.40%; the index fell between the two dates, which is part of why the gap is smaller. Against that earlier index figure the rebuild's 25.35% would be +2.95 pp, still inside 3.0 but only just. That comparison is not like-for-like (the rebuild didn't exist on 03-14) and is not the gate; it is reported so the margin isn't overstated.
- The rebuild's universe change itself moved its CAGR only from 25.75% (round 1) to 25.35%; correlation is unchanged at 0.944. The rebuild still runs ~1.9 pp a year above the index, before costs.
- Total (not free-float) market cap, as stated in the prereg.

## Mechanics (no returns)

Unmatched top-300 names (skipped, next rank filled): 2020H2 BAJAJAUTO, MCDOWELLN, NAMINDIA (AMFI printed these without NSE's hyphens: BAJAJ-AUTO, MCDOWELL-N, NAM-INDIA); 2022H2 PATANJALI; 2023H1 PATANJALI, LLOYDSME. Per the rule they are skipped, not corrected by hand.

## AMFI lists (parser rows vs last rank)

| List | Rows | Last rank | Rank-300 NSE symbol |
|---|---|---|---|
| 2017H2 | 3452 | 3452 | SYNDIBANK |
| 2018H1 | 5054 | 5077 | VIJAYABANK |
| 2018H2 | 4895 | 4895 | CHAMBLFERT |
| 2019H1 | 4955 | 4955 | DELTACORP |
| 2019H2 | 4992 | 4992 | FINCABLES |
| 2020H1 | 5004 | 5004 | CANFINHOME |
| 2020H2 | 5019 | 5019 | SYMPHONY |
| 2021H1 | 5059 | 5059 | CGPOWER |
| 2021H2 | 5083 | 5083 | LUXIND |
| 2022H1 | 5041 | 5041 | TTKPRESTIG |
| 2022H2 | 5072 | 5072 | MEDANTA |
| 2023H1 | 5062 | 5063 | RHIM |

## Per review

| Cut-off | List | Top-300 matched | Unmatched skipped | Eligible (round 2) | Eligible (round 1) | In both | Round-1 names dropped |
|---|---|---|---|---|---|---|---|
| 2018-02-28 | 2017H2 | 300 | 0 | 279 | 272 | 196 | 76 |
| 2018-05-31 | 2017H2 | 300 | 0 | 281 | 277 | 199 | 78 |
| 2018-08-31 | 2018H1 | 300 | 0 | 279 | 276 | 202 | 74 |
| 2018-11-30 | 2018H1 | 300 | 0 | 286 | 282 | 210 | 72 |
| 2019-02-28 | 2018H2 | 300 | 0 | 290 | 278 | 215 | 63 |
| 2019-05-31 | 2018H2 | 300 | 0 | 290 | 280 | 218 | 62 |
| 2019-08-30 | 2019H1 | 300 | 0 | 286 | 276 | 213 | 63 |
| 2019-11-29 | 2019H1 | 300 | 0 | 288 | 281 | 219 | 62 |
| 2020-02-28 | 2019H2 | 300 | 0 | 284 | 280 | 213 | 67 |
| 2020-05-29 | 2019H2 | 300 | 0 | 280 | 282 | 217 | 65 |
| 2020-08-31 | 2020H1 | 300 | 0 | 287 | 286 | 215 | 71 |
| 2020-11-27 | 2020H1 | 300 | 0 | 287 | 274 | 203 | 71 |
| 2021-02-26 | 2020H2 | 300 | 3 | 283 | 264 | 206 | 58 |
| 2021-05-31 | 2020H2 | 300 | 3 | 288 | 262 | 203 | 59 |
| 2021-08-31 | 2021H1 | 300 | 0 | 276 | 248 | 192 | 56 |
| 2021-11-30 | 2021H1 | 300 | 0 | 282 | 245 | 192 | 53 |
| 2022-02-28 | 2021H2 | 300 | 0 | 271 | 250 | 199 | 51 |
| 2022-05-31 | 2021H2 | 300 | 0 | 268 | 250 | 193 | 57 |
| 2022-08-30 | 2022H1 | 300 | 0 | 266 | 252 | 192 | 60 |
| 2022-11-30 | 2022H1 | 300 | 0 | 276 | 260 | 201 | 59 |
| 2023-02-28 | 2022H2 | 300 | 1 | 279 | 273 | 202 | 71 |
| 2023-05-31 | 2022H2 | 300 | 1 | 288 | 286 | 209 | 77 |
| 2023-08-31 | 2023H1 | 300 | 2 | 288 | 282 | 206 | 76 |
| 2023-11-30 | 2023H1 | 300 | 2 | 289 | 283 | 201 | 82 |

## First review, cut-off 2018-02-28

Unmatched top-300 names skipped (0): none.

Failed the listing/frequency rules, not replaced (21): HDFCLIFE, GICRE, SBILIFE, DMART, NIACL, ABCAPITAL, ICICIGI, FRETAIL, IIFL, SUNDARMFIN, AUBANK, RNAM, KIOCL, HUDCO, TIFIN, GODREJAGRO, ERIS, SPICEJET, SCHAEFFLER, ADVANTA, COCHINSHIP.

Round-1 names dropped (76): 8KMILES, ABAN, ALBK, ANDHRABANK, APTECHT, BAJAJELEC, BALRAMCHIN, BEPL, BFUTILITIE, BOMDYEING, CHENNPETRO, CYIENT, DCBBANK, DELTACORP, DREDGECORP, EQUITAS, FSL, GHCL, GITANJALI, GNFC, GRANULES, GSFC, HCC, HCL-INSYS, HDIL, HEG, HFCL, HINDOILEXP, HSCL, ICIL, IFCI, INDIACEM, INDIAGLYCO, ITI, JAICORPLTD, JETAIRWAYS, JINDALSAW, JISLJALEQS, JKTYRE, JPASSOCIAT, JUSTDIAL, KIRIINDUS, KPIT, KSCL, KTKBANK, MCX, MEGH, MOIL, NCC, NIITTECH, NOCIL, ORIENTBANK, PHILIPCARB, PRAJIND, PTC, PVR, RADICO, RAYMOND, RCF, RCOM, RELIGARE, RIIL, SAREGAMA, SOBHA, SOUTHBANK, SREINFRA, TATAELXSI, TATAMTRDVR, TATASPONGE, TFCILTD, TINPLATE, TIRUMALCHM, TWL, UJJIVAN, UNITECH, VENKEYS.


## Step 2: the grid — FAIL (code 59d218c, run once)


Window 2018-03-28 to 2023-12-29, net of costs at 36.1 bps per side.

## Pass criteria

- 1 better risk-adjusted (Sharpe above base, bootstrap >= 90%): **FAIL**
- 2 smaller max drawdown: **FAIL**
- 3 breadth: >= 9 of 12 above base: **FAIL**
- 4 both halves above base: **FAIL**
- 5 walk-forward above base 2019-23: **FAIL**

**Step 2 FAIL**

Median version (6th of 12 by Sharpe): **skip 2m, 9m, no filter**, Sharpe 1.097 vs base 1.242; bootstrap share 3.9% (need >= 90%); max drawdown -40.7% vs base -38.7%; 2 of 12 above the base.

| Half | Median | Base |
|---|---|---|
| 2018-03-28 to 2020-06-30 | 0.035 | 0.297 |
| 2020-07-01 to 2023-12-29 | 1.947 | 1.996 |

Walk-forward 2019-23: stitched Sharpe 1.348 vs base 1.429. Choices: 2019 skip 1m, 12m, no filter; 2020 skip 1m, 9m, no filter; 2021 skip 1m, 9m, no filter; 2022 skip 2m, 9m, SMA200; 2023 skip 1m, 9m, no filter.

## All versions (reported, not scored)

| Version | CAGR | Sharpe | Max DD | Time in cash | Turnover/yr | Sold < 1 yr (short-term tax) |
|---|---|---|---|---|---|---|
| base (index rules) | +24.12% | 1.24 | -38.7% | 0% | 2.80x | 81% |
| skip 1m, 9m, no filter | +25.43% | 1.29 | -38.0% | 0% | 3.32x | 89% |
| skip 1m, 9m, SMA150 | +17.66% | 1.24 | -19.5% | 34% | 4.44x | 98% |
| skip 1m, 12m, no filter | +23.28% | 1.20 | -38.9% | 0% | 2.89x | 83% |
| skip 1m, 12m, SMA150 | +15.84% | 1.16 | -21.2% | 34% | 4.14x | 97% |
| skip 2m, 9m, SMA150 | +15.74% | 1.14 | -22.6% | 34% | 4.54x | 98% |
| skip 1m, 9m, SMA200 | +16.46% | 1.12 | -24.1% | 29% | 4.85x | 98% |
| skip 2m, 9m, no filter ← median | +21.17% | 1.10 | -40.7% | 0% | 3.51x | 90% |
| skip 1m, 12m, SMA200 | +14.52% | 1.03 | -23.4% | 29% | 4.56x | 97% |
| skip 2m, 12m, no filter | +17.43% | 0.94 | -42.8% | 0% | 3.04x | 86% |
| skip 2m, 9m, SMA200 | +13.24% | 0.94 | -26.0% | 29% | 4.97x | 98% |
| skip 2m, 12m, SMA150 | +11.24% | 0.87 | -29.3% | 34% | 4.30x | 97% |
| skip 2m, 12m, SMA200 | +9.70% | 0.73 | -29.2% | 29% | 4.70x | 97% |

## Median and base vs the indices (2018-03-28 to 2023-12-29, price indices, ours net of costs)

| Series | CAGR | Sharpe | Max DD |
|---|---|---|---|
| median version | +21.17% | 1.10 | -40.7% |
| base | +24.12% | 1.24 | -38.7% |
| NIFTY Alpha 50 | +23.50% | 1.12 | -40.0% |
| NIFTY 500 | +14.50% | 0.87 | -38.3% |

## Per year (first year part-year)

| Year | Median | Base | Alpha 50 |
|---|---|---|---|
| 2018 | -7.0% | -2.3% | -2.9% |
| 2019 | +4.7% | +12.6% | +7.2% |
| 2020 | +38.8% | +39.4% | +51.8% |
| 2021 | +57.4% | +60.0% | +74.4% |
| 2022 | -6.3% | -7.5% | -14.2% |
| 2023 | +51.6% | +52.8% | +42.5% |

## Largest single-stock weight per review (median version)

2018-02-28: 5.6% 2018-05-31: 7.1% 2018-08-31: 8.0% 2018-11-30: 5.3% 2019-02-28: 6.2% 2019-05-31: 7.7% 2019-08-30: 5.5% 2019-11-29: 4.3% 2020-02-28: 8.7% 2020-05-29: 7.7% 2020-08-31: 8.3% 2020-11-27: 5.5% 2021-02-26: 5.1% 2021-05-31: 4.3% 2021-08-31: 4.2% 2021-11-30: 4.1% 2022-02-28: 4.5% 2022-05-31: 4.5% 2022-08-30: 4.0% 2022-11-30: 4.1% 2023-02-28: 4.8% 2023-05-31: 4.7% 2023-08-31: 7.0% 2023-11-30: 4.1%

2024-26 (newer price store, survivorship-biased): reported later from the VM, not part of the verdict.

## What this does and does not say

- The market filter **halved the worst fall** (about -20% to -29% against -39%) but gave up more return than it saved: every filtered version's Sharpe is at or below the base's, it is in cash about a third of the time (earning nothing, as pre-registered), and it trades ~1.5x more, nearly all short-term for tax. That trade-off is reported, not a pass: criterion 2 is judged on the median version, which is unfiltered.
- Skipping the latest month(s) of alpha does not help: only skip-1/9-month (Sharpe 1.29) and the 150-day filter on it (1.24, a tie) are at or above the base's 1.24, 2 of 12 versions.
- The base itself (the index rules, net of 36 bps per side) ran close to the real index: CAGR +24.1% vs +23.5%, Sharpe 1.24 vs 1.12. Buying the ETF gets this without the rebuild.
