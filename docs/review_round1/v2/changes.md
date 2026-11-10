# What changed in the 15 reads (2026-11-11)

Two steps, listed separately: the code-bug fixes alone (v1 + fixes against v1), then definitions v2 (against v1 + fixes). Full texts: `../reads.md` (v1) and `reads.md` (v2).

## 1. The two code-bug fixes (cd98683)

| Read | Items changed |
|---|---|
| R03 JSL | 1: L2.virgin |
| R06 ANTELOPUS | 1: L2.virgin |
| R09 IRFC | 11: H.hot, L2.virgin, V.long, V.periods, V.virgin, X.watch, Z.a2, Z.a3, Z.b1, Z.b2, Z.inside |
| R10 TEJASNET | 1: L2.virgin |
| R11 BIOCON | 1: L2.virgin |
| R12 SSWL | 3: H.hot, L2.virgin, V.periods |
| R14 NBCC | 13: H.hot, L2.virgin, V.long, V.periods, V.virgin, X.watch, Z.a1, Z.a2, Z.a3, Z.b1, Z.b2, Z.b3, Z.inside |

7 of 15 reads change; the other 8 are identical.

- **Bucket edges** move IRFC (R09) and NBCC (R14), the two reads with decimal buckets (steps 0.2): value areas, virgin levels and zones shift by one bucket. IRFC's weekly money-zone VA becomes 131.6-135.2 (was 132.2-135.8) and its 250-day VA 122.4-159.8 (was 122.8-160.2), the values Fable computed independently. NBCC's zones re-cluster around the shifted levels: price is no longer inside a strong zone; the nearest zones are 0.04 ATR below and 0.06 ATR above.
- **Daily-layer virgin counts** fall slightly in several reads (e.g. JSL 341 to 326, IRFC 306 to 246): a session level exactly on a bucket edge was one bucket low, so a later bar could miss it. The nearest levels shown don't change except in IRFC and NBCC.
- **Bad 5-minute bars:** no item changes in these 15 reads. Counted read-only on the VM on 2026-11-11 across the whole 5-minute store: **80 bad rows out of 64,105,882 (34 of 502 stocks)**. 79 have high below low; 1 (GMMPFAUDLR, 2018-03-05) has a missing or non-positive price. Almost all are on one Fyers day, 2019-12-06; KERNEX, OPTIEMUS, SHRIPISTON and JAYNECOIND also have a few in 2018-09/10 and 2019-09-23. They are now dropped when the store is read; the files keep what Fyers sent.

## 2. Definitions v2

### Structure, alignment and zones per read

Structure cells show state, age in bars, last event and level, and the protected level, before → after (only the timeframes that changed).

