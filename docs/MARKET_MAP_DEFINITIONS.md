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

**Sources.** Checked on 2026-11-05 against the user's copy of *Secrets of a Pivot Boss*: Ch. 4 *Advanced Money Zone Concepts*, Ch. 6 *The Central Pivot Range*, Ch. 7 *Introducing the Camarilla Equation*, Ch. 8 *Advanced Camarilla Concepts*. Items cite the chapter, table or figure. Items marked *(not yet checked)* come from parts of the book not provided yet: the Floor Pivots and Money Zone construction chapters (Ch. 5 and 3, by the book's own cross-references) and Appendix B (indicator code). An earlier AI summary of the book got several points wrong (chapter numbers, "the last 3–10 sessions", the meaning of "unchanged", virgin CPR), so nothing in v1 rests on it.

- **Classical floor pivots** *(not yet checked: Ch. 5)*, as in the existing map:
  - P = (H+L+C)/3;
  - R1 = 2P−L, S1 = 2P−H;
  - R2 = P+(H−L), S2 = P−(H−L);
  - R3 = H+2(P−L), S3 = L−2(H−P).
- **Central pivot range (CPR)** *(book: Ch. 6, Table 6.1)*:
  - Pivot = (H+L+C)/3;
  - BC = (H+L)/2;
  - TC = (Pivot − BC) + Pivot.

  The higher of the two is TC and the lower is BC; Ochoa's software makes this swap automatically.
- **CPR width** = (TC − BC) / P × 100.
  - Ochoa reads an *abnormally* narrow CPR as a likely trend or breakout and an abnormally wide one as a likely range. Width of average size tells you nothing (Ch. 6, *Pivot Width Forecasting*).
  - He quantifies it with his Pivot Range Histogram: below 0.25 means trending is more likely, above 0.75 means sideways is more likely, with 0.5 as the midline (Ch. 6, *The Pivot Range Histogram*). Its code is in Appendix B *(not yet checked)*.
  - **v1 reading:** the percentile rank of the width among the previous 20 periods of the same kind. Narrow is ≤ 0.25, wide is ≥ 0.75, and anything between is "average, no reading". The thresholds are Ochoa's. The percentile-rank form and the 20-period window are v1's own until Appendix B shows his formula.
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

  **His condition:** each bias is a starting point, confirmed or rejected by where the prior period closed against its pivot range and by the next open. v1 records the relationship, the width ratio to the previous range, and where the period's close sits against its own CPR (above TC, inside, below BC).

  **Same rule on two more ranges** (Ochoa: "these relationships are the same", Ch. 8): v1 also records the relationship of [VAL, VAH] against the previous value area (Ch. 4) and of [L3, H3] against the previous [L3, H3] (Ch. 8).

  Recorded only, never used as a signal. Whether the biases hold on NSE swing periods is a hypothesis for S7/S8.
- **CPR trend** *(book: Ch. 6, Pivot Range Trend Analysis, Figs 6.26–6.27)*. In a trend, price holds above BC (up) or below TC (down). A close beyond the range marks a trend change or a range. Ochoa says this works on any timeframe ("next day, month, or year").
  - v1 records, for week and month CPRs, the run of consecutive periods that closed above TC or below BC, and the date of the last close beyond the opposite edge.
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

  **v1 map levels:** H3, H4, L3 and L4 only. H5/L5 are targets, not zones: they are computed and shown, but kept out of clustering and out of the fidelity test. H1, H2, L1 and L2 are left out.

  **Camarilla width** (Ch. 8, *Pivot Width Analysis*): the L3–H3 width, read like CPR width with the same percentile rule. Recorded only.
- **Money zone** (the period's value area) *(book: Ch. 4, 70% of the activity; construction in Ch. 3, not yet checked)*:
  - POC, VAL and VAH, with a value area of 70% around the POC (the existing `value_area` rule);
  - month, quarter and year come from daily bars. The week comes from 5-minute bars, and only where those exist (the last 100 days); a weekly money zone is otherwise not computed;
  - **Caveat:** QuantOS builds these from **volume** at price. Ochoa's Money Zone POC is price-based (Market Profile time at price), and he treats the volume POC (VPOC) as a separate level that is "usually the same" but can differ (Ch. 4, *Understanding Volume at Price*). v1 labels them "volume-based".
  - **Value-area width:** an abnormally wide or narrow value area carries the same reading as CPR width (Ch. 4, *Value Area Width*). Recorded with the same percentile rule.
- **Virgin money-zone levels** *(book: Ch. 4, Virgin Money Zone Levels, Figs 4.18–4.19; The Virgin Volume Point of Control, Fig. 4.24)*. Ochoa: "A Money Zone level that was never touched during its session of origin is called a virgin Money Zone level", also called a naked level; "A VPOC that is not touched during its session of origin is called a Virgin Volume Point of Control."
  - He treats them like unfilled gaps that attract price. The first test usually turns price back toward value.
  - Timing: price "will usually return to a virgin VPOC and test it within a week of its creation", and "the farther price moves away from this level, or the longer price stays away from it, the less significance the level will carry" (Ch. 4).
  - **Operational rule:** a period's POC, VAH or VAL is virgin from the period's close until a later bar trades through it. That bar retires the level, and the fill date is recorded. His phrase "during its session of origin" can't be computed from a profile built from that same session, so v1 uses the usual naked-level reading.
  - **Which levels:** Ochoa watches two of the three: the virgin POC, and whichever of the virgin VAH or VAL is closest to price. v1 records all three and flags those two.
  - **Age and distance:** every virgin level carries its age in periods and its distance in ATR, with no cutoff. Ochoa says significance fades but gives no number, so the signal test scores by age instead.
  - **Periods:** week, month, quarter and year, from the same profiles as the money zone. Daily virgin levels belong to the intraday layer (§8).
  - **Family:** volume (§6). His first-sixty-minutes timing rule is intraday execution and stays out of v1.
- **Periods.** Ochoa applies the CPR and Camarilla to any timeframe (Ch. 6; Ch. 7: "quite powerful for all timeframes"). The book doesn't assign periods to roles: the split here (week and month for the swing horizon, quarter and year for the backdrop) is v1's own. The read labels each pivot with its period.

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
| volume | POC, VAL/VAH, HVN shelves, money zones, virgin money zone levels (§4, §5) |
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
- Camarilla H1/H2/L1/L2, and H5/L5 as map levels (see §4).
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
