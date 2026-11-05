# Market Map: definitions v1 (DRAFT 2026-11-04, for the user's approval)

Sprint S4. Exact rules for the higher-timeframe (L1) and SMC layers, the period pivots and the
long profile. Concepts: `docs/MARKET_MAP_ENGINE_DESIGN.md` §2b and §3 (agreed 2026-11-03),
Ochoa's *Secrets of a Pivot Boss* (pivots, CPR, two-day relationships, Camarilla, money zone),
Dalton (value area, poor highs/lows) and SMC as the design describes it.

**How this document is used (user, 2026-11-04):** the rules come from the concepts, not from the
user's marks. v1 is written and frozen **before** any golden-set chart is seen. The golden set
then tests v1 (§9); a miss is reported as a miss. A rule change is v2, scored only on charts v1
and v2 never saw. HDFCBANK and SUPREMEIND were discussed before v1 was written, so they
illustrate it but are never scored.

Every parameter below is fixed in v1. None is tuned on outcomes or on marks.

## 0. Common ground

- **Bars.** NSE daily bars, split- and bonus-adjusted (`core/techno_funda/prices.py`). Weekly bars are ISO weeks (Mon–Fri); monthly, quarterly and yearly are calendar periods. Each higher bar is open = first open, high = max high, low = min low, close = last close, volume = sum.
- **Point in time.** A read for day D uses only bars that **completed** before D. The current week, month, quarter and year are left out until they close. A swing point counts only from the bar on which it is confirmed (§1).
- **ATR(TF).** 14-period Wilder ATR on that timeframe's own bars. Every distance below is in that timeframe's ATR unless it says otherwise.
- **Close-based breaks.** A level is broken by a **close** beyond it, never by a wick. A wick through it that closes back inside is a sweep (§3.4).
- **Timeframes in L1:** monthly (M), weekly (W). The daily (D) runs the same code for alignment (§7). Daily pivots and daily Camarilla are intraday tools and stay out of the swing map (design noise assessment).

## 1. Swing points

- **Swing high** on TF: bar *i* whose high is strictly greater than the high of every bar in the *k* bars before and the *k* bars after it. **Swing low**: the mirror on lows.
  - k = 2 (M), 3 (W), 5 (D; the same as the existing price map).
  - Confirmed on bar *i + k*, the bar that completes the window. Never used before that bar.
- **Size filter (zig-zag).** Swing highs and lows must alternate, and each must be at least 1 ATR(TF) from the previous opposite swing.
  - Two highs in a row without a qualifying low between them: keep the higher one. Two lows: keep the lower.
  - A swing less than 1 ATR from the previous opposite swing is dropped.
- **Labels.** Each swing high is HH or LH against the previous swing high; each low is HL or LL against the previous low. They describe the structure; trend state comes from §2.

## 2. Structure: BOS, CHoCH, trend state (SMC)

State per timeframe: `up`, `down` or `none` (before the first break).

- **Protected (strong) low** in an uptrend: after each up break, the lowest low between the bar of the broken swing high and the break bar. In a downtrend, the **protected (strong) high** is the mirror.
- **BOS (break of structure), continuation:**
  - in `up`: a close above the most recent confirmed swing high not yet broken;
  - in `down`: a close below the most recent confirmed swing low not yet broken.

  Each BOS resets the protected level as above.
- **CHoCH (change of character), reversal:**
  - in `up`: a close below the protected low. The state becomes `down`, and the protected high becomes the highest high between the protected low's bar and the CHoCH bar;
  - in `down`: the mirror.
- **Start.** From `none`, the first close beyond any confirmed swing sets the state. It is recorded as a BOS, with the protected level set as above.
- **Weak high** in `up`: the highest high since the last up break, not protected and the obvious target. **Weak low** in `down`: the mirror.
- **Strong / weak.** The protected level is the strong low or high; the opposite extreme is the weak one.
- **Output per timeframe:**
  - state;
  - last event (BOS or CHoCH) with its date and level;
  - protected level;
  - weak level;
  - age of the state in bars.

