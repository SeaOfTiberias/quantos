# From maps to an engine: a proposal (2026-11-16)

**Status:** a proposal for the user and reviewers. Nothing here is built yet, and nothing here trades.

## 1. Why 20 candidates failed, and why the 8-pick work proves little

The data is good:
- **L1 daily store:** 3,825 symbols, 2020–2026.
- **5-minute bars:** from 2017.
- **Higher-timeframe maps:** structure (protected/weak, CHoCH), zones (OB/FVG), CPR pivots, weekly volume profiles and money zones.
- **Derivatives data:** the F&O bhavcopy with OI, and full option chains every minute since 30 Sep.
- **Results calendar.**
- **Order stack:** a gateway with checks, GTT OCO exits, and a journal.

The way we have used it has been the problem.

1. **Every candidate was a bespoke hypothesis with its own backtest script.** About 20 scripts, each with its own conventions and bugs, each run once. Research was expensive, so every failure cost a week.
2. **We tested maps as predictors.** "Do zones bounce more than placebo?" failed (60.1% vs 61.1%). The conclusion is that a level is not a signal. It doesn't follow that a level is useless. A level tells you **where you are wrong**, which no price-only signal does.
3. **The unit of evidence was wrong.** The 8 Darvas picks and the 194 F&O calls sit in one market swing: the Nifty 500 swept its 12 Oct low on 23–26 Oct, then rallied 8%. That is one bet, not 194. Six years of data contain dozens of swings, and we tested on one.
4. **Direction was the target.** Intraday direction is dead (4 for 4), and volatility conditioning is dead (5 for 5). The little real evidence we have is cross-sectional momentum: Darvas ATR-stop Bucket B passed out of sample, and candidate 11 cleared its review gate. The second sign of life is liquidity structure, but only as a timing and risk tool.

**The thesis this proposal builds on:** trend and momentum choose *what* to own, the market's state chooses *when*, and the map chooses *where to enter, where you're wrong and where to take profit*. Each part is measured by its own metric.

## 2. Four layers, each scored by its own metric

| Layer | Question | Inputs (all already in the repo) | Output | Scored by |
|---|---|---|---|---|
| **1. Market state** | Is this a time to add risk? | Index maps (Nifty, Nifty 500, Bank Nifty), breadth from the L1 store, India VIX | State: trend / pullback / **index sweep-and-reclaim** / breakdown, and a risk multiplier of 0, ½ or 1 | Forward 10–20-day index return and drawdown by state |
| **2. Selection** | Which stocks are leaders? | Darvas box, 52-week-high proximity, F&O OI build-up, **structural relative strength** (see below) | A ranked list | Forward return spread between top and bottom of the ranking |
| **3. Setup geometry** | Where to enter, where wrong, where out? | Card levels, zones, weekly POC and value area, CPR | Entry level, stop beyond liquidity, target at the opposing level, R:R | MAE/MFE in ATR; how often target comes before stop |
| **4. Sizing and execution** | How much, and how to fill? | 5-minute bars, the gateway, GTT OCO | Size from the structural stop; heat caps; limit orders | Implementation shortfall against the decision price |

### Two new signals that only this data can make

1. **Sweep breadth (layer 1).** Each day, count the Nifty 500 stocks that trade through a structural level and close back above it, as a share of all stocks with a level in range. A market-wide shakeout shows as a spike in sweeps followed by reclaims. On 23–26 Oct, GLAND, ZYDUSLIFE and the index all did this together. A breakdown shows as sweeps without reclaims. Both are measurable from the cards we already build. Neither is in any retail tool.
2. **Structural relative strength (layer 2).** During the last index pullback, did the stock *hold* its own D protected low, while the index swept its own? The stocks that held are the leaders, in Darvas's and O'Neil's sense of the word. The stocks that broke with the market are not. This settles the tension the reviewers found: we don't wait for a strong stock to fall. We wait for the market to shake out, then buy the stock that held its level when the index reclaims its own.

## 3. The core: an event ledger, and strategies as queries over it

The one component that changes research from weeks to minutes:

