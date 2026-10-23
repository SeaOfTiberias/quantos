# QuantOS F&O screener and structure picker: logic for external review

Status as of 2026-10-23. Every number below is taken from the code or live config, not paraphrased from memory. Please verify the logic, point out errors, and say where the math is wrong or missing.

Market: NSE stock F&O (~210 underlyings), monthly stock options (European-style, cash-settled), lot sizes per NSE. Trader: retail, manual execution, 1–5 day swing horizon, risk budget ~₹10–12k per trade.

There are two separate tools:

- **Part 1, the evening screener.** It picks up to 5 call and 5 put candidates after the close, names one option contract for each, and adds three debit-spread variants.
- **Part 2, the structure picker.** It is run by hand per trade idea. Given a direction, target, stop and horizon, it prices futures, single options, debit verticals and credit verticals against a live chain and ranks them.

---

## Part 1: The evening screener (runs 18:15 IST on trading days)

### 1.1 Data

- Daily OHLCV bars per underlying, one year (Fyers API).
- NSE F&O bhavcopy for today and for 5 sessions ago. It supplies option close, OI (in lots), volume (contracts), lot size, expiry, and underlying price (`UndrlygPric`) for every contract, plus futures OI.
- Optional post-close Fyers bid/ask for the spread legs. If it's unavailable, bhavcopy closes are used.

### 1.2 Direction (setup)

**Calls** come from the real daily bars. **Puts** come from the same code run on **price-inverted bars**, `p → C²/p` (C = last close, high and low swapped). A new high in the inverted series is a new low in the real one, so "near the 52-week high" becomes "near the 52-week low", a box breakout becomes a box breakdown, and the uptrend gate becomes a downtrend gate. Known simplification: this assumes falls behave like rises.

A stock must pass three filters:

1. **Momentum tier.** Score = close / 252-day high × 100. Names are ranked across the whole F&O universe and split into terciles (LEADER, MIDPACK, LAGGARD). **LAGGARD (bottom third) is excluded.**
2. **Trend gate.** Daily EMA9 > EMA21. Puts use the inverted bars, so for puts this effectively means EMA9 < EMA21 on real prices (approximately).
3. **Weekly Darvas box.** Daily bars are aggregated to weekly.
   - The box **ceiling** is confirmed when **3 consecutive weeks** fail to exceed a pending weekly high. The **floor** is confirmed the same way with lows. A box exists once both are confirmed. The most recent confirmed box is used.
   - A box wider than 35% (ceiling vs floor) is discarded. At least 60 daily bars are required.
   - Breakout state, with the ceiling as the reference:
     - **FRESH**: close > ceiling + 0.1 × ATR(14), volume ≥ 1.5 × 20-day average volume, and the previous close ≤ ceiling.
     - **OUT**: close above the ceiling (no volume requirement). `days_out` = consecutive daily closes above the ceiling.
     - **NEAR**: close 0–**7%** below the ceiling (the Darvas "APPROACHING" band).
     - Anything else (IN BOX, NO BASE) is not a setup.
   - For puts, the floor reported in real prices is `C² / inverted_ceiling`.

**Setup rank (lower is better):**

| Rank | State |
|---|---|
| 0 | FRESH |
| 1 | OUT, 1–3 sessions |
| 2 | NEAR (within 7% of the edge, not yet broken) |
| 3 | OUT, 4–5 sessions |
| — | OUT for more than 5 sessions: dropped |

### 1.3 Confirmation: futures OI build-up (ranks, never filters)

- Look-back is 5 sessions. Futures OI is summed over the expiries **listed today**, compared with the same expiries 5 sessions ago. Price change uses the bhavcopy underlying price.
- If |OI change| < 2%, the label is "OI flat". Otherwise:

| | Price up | Price down |
|---|---|---|
| **OI up** | long build-up | short build-up |
| **OI down** | short covering | long unwinding |

- Order of preference:
  - Calls: long build-up, then short covering, then flat or n/a, then the rest.
  - Puts: short build-up, then long unwinding, then flat or n/a, then the rest.

**Sort key:** (setup rank, OI rank, −momentum). The top 5 per side are kept.

### 1.4 Contract selection, including moneyness

