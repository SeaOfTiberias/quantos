# Playbook v1: S8 test pre-registration

**Written 2026-11-13, before any universe run and before any outcome beyond the walk-through.**
Status: **APPROVED by the user 2026-11-13 and frozen.** Any later change is a dated amendment, written before the data it touches is seen.

**What is tested:** `docs/MARKET_PLAYBOOK_V1.md` (c00010e), exactly as coded in `core/market_map/playbook.py` (0746807), on the v3 map (`docs/MARKET_MAP_DEFINITIONS_V3.md`, code f7bfa2b).

**The two questions:**
1. Does P1 (continuation) make money net of costs?
2. Do the map's zones and the sweep add anything over the same rules applied without them?

This is a test of the playbook as a trading rule. It is not the S4 level test (`docs/MARKET_MAP_SIGNAL_PREREG_2026-11-05.md`), which was written for definitions v1 and is left for its own amendment.

**The verdict is pass or fail on the criteria below.** No parameter in the playbook, the map or this document is re-tuned in this round. The v2 questions from the walk-through (`docs/review_round1/v3/playbook/walk.md`) are not answered here. They wait for this result.

## 1. Data and point in time

**Bars:**
- NSE daily bhavcopy, split- and bonus-adjusted, from the L1 store (`core/market_map/l1_store.py`).
- The run uses a snapshot of the VM store taken on 2026-11-13. Its last session is 2026-11-12; it holds 3,823 symbols from 2010, delisted names included.
- The run happens on the PC. The VM's live store and jobs are not touched.

**Universe on read date D:**
- The `Store.universe` rule: top 500 by median traded value over the last 60 sessions, EQ series, ETFs excluded.
- It is computed from the sessions before D, so delisted and renamed stocks take part while they qualify.

**Read period:** 2013-01-01 to 2026-08-31.
- The start leaves three years of history for monthly structure.
- The end leaves at least 50 sessions for an order's 10-session life plus the 40-session time exit.

**Segments:**
- Where a stock's adjusted history restarts at an unexplained jump (`seg` in the store), a read on date D uses only the segment that contains D's last completed bar.
- The forward walk uses the same segment. A trade still open when its segment ends is closed at the segment's last close and flagged "segment end". It counts in the results and is also reported.
- Reason for the rule: `l1_read` and `simulate` take a stock's *latest* segment. That is right for today's read but would mix histories in a past one, so the runner passes the right segment explicitly.

**No look-ahead:**
- A read on D uses only bars completed before D (definitions §0).
- The forward walk re-reads M, W and D after each close from completed bars only (`playbook._States`).
- 5-minute data exists only for the last 100 days, so historical reads run without it (`m5=None`). The W money zone and W VPOC are therefore absent, as in the S4 test.

**Prices:**
- Adjusted prices are rounded to the 0.05 tick as the code does.
- Back-adjustment makes old ticks slightly off-grid. This changes no R by more than a tick and is ignored.

**Excluded from scoring:** any setup on a symbol whose read date is within 60 sessions of a case that shaped the rules.
- The round 1 reads: KEI 2025-06-23, DMART 2026-08-28, JSL 2026-03-04, LTM 2026-10-13, HCLTECH 2025-07-14, ANTELOPUS 2026-08-24, NEOGEN 2026-10-21, GRSE 2026-08-07, IRFC 2025-07-28, TEJASNET 2025-04-21, BIOCON 2026-05-13, SSWL 2025-09-17, BLUESTARCO 2025-08-07, NBCC 2025-05-30, CHOLAFIN 2024-12-19.
- HDFCBANK and SUPREMEIND from 2026-09-01.
- Excluded setups are counted and reported.

## 2. When the playbook reads a stock

**P1 reads, every other week:**
- A read happens on the first session of each even-numbered ISO week, for every stock in that date's universe.
- Reason: an order lives 10 sessions (two weeks), so reading every other week keeps one order resting almost continuously.
- **Gate, run before the full read to save time:** W in a trend, and M not the opposite. It is computed with the same `structure` functions on the same completed bars. The gate never changes a result, because P1 itself returns NO TRADE when it fails.

**P2 reads, triggered by an event:**
- P2 needs a daily CHoCH in the 10 sessions before the read.
- So a P2 read happens on the session after each daily CHoCH against the W trend: a CHoCH up while W is down, or a CHoCH down while W is up.
- The candidate CHoCHs come from one structure run over the segment. The full read on the next session then recomputes everything from completed bars and makes the decision.
- **Check before the run:** a unit test on real stocks from the snapshot confirms that the daily events of a truncated run are a prefix of the full run's events. If they are not, P2 falls back to reads on every session that passes the gate (W in a trend), at whatever run time that costs.

**One order or trade at a time, per stock, per setup type:**
- A P1 read is skipped while an earlier P1 order or trade on the same stock is still alive. P2 follows the same rule within its own track.
- Placebos and controls never block a read.

