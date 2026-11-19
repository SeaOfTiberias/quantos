# Darvas Bucket B: go/no-go rule (frozen 2026-11-19)

Execution plan E2 (`docs/EXECUTION_PLAN_2026-11-19.md`). **Written before any paper return was read.** On the day: 5 closed paper trades and 3 open, counted as rows only. Their returns are read for the first time at the review this rule sets.

Standing rules apply: trading is paused, and capital, size and `dry_run` change only with the user's go-ahead. Passing this rule means the user is *offered* a pilot; nothing switches on by itself.

## 1. What the backtest says a short record looks like

From the frozen 2016-23 out-of-sample run (`docs/DARVAS_ATR_STOP_OOS_RESULTS.md`), rebuilt from its own results cache with its own trade assembly and Stressed costs. The rebuild reproduces it exactly: 991 trades, mean net +2.16%. Computed by `scripts/research/darvas_go_no_go_bands.py` and saved in `docs/DARVAS_GO_NO_GO_BANDS.json`.

The windows are runs of k consecutive trades in exit order (the order a paper record closes in). Drawdown is the largest fall of the running sum of net returns per trade, in % of one position.

| k trades | mean p05 | **mean p10** | mean p50 | windows with mean < 0 | dd p50 | **dd p90** | dd p95 | zero-edge copy fails the p10 check |
|---|---|---|---|---|---|---|---|---|
| 10 | −8.58% | −6.69% | +1.26% | 42% | 32.8% | 78.9% | 91.4% | 19% |
| 20 | −6.06% | **−4.73%** | +1.62% | 40% | 55.5% | **123.8%** | 138.7% | 23% |
| 30 | −5.39% | −4.43% | +1.79% | 35% | 74.3% | 159.5% | 175.6% | 19% |
| 60 | −4.92% | **−4.19%** | +2.76% | 28% | 119.0% | **278.0%** | 314.4% | 20% |

**What this means:**
- The trade distribution is lumpy: median trade −1.11%, 47.2% winners. The edge comes from a few large winners, clustered in good years (2017, 2020, 2021, 2023).
- **Even in the backtest, 40% of all 20-trade runs lose money.**
- A zero-edge system would fail the p10 check only about 20% of the time, at any length up to 60 trades.
- So **no paper record of realistic length can confirm or refute the edge from its P&L.** The P&L check below is a tripwire for a broken system, not evidence of an edge. The evidence for the edge is still the OOS backtest only: a PASS, with the excess-return CI just above zero (+0.03% .. +1.36%).
- An independent (iid) bootstrap would give much tighter bands (20 trades: p10 −1.79%, dd p90 77.2%). It ignores how losing trades cluster in bad markets, so it is not used.

What a paper record *can* show is whether **live trading reproduces the backtest's mechanics**. Most of the rule is about that.

## 2. How a paper trade is scored

From `~/.quantos/darvas_atr_stop_dry_run_trades.jsonl` (`core/darvas_atr_stop/dry_run_log.py`):
- **Entry:** `entry_price` (the sizing-time price, as logged).
- **Exit:** `exit_ltp` (the real quote at exit) when present; otherwise `boundary_price` (the stop or target level), counted and labelled.
- **Net return:** after the backtest's Stressed costs (`STRESSED_COST_MODEL`: STT, exchange, SEBI, stamp, GST, 25 bps slippage) with `net_return` from `scripts/backtest_darvas_atr_stop_oos.py`, at ₹1,00,000 per trade as in the backtest. The paper's own size doesn't enter.
- **Order:** trades are taken in exit order. Open trades don't count.

## 3. The rule

**When:** at the **20th closed paper trade**, counting from the first (ZYDUSLIFE, entered 2026-09-28). At about 0.7 closed trades a week so far, that's around April 2027. Before then, only counts are reported.

### Health: does live reproduce the backtest? (all must hold)

| | Check | Pass |
|---|---|---|
| H1 | Every Darvas scan, pre-open and execute ran | No watchdog STUCK / FAILED / MISSED fault on the three Darvas units on any session from 2026-11-19 (E1). Before that date: the journal shows each session's runs, or the gap is declared |
| H2 | Every paper trade is a Bucket B trade | box width in (35%, 50%] on every row |
| H3 | Exit quotes are captured | `exit_ltp` present on ≥ 90% of closed trades |
| H4 | Exits cost no more than the backtest assumed | median adverse slip at exit, (boundary − exit_ltp) / boundary for stops (mirrored for targets), ≤ 25 bps |
| H5 | The frozen rules find the same trades | the backtest's `find_atr_trades` run over the paper window on the L1 store reproduces ≥ 90% of paper entries (same symbol, entry within one session), and the paper took ≥ 90% of the replay's Bucket B entries in the executor's universe. Every miss either way is listed with its cause |

H5 needs a replay script, built at the review. It is the most important check: it answers whether the system being paper-traded is the system that was tested.

### Tripwire: is it broken? (both must hold, at 20 closed trades)

| | Check | Pass |
|---|---|---|
| C1 | Mean net return per trade | ≥ **−4.73%** (backtest 20-trade p10) |
| C2 | Largest fall of the running sum | ≤ **123.8%** of one position (backtest 20-trade p90) |

## 4. Outcomes

| Result | What happens |
|---|---|
| Any H fails | Fix the cause, declare it in this file, restart the count from the fix. Trades before it are reported, not counted |
| H pass, C fails | **Fail.** Darvas returns to research and stays paper-only. Reported as a fail, not re-tuned |
| H pass, C pass | The user is **offered** a small real-money pilot. The size is the user's call, made knowing the edge rests on the backtest alone. The pilot is then re-checked at **60 closed trades** (paper and pilot together): C1 ≥ **−4.19%**, C2 ≤ **278%** (60-trade p10 and p90), and H1–H5 again |

**Pilot risk limit (a limit, not a verdict):** the pilot pauses for the user's review if its running-sum drawdown passes the backtest's 95th percentile for its trade count (20 trades: 138.7%; 60 trades: 314.4%).

## 5. Not allowed

- Reading paper returns before the 20th trade closes (counts are fine).
- Moving the thresholds after seeing the record. A change needs a dated amendment, written before the record is read, as for 18b on 2026-11-19.
- Treating a pass as proof of edge (section 1).