1. The entry day is the next weekday after the bhavcopy date. DTE is counted in calendar days from that day.
2. Consider the current and next monthly expiry. Drop any expiry with **fewer than 10 DTE**. Try the **next month first**, then the current month. (Measured on 2026 bhavcopies: next-month one-ITM stock options are nearly untradeable until the last ~7–10 days of the current month. About 13–15 of 210 names were liquid mid-cycle, vs ~145 in the final 4 days.)
3. **Moneyness rule:** only **in-the-money** strikes. For a call, strike ≤ underlying; for a put, strike ≥ underlying. ITM strikes are sorted by distance from spot, and the **nearest 2** are tried in order (nearest ITM first).
4. Hard filters on each strike:
   - option close > 0
   - OI ≥ 50 lots
   - volume ≥ 20 contracts
   - premium × lot ≤ ₹25,000
   - |delta| ≤ 0.80
5. Greeks are Black-Scholes with r = 6.5%, no dividends, T = DTE / 365. IV is solved from the **bhavcopy option close** against the **bhavcopy underlying price** (strict solve). Delta and theta come from that IV. The message shows **θ% per day = |theta per calendar day| / premium × 100**.
6. The first strike that passes is the pick. If none passes, the name goes to a "setup but no liquid contract" line.

**What it does not do:**

- It does **not** split the premium into intrinsic and extrinsic, and it shows no extrinsic % or breakeven for the single option.
- It does **not** check the single option's bid-ask spread. Liquidity is judged only by OI and volume.
- It has no IV-percentile or IV-vs-realised-vol filter, and no check for an upcoming results date (that NSE endpoint is unreachable from the server).

### 1.5 Debit-spread variants (shown alongside each pick)

The long leg is the screener's contract above. The short leg is the listed strike nearest to:

```
spot ± k × EM,   EM = spot × IV_long × sqrt(DTE / 365),   k ∈ {near 0.5, mid 1.0, far 1.5}
```

