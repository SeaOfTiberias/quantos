---
title: Strategy Search
compiled: 2026-10-13
tags:
  - wiki/concept
  - strategy/index
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-13-quantos-full-project-state-for-external-review, 2026-10-13-strategy-status-snapshot-2026-10-13
---

# Strategy Search

> [!abstract] Compiled page
> Hub for every strategy this project has tested or run. First compiled 2026-09-17; rewritten 2026-10-13 from `[[2026-10-13-quantos-full-project-state-for-external-review]]` and `[[2026-10-13-strategy-status-snapshot-2026-10-13]]`. Context and retrieval only — nothing here executes, and nothing here is a claim that any strategy works.

## How the record is kept

Each strategy has one page tagged `wiki/strategy` with fixed record properties (status, verdict, family, instrument, dates, headline numbers, next gate), defined in SCHEMA.md under "Strategy records". The pages hold the evidence and its citations. Two views read the properties:

- **Live table in Obsidian**: [[Strategy Register.base]], embedded below. It has four views: all strategies, running now, by family, passed or open.
- **Generated report**: `python scripts/vault.py report` writes a dated register to `wiki/reports/`, with filters such as `--live`, `--verdict`, `--family` and `--since`. The first one is [[strategy-register-2026-10-13]].

![[Strategy Register.base]]

## The state of the search, plainly (2026-10-13)

- **No strategy has traded real capital** `[[2026-10-13-strategy-status-snapshot-2026-10-13]]`.
- **One systematic strategy is running on paper with a passing verdict**: [[darvas-atr-stop-bucket-b]], ₹5L paper since 2026-10-08. Real capital waits on the user's explicit go-ahead.
- **One is running on paper without a verdict**: [[momentum-turnover-candidate-11]], a quarterly walk-forward that needs 4 out-of-sample quarters.
- **Two discretionary aids are running**, neither placing orders: [[trade-watcher]] and [[fno-screener]].
- **Switched off**: [[orb-options-scalping-candidate-18]], the first candidate ever to pass, failed on 2026-09-30 once option premiums were priced with a convention calibrated to real quotes. [[orb-entry-filter-candidate-18b]] stopped with it. The weekly [[rs-momentum-rotation-s8-3]] dry run and its pilot were switched off on 2026-10-12.

`[[2026-10-13-strategy-status-snapshot-2026-10-13]]`

## Lines of inquiry closed for good

| Line | Pages | Why it is closed |
|---|---|---|
| Conditioning on volatility or regime state | [[regime-classifier-s8-1]], [[iv-minus-rv-vol-spread]], [[nifty-banknifty-option-skew]], [[atm-iv-term-structure]], [[event-proximity-vol]], plus [[vrp-iv-gated-short-premium]] | Five-for-five failures led the project to close the line explicitly `[[2026-10-13-quantos-full-project-state-for-external-review]]`. The sixth, an IV gate on premium selling, failed on fresh data because high IV leads into crashes |
| Mean reversion on NSE stock futures | [[pairs-trading-candidate-12]], [[pairs-trading-v2-candidate-17]], [[statarb-residual-mean-reversion]] | Stock-vs-stock and stock-vs-family both failed. Strays are mostly lasting re-ratings, and costs swamp a gross edge near zero |
| Intraday index signals | [[orb-options-scalping-candidate-18]], [[orb-entry-filter-candidate-18b]], [[trend-day-filter-candidate-21]], [[ema8-second-trade]], [[breakout-1010-banknifty-candidate-15]], [[candle-confirm-momentum-gutcheck-candidate-19]], [[goodnight-scalper-candidate-20]] | Measured in index points with futures costs, the gross edge is a few points a trade against a round-trip cost of similar size |

## The process lesson recorded by the project

The cheap screen (pooled per-trade profit factor > 1 and Sharpe > 0.5) correctly killed most candidates early. But nothing required [[capital-readiness-validation]] the moment a candidate passed, and the screen's Sharpe used a wrong, hard-coded annualisation until 2026-09-24 `[[2026-10-13-quantos-full-project-state-for-external-review]]`. [[darvas-atr-stop-bucket-b]] is the first candidate to go through all three later steps before going live on paper: capital readiness, a falsification pass and an out-of-sample test.
