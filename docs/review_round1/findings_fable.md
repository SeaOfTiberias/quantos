# Round 1 findings: Fable (2026-11-09)

This document classes Fable's findings as `docs/MARKET_MAP_REVIEW_ROUND1.md` pre-registered:
- **(a) code bug:** the code doesn't do what v1 says.
- **(b) definition gap:** the code does what v1 says, but v1 misses something.
- **(c) reviewer misread.**

It covers Fable's three independent batches only (answers in `fable/R##.json`). The user's own review and the user's model judge are still to come. **Nothing has been changed.**

## The tally

- **Coverage:** 15 reads, 35 items each, 525 items in all. Every item was answered once.
- **Rule = N: 0.** Fable rebuilt v1 in its own scripts from the bars, without the engine's source. It got back the same numbers, exactly or within one price bucket:
  - the M/W/D states, events, protected and weak levels and ages;
  - ATR;
  - every W/M/Q/Y pivot, CPR, Camarilla level, width percentile and relationship;
  - the money zones and volume profiles, including the weekly ones built from 5-minute bars;
  - the 250-day and 750-day profiles;
  - the daily layer.

  It checked about 1,400 L1 virgin levels against the later daily bars and found none traded through.
- **Rule = Y on 75%.** Nearly all the rest are "unclear": the sweep items (v1 hasn't frozen the definition) and the zone items (the clustering behind v1 §6 isn't written in v1).
- **Chart = Y on 81%; Chart = N on 55 items.**
- **Overall verdict: "partly" on all 15 reads.**

| Item kind | Items | Rule Y | Chart Y | Chart N |
|---|---|---|---|---|
| state (M/W/D) | 45 | 100% | 58% | 15 |
| event (BOS/CHoCH) | 45 | 100% | 76% | 10 |
| protected | 45 | 100% | 73% | 8 |
| weak | 45 | 100% | 98% | 1 |
| premium/discount | 45 | 100% | 87% | 3 |
| sweep | 45 | 0% (all unclear) | 93% | 3 |
| zone | 105 | 30% | 90% | 1 |
| hot zone | 15 | 100% | 33% | 0 |
| period pivots | 30 | 100% | 100% | 0 |
| profiles | 45 | 87% | 84% | 2 |
| daily layer | 45 | 89% | 69% | 8 |
| what to watch | 15 | 100% | 47% | 4 |

**Missing:** Fable listed 46 things the reads leave out:

| What's missing | Entries |
|---|---|
| Daily and weekly swing highs and lows | 11 |
| A CHoCH the read doesn't show | 6 |
| EQH/EQL and double tops or bottoms | about 10 |
| Sweeps and failed breakouts | about 7 |
| Demand zones and gaps | 5 |
| Ranges | 2 |

## Code bugs (a): two, both small, neither fixed

1. **A price on a bucket edge lands one bucket low.**
   - **Cause:** `np.floor_divide(132.2, 0.2)` gives 660 (132.2/0.2 = 660.9999…), so a price exactly on an edge falls into the bucket below. The bucketing lives in `core/market_map/profiles.spread` and `tpo`, and in `core/price_map/levels`.
   - **Affected:** only decimal steps (0.1, 0.2, 0.5 …), which come from `step_for(ATR/20)` on lower-priced stocks. A step of 5 is exact.
   - **Seen in:** IRFC (R09). Its weekly money-zone value area reads 132.2–135.8, where exact bucketing gives 131.6–135.2. Its 250-day value area reads 122.8–160.2, where exact bucketing gives 122.4–159.8. Its virgin level 132.2 also shifts.
   - **Fix, if approved:** round `x / step` to about 9 decimals before taking the floor, then regenerate all 15 reads and list what changes.
