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

- **Classical** (as in the existing map):
  - P = (H+L+C)/3;
  - R1 = 2P−L, S1 = 2P−H;
  - R2 = P+(H−L), S2 = P−(H−L);
  - R3 = H+2(P−L), S3 = L−2(H−P).
- **CPR:**
  - pivot P;
  - BC = (H+L)/2;
  - TC = 2P − BC.

  If BC > TC, swap them, so that TC is the upper edge.
  - **Width** = (TC − BC) / P × 100.
  - **Narrow:** width below the 25th percentile of the previous 10 periods of the same kind. **Wide:** above the 75th percentile.
  - Ochoa gives no number. He compares the width with the last 3 to 10 sessions by eye (Ch. 3, per the user 2026-11-04). v1 encodes that comparison as percentiles over his longer window, 10 periods.
  - Ochoa's reading: narrow means a trending period is likely, wide means a range. v1 records narrow or wide and does not use it as a signal.
- **Virgin CPR** (Ochoa Ch. 6). The CPR in force during a period is virgin if no bar of that period traded into [BC, TC].
  - It stays a level until a later bar trades into it. That bar retires it, and the touch date is recorded.
  - Computed for week and month CPRs, from daily bars.
  - Ochoa reads it as a magnet and as support or resistance. v1 records it as a level in the pivot family; whether it attracts price is for the signal test.
- **Two-period relationship.** The CPR of the current period ([BC, TC]) against the one before it ([pBC, pTC]), the first rule that holds:
  1. **Unchanged:** both edges within 10% of the previous width;
  2. **Higher value:** BC > pTC;
  3. **Lower value:** TC < pBC;
  4. **Outside:** TC > pTC and BC < pBC;
  5. **Inside:** TC < pTC and BC > pBC;
  6. **Overlapping higher:** TC > pTC (and BC within [pBC, pTC]);
  7. **Overlapping lower:** BC < pBC (and TC within [pBC, pTC]).

  Ochoa reads these as bias (Ch. 3, checked by the user 2026-11-04):
  - higher: bullish; overlapping higher: moderately bullish;
  - lower: bearish; overlapping lower: moderately bearish;
  - outside: sideways, a two-way auction;
  - inside: volatility expansion or breakout likely;
  - unchanged: consolidation or accumulation before a move.

  Ochoa names "unchanged" without a numeric tolerance. The 10%-of-width tolerance in rule 1 is the v1 adaptation.

  v1 **records** the relationship and does not encode the bias as a signal. The bias is a hypothesis for S7/S8.
- **Camarilla** (as in the existing map):
  - H3 = C + 1.1(H−L)/4;
  - H4 = C + 1.1(H−L)/2;
  - L3 = C − 1.1(H−L)/4;
  - L4 = C − 1.1(H−L)/2.

  In Ochoa's reading, H3/L3 bound the reversal (mean-reversion) range and H4/L4 are the breakout levels (Ch. 4).
  - H1/H2/L1/L2 are minor intraday reaction levels, so they stay out of the swing map.
  - H5/L5 (extreme trend targets) are left out of v1: they are targets, not zones, and their formula differs between sources. They can be added in v2 with the formula from the book.
- **Money zone** (Ochoa's value area for the period):
  - POC, VAL and VAH of the period's volume profile (§5 method), with a value area of 70% around the POC (the existing `value_area` rule);
  - month, quarter and year come from daily bars;
  - the week comes from 5-minute bars, and only where those exist (the last 100 days);
  - a weekly money zone is otherwise not computed.
- **CPR against the money zone** (Ochoa Ch. 5). For each period, v1 records where the current CPR sits against the previous period's value area: inside it, above it, below it, or overlapping an edge. It is recorded only, not used as a signal.
- **Periods** (Ochoa Ch. 8): week and month pivots are the swing horizon (1–20 days); quarter and year pivots are the macro backdrop. The read labels each pivot with its period.

## 5. Long composite volume profile

- Daily bars over the last **250** and the last **750** sessions, as two profiles. Each day's volume is spread evenly over its range.
- Bucket size: the existing `step_for(ATR(D))`.
- **POC and value area:** 70%, the existing rule.
- **HVN shelves:** runs of buckets at 1.5× the median or more (the existing `shelves` rule).
- **LVN:** runs of buckets below 0.5× the median, lying between two HVN shelves.
- Labelled "approximation (daily bars)" wherever shown.

## 6. Families and the HTF strong zone

Agreement counts once per family (design §2b: ideas that appear in two frameworks are one family).

| Family | Members |
|---|---|
| structure | swing highs/lows (§1), protected and weak levels (§2), multi-touch levels (§3.2) |
| imbalance | demand/supply zones (§3.1), order blocks (§3.3), LVN edges (§5) |
| liquidity | EQH/EQL and poor highs/lows (§3.4) |
| volume | POC, VAL/VAH, HVN shelves, money zones (§4, §5) |
| pivot | classical, CPR, virgin CPR and Camarilla, all periods (§4); one family, as they are all formulas of H, L and C |

- **HTF zone:** levels and bands from M and W clustered within 0.3 ATR(W). The same clustering as the existing map, at the weekly scale.
- **HTF strong zone:** at least 2 families. There are no weights in v1: families are counted, not scored.
- Each element keeps its timeframe, family, date and source, so the S4 signal test can score every family separately.

## 7. Alignment and stage

- **ALIGNMENT:** the §2 state on M, W and D.
  - "Aligned up": all three are `up`. "Aligned down": all three are `down`.
  - Otherwise the output names the timeframe(s) that conflict.
- **Weinstein stage:** `core/vault/stages.py` as built. It isn't redefined here.

## 8. Not in v1

- Intraday items: opening range, initial balance, open types, daily CPR, developing pivots, Camarilla H1/H2/L1/L2. These belong to the intraday phase.
- Camarilla H5/L5 (see §4).
- Ochoa's candlestick reversal setups and indicator chapters: they are entry triggers, not map levels.
- Role reversal of invalidated zones.
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
| POC, value area, money zone | volume |
| pivot, CPR, virgin CPR, Camarilla | pivot |

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
