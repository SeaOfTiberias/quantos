# NIFTY Alpha 50 rebuild, round 2 (AMFI market-cap universe): results, 2026-11-27

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


## Next

Step 2 (12-version grid, prereg 0a01741, window from the March 2018 expiry) runs once, as pre-registered. Its code is not yet written; worked cases come first.