## 3. Zones and levels

### 3.1 Demand and supply: base and departure (multi-year zones)

On W and M bars:

- **Base:** 1 to 6 consecutive bars, each with a range of at most 1.0 ATR(TF).
- **Departure:** within the 3 bars after the base, a close at least 2.0 ATR(TF) beyond the base's far edge.
  - Upward departure: a **demand zone**, from the base's lowest low to its highest body top (max of open and close).
  - Downward departure: a **supply zone**, from its lowest body bottom to its highest high.
- **Strength:** the departure size in ATR(TF), measured as the furthest close within the 3 bars.
- **Tests:** each later bar that trades into the zone after price first left it by 2 ATR(TF) adds a test.
- **Invalidated** by a close beyond the far edge (below a demand zone's low, above a supply zone's high). An invalidated zone is dropped; it does not flip roles in v1.

### 3.2 Multi-touch levels (role reversal)

On W bars:

- A band of width 0.3 ATR(W) that holds at least 3 confirmed swing points of either kind, with at least 26 weeks between the first and the last.
- The level is the median of those swing prices; the band is their min to max.

### 3.3 Order blocks (SMC)

For each BOS or CHoCH on W or M:

- **Up break:** the order block is the last down bar (close < open) at or before the bar that made the protected low, searching back at most 3 bars. If none, it is the protected-low bar itself.
- **Down break:** the mirror, using the last up bar at or before the protected high.
- **Zone:** that bar's full range, low to high.
- **Mitigated** (kept, but counted as tested) when price trades back into it; **invalidated** by a close beyond its far edge.
- **Overfit risk:** the design marks order blocks as high risk. The definition above is the only one v1 uses; no variants.

### 3.4 Liquidity: EQH / EQL and poor highs / lows

On W and M:

- **EQH:** two or more confirmed swing highs within 0.1 ATR(TF) of each other, at least 5 bars apart, with no close above the highest of them in between. The level is the highest of them. **EQL:** the mirror, at the lowest.
- **Swept:** a later bar trades beyond the level and closes back inside. That is a LIQUIDITY_SWEEP event, and the level is retired.
- **Broken:** a later close beyond the level. The level is retired.
- Dalton's poor highs and lows are the same idea (resting orders at a clean edge). They are this family, not a separate one (design §2b).

### 3.5 Premium and discount

- **Dealing range** on TF: in `up`, from the protected low to the weak high; in `down`, from the weak low to the protected high.
- **Equilibrium:** 50% of the range. Above it is premium, below it is discount.
- The output adds the position in the range, from 0 to 100%.
- **Arbitrary:** the design flags this as depending on the range chosen. v1 uses only the range above.

## 4. Period pivots (Ochoa)

From the completed previous period's high H, low L and close C. Periods: week, month, quarter, year.

**Sources.** Checked on 2026-11-05 against the user's copy of *Secrets of a Pivot Boss*: Ch. 4 *Advanced Money Zone Concepts*, Ch. 6 *The Central Pivot Range*, Ch. 7 *Introducing the Camarilla Equation*, Ch. 8 *Advanced Camarilla Concepts*; then Ch. 3 *Introducing the Money Zone*, Ch. 5 (Floor Pivots), Appendix A *Floor Pivots Research* and Appendix B *Custom Code Library*; then Ch. 9 *Higher Timeframe Pivot Analysis*, Ch. 10 *Multiple Pivot Hot Zones* and Ch. 11 *Planning for Success*. Items cite the chapter, table, figure or code file. Where the book gives no rule, the text says the rule is v1's own. An earlier AI summary of the book got several points wrong (chapter numbers, "the last 3–10 sessions", the meaning of "unchanged", virgin CPR), so nothing in v1 rests on it.