| Read | Structure (M/W/D) | Alignment | HTF zones | Strong share |
|---|---|---|---|---|
| R01 KEI | M: up 48b, BOS 2815.15, prot 2223 → **down 3b, CHoCH 3705, prot 4706**<br>W: down 11b, CHoCH 2822.45, prot 5039.7 → **down 34b, BOS 3705, prot 4706**<br>D: up 34b, BOS 3522.7, prot 3411.4 → **up 42b, BOS 3522.7, prot 3411.4** | not aligned: up on M, D, W down → not aligned: down on M, W, D up | 41 → 68 | 78% → 43% |
| R02 DMART | M: down 19b, CHoCH 3644.3, prot 5484.85 → **down 6b, CHoCH 3761.2, prot 4644**<br>W: down 36b, BOS 3955, prot 4429.4 → **down 5b, CHoCH 3955, prot 4429.4**<br>D: down 32b, BOS 3886.7, prot 4124.9 → **down 32b, BOS 3886.7, prot 4098.9** | aligned down → aligned down | 49 → 40 | 82% → 85% |
| R03 JSL | M: up 55b, BOS 329, prot 255 → **up 2b, CHoCH 803, prot 496.6**<br>W: up 38b, BOS 826, prot 715.5 → **up 38b, BOS 826, prot 730.2**<br>D: up 43b, CHoCH 826, prot 715.5 → **up 22b, CHoCH 816, prot 734** | aligned up → aligned up | 39 → 45 | 77% → 51% |
| R04 LTM | W: down 82b, BOS 4000, prot 4784 → **down 34b, BOS 4000, prot 4850**<br>D: up 51b, CHoCH 4360, prot 3528 → **down 21b, CHoCH 4414.8, prot 4700** | not aligned: down on M, W, D up → aligned down | 51 → 36 | 76% → 69% |
| R05 HCLTECH | M: up 59b, BOS 1697.35, prot 1235 → **up 24b, BOS 1697.35, prot 1302.75**<br>W: up 82b, BOS 1702.6, prot 1594 → **up 47b, BOS 1702.6, prot 1594**<br>D: up 44b, BOS 1675.8, prot 1605.7 → **down 2b, CHoCH 1689.2, prot 1752.5** | aligned up → not aligned: up on M, W, D down | 54 → 62 | 83% → 53% |
| R06 ANTELOPUS | M: up 52b, BOS 767.95, prot 357 → **up 2b, CHoCH 767.95, prot 357** | not aligned: up on M, W, D down → not aligned: up on M, W, D down | 29 → 33 | 79% → 48% |
| R07 NEOGEN | M: up 0b, CHoCH 2420, prot 966.7 → **up 5b, BOS 1797, prot 966.7**<br>W: up 25b, BOS 2483.9, prot 2086.4 → **up 26b, BOS 2483.9, prot 2086.4**<br>D: up 127b, BOS 2499.7, prot 2296.7 → **up 127b, BOS 2499.7, prot 2300** | aligned up → aligned up | 32 → 30 | 78% → 70% |
| R08 GRSE | M: up 56b, BOS 2833.8, prot 1184.9 → **up 3b, CHoCH 2845, prot 1963.7**<br>W: up 14b, CHoCH 2844.9, prot 1963.7 → **up 14b, CHoCH 2844.9, prot 2530**<br>D: down 1b, CHoCH 2530, prot 2934.7 → **down 21b, BOS 2535.5, prot 2665** | not aligned: up on M, W, D down → not aligned: up on M, W, D down | 39 → 43 | 77% → 42% |
| R09 IRFC | M: up 31b, BOS 192.8, prot 97.8 → **down 4b, CHoCH 132.8, prot 166.9**<br>W: down 40b, BOS 127.71, prot 155.52 → **up 10b, CHoCH 134.6, prot 131.56** | not aligned: down on W, D, M up → not aligned: down on M, D, W up | 45 → 35 | 69% → 63% |
| R10 TEJASNET | M: up 51b, BOS 940, prot 651.25 → **down 2b, CHoCH 1102.85, prot 1459.9**<br>D: up 16b, BOS 844.45, prot 741.1 → **up 16b, BOS 844.45, prot 731.05** | not aligned: up on M, D, W down → not aligned: down on M, W, D up | 33 → 39 | 73% → 46% |
| R11 BIOCON | M: down 37b, BOS 303, prot 404.7 → **down 14b, CHoCH 303, prot 424.95**<br>W: up 25b, CHoCH 404.7, prot 291 → **down 15b, BOS 359.05, prot 402.8**<br>D: down 31b, CHoCH 368.3, prot 402.8 → **down 33b, CHoCH 375.35, prot 402.8** | not aligned: down on M, D, W up → aligned down | 44 → 43 | 93% → 67% |
| R12 SSWL | M: up 50b, BOS 225, prot 167.41 → **up 3b, CHoCH 225, prot 167.41**<br>D: down 30b, CHoCH 230.29, prot 280 → **down 34b, CHoCH 234.9, prot 259.45** | not aligned: up on M, W, D down → not aligned: up on M, W, D down | 42 → 46 | 81% → 48% |
| R13 BLUESTARCO | M: up 52b, BOS 820, prot 701.7 → **down 3b, CHoCH 1711.05, prot 2417** | not aligned: down on W, D, M up → aligned down | 39 → 58 | 79% → 62% |
| R14 NBCC | M: up 49b, BOS 117.9, prot 70.07 → **down 2b, CHoCH 85.21, prot 121.13**<br>W: up 131b, BOS 104.15, prot 70.8 → **up 1b, CHoCH 104.15, prot 70.8**<br>D: up 11b, CHoCH 104.15, prot 70.8 → **up 46b, BOS 102.5, prot 90.07** | aligned up → not aligned: up on W, D, M down | 35 → 34 | 74% → 50% |
| R15 CHOLAFIN | unchanged | not aligned: up on M, D, W down → not aligned: up on M, D, W down | 42 → 61 | 81% → 54% |

**Strong share** (a description, not a target; v2 G2): median 78% under v1 → 53% under v2, range 42–85%.

### New review items

New item kinds: `D.failed`, `D.liq`, `M.failed`, `W.failed`, `Z.inside2`, `Z.inside3`.
- `M/W/D.failed`: the last failed break (G4).
- `D.liq`: the daily equal highs and lows nearest the price (G3), shown and not clustered.
- `Z.inside2`: a second zone around the price; v2 bands may overlap.
- `M/W/D.sweep` now names the swept swing and its period (G4, frozen).