**The setup ledger.** One table covering the Nifty 500 and F&O universe for 2021–2026. Each row is a *setup event*: a stock-day on which a defined setup appears, such as a sweep-and-reclaim of a structural level, a retest of a Darvas ceiling, or a pullback to the weekly value area.

Each row records:
- **Point-in-time features:**
  - map features: level type, distance to level in ATR, HTF trend, position relative to the weekly value area and POC, CPR width;
  - market state;
  - structural relative strength and sweep breadth that day;
  - OI build-up, and sessions until results.
- **Forward outcomes:** MFE and MAE in ATR over 1, 5, 10 and 20 sessions; which came first, target or stop; returns net of costs.
- **Swing id:** which index swing the event belongs to.

**The strategy builder.** A strategy is a short spec: setup type, feature filters, exit rule, sizing. The engine runs it as a query over the ledger and prints one standard report:
- results **by market swing**, so the evidence count is swings, not trades;
- results by year, as a walk-forward;
- costs included;
- a placebo: the same filter on the same stocks at random dates;
- the paired comparison against simply holding the pick.

This standard is built **once**, not re-argued for each candidate. A new idea costs a few lines of spec and a minute of compute, not a new script and a week.

**The honest cost.** Point-in-time cards are slow: the call-plan replay needs minutes per session for about 100 stocks. Levels change slowly, so the ledger computes the full map **weekly** (Nifty 500 × about 300 weeks ≈ 150,000 cards) plus cheap daily updates (swing points, sweeps, reclaims). The first step of the build is to time one card and size this properly before committing to it.

## 4. Execution engine (layer 4), mostly built already

- **Sizing:**
  - risk per trade = a fixed fraction × the market-state multiplier;
  - quantity = risk ÷ (entry − structural stop).
- **Correlation:**
  - total open risk is capped per market swing, because 10 longs entered in the same index sweep are one bet;
  - a per-sector cap on top of that.
- **Entry:**
  - the 5-minute store lets the engine enter **intraday on the reclaim** with a limit order at the level, instead of at the next day's open after a gap;
  - this is testable on the ledger first, since 5-minute history goes back to 2017.
- **Exits:** the map stop and target as a GTT OCO, which `core/orders/gateway.py` and the position manager already do. A runner rule (half at target, half trailing the last protected low) is tested as a spec variant, not hard-coded.
- **The money rule is unchanged:** code drafts and checks; the user releases entries; rule exits are placed by code. Models explain, summarise news and results, and draft tickets. **They never decide.** The intelligence is in the ledger's conditional statistics, not in a model's opinion.

## 5. Build order (bounded; no paid API in any step)

1. **Market state and sweep breadth.** About 2 days.
   - Index maps exist; breadth comes from the existing cards.
   - Output: a daily state and a breadth series for 2021–2026.
   - Every call plan records the state starting tonight.
2. **Ledger v0 for the one setup we have:** structural sweep-and-reclaim, Nifty 500, 2021–2026, with market state and structural RS as features. It answers the question the 8 picks cannot: **does the sweep entry work across about 30 swings, and in which market states?** It decides whether the call plan goes near money. First action: time one card. If the compute is too heavy, cut to the F&O universe.
3. **Strategy spec and standard report** on the ledger. Then re-express existing evidence as specs, to check that the ledger reproduces known results:
   - Darvas Bucket B, whose OOS pass should reappear;
   - the failed 100-day zones, whose failure should reappear.

   If the ledger can't reproduce both, it's wrong.
4. **Intraday entry on the reclaim** from 5-minute bars, compared with the next-open entry on the same events.
5. **Forward:** the journalled paper record feeds the ledger every night, and scoring is by swing, monthly.

**What stops:**
- more replays of 8 picks;
- bespoke backtest scripts per idea;
- judging anything on fewer than 10 independent market swings.

## 6. What would kill this

- **The ledger can't reproduce known results** (step 3). Fix it or stop.
- **The sweep entry has no edge by swing** over 2021–2026, net of costs, against holding the pick. The call plan stays a reading aid, and the map's role shrinks to stop and target placement, measured by MAE/MFE.
- **Market state doesn't separate forward returns.** Drop layer 1's risk multiplier, and keep the per-swing exposure cap anyway.