- **Floor pivots** *(book: Ch. 5, Table 5.1 standard and Table 5.2 expanded)*:
  - Pivot = (H+L+C)/3;
  - R1 = 2 × Pivot − L, S1 = 2 × Pivot − H;
  - R2 = Pivot + (H−L), S2 = Pivot − (H−L);
  - R3 = R1 + (H−L), S3 = S1 − (H−L). This is algebraically the same as the existing map's H+2(P−L) and L−2(H−P);
  - R4 = R3 + (R2 − R1), S4 = S3 − (S1 − S2). Ochoa's own additions; he uses the expanded set "throughout the book".

  **v1 map levels:** Pivot, R1, R2, S1 and S2, the existing map's set. Ochoa's touch statistics (Appendix A) show the first layer reached on 73% of days and the second on 38%, with the outer layers rarer. R3, R4, S3 and S4 are computed and shown but kept out of clustering and out of the fidelity test, the same treatment as Camarilla H5/L5.
- **Ochoa's own evidence** (Appendix A): touch and close-beyond counts at each pivot layer, from 8 months of Mini Dow futures on intraday charts (Nov 2008–Jun 2009). They are frequencies with no placebo comparison, so they say how often price reaches a level, not whether the level turns price. They are not evidence of the kind the S8 tests require.
- **Central pivot range (CPR)** *(book: Ch. 6, Table 6.1)*:
  - Pivot = (H+L+C)/3;
  - BC = (H+L)/2;
  - TC = (Pivot − BC) + Pivot.

  The higher of the two is TC and the lower is BC; Ochoa's software makes this swap automatically.
