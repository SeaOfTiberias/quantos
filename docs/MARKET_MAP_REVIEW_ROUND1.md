# Market map review, round 1 (pre-registered 2026-11-08)

The user changed slice 8 on 2026-11-08: before the golden-set fidelity test, the engine's own reads go out for review, so nothing built is changed without being vetted first.

- **Round 1 (this document):** 15 random reads from the engine, reviewed by:
  - the user, by hand;
  - the user's own model judge;
  - Fable.
- **Round 2:** the user's 10–20 golden-set charts, scored by the §9 fidelity test in `docs/MARKET_MAP_DEFINITIONS.md` exactly as pre-registered there. The user marks those charts before seeing the engine's read of them.

Round 1 is a **correctness review, not the fidelity test.** Reviewers see the engine's drawing first, so agreement here can't show that the engine finds what the user would find; round 2 does that. Round 1 looks for three things:
- items that break the v1 definitions;
- items that don't match the chart;
- things the reviewers see that the read leaves out.

## Sample (fixed before any read is generated)

- **Generator:** `scripts/review_pack.py`, run on the VM against the L1 store and the 5-minute store.
- **Universe:** the top 500 in `~/.quantos/l1_store/universe.json` (as of 2026-11-06), minus HDFCBANK and SUPREMEIND (discussed before v1). Stocks only, because indices are not in the L1 store.
- **Random draw:** seed `20261108`, `numpy.random.default_rng`. The symbols are shuffled once. Going down that order, each symbol gets one as-of session, drawn uniformly from its own trading days between 2024-11-08 and 2026-11-06.
- **Eligible if all three hold** (otherwise skipped, and the skip is logged with its reason):
  - at least 756 daily bars (three years) before the as-of date in the latest segment;
  - 5-minute bars in the 30 days before it;
  - `map_read` returns an L1 read with no error.
- **N = 15:** the first 15 eligible.
- **Point in time:** the read uses only bars that completed before the as-of date (§0). The pack contains no bar on or after the as-of date, so no reviewer sees what happened next.

## What each read shows (markers, never signals; no entries, stops or sizes)

- **Structure, for M, W and D:**
  - trend state and age;
  - last BOS/CHoCH (type, direction, level, period);
  - protected and weak levels;
  - premium/discount;
  - last weak-level sweep (labelled "definition not frozen").
- **HTF zones:**
  - the zone the price is inside;
  - the 3 nearest zones below and above, with families and the strong flag;
  - Ochoa hot zones.
- **L1 pivots and profiles:** as in `s.lines`.
- **L2 daily layer:**
  - daily pivots, with the CPR reading and relationship;
  - the last session's money zone and volume profile;
  - the nearest virgin session levels.
- **What the map says to watch:** the first zone below and above, the room to each in ATR(D), and whether the M/W/D states align.

## Review form (the same for every reviewer)

Each item in a read has an id (for example `R07.W.weak`). For every item, the reviewer answers two questions and may add a note:
- **Rule:** does it follow the v1 definition? Answer Y, N or unclear.
- **Chart:** does it match what you see on the chart? Answer Y, N or unclear.

For each read, the reviewer also gives:
- **Missing:** what you see that the read leaves out, each with a type and a price.
- **Overall:** does the read describe this chart? Answer yes, partly or no, with a sentence on why.

## Reviewers

- **The user**, by hand, from the review page: candles for M, W and D up to the as-of date, with the read drawn on them.
- **The user's model judge.** The user runs it with the same files and form, and the judge prompt is in the pack.
- **Fable** (`claude-fable-5-1`). It runs as three separate agents with 5 reads each, all on the same prompt. Each agent gets only this document, `docs/MARKET_MAP_DEFINITIONS.md`, the bars and the reads. It is told not to read `core/market_map/` or the tests, so it works from the definitions rather than re-running the code. It may compute from the bars itself. Its answers are saved verbatim.

No prompt contains household data: the pack is NSE market data only.

## What happens to findings (fixed now)

1. Every item that any reviewer marks Rule = N or Chart = N, and every Missing entry, goes on a findings list. The list records which reviewers raised each one and how many agree.
2. Claude checks each finding against the definitions and the code, and classes it as one of:
   - **(a) code bug:** the code doesn't do what v1 says;
   - **(b) definition gap:** the code does what v1 says, but v1 misses something;
   - **(c) reviewer misread:** the read is right and the reviewer misread it.
3. **Nothing is changed during the round.**
   - A code bug is fixed only after the user approves. All 15 reads are then regenerated and the differences listed.
   - A definition gap goes to the v2 list. v1 stays frozen, and v2 is written only after the user has seen all the findings. Round 2 then scores whichever version is current, on charts it has never seen.
4. Round 1 has no pass/fail. Its result is:
   - the findings list with its classes;
   - the share of items rated Rule = Y and Chart = Y, per reviewer and per item kind;
   - where the reviewers agreed and disagreed.
