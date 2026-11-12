# What changed in the 15 reads under definitions v3 (2026-11-13)

Same 15 picks as round 1 (seed 20261108). v2 = code 5f6deb5; v3 = code f7bfa2b (definitions `docs/MARKET_MAP_DEFINITIONS_V3.md`, bc46784 + ba6825c). Both runs were made on the VM from scratch copies (`~/v2_run`, `~/v3_run`), reading the live stores read-only. Both were measured with the same H4 coverage formula (`htf.coverage`), so the v2 column is v2's zones under v3's yardstick.

These are descriptions (v3 H4). No parameter was set or changed from them.

## Per read

"Near" = zones meeting the window price ± 3 ATR(W). Coverage = the share of that window inside at least one zone.

| Read | Zones (all) | Strong share | Near zones | Near strong | Coverage | Strong coverage | FVGs kept | Removed (H2/H5) |
|---|---|---|---|---|---|---|---|---|
| R01 KEI | 68 → 84 | 43% → 40% | 13 → 8 | 9 → 4 | 83.8% → **45.6%** | 58.4% → **23.9%** | 42 | 108 |
| R02 DMART | 40 → 38 | 85% → 34% | 13 → 10 | 13 → 0 | 92.2% → **20.3%** | 92.2% → **0%** | 13 | 118 |
| R03 JSL | 45 → 54 | 51% → 43% | 8 → 6 | 5 → 2 | 81.7% → **34.3%** | 67.3% → **34.3%** | 27 | 94 |
| R04 LTM | 36 → 44 | 69% → 36% | 6 → 9 | 4 → 1 | 87.9% → **38%** | 74.2% → **8.2%** | 25 | 90 |
| R05 HCLTECH | 62 → 64 | 53% → 34% | 10 → 6 | 3 → 1 | 78.6% → **58.4%** | 38.7% → **10.7%** | 36 | 128 |
| R06 ANTELOPUS | 33 → 31 | 48% → 32% | 9 → 6 | 6 → 2 | 82.8% → **9.6%** | 70.2% → **9.4%** | 13 | 141 |
| R07 NEOGEN | 30 → 25 | 70% → 52% | 8 → 3 | 4 → 1 | 68.1% → **13.5%** | 54.3% → **13.5%** | 7 | 57 |
| R08 GRSE | 43 → 52 | 42% → 38% | 4 → 6 | 3 → 1 | 89.7% → **24%** | 89.7% → **14.5%** | 22 | 71 |
| R09 IRFC | 35 → 45 | 63% → 36% | 6 → 6 | 6 → 0 | 89.8% → **46.3%** | 89.8% → **0%** | 22 | 30 |
| R10 TEJASNET | 39 → 53 | 46% → 38% | 8 → 8 | 6 → 3 | 88.6% → **62.2%** | 81.8% → **33.8%** | 26 | 52 |
| R11 BIOCON | 43 → 50 | 67% → 30% | 9 → 10 | 9 → 2 | 99.8% → **44.9%** | 99.8% → **23.9%** | 20 | 139 |
| R12 SSWL | 46 → 49 | 48% → 41% | 7 → 8 | 5 → 2 | 95% → **19%** | 81.1% → **10.5%** | 24 | 111 |
| R13 BLUESTARCO | 58 → 64 | 62% → 38% | 8 → 7 | 5 → 1 | 87.1% → **33.9%** | 67% → **24.7%** | 34 | 110 |
| R14 NBCC | 34 → 42 | 50% → 33% | 6 → 4 | 4 → 0 | 89.9% → **76.8%** | 82.5% → **0%** | 23 | 154 |
| R15 CHOLAFIN | 61 → 71 | 54% → 34% | 9 → 7 | 3 → 1 | 86.9% → **43%** | 47.7% → **14.4%** | 38 | 91 |
**Medians across the 15 reads, v2 → v3:**
- coverage: 87.9% → **38.0%**;
- strong coverage: 74.2% → **13.5%**;
- strong share: 53% → 36%;
- near strong zones: 5 → **1**. Three reads (DMART, IRFC, NBCC) have no strong zone in the window;
- near zones: 8 → 7. The number of zones near the price hardly moved. Coverage fell because zones got narrower: pivot and volume clusters no longer widen them (H1);
- all zones: 43 → 50. Gaps add many. Most of them sit far from the price, unfilled since an old trend leg (KEI keeps 42 of its 139 gaps).

## Removals (H2, H5)

From 30 (IRFC) to 154 (NBCC) zones per read are removed. Most removals are filled gaps. KEI: 97 gaps filled, 9 bull OBs and 1 bear OB spent on a second touch, 1 bull OB broken by a daily close. Every removed zone is kept in `l1["zones_removed"]` with its reason and date.

## Findings (reported; any change is a v4, written first)

1. **H3's confluence condition does not select.** 765 of 766 zones across the 15 reads have a pivot or volume level within 0.3 ATR(W). The levels layer is dense enough that a level is almost always nearby. This is the same reason pivots and volume made v1's strong flag non-selective. Under v3, all the selectivity comes from "fresh" and "at a break".
2. **The nearest strong zone can be far away.** Distance from the price, in ATR(W), to the nearest strong zone:

   | Read | Below | Above |
   |---|---|---|
   | R01 KEI | 6.3 (M bull OB 2022-12, 54% away) | 1.0 |
   | R02 DMART | 3.4 | 3.4 |
   | R03 JSL | 0.9 | none |
   | R04 LTM | 2.3 | 5.1 |
   | R05 HCLTECH | 0.5 | none |
   | R06 ANTELOPUS | 2.4 | none |
   | R07 NEOGEN | 1.0 | none |
   | R08 GRSE | 1.6 | none |
   | R09 IRFC | 3.9 | 6.0 |
   | R10 TEJASNET | 1.8 | 2.2 |
   | R11 BIOCON | 6.7 | 1.6 |
   | R12 SSWL | 2.4 | none |
   | R13 BLUESTARCO | 5.1 | 1.5 |
   | R14 NBCC | 3.5 | none |
   | R15 CHOLAFIN | 0.7 | 3.4 |

   Eight reads have no strong zone above. Either price is at or near its highs, or every supply zone above it has been touched or broken. This is what an SMC chart shows too: no fresh supply above a market that has taken it out.
3. **Monthly order blocks are wide.** An M order block is a whole month's range, for example KEI's 4141–4706 (565 points, about 1.9 ATR(W)). Such a zone overlaps W blocks and swings, so it still covers a lot of the window by itself.
4. **No zone around the price for KEI.** v2 had price inside 3483.75–3620, made of imbalance, volume and pivot. Under v3 the nearest zones are a W bull FVG at 3128.5–3332.9 below and the W supply at 3875.5–3964.85 above. The D structure near the price (the 3522.7 BOS, the 3411.4 protected low) stays out of the HTF map (v1 §0).

## Next

Side-by-side charts against the SMC indicator on 3–4 stocks. Then deploy (v2 was never deployed). Then S8, which also tests the mitigation rule itself, from `zones_removed`.
