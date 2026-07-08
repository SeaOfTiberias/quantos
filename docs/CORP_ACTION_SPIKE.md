# S5-3 Spike — Is the broker's daily OHLC split-adjusted?

**Status:** ✅ **RESOLVED 2026-07-08 — broker daily OHLC is SPLIT-ADJUSTED.** Conditional 5-pt adjusted-store work is **not needed** (dropped).
**Backlog item:** S5-3 (P1-8), `docs/SPRINT4_BACKLOG.md`.
**Tool:** [`agent/spike_corp_action.py`](../agent/spike_corp_action.py) (read-only market-data reads).
**Verified against:** Fyers (`BrokerAdapter.get_historical_data`, `"1d"`), account BRIDGET PRIYA JOHN, run 2026-07-08.

## Why this matters

The Darvas pipeline (box detection, ATR stops, RR sizing in `core/darvas/*`,
`core/regime/*`) assumes a **continuous** price series. A stock split or bonus
issue rebases the traded price overnight by the split factor. If the broker's
historical feed returns **raw, unadjusted** prices, that rebase appears as an
artificial gap that:

- blows a Darvas box wide open (fake breakout **or** breakdown on the ex-date),
- corrupts every ATR computed across the split boundary, hence stop distances
  and position sizes,
- silently — nothing errors; the numbers are just wrong.

So before building anything, we verify empirically whether
`BrokerAdapter.get_historical_data(..., "1d", ...)` is already adjusted.

## Method

Fetch daily candles straddling a **known** corporate action and compare the
last close *before* the ex-date to the first open *on/after* it:

```
boundary_ratio = pre_split_close / post_split_open
```

| boundary_ratio | interpretation |
|---|---|
| ≈ split factor (e.g. ~10) | **UNADJUSTED** — raw as-traded; the split is an artificial gap |
| ≈ 1.0 | **ADJUSTED** — history is back-scaled; the series is continuous |

Default test case: **NESTLEIND**, 1:10 face-value split, ex-date **2024-01-05**.
A 10× factor cannot be confused with a real one-day price move. (Nestlé traded
around ₹27,000 pre-split and ~₹2,700 post-split.)

## How to run (reproduction)

The daily-history fetch is non-interactive, but the Fyers access token expires
daily. Refresh it first (this opens a browser OAuth flow — run it in your own
terminal), then run the spike:

```bash
# 1. Refresh the Fyers token (interactive OAuth in a browser)
python agent/auth/fyers_auth.py --config agent/config.yaml

# 2. Run the spike (read-only)
python agent/spike_corp_action.py
```

Test a different / more recent action if you prefer:

```bash
python agent/spike_corp_action.py --symbol IRCTC --ex-date 2021-10-28 --factor 5
```

The script prints the candle table around the ex-date, the boundary ratio, and
a one-line VERDICT (ADJUSTED / UNADJUSTED / INCONCLUSIVE).

## Verdict — ADJUSTED

Two independent known splits, run 2026-07-08 against live Fyers daily history.
In both, the price series is **continuous across the ex-date** — no
split-factor gap — so the feed is already corporate-action adjusted.

| symbol | split | ex-date | last close before | first open on/after | boundary ratio | verdict |
|---|---|---|---|---|---|---|
| NESTLEIND | 1:10 | 2024-01-05 | 1355.82 | 1377.00 | **0.985** | ADJUSTED |
| IRCTC | 1:5 | 2021-10-28 | 826.03 | 817.00 | **1.011** | ADJUSTED |

An *unadjusted* feed would have shown ratios of ≈10 and ≈5 respectively (a
90% / 80% artificial overnight drop on the ex-date). Both landed at ≈1.0 —
a 10× / 5× discriminator, so the result is unambiguous.

NESTLEIND candle table around the split (note the smooth 2024-01-04 close
1355.82 → 2024-01-05 open 1377.00, exactly where a raw feed would gap to ~136):

```
date                open        high         low       close        volume
2023-12-29       1312.50     1332.50     1307.28     1329.02     2,068,160
2024-01-01       1332.50     1372.26     1332.00     1368.62     2,632,200
2024-01-02       1375.00     1384.65     1351.21     1361.16     2,831,540
2024-01-03       1367.25     1370.87     1328.65     1331.76     2,026,920
2024-01-04       1342.55     1357.51     1332.61     1355.82     2,647,800
2024-01-05       1377.00     1377.00     1321.23     1333.20     5,154,128  <== ex-date
2024-01-08       1341.50     1344.50     1305.50     1309.65     2,064,756
2024-01-09       1320.00     1320.15     1293.47     1296.30     1,626,054
```

### Decision

**Fyers already back-adjusts, so drop the conditional 5-pt adjusted-OHLC store**
(DuckDB+parquet). The Stage A/B fetch path needs no change — splits and bonuses
in the scan universe will not fabricate Darvas breakouts or corrupt ATR/stops.

(Had the verdict been UNADJUSTED, the conditional half of S5-3 would have been
warranted: build the adjusted store, or as a stopgap exclude symbols with a
corporate action inside the box lookback window.)

## Caveats / notes

- **Level, not just gap:** the adjusted 2024-01-04 close shows as ~₹1,356, below
  the pure split-only level (~₹2,700). Fyers appears to apply *continuous*
  back-adjustment (folding in later actions/dividends) so the historical series
  is scaled to line up with the current price. That's fine — and ideal — for the
  pipeline, which works on **relative** levels within a lookback window (box
  widths, ATR, RR), never absolute rupee prices. Only the continuity across the
  ex-date matters, and it holds.
- **History depth:** IRCTC 2021 data returned fine, so Fyers daily history reaches
  back **at least ~4.5 years** — comfortably more than any Darvas lookback needs.
- **Scope:** verified for NSE **equity** daily candles. Not tested for indices or
  intraday resolutions (the pipeline's corp-action exposure is entirely in the
  daily equity path, so that's the relevant surface).
- **Reproduce:** `python agent/spike_corp_action.py` (Nestlé) or
  `python agent/spike_corp_action.py --symbol IRCTC --ex-date 2021-10-28 --factor 5`.
  Needs a fresh Fyers token (see below).

## Notes

- The spike deliberately tests the *broker feed the pipeline actually uses*
  (Fyers via `get_historical_data`), not a third-party source like yfinance —
  a different feed would answer a different question.
- `core/brokers/fyers.py` passes `cont_flag: "1"` to the Fyers history endpoint;
  that flag governs continuous **futures** stitching, not equity corp-action
  adjustment, so it does not pre-answer this question.