**Unchanged from the code:** the plan (`plan_p1`, `plan_p2`) and its forward walk (`simulate`, with `opposing_strong` for E2).

**Not modelled:**
- The P3.9 circuit breaker. It is a book-level rule, proposed and not yet approved.
- Futures basis and rolls (P3.10). Shorts are walked on cash prices.

## 3. Outcome per setup

**R per setup.** Each SETUP's result in R of its planned risk:
- **Closed trade:** (exit − fill) / risk, signed for the side, minus costs.
- **Order that never filled** (cancelled or expired): **0R**. An order that never fills costs nothing.

**Primary unit: R per setup**, not per filled trade.
- The playbook's product is the order. A rule that fills only on its losers should show that.
- R per filled trade, the fill rate, the outcome mix (target, stop, break-even, trail, E1–E3, time) and MFE/MAE are reported too.

**Costs:** the stressed delivery model from the Darvas tests (`STRESSED_COST_MODEL` in `scripts/backtest_darvas_box_width.py`).
- It covers STT on both legs, stamp, exchange charges, SEBI fees, GST and slippage, on Rs 1,00,000 a trade.
- It is applied to both sides. Futures shorts cost less, so this is conservative for shorts.
- Cost in R = cost / (risk × quantity).
- The R before costs is reported too.

## 4. Controls

### 4.1 P1 placebo: the same trade, anywhere in the discount but at a zone

The aim is to isolate the zone. For each real P1 setup that rests below the price (long; shorts mirror), up to **K = 3 placebo bands** are drawn with a seed made from the symbol and the read date.

**What the placebo shares with the real setup:**
- the stock, read date and side;
- the band width;
- the entry rule (top of the band);
- the stop rule (band low − 0.25 ATR(D)), and so the same risk;
- the target (W weak high);
- the 2R and risk-cap checks, the cancels and the management, including E2's opposing strong zones.

