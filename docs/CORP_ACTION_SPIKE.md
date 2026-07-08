# S5-3 Spike — Is the broker's daily OHLC split-adjusted?

**Status:** ⏳ Tooling ready — **verdict PENDING one live run** (needs a fresh Fyers token).
**Backlog item:** S5-3 (P1-8), `docs/SPRINT4_BACKLOG.md`.
**Tool:** [`agent/spike_corp_action.py`](../agent/spike_corp_action.py) (read-only market-data reads).

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

## Verdict

> _Pending the live run above. Paste the script's output here (the candle table +
> boundary analysis) as the evidence, and record the verdict._

**Boundary evidence (fill in after the run):**

| field | value |
|---|---|
| symbol / ex-date / factor | NESTLEIND / 2024-01-05 / 10 |
| last close before ex-date | `____` |
| first open on/after ex-date | `____` |
| boundary ratio | `____` |
| **verdict** | `ADJUSTED` / `UNADJUSTED` |

### Decision (drives the conditional 5 pts)

- **If UNADJUSTED** → the conditional half of S5-3 is warranted: build the
  DuckDB + parquet adjusted-OHLC store (with adjustment factors) and route the
  Stage A/B fetch path through it. Until then, splits in the scan universe are a
  live hazard — a mitigation stopgap is to exclude symbols with a corporate
  action inside the box lookback window.
- **If ADJUSTED** → the broker already does the work; **drop the conditional
  5 pts** and note that the fetch path needs no change.

## Notes

- The spike deliberately tests the *broker feed the pipeline actually uses*
  (Fyers via `get_historical_data`), not a third-party source like yfinance —
  a different feed would answer a different question.
- `core/brokers/fyers.py` passes `cont_flag: "1"` to the Fyers history endpoint;
  that flag governs continuous **futures** stitching, not equity corp-action
  adjustment, so it does not pre-answer this question.