2. **Bad 5-minute bars aren't filtered.**
   - **What happens:** NEOGEN has 5 Fyers bars on 2019-12-06 whose high is below their low. In `profiles.spread` they divide by zero (the warning in R07's generation), and that week's and that session's profiles take an inf or NaN weight. No daily bar is bad.
   - **Fix, if approved:** drop or repair 5-minute bars with `h < l` when the 5-minute store is read, and count how many there are across all 500 stocks.

## Definition gaps (b): the code follows v1, but v1 misses what the chart shows

Ranked by how often Fable raised them and how much they change a read.

1. **Structure states go stale (all three batches; most of the Chart = N on state, event and protected).**
   - **Why:** v1 §2 moves the protected level only on a BOS. After a CHoCH it takes the extreme of the whole prior leg. With no break of internal structure, a timeframe can hold its state through a large move the other way:
     - R06 monthly reads "up for 52 bars" through a 67% fall.
     - R10 monthly reads "up" after a 57% fall.
     - R04 weekly reads "down for 82 bars" through a 69% rally.
     - R05 weekly reads "up for 82 bars" through a 35% fall.
     - NBCC weekly reads "up for 131 bars" through a 49% fall.
     - R07 monthly reads "up for 0 bars" after a 150% rally.
   - **Knock-on:** the ages, the BOS/CHoCH labels and the alignment line inherit this. R09 and R10 name the wrong conflicting timeframe. The engine's own swing labels (LH/LL inside an "up" state) contradict the state.
2. **The strong flag doesn't discriminate, and the zones cover the whole price range (all three batches).**
   - **Scale:** 73–83% of zones are strong, and every zone within several ATR of price is strong. They come from hundreds of virgin weekly and monthly profile levels (the volume family) plus four periods of formula levels (the pivot family).
   - **Width:** the existing map's clustering lets a zone grow to about 1.2–1.5 × 0.3 ATR(W). The read still says "within 91.28", which misleads.
   - **Band edges:** supply, demand and order-block bands are clustered as their two edges, so one band can credit two zones and leave its own middle unzoned.
   - **Earlier note:** this is the same non-selectivity the 11-08 note recorded (median 73%).
3. **Equal highs and lows are never swings (R04, and in several "missing" entries).**
   - **Why:** §1 requires a high strictly greater than every bar in the window. So a double top such as LTM's 4850/4850 (2026-08-11 and 08-12) yields no swing: D reads "up", and 4700 is labelled the higher high.
   - **Related:** EQH/EQL exist only on W and M, and daily structure is never clustered into zones (§0, by design). Daily double tops and bottoms and daily trend-defining swings are therefore missing.
4. **Sweeps and failed breakouts aren't named.**
   - **Why:** only sweeps of the weak level are tracked, and v1 hasn't frozen the definition (S7).
   - **Missed:**
     - NEOGEN's triple top at 2484–2500, run to 2785 and closed back below;
     - GRSE's triple bottom at 2525–2535, run to 2471.7 and reclaimed;
     - TEJASNET's sweep of its protected low 741.1;
     - BIOCON's most recent sweeps.
   - **Over-counted:** a 1.9-point overshoot (CHOLAFIN) counts as a sweep.
5. **The nearest virgin levels are mostly trivial.** Most of the nearest daily and weekly "virgin" levels belong to the session or week that has just closed. They are virgin only because no bar has printed since, sit 0–0.2 ATR from price, and crowd out older untouched levels. This was already noted at slice 7b; it affects the L2 virgin and V.virgin items.
6. **Smaller gaps**, each a choice v1 leaves open:
   - **Camarilla width:** the code divides H3−L3 by the close; CPR width divides by P. This flips R02's yearly Camarilla reading.
   - **Volume POC tie:** v1 gives no tie rule. In R04 the monthly VPOC is 4090, where "nearest the middle" would give 4130, which would also make it a GPZ member.
   - **Percentile ties:** the code gives a tie half rank. On NBCC this gives the monthly Camarilla 0.70 against 0.75, which is the line for "wide".
   - **EQH/EQL tolerance:** v1 doesn't say whether it uses the ATR at the time of the swing or today's. A BLUESTARCO weekly EQL passes with one and fails with the other.
   - **GPZ:** volume VAL and VAH are never GPZ members, which is one valid reading of Ochoa.
   - **Bucket step:** the step can differ between periods within one read, because each period's own ATR(D) sets it.
   - **Stale wording:** v1 §4 says weekly profiles exist for "the last 100 days" of 5-minute bars. The 5-minute store now runs from 2017-12, and the code builds every week it has bars for. The code follows the rule ("only where those exist"); the parenthesis is out of date.

## Reviewer misreads (c)

None found so far. Fable's figures held up wherever I checked them against the code.

## What happens next (per the protocol)

- **The two bugs:** fixed only after the user approves, then all 15 reads are regenerated and the differences listed.
- **The gaps:** go to the v2 list, which is written only after the user's review and the model judge are in.
- **Round 2:** scores whichever version is current, on fresh charts, with §9 unchanged.