- **CPR width** = (TC − BC) / P × 100.
  - Ochoa reads an *abnormally* narrow CPR as a likely trend or breakout and an abnormally wide one as a likely range. Width of average size tells you nothing (Ch. 6, *Pivot Width Forecasting*).
  - He quantifies it with his Pivot Range Histogram (Ch. 6; code `iPivotRangeHIST`, Appendix B): `fPivotRange = ((FLOOR_PIV(1) − FLOOR_PIV(−1)) / FLOOR_PIV(0)) × 100`, that is (TC − BC) / Pivot × 100, plotted on a 0–1 scale with markers at 0.25 and 0.75. So his thresholds are **absolute widths**: below 0.25% of price points to a trending day, above 0.75% to a sideways day, with 0.5% as the midline. They are not percentiles, and they are set for daily pivots.
  - **Daily CPR** (intraday layer, §8): Ochoa's absolute thresholds apply as written.
  - **Week, month, quarter and year: v1's own rule, not Ochoa's.** A week's or month's range is several times a day's, so his daily thresholds would label almost every period "wide". v1 uses the percentile rank of the width among the previous 20 periods of the same kind: narrow is ≤ 0.25, wide is ≥ 0.75, and anything between is "average, no reading". It borrows his cut points, not his formula. The raw width % is always recorded too.
  - **Ch. 9 reads long-period width relative to earlier periods, never against a fixed %:** the 2007 yearly range was "noticeably wider than that of 2006" (Fig. 9.6), a wide 1994 range led to a tight 1995 (Fig. 9.7), and April's monthly value area was "quite wide" (Fig. 9.8). A relative rule fits this; the percentile is still v1's own. Ch. 9 also names a cycle: "narrow pivots and trending markets usually pave the way for wide pivots and trading range markets" (before Fig. 9.11). This is recorded as a hypothesis, not a signal.
  - **Minimum history (v1's own):** a percentile reading needs at least 8 previous periods of the same kind (the window is still up to 20). Prices start on 2010-01-01, so yearly readings begin with 2019. With fewer than 8, no width reading is given; the raw width and the width ratio to the previous period (recorded with the two-period relationship) are the only record.
  - **A property of the formula:** TC − BC = |2C − H − L| / 3. The width measures how far the close sat from the middle of the period's range, not the size of the range. A wide-range period that closes mid-range gives a narrow CPR. Ochoa reads narrow as "the prior period was quiet"; whether that holds is for the signal test.
  - Recorded only, not used as a signal.
- **Two-period relationship** *(book: Ch. 6, Table 6.2 and Fig. 6.15; the same seven in Ch. 4 for value areas and Ch. 8 for Camarilla)*. The current range [BC, TC] against the previous one [pBC, pTC], the first rule that holds:
  1. **Unchanged:** "virtually unchanged". v1's tolerance: both edges within 10% of the previous width;
  2. **Higher value:** BC > pTC;
  3. **Lower value:** TC < pBC;
  4. **Outside:** TC > pTC and BC < pBC (the current range engulfs the previous one);
  5. **Inside:** TC < pTC and BC > pBC;
  6. **Overlapping higher:** TC > pTC and BC within [pBC, pTC];
  7. **Overlapping lower:** BC < pBC and TC within [pBC, pTC].

  Ochoa's biases (Table 6.2):
  - higher: bullish (the most bullish); overlapping higher: moderately bullish;
  - lower: bearish (the most bearish); overlapping lower: moderately bearish;
  - unchanged: sideways or breakout. It is the one relationship with two outcomes, quiet trade inside the range or a major breakout, and the open decides which;
  - outside: sideways, more telling when the current range is significantly wider;
  - inside: breakout (the most explosive), more telling when the current range is noticeably narrower.

  **His condition:** each bias is a starting point, confirmed or rejected by where the prior period closed against its pivot range and by the next open (Ch. 6: "the prior day's closing price and the current day's opening price"). The book uses two different "closed against the pivot range" comparisons, so v1 names both:
  - **Close against the CPR it creates** (Ch. 9, Fig. 9.13: "if price closes the prior month above the pivot range for the following month, continued trending behavior is likely"). **A property of the formula:** this CPR is built from the same H, L and C, and TC = (H + L + 4C)/6 when C is above the midpoint. So the close is above TC exactly when C > (H+L)/2, below BC exactly when C < (H+L)/2, and inside only when C sits on the midpoint. This comparison says only which half of its range the period closed in. v1 records it under that name ("close in upper/lower half").
  - **Close against the CPR in force during the period** (computed from the period before; Ch. 10, Fig. 10.7: "the prior session's closing price should fall above the prior day's central pivot range"): above TC, inside or below BC. This is the non-trivial reading, and the CPR trend below uses it.
  - **The next open against the CPR** (Ch. 9: the next month "must accept this theory by opening anywhere above the bottom of the pivot range"; Ch. 10, Fig. 10.7: open above the CPR) is acceptance at the start of the new period. It is an S7 situation (ACCEPTANCE), not a map level.

  v1 records the relationship, the width ratio to the previous range, and the two close readings above.

  **Same rule on two more ranges** (Ochoa: "these relationships are the same", Ch. 8): v1 also records the relationship of [VAL, VAH] against the previous value area (Ch. 4) and of [L3, H3] against the previous [L3, H3] (Ch. 8).

  Recorded only, never used as a signal. Whether the biases hold on NSE swing periods is a hypothesis for S7/S8.
- **CPR trend** *(book: Ch. 6, Pivot Range Trend Analysis, Figs 6.26–6.27)*. In a trend, price holds above BC (up) or below TC (down). A close beyond the range marks a trend change or a range. Ochoa says this works on any timeframe ("next day, month, or year").
  - v1 records, for week and month CPRs, the run of consecutive periods that closed above TC or below BC **of the CPR in force during that period**, and the date of the last close beyond the opposite edge. (Against the CPR a period creates, the run would only count closes in the upper half of the range; see above.)
  - Ch. 9 applies this to monthly CPRs (Figs 9.13–9.14: pull-backs to the monthly pivot range bought in uptrends), monthly money zones (Fig. 9.15: price held below the top of the money zone in a decline) and monthly Camarilla H3 (Fig. 9.16: "as long as price opens the month below H3, any pull-back to this zone should be a sell"). The levels are already in the map. The pull-back entries are S7 situations.
  - Recorded only. His trailing-centrals stop is an exit rule and stays out of the map.
- **Camarilla** *(book: Ch. 7, Table 7.2 "Expanded Formula")*, RANGE = H − L:
  - H1/L1 = C ± RANGE × 1.1/12;
  - H2/L2 = C ± RANGE × 1.1/6;
  - H3/L3 = C ± RANGE × 1.1/4;
  - H4/L4 = C ± RANGE × 1.1/2;
  - H5 = (H/L) × C, L5 = C − (H5 − C).

  How Ochoa reads them (Ch. 7):
  - H3/L3 are the reversal layer, where responsive traders push price back toward value;
  - H4/L4 are "the last line" and the breakout layer, and also "as prone to reversals as the third layer";
  - H5/L5 are targets after a break through H4/L4;
  - L1/L2/H1/H2 "are typically ignored and generally not even plotted".

  **The hidden layers** *(book: Ch. 8, The Hidden Layers, Figs 8.15–8.17; Ch. 9, Figs 9.11–9.12)*. Ch. 7's "typically ignored" has a stated exception. When the prior period's range was abnormally wide, so that the pivots are wide, Ochoa turns on H1, H2, L1 and L2. They "are always played for reversals just like the third layer" (Ch. 8). Ch. 9 does this on monthly pivots: a trending September gave October a wide third layer, and "every significant reversal during this month occurred off the hidden layers" (FSLR, Figs 9.11–9.12).

  **v1 map levels:** H3, H4, L3 and L4. H5/L5 are targets, not zones: they are computed and shown, but kept out of clustering and out of the fidelity test. H1, H2, L1 and L2 are computed and shown **only when that period's Camarilla width reads "wide"** (below), with the same treatment: out of clustering and out of the fidelity test. Otherwise they are left out.

  **Camarilla width** (Ch. 8, *Pivot Width Analysis*): the L3–H3 width, read like CPR width with the same percentile rule. Recorded only, apart from switching the hidden layers on.
- **Two profiles per period** (user, 2026-11-05: follow Ochoa's price-based method and keep the volume-based one too). Ochoa's Money Zone POC is price-based (time at price, Market Profile style). He treats the volume POC (VPOC) as a separate level that is "usually the same" but can differ (Ch. 4, *Understanding Volume at Price*). v1 computes both, and each is labelled with its kind:
  - **Money zone, price-based (Ochoa's)** *(book: Ch. 3, Figs 3.1–3.2; Ch. 4)*. "The Money Zone is derived solely from price-based, market-generated information" (Ch. 3). It takes the Market Profile's POC, VAH and VAL and draws them as levels for the next period:
    - **Time-price opportunities (TPOs):** each 30-minute segment of the session places one letter at every price it traded (Ch. 3, Fig. 3.1). v1 builds the weekly profile from 30-minute brackets of 5-minute bars, as the book describes.
    - **Month, quarter and year:** one TPO per daily bar, at every price that day traded. **This is v1's own adaptation:** the book builds the profile from intraday segments, and 5-minute bars don't go back far enough for long periods. Ch. 9 draws monthly Money Zone levels on daily charts (Figs 9.8–9.10, 9.15) but doesn't say how the monthly profile is built, and it has no quarterly or yearly money zone. So the rule stays v1's own, and the quarterly and yearly money zones are v1's extension, labelled so.
    - **POC** (Ch. 3): "the longest line of TPOs nearest to the center of the entire structure". So it's the bucket with the most TPOs, and on a tie, the one nearest the middle of the period's range.
    - **Value area** (Ch. 3): where 70% of the period's activity took place. The book doesn't give the growth procedure. v1 grows from the POC toward the heavier neighbour until 70% of TPOs are inside, the Market Profile convention and the same rule as the volume profile.
  - **Volume profile (VPOC)**: POC, VAL and VAH from volume at price, with a 70% value area (the existing `value_area` rule). Ochoa's volume at price "divides volume equally across all of the price points that were reached during a specific period", and the VPOC is its longest line (Ch. 3, *Volume at Price*, Fig. 3.7). That matches how QuantOS spreads each bar's volume.
  - **Bars:** both profiles use the same buckets (`step_for(ATR(D))`). Month, quarter and year come from daily bars. The week comes from 5-minute bars, only where those exist (the last 100 days); otherwise a weekly profile is not computed.
  - **One family:** both profiles belong to the volume family (§6). When the price-based and volume-based levels agree, they count once and never make a strong zone on their own.
  - **Width and two-period relationships** use the price-based value area, since that is the one Ochoa reads (Ch. 4). An abnormally wide or narrow value area carries the same reading as CPR width (Ch. 4, *Value Area Width*), with the same percentile rule. The same two figures are also recorded for the volume value area, so the two can be compared.
- **Virgin money-zone levels** *(book: Ch. 4, Virgin Money Zone Levels, Figs 4.18–4.19; The Virgin Volume Point of Control, Fig. 4.24)*. Ochoa: "A Money Zone level that was never touched during its session of origin is called a virgin Money Zone level", also called a naked level; "A VPOC that is not touched during its session of origin is called a Virgin Volume Point of Control."
  - He treats them like unfilled gaps that attract price. The first test usually turns price back toward value.
  - Timing: price "will usually return to a virgin VPOC and test it within a week of its creation", and "the farther price moves away from this level, or the longer price stays away from it, the less significance the level will carry" (Ch. 4).
  - **Both kinds:** virgin Money Zone levels (price-based POC, VAH, VAL) and virgin VPOCs (volume-based) are tracked separately, each labelled with its kind. The book names both.
  - **Operational rule:** a period's POC, VAH or VAL is virgin from the period's close until a later bar trades through it. That bar retires the level, and the fill date is recorded. His phrase "during its session of origin" can't be computed from a profile built from that same session, so v1 uses the usual naked-level reading.
  - **Which levels:** Ochoa watches two of the three: the virgin POC, and whichever of the virgin VAH or VAL is closest to price. v1 records all three and flags those two.
  - **Age and distance:** every virgin level carries its age in periods and its distance in ATR, with no cutoff. Ochoa says significance fades but gives no number, so the signal test scores by age instead.
  - **Periods:** week, month, quarter and year, from the same profiles as the money zone. Daily virgin levels belong to the intraday layer (§8).
  - **Family:** volume (§6). His first-sixty-minutes timing rule is intraday execution and stays out of v1.
- **Periods** *(book: Ch. 9, Types of Higher Timeframe Pivots; Table 10.1)*. Ochoa applies the CPR and Camarilla to any timeframe (Ch. 5: "the prior day (or week, month, and year)"; Ch. 6; Ch. 7: "quite powerful for all timeframes"; his CPR code takes a daily or monthly periodicity, `iCentralPivotRange`, Appendix B). Ch. 9 names three higher-timeframe periods, weekly, monthly and yearly, each from the prior period's H, L and C (the week runs Monday to Friday). Each draws a different group of traders:
  - weekly pivots: swing traders (two- to three-day swings, Fig. 9.5);
  - monthly pivots: position and swing traders, "moves range anywhere from a week to several months" (Figs 9.3–9.4);
  - yearly pivots: investors (Figs 9.1–9.2).

  Table 10.1 sets out the same roles (investors: yearly; position traders: monthly; swing traders: weekly; day traders: intraday). A higher period's pivot is a price level on any lower chart: "yearly pivots can be played in all timeframes from intraday to weekly, while monthly pivots can be used in intraday and daily charts" (Ch. 9, Fig. 9.12).
  - **v1:** week and month make the swing horizon, and the year is the backdrop. This follows the book's roles.
  - **The quarter is not Ochoa's.** Ch. 9 has no quarterly pivot. v1 keeps it from the design (L1: quarterly and yearly pivots) as part of the backdrop, labelled "not Ochoa" wherever it is shown.
  - The read labels each pivot with its period.

## 5. Long composite volume profile

- Daily bars over the last **250** and the last **750** sessions, as two profiles. Each day's volume is spread evenly over its range.
- Bucket size: the existing `step_for(ATR(D))`.
- **POC and value area:** 70%, the existing rule.
- **HVN shelves:** runs of buckets at 1.5× the median or more (the existing `shelves` rule).
- **LVN:** runs of buckets below 0.5× the median, lying between two HVN shelves.
- Ochoa's high- and low-volume areas are the same idea: price moves freely between volume peaks, and a low-volume area between two peaks "can be easily penetrated" (book: Ch. 4, *Understanding Volume at Price*, Figs 4.21–4.22).
- Labelled "approximation (daily bars)" wherever shown.

## 6. Families and the HTF strong zone

Agreement counts once per family (design §2b: ideas that appear in two frameworks are one family).

| Family | Members |
|---|---|
| structure | swing highs/lows (§1), protected and weak levels (§2), multi-touch levels (§3.2) |
| imbalance | demand/supply zones (§3.1), order blocks (§3.3), LVN edges (§5) |
| liquidity | EQH/EQL and poor highs/lows (§3.4) |
| volume | price-based money zones and volume profiles (POC, VAL/VAH), their virgin levels, HVN shelves (§4, §5) |
| pivot | classical, CPR and Camarilla, all periods (§4); one family, as they are all formulas of H, L and C |

- **HTF zone:** levels and bands from M and W clustered within 0.3 ATR(W). The same clustering as the existing map, at the weekly scale.
- **HTF strong zone:** at least 2 families. There are no weights in v1: families are counted, not scored.
- Each element keeps its timeframe, family, date and source, so the S4 signal test can score every family separately.

## 7. Alignment and stage

- **ALIGNMENT:** the §2 state on M, W and D.
  - "Aligned up": all three are `up`. "Aligned down": all three are `down`.
  - Otherwise the output names the timeframe(s) that conflict.
- **Weinstein stage:** `core/vault/stages.py` as built. It isn't redefined here.

## 8. Not in v1

- Intraday items: opening range, initial balance, open types, daily CPR and daily Camarilla, daily virgin money-zone levels, the developing pivot range, the magnet trade (Ch. 6) and the Unchanged VPOC relationship (Ch. 4). These belong to the intraday phase.
- Camarilla H1/H2/L1/L2 outside a wide period, and H5/L5 as clustered map levels (see §4).
- Ochoa's candlestick reversal setups and indicator chapters: they are entry triggers, not map levels.
- Role reversal of invalidated zones.
- "Virgin CPR": not in Ochoa (his virgin levels are money-zone levels, Ch. 4). Left out.
- CPR against the previous value area: not found in Ch. 4 or 6–8. It came from the AI summary, so it is left out.
- Weights between families.
- Any bias read as a signal.

## 9. Fidelity test (pre-registered here, run on the golden set)

**Charts.** 10 to 20 charts the user marks without reading this document. Stocks and indices, across uptrends, downtrends and ranges. Each chart has a symbol, a timeframe and an as-of date. HDFCBANK and SUPREMEIND are excluded from scoring.

**Matching:**
- A user mark (a level or a zone, with a type) **matches** if an engine element of the mapped family overlaps it, or has an edge within 0.25 ATR(chart TF) of it, on the chart's as-of date.
- Type mapping:

| User mark types | Engine family |
|---|---|
| demand, supply, base | imbalance |
| strong or weak low/high, swing | structure |
| EQH, EQL, poor high/low | liquidity |
| POC, value area, money zone, virgin/naked POC, VAH or VAL | volume |
| pivot, CPR, Camarilla | pivot |

- A mark with no listed type is matched against any family, and reported separately.

**Measures:**
- **Recall:** the share of the user's marks matched, overall, per family, and for marks the user would act on.
- **Precision:** the share of engine HTF strong zones inside the chart's visible price range that match a user mark.

**Pass, all three:**
1. Recall of every mark ≥ 70%.
2. Recall of marks the user would act on ≥ 80%.
3. Precision ≥ 50%.

**If it fails:** the result is reported as a fail, with every miss listed. v2 is written from the misses and the concepts, and scored on a fresh set of charts.

Fidelity says only that the engine sees what the user sees. Whether those zones turn price is the separate signal test (pre-registration to follow, before any L1 code).
