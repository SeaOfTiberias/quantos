# Round 1 findings: all reviewers so far (2026-11-11)

This file adds the user's submitted reviews to Fable's findings (`findings_fable.md`) and classes the new findings as the protocol says (`docs/MARKET_MAP_REVIEW_ROUND1.md`):
- **(a) code bug**
- **(b) definition gap**
- **(c) reviewer misread**

**Nothing has been changed.**

## What came in

| Reviewer | Reads | Format | Saved in |
|---|---|---|---|
| Fable | all 15 | review-form JSON | `fable/R##.json` |
| User | R01 KEI, R02 DMART | Markdown, converted to review-form JSON. All 70 item ids were checked against `reads.md`: none missing, none extra, none duplicated. | `user/R01.json`, `user/R02.json`; the originals, unchanged, are in `user/source/` |
| User's model judge | R01 only | free-form, covering 7 items | `judge/R01_freeform.md` |

No judge reply in review-form JSON has been received yet.

**Provenance of the user's two files.** They came from the folder `GeminiReview` and are written in Gemini's voice:
- LaTeX arithmetic;
- "classical SMC";
- trade-execution rules.

They are filed as the user's answers because the user submitted them as such. In the tally they are labelled **"user (Gemini-written)"**, because they are not the independent hand review the protocol describes. The screenshots in that folder (review-page tabs and a TradingView replay) are not committed.

## Tally: R01 and R02, the reads with two full reviewers

Each cell gives the count of Y / N / unclear. There are 70 items per reviewer.

| Item kind | Items | User rule | Fable rule | User chart | Fable chart |
|---|---|---|---|---|---|
| state | 6 | 5/0/1 | 6/0/0 | 6/0/0 | 5/1/0 |
| event | 6 | 5/1/0 | 6/0/0 | 6/0/0 | 4/2/0 |
| protected | 6 | 4/0/2 | 6/0/0 | 6/0/0 | 4/2/0 |
| weak | 6 | 6/0/0 | 6/0/0 | 6/0/0 | 6/0/0 |
| premium/discount | 6 | 6/0/0 | 6/0/0 | 6/0/0 | 5/1/0 |
| sweep | 6 | 6/0/0 | 0/0/6 | 6/0/0 | 6/0/0 |
| zone | 14 | 14/0/0 | 9/0/5 | 14/0/0 | 14/0/0 |
| hot zone | 2 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 |
| period pivots | 4 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 |
| profiles | 6 | 6/0/0 | 6/0/0 | 6/0/0 | 5/1/0 |
| daily layer | 6 | 6/0/0 | 6/0/0 | 6/0/0 | 4/2/0 |
| what to watch | 2 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 |
| **all** | **70** | **66/1/3** | **59/0/11** | **70/0/0** | **61/9/0** |

**Judge (R01, free-form).** It rates Y on 7 items:
- price;
- D state;
- D event;
- D weak;
- D protected;
- Z.inside;
- L2 CPR.

It flags the W CHoCH (R01.W.event) as late and stale, which is a chart N.

**Agreement between the user and Fable:**
- chart answers: 61 of 70;
- rule answers: 55 of 70.

**Where they disagree (24 answers), in four groups:**
1. **Weekly structure (8 answers on 6 items).** Both reviewers object to the same items, but in different columns:
   - Fable answers Rule Y (the item follows v1) and Chart N.
   - The user answers Rule N or unclear, and Chart Y.
   - The items: R01.W.event, R01.W.protected, R01.W.pd, R02.W.state, R02.W.event, R02.W.protected.

   The substance is the same in both: the W state has gone stale, which is gap 1 (see U1 to U3).