- The same IV (the long leg's) is used for both legs. No skew.
- **Pricing.** With two-sided quotes, debit = long ask − short bid. Without them, debit = difference of bhavcopy closes (marked "close").
- **Round-trip bid-ask cost** = 2 × (debit − mid debit) / debit. It is flagged at > 10%.
- **Per lot:**
  - max loss = debit × lot
  - max profit = (width − debit) × lot
  - R:R = (width − debit) / debit
  - breakeven = long strike ± debit
- **Day-5 scenario.** Stock at the short strike after 5 sessions (7 calendar days). Both legs are repriced with Black-Scholes at the same IV. The spread's P&L is compared with the single option's.
- **The Telegram message shows only the "mid" (1.0 EM) spread.** All three are stored.

### 1.6 Exit rules (alerts only, applied to the option premium)

| Rule | Setting |
|---|---|
| Initial stop | −10% of premium |
| Breakeven lock | at +8%, the stop moves to +5% |
| Trailing stop | once +12% is reached, trail 8% below the peak |
| Time exit | by session 5 |

### 1.7 Measured results so far (9–22 Oct 2026)

Close-to-close, before costs, 77 picks. The sample is small, from one regime, with overlapping and repeated names (AXISBANK was picked 4 times), so this is not conclusive.

**Mean / median % return. Single = the screener's single option. Near spread = the 0.5 EM debit spread. Spot = underlying move in the pick's direction.**

| Group | Day | n | Single | Near spread | Spot |
|---|---|---|---|---|---|
| FRESH + OUT | d1 | 41 | +2.5 / −6.6 | +2.1 / −3.3 | +0.2 / −0.1 |
| FRESH + OUT | d3 | 31 | +7.2 / −19.2 | +2.6 / +0.4 | −0.2 / −0.2 |
| FRESH + OUT | d5 | 19 | −14.0 / −36.7 | −9.1 / −33.6 | −1.1 / −1.5 |
| NEAR | d1 | 28 | −0.9 / −1.7 | −5.5 / +0.7 | −0.1 / −0.3 |
| NEAR | d3 | 25 | −13.9 / −13.1 | −3.0 / +1.6 | −0.6 / −0.3 |
| NEAR | d5 | 21 | −33.2 / −31.1 | −20.3 / −8.1 | −1.1 / −0.9 |

What this shows so far:

- The underlying has **not** moved in the picked direction on average. The direction signal has shown no edge yet.
- Losses grow from day 3 to day 5 (theta).
- The near (0.5 EM) spread loses least.
- At the time of these picks, theta on the chosen contracts was ~2.5–4.5% of premium per day, because they were current-month contracts with 10–18 DTE.

---

## Part 2: The structure picker (`pick_structure.py`, run per idea)

**Input:** a view with direction, target, stop, horizon (trading days) and risk budget (max loss per trade, default ₹10k). It also takes `p`, the assumed chance the target is hit before the stop (default 0.5). Not yet measured; the trade-idea log will supply it.

**Live chain:** Fyers bid/ask for the underlying, the futures, and option strikes around ATM (10 strikes each side), for every listed expiry.

**IV:** solved **per leg** from that leg's own mid (Black-Scholes, r = 6.5%, bisection between 1% and 300%). Legs priced at or below intrinsic are dropped. IV is held constant across scenarios unless `--vol-shift` is set (e.g. −0.05 for a post-results crush).

**Expiries:** a structure must outlive the view. Its expiry must be more than horizon × 7/5 calendar days away, plus 1 day.

### 2.1 Three scenarios per structure

| Scenario | Spot | Time elapsed |
|---|---|---|
| target | at the target | full horizon |
| stop | at the stop | half the horizon |
| stall | halfway between spot and target | full horizon |

Execution costs:

- Entry pays the ask on long legs and receives the bid on short legs.
- Exit gives up half the current bid-ask on every leg again.

### 2.2 Candidates (every expiry, every strike in the fetched chain)

- **Futures with a stop.**
  - Gain = (target + basis − entry) × lot.
  - Normal loss = stop distance + 0.1% slippage.
  - Worst case (overnight) = stop distance + a 2% gap through the stop.
- **Single long option:** every strike with ask ≥ ₹1. ITM, ATM and OTM are all eligible; there is no moneyness preference.
- **Debit vertical:** every (long k1, short k2) pair in the view's direction. Kept only if 5% of width ≤ debit < width.
- **Credit vertical** on the opposite side: every (short k1, long k2) pair. Kept only if 5% of width ≤ credit < width. Worst case = (width − credit) × lot.

### 2.3 Math per candidate (per lot)

```
gain      = value at target scenario − entry cost
loss      = min(stop-scenario P&L, stall-scenario P&L, 0)   # the worse of the two (risk-averse)
worst     = most the lot can lose (premium, spread max loss, or stop + gap for futures)
be_p      = −loss / (gain − loss)        # hit rate needed to break even
EV(p)     = p × gain + (1 − p) × loss
score     = EV(p) / worst
lots      = floor(budget / worst); a candidate needs at least 1 lot to be kept
```

Ranking is by `score`. The report shows the best of each family (future, single, debit, credit). **In practice I recommend the structure with the lowest `be_p` that fits the budget.** If every structure needs `be_p` > ~55%, the view's target-to-stop geometry is too poor, and I suggest changing the entry, stop or target, or skipping.

**Moneyness here:** there is no explicit rule. Strike choice falls out of the scenario P&L. Deep-ITM legs behave like futures, and far-OTM legs need the target to land, so the `be_p` comparison decides.

### 2.4 Known simplifications

- Black-Scholes with constant per-leg IV. No vol term structure, no skew dynamics, no early exercise (correct for NSE stock options, which are European).
- Three point scenarios, not a distribution. The `p` is assumed, not yet measured.
- Futures basis is held constant. There is no carry or dividend adjustment.
- Fills are assumed at the quoted bid/ask, with no depth check.

---

## Questions for the reviewer

1. Is the price-inversion trick a sound way to generate put setups, or does it distort the box, EMA or momentum logic?
2. Is "nearest ITM, |Δ| ≤ 0.80, ≥ 10 DTE" the right moneyness and expiry rule for a 1–5 day hold, given that next-month stock options are illiquid mid-cycle?
3. Should the single option be gated on bid-ask % (and at what threshold) instead of OI and volume?
4. Is the 0.5/1.0/1.5 × expected-move short-strike rule reasonable, and which width should be shown by default?
5. Are there errors in the IV, Greeks, cost or scenario math above?
6. The direction signal has shown no edge on the underlying so far. Which part of the setup logic is most likely responsible?
