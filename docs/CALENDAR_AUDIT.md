# Calendar Audit — do the naive weekday helpers invalidate any closed verdict?

**Run 2026-08-18, read-only. Verdict: no. No closed candidate needs reopening.**

`core/reference/calendar.py` established that the private `weekday() < 5`
helpers carried by six research scripts are wrong 175 times over
2015-01-01 .. 2026-08-18 — 164 holidays counted as sessions, 11 real weekend
sessions dropped. This audit answers the only question that matters
downstream: **does that change any published result?**

It was run *before* migrating any caller, deliberately, so the size of the
problem was known before anything moved.

---

## The six callers

| Script | Candidate | Use of the helper |
|---|---|---|
| `backtest_pairs_trading.py` | 12 · pairs trading | iterate dates → `fetch_raw` → `continue` on `BhavcopyNotAvailable` |
| `fetch_vrp_bhavcopy.py` | (cache builder) | iterate dates → `fetch_and_parse`, tally holidays |
| `gutcheck_expiry_day_effect.py` | 13 · expiry-day effect | iterate dates → `fetch_raw` → `continue` on unavailable |
| `pead_gutcheck.py` | 5 · PEAD | iterate dates → `fetch_and_parse`, tally holidays |
| `reconstitution_gutcheck.py` | 6 · index reconstitution | iterate dates → `fetch_and_parse`, tally holidays |
| `validate_vol_skew_signal.py` | vol skew | iterate dates → `fetch_raw` → `continue` on unavailable |

**All six share one pattern**, and that pattern is what saves them: the helper
produces a *candidate list*, and a real fetch against real data filters it.

---

## Finding 1 — the 164 false positives are self-correcting

A holiday has no bhavcopy. The fetch raises `BhavcopyNotAvailable`, the loop
`continue`s, and the date never enters the result. Two of the six even count
the misses explicitly (`fetched, cached, holidays = 0, 0, 0`).

So the larger error by far — 5.4% of the days the helpers claim — **has no
effect on any published number.** The naive helper was over-generating
candidates into a filter, not asserting facts about sessions.

This is why the audit came before the migration. The headline defect number is
real, and it is almost entirely harmless in the way it was actually used.

## Finding 2 — the 11 false negatives are real, small, and bounded

These the helpers never *request*, so no filter can recover them. Every
bhavcopy-backed study shares the cache's window, 2023-07-24 .. 2026-07-22:

| | |
|---|---|
| Real sessions in window | 743 |
| Silently never requested | **6 (0.81%)** |

2023-11-12 (Sun, Muhurat) · 2024-01-20, 2024-03-02, 2024-05-18 (Sat, special
live sessions) · 2025-02-01 (Sat, Budget) · 2026-02-01 (Sun, Budget)

### Does 0.81% flip any verdict?

No, and not marginally. The closed candidates missed the bar
(`PF > 1.0 AND Sharpe > 0.5`) by margins that six sessions cannot close:

| Candidate | Result | Distance from the bar |
|---|---|---|
| Pairs trading v2 | PF 1.04, Sharpe 0.14 | Sharpe short by 0.36 |
| VRP short strangle | PF 1.034, Sharpe 0.092 | Sharpe short by 0.41 |
| Expiry-day effect | failed at gut-check | premise inverted — direction, not magnitude |
| Index reconstitution | closed on 0/149 F&O coverage | structural, not statistical |
| PEAD | shelved on absent data | more sessions would not create fundamentals |

**No reopening is warranted.** Recording that as an audited outcome is the
honest ledger entry, not a to-do.

### One case where the omission was accidentally helpful

`gutcheck_expiry_day_effect.py` measures volatility around expiry. Muhurat is
a ~1-hour ceremonial session and the Budget Saturdays are atypical in volume
and participation. Including them in a volatility baseline would arguably have
*added* noise. The exclusion was unprincipled, but for that one study it
pointed the right way. Worth knowing before "fixing" it changes a number.

---

## What follows

1. **Fix the fetcher first.** `fetch_vrp_bhavcopy.py` built the cache, so its
   naive helper is why the cache has no weekend sessions. Migrating it and
   re-running backfills the 6 missing dates and removes the blind spot at
   source.
2. **Migrate the remaining five** to `core/reference/calendar`. Cheap, and it
   prevents the next study — which may well count days rather than filter
   them — from inheriting the defect.
3. **Do not re-run any closed candidate.** Their verdicts stand, now audited.

> The general lesson is worth carrying into the falsification harness: this
> defect was harmless *because of how it was used*, not because it was small.
> A future script that computes forward returns over N days, rather than
> filtering a candidate list against real data, would be materially biased by
> the same helper. That is the argument for the calendar being the single
> authority rather than a convention — the next caller does not get to be
> lucky.