2. **Sweep rule (6 answers).** The user gives Y; Fable gives unclear, because v1 hasn't frozen the sweep definition (S7). The user's answers judge the sweeps against general SMC practice, not v1.
3. **Zone rule (5 answers).** The user gives Y; Fable gives unclear, because v1 §6 doesn't write down the clustering.
4. **Others Fable rates Chart N that the user rates Y (5 answers):**
   - R01.V.virgin, R01.L2.virgin and R02.L2.virgin: trivial virgin levels from the session that has just closed, gap 5.
   - R02.M.protected: the 2024 all-time high, gap 1.
   - R01.W.pd: inherits the stale 5039.7.

**Fable's tally across all 15 reads** is unchanged (`findings_fable.md`).

## New findings from the user's files

| # | Item or entry | Raised by | Class | Check |
|---|---|---|---|---|
| U1 | R01.W.protected 5039.7: should it be the lower high near 4700? | user (unclear), Fable (Chart N, 4706 2024-W50), judge (W CHoCH stale) | **(b) gap 1**, already listed | v1 §2: after a CHoCH, the protected level is the highest high between the protected low's bar and the CHoCH bar, which gives 5039.7. The engine follows v1; v1 keeps a high two lower highs back. |
| U2 | R02.W.state "down for 36 bars" runs through the 2026 HH near 4650 | user (unclear), Fable (Chart N, HH 4644) | **(b) gap 1**, already listed | The W state never turned up under v1, because no close above the protected high came. The count is right under v1 but stale on the chart. |
| U3 | R02.W.event: a BOS down at 3955 "should be a CHoCH" | user (**Rule N**), Fable (Rule Y, Chart N) | **(c) on the rule; (b) gap 1 on the chart** | v1 §2: in a `down` state, a close below the latest unbroken swing low is a BOS. The state was `down`, so BOS follows v1. The user's file applies textbook naming, where an HH/HL leg flips the read. That is the gap 1 change, not a code bug. |
| U4 | R02.W.protected 4429.4 versus HH 4650 | user (unclear); Fable rates Y/Y | **(b) gap 1** | After the BOS at 3955 in W29, v1 sets the protected high to the highest high between the broken swing-low bar (W24) and the break bar, which is 4429.4. That follows v1. 4644 is the analyst's choice if the HH/HL leg counted as a turn up. |
| U5 | Missing: W supply / bearish OB 3875.50–3964.85 (KEI) | user; Fable (in its R01.Z.a2 note); judge (in its forward note) | **(c) as missing; supports gap 2** | The read has it: "W supply low (2025-W09)" is a member of a2 and "W supply high (2025-W09)" is a member of a3. It looks missing because the band is clustered as two edges and its middle is split across two zones. That is gap 2 (band edges), which all three reviewers now touch. |
| U6 | Missing: the D sweep at 3861 "taken and rejected" (KEI) | user | **(c)** | Already in R01.D.sweep. The entry is an interpretation (a pullback followed), not a missing level. |
| U7 | Missing: D protected low 3411.4 as invalidation (KEI) | user | **(c)** | Already in R01.D.protected. It describes a scenario, not a missing level. |
| U8 | Sweep and zone items rated Rule Y | user | **(c), a method note** | v1 has no frozen sweep rule and no written clustering rule, so Y can't be checked against v1. These answers judge against general SMC, not v1. |

**Net result:**
- no new code bug;
- no new definition gap.

The user's substantive flags all fall under gap 1 (stale structure states), already the top v2 item. With them, gap 1 is raised by all three reviewers on R01, and by the user and Fable on R02. The KEI supply entry adds a third reviewer to gap 2's band-edge split.

## What isn't scored here

Both of these are filed in `s8_forward_notes.md` as notes for the S8 signal test, not as round 1 scores:
- the forward walk-throughs (R01 from the judge, R02 from the user's file);
- the trade-rule proposals in R02 Part 3.

## Still open

1. The two code bugs (`findings_fable.md`): fix them or not. That is the user's decision.
2. Which gaps go into v2. That is the user's decision.
3. The user's review of the other 13 reads, and the judge's review-form JSON.