**Where a placebo band can go:** its top is drawn uniformly so that
- it is below the read price and in W discount (below the equilibrium of the read's W dealing range);
- the band's low is at or above the W protected low; and
- the band overlaps **no v3 zone of the read** (any HTF zone cluster, strong or not, low to high).

**Drawing:**
- Up to 200 draws are tried to find valid bands.
- A setup that gets no valid placebo is reported, and is left out of the comparison but not out of A1.

**At-open setups:** where the real setup enters at the next open (the price is already inside the band), a placebo of the same width at the same position would be the same trade. These setups count in A1 and are reported separately. They are not in the placebo comparison.

**Reported only:** a **market-entry** comparison. It enters at the read's next open, with the same risk distance, target and management. It shows how much of any result is the W direction alone.

### 4.2 P2 control: the shift without the sweep

This answers the sprint plan's S8 question: does a daily CHoCH back the other way do better after a sweep than after a plain break?

On the same event-triggered reads, a **control setup** is built wherever P2 finds the context (W trend, a CHoCH against it in the last 10 sessions) but **no qualifying sweep**, and the low of the 10 sessions before the CHoCH is at or below the W weak low (the market broke the weak low rather than swept it). The control:
- takes the same entry (the CHoCH's D order block) and the same target;
- puts its stop at that 10-session extreme − 0.25 ATR(D), in place of the sweep extreme;
- applies the same 2R and risk-cap checks, the same management and the same half-risk flag;
- has no E3, because no level was swept. P2 is also reported with E3 switched off, so the two can be compared like for like.

Shorts mirror all of this.

## 5. Statistics

**Bootstrap:**
- 10,000 resamples of **calendar months** (by read date), with replacement, seed 20261113.
- Months are used because setups across stocks move together, and trades last weeks.
- 95% interval: the 2.5th to 97.5th percentile.
- Two-sided p: 2 × min(share of resamples ≤ 0, share ≥ 0).

**The comparisons:**
- **P1, matched:** for each comparable setup, real net R − the mean net R of its placebos. The measure is the mean of those differences.
- **P2:** mean net R of P2 setups − mean net R of control setups (independent groups, resampled together by month).

**Multiple testing:** Holm–Bonferroni over the two comparisons (P1 vs placebo, P2 vs control), at a family-wise α of 0.05.

## 6. Pass criteria

### P1 passes only if all of these hold

| # | Criterion |
|---|---|
| A1 | Mean net R per setup > 0, with the bootstrap 95% interval's lower end > 0 |
| A2 | Matched real − placebo ≥ **+0.10R** per setup, and its p-value passes Holm |
| A3 | Both of these hold in **each era**, 2013–2019 and 2020–2026 (by read date): the A1 mean > 0, and the A2 difference > 0 |
| A4 | The A2 difference > 0 for **longs and for shorts** separately |
| A5 | At least **300 filled** real trades, and at least **300** setups in the placebo comparison |

- If one side has fewer than 100 comparable setups, A4 is judged on the other side alone. Any pass is then reported as one-sided (for example "long-only"), and the thin side is labelled untested.
- **Passing A1 but failing A2 means the money came from the W direction, not the zones.** It is reported as such: a fail for the playbook as written.

### P2 passes only if all of these hold

| # | Criterion |
|---|---|
| B1 | Mean net R per setup > 0, with the 95% interval's lower end > 0 |
| B2 | P2 − control ≥ **+0.10R** per setup, and its p-value passes Holm |
| B3 | Both of these hold in each era: the B1 mean > 0, and the B2 difference > 0 |
| B4 | At least **200 filled** P2 trades, and at least **200** control setups |

**If B4 fails,** P2 is reported as **not testable at this sample size**. That is neither a pass nor a fail. P2 stays unused (playbook P2: "not used until its S8 test passes"). Any wider run is a new pre-registration.

## 7. Reported only (no verdict depends on these)

None of these rescues a failed criterion. A strong cell in a failed test is a lead for a new pre-registered test, never a pass.

- R before costs, R per filled trade, the fill rate, and the outcome mix.
- Cost in R, by terciles of risk as a percentage of price. Tight stops pay more cost per R.
- By the entry band's kind (demand, OB) and timeframe (W, M).
- By W/M alignment (both in a trend, or M ranging).
- **The walk-through's four v2 questions, as counts only:**
  1. give-back after +2R;
  2. reads refused as "zone too wide";
  3. setups cancelled by C3;
  4. P2 contexts that turned in a V without a fill.
- Market entry (§4.1), and P2 with E3 off.
- "Segment end" closes, excluded setups, and setups with no placebo.

## 8. Order of work

1. **The user approves this document. It is committed.**
2. **The runner** (`scripts/playbook_s8.py`) and its unit tests on synthetic bars:
   - universe ranking;
   - segment selection;
   - placebo drawing and its exclusions;
   - the P2 control;
   - cost in R;
   - the month bootstrap;
   - the event-prefix check from §2.
3. **Count-only pass,** on every fourth P1 read date and every P2 trigger. It counts reads, setups by type, at-open setups, setups with placebos and control setups. **It looks at no fills and no R.** Its output is committed before the full run.
   - If the projected P1 setups for the full run are under 600, P1 reads move to **every week** (this fallback is fixed here).
4. **The full run,** once. The results are committed before they are reported.

## 9. Afterwards

**P1 passes:** the playbook's P1 becomes a tested paper rule.
- Paper trading it forward comes next (CLAUDE.md: Surge 23b, no P&L before 60 closed trades).
- Real money stays paused until the user lifts the pause. Every order still goes through the gateway and the user's release.

**P1 fails:** the playbook stays "untested" in use and "failed its test" on record.
- A v2 written from the walk-through's questions is a new document with its own test.
- Nothing is re-tuned against this run.

**P2:** the same rules, and it stays unused unless it passes.

## Amendment 1 (2026-11-13, before any outcome)

**Why.** A smoke run of the count pass on 6 stocks found zone-free room for a placebo in only 20 of 57 P1 setups. The v3 zones fill much of the W discount, so A5's 300 matched setups may be out of reach. As written, that shortfall would make P1 **fail**. That was a design flaw: too few controls means the test can't answer, not that the playbook is wrong. The S4 pre-registration already handles this with a fallback placebo and a "not testable" outcome; this document now does the same.

**When.** Written after the smoke run's counts and before the full count pass finished. No fill, exit or R had been computed for any setup.

**Changes:**
1. **Two-step placebo (§4.1).**
   - **Step 1** is the rule as written: the band overlaps no v3 zone of the read.
   - **Step 2** applies only to a setup that gets no step 1 placebo after 200 draws. Its bands may overlap a zone that is **not strong**, but must not overlap any strong zone or the real entry band. Up to K = 3, with the same seed and draw rules.
   - A2 uses step 1 and step 2 placebos together. Two comparisons are reported only: step 1 alone, and step 2 alone. A step 2 comparison means "strong zone vs weak or no zone".
2. **Not testable instead of a fail (§6).**
   - If fewer than 300 setups have a placebo (step 1 or 2), the zone comparison (A2, A4) is **not testable (placebo scarcity)**.
   - A1 and the era test of A1 (A3's first half) are still judged on their own and reported as "P1 makes money / does not, net of costs".
   - The playbook as a whole then reads "**not shown to come from the zones**". It is not a pass.
3. **Reported (§7):** the share of setups with a step 1 placebo, with only a step 2 placebo, and with none. This measures how densely the map covers the discount and premium.

**Unchanged:** every threshold, the read cadence, the costs, the bootstrap, Holm, and P2.
