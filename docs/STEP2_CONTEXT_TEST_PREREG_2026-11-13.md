# Step 2 test: does map context improve the screener's picks? Pre-registration (2026-11-13)

Written and committed before any signal was read against a card. The user's framing (2026-11-13): a trade is two steps. Step 1 picks the instrument (the F&O screener, sent on Telegram). Step 2 applies context: levels, structure, structure choice, stops. This test asks whether step 2, done by frozen rules (A1) or by the model (A2) reading the context card (`core/market_map/card.py`), keeps better trades than it drops.

## What is already known (not re-tested)

- Year backtest of the screener (`scripts/backtest_fno_screener.py`, Sep 2025 – Oct 2026): calls have no edge; puts have a small one, mostly in the first half.
- `docs/FNO_ENTRY_SEARCH_PREREG_2026-10-23.md`: the puts' retest entry (H1) passed; every other entry failed.
- `docs/FNO_INDICATOR_FILTER_PREREG_2026-10-26.md`, `docs/PUT_SETUPS_PREREG_2026-10-25.md`: indicator filters and put variants failed.
- Live picks 2026-10-09 to 11-13 (179 with 5 sessions): CE 58% right, PE 31%. In W44, 49 puts were 4% right while NIFTY rose 5.5%. This is the motivation, not evidence: one regime, a handful of weeks. It is reported again as a diagnostic only.

None of those used the market map. Setup state, OI label, Nifty vs EMA20, tier, box width, volume ratio and bucket were examined before, and are not context here.

## Fixed for every arm

- **Signals:** FRESH, or OUT ≤ 5 sessions, from `~/.quantos/bt_fno/outcomes.jsonl`. That is 5,431 signals (2,501 CE, 2,930 PE) over 209 stocks, 2025-09-02 to 2026-10-23. A signal on day *t* is acted on at the open of *t+1*.
- **Card:** `card.card()` on `read.l1_for(sym, t+1)` from the L1 store snapshot `~/.quantos/l1_snap_20261113`, meaning bars through *t* only. The index card is NIFTY's, from `~/.quantos/index_bars`, read the same way. A signal whose stock has no L1 read is reported and left out of every arm.
- **Outcomes**, signed by side (+ for CE, − for PE), already in the file:
  - **Swing (overnight):** `oc5`. Enter at the next open, exit at the close of session *t+5*. Futures, cost 0.10% round trip.
  - **Intraday:** `oc1`. Enter at the next open, exit at that session's close. Cost 0.10%.
  - Reported, no verdict: `ex5` (the market-stripped move), the single option contract and debit verticals (buy the screener's strike; sell 1, 2 or 3 strikes further OTM), all priced at bhavcopy closes from `chain` at day 0 and day 5.
- **Halves:** split at the median signal date (2026-03-12).

## Arms

### A0, the screener as issued
Every signal.

### A1, frozen context rules
Rules derived from the concepts in `docs/TRADE_REASONING.md` (steps 1 and 5, lessons 1–3). They were frozen here, not fitted to any outcome. All are computed by code from the card. For a CE (long) signal, "opposing" means above the price and "same side" means below; a PE mirrors this.

| ID | Rule | Concept |
|---|---|---|
| R1 room | The nearest STRONG opposing zone's edge is ≥ 1.5 ATR(D) away, or no strong opposing zone is on the card. | A target beyond a strong opposing zone is a hope, not a plan. |
| R2 no opposing sweep (stock) | No D or W sweep in the last 10 sessions against the trade. For a PE that is a sweep of a low (sell-side liquidity just taken); for a CE, a sweep of a high. | Sweep then shift: a fresh sweep is where reversals start. |
| R3 no opposing sweep (index) | R2 applied to the NIFTY card. | Index first: in W44, puts were sold straight into NIFTY's swept lows. |
| R4 structure or location | The stock's W state is in the trade's direction, or the price is inside a STRONG zone, or within 1.0 ATR(D) of a STRONG same-side zone. | Trade with the weekly structure, unless the trade starts at a strong level. |

**A1 keeps a signal only if it passes all four.** Each rule's own keep/drop split is reported, with no verdict.

### A2, the model with the card
- **Window:** signals dated **2026-07-01 to 2026-10-23** only (1,553 signals over 80 days). The model's knowledge runs to June 2026. Earlier dates could be recalled, not reasoned about.
- **Anonymised:** stocks are relabelled S01, S02, … per day. Every calendar date becomes "N sessions ago". All prices for a symbol are scaled by one random factor in [0.5, 2.0], seeded from (symbol, date). Distances in % and ATR are unchanged by the scaling. The index is labelled "INDEX" and scaled the same way.
- **One call per signal day**, as the book routine works:
  - the index card;
  - each signal's side and card;
  - `docs/TRADE_REASONING.md` as the procedure.

  For each signal the model answers `take` or `skip`, a structure (`futures`, `option`, `spread`, `intraday` or `none`) and one line of reasons. No web search. The model comes from `model_for("step2_judge")`, effort high, and every call is logged.
- A2's verdict uses its take/skip split only. Its structure choices are reported against the option and spread outcomes, with no verdict.
- A1 is also scored on the same post-cutoff signals so the two arms compare on equal ground (reported).

## Pass criteria (each arm × horizon × side: 2 × 2 × 2 = 8 tests)

A filter **passes** on a horizon and side when all of these hold:

1. **It separates.** Kept minus dropped mean outcome > 0, with t ≥ **2.7** (about p < 0.05 / 8). The t is computed over days that have both kept and dropped signals, one mean difference per day.
2. **What it keeps is tradeable.** The kept mean after cost is > 0 in **both** halves. For A2, whose window is shorter than a half, it must be > 0 in each half of its own window.
3. **Enough trades.** At least **150** kept for A1, and **100** for A2.

Anything else is **FAIL**. A failed arm is reported as failed and not re-tuned in this round. A pass makes the filter a **label** on the screener's Telegram picks and the book routine's candidates, with a forward record. It does not make it a gate or a sizing input.

## Known limits, stated up front

- Survivorship: today's F&O list is used for the whole year (the same as the year backtest).
- Fixed exits (5 sessions, or the same session) stand in for the playbook's stops and targets. The question is whether context picks better trades, not the best exit.
- A2's window is one regime: July to October 2026.
- The L1 map (definitions v3) is untested. This test uses it as context; it does not test the map's zones (that is S8).

## Steps

1. Commit this document.
2. `scripts/step2_context_test.py --arm a1` builds the cards (cached per symbol and date), applies R1–R4 and writes the rows and results. The A2 cards and prompts are built and their anonymisation is spot-checked (no symbol, no date, no unscaled price) before any call is sent.
3. Results are committed, then reported, including failures.
