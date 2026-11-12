# Market Map: definitions v3 (written 2026-11-13, before any v3 code)

v3 is v2 (`docs/MARKET_MAP_DEFINITIONS_V2.md`) with the changes below. v2 is itself v1 (`docs/MARKET_MAP_DEFINITIONS.md`) with amendments. Every section not named here is unchanged. v1 and v2 stay in the repo as the record.

**Why v3 exists.** v2 cut the strong share from a median of 78% to 53% across the 15 round 1 reads. The zones still tile nearly the whole price range around the price, so on most days the price is "at a level". KEI R01 went from 41 zones to 68. A map like that cannot beat a placebo of random levels in the S8 test, because random levels also land near a zone. On 2026-11-13 the user chose four changes, taken from how SMC charts draw zones (the LuxAlgo Smart Money Concepts indicator on the user's charts), not from any outcome:
1. two layers: zones from price action only; pivots and volume become a levels layer;
2. mitigation: used zones leave the map;
3. strong means fresh and at a break;
4. coverage is reported, not targeted;
5. fair-value gaps (H5), added by the user the same day, before any code.

v3 follows the same rules as v1 and v2:
- **Rules come from the concepts, not from marks or outcomes.** No parameter here was set from prices after an as-of date, from the golden set, or from the KEI 2026 chart discussed on 2026-11-13.
- **This file is committed before the code.** Anything the code needs that this file leaves open is written in the module's docstring.
- **The 15 round 1 reads are regenerated under v3** for the user to look at, with side-by-side charts against the SMC indicator on 3–4 stocks. They are not a fidelity test.
- **Round 2 (§9) is skipped** (user, 2026-11-13): more review rounds check drawing, not edge. The map stays labelled **untested** until the S8 tests report.

Untested. Markers, never signals.

## H1. Two layers: zones and levels (amends v1 §6 and v2 G2)

**The miss.** Pivots (classical, CPR, Camarilla, all periods) and volume levels (POC, VAH, VAL, virgin levels, HVN and LVN edges) exist for every period by formula. Clustered into the zone list, they land near almost any price, whatever price itself did.

**v3 rules:**
- **Zones** are built only from levels where price itself turned, left a base or left resting orders:

  | Family | Members in v3 zones |
  |---|---|
  | structure | W and M swings not yet broken by a close (v2 G2), the protected and weak levels (v2 G1), multi-touch levels (§3.2) |
  | imbalance | demand and supply zones (§3.1), order blocks (§3.3) |
  | liquidity | W and M EQH/EQL (§3.4, v2 G3) |

- **LVN edges leave the imbalance family.** They come from the volume profile, so they belong to the levels layer with the other volume levels.
- **The levels layer** holds everything else the map computes: the §4 period pivots and profiles, the virgin `watch` levels (v2 G5), the §5 long-profile POC, VA, HVN and LVN edges, and Ochoa's hot zones (§6.1, unchanged). The read keeps showing them as now (the `P.`, `V.` and `H.` lines). **They never create a zone and never widen one.** They are used for one thing in the zone layer: the confluence check in H3.
- **Clustering is unchanged** for what is left (v2 G2): bands keep their range and never merge; a point level within 0.3 ATR(W) of a cluster's last level joins it; a point cluster stays at most 0.45 ATR(W) wide; a point cluster within 0.3 ATR(W) of a band joins the nearest band.
- **Each element still keeps** its timeframe, family, date and source, so S8 can score every family separately, including the levels layer on its own.

## H2. Mitigation: used zones leave the map (amends v1 §3.1, §3.3)

**The miss.** v1 dropped a demand or supply zone only on a close beyond its far edge, on its own timeframe's bars. It kept a mitigated order block on the map, counted as tested. So zones that price had already traded through stayed listed for years.

**The concept.** In SMC, a zone's resting orders are filled the first time price returns to it. A zone that has been returned to is weaker, and one that price has closed through is spent.

**v3 rules, for bands (demand and supply §3.1, order blocks §3.3):**
- **Broken:** a **daily close** beyond the zone's far edge (below a demand zone or bullish order block; above a supply zone or bearish order block). The zone is removed. v1 used a W or M close for this; a daily close is the stricter, SMC-style test.
- **Touch:** after the zone is formed, a run of consecutive daily bars that trade into the zone counts as **one** touch. The run ends at the first daily bar whose range is entirely outside the zone.
  - For §3.1 zones, touches count only after price first left the zone by 2 ATR(TF), as in v1.
  - For order blocks, touches count from the bar after the break that made the block.
- **Tested once:** a zone with one touch and no break is kept and labelled "tested once".
- **Removed on the second touch.** The zone is spent.
- Removed zones are kept in the element store with the date and the reason (`broken` or `spent`), so S8 can test the rule itself. They do not appear in the read.

**Not changed:**
- Swings already leave the zones when broken by a close (v2 G2).
- EQH/EQL already retire when swept or broken (§3.4).
- Multi-touch levels (§3.2) are many touches by definition. The tested-once rule does not apply to them. They stay until a W close beyond the band, as in v2.

## H3. The strong zone: fresh, at a break, with confluence (replaces v1 §6's strong rule and v2 G2's)

**The miss.** Counting two families made half the zones strong, because pivot and volume levels agree with almost anything.

**v3 rule.** A zone is **strong** when all three hold:
1. **At a break.** It contains an order block (§3.3, which by definition comes from a BOS or CHoCH on W or M), or a demand or supply zone (§3.1) whose departure window (the base and the 3 bars after it) contains a BOS or CHoCH on the same timeframe in the departure's direction.
2. **Fresh.** That band has no touch (H2): price has not returned to it since it was formed.
3. **Confluence.** At least one level from the levels layer (H1) lies inside the zone or within 0.3 ATR(W) of either edge.

All other zones are shown as ordinary zones. Family counts are still recorded per zone, without weights.

## H4. Coverage is reported, not targeted (new)

After each regeneration, the report gives, per read and as the median across reads:
- the number of zones and of strong zones;
- **coverage:** the share of the window from price − 3 ATR(W) to price + 3 ATR(W) that lies inside at least one zone, and the same share for strong zones.

These are descriptions. No parameter in v1, v2 or v3 is set or changed from them. If coverage stays high, that is reported, and any further change is a v4 written the same way as this file.

## H5. Fair-value gaps (new; added by the user 2026-11-13, before any v3 code)

**The concept.** In SMC, a fair-value gap is a three-bar imbalance: the middle bar moved so fast that the bars on either side of it don't overlap. Price that left a gap has unfilled orders there until it returns.

**v3 rules, on W and M bars** (the HTF map; D gaps stay out, as D structure does under v1 §0):
- **Bullish FVG** at bar *i*: the low of bar *i* is above the high of bar *i* − 2. The gap runs from the high of *i* − 2 to the low of *i*.
- **Bearish FVG:** the mirror. The high of bar *i* is below the low of bar *i* − 2, and the gap runs from the high of *i* to the low of *i* − 2.
- **Minimum size:** the gap is at least 0.1 ATR(TF), with the ATR at bar *i*. This is the same tolerance §3.4 uses for "equal", so a gap smaller than that counts as no gap.
- **Family:** imbalance. It enters the zones as a band (v2 G2: never split, never merged with another band).
- **Filled and removed:** a gap leaves the map once a daily bar trades to its far edge. That means a daily low at or below the bottom of a bullish gap, or a daily high at or above the top of a bearish one.
- **Partly filled:** what is left of it stays. A bullish gap's top moves down to the lowest daily low since it formed, and a bearish gap's bottom moves up to the highest daily high.
- H2's tested-once rule does not apply to gaps. Filling is their mitigation.
- Filled gaps are kept in the element store with the date, as H2 does for removed bands.
- **Strong:** a gap is not a break origin under H3.1. It can sit in a strong zone, but it does not make one strong.

## What is not in v3

- FVGs on D bars.
- No cap on the number of zones shown. The read already lists the nearest 3 above and below.
- No change to swings (§1, v2 G3), structure (v2 G1), sweeps and failed breaks (v2 G4), §4's pivot and profile rules, §5, §7 alignment, or §8's out-of-scope list.
- No weights between families.
- No signals. Zones, sweeps, failed breaks and alignment remain markers.
