# Market Map: definitions v2 (written 2026-11-11, before any v2 code)

v2 is v1 (`docs/MARKET_MAP_DEFINITIONS.md`, frozen 2026-11-05) with the changes below. Every section not named here is unchanged. v1 stays in the repo as the record.

**Why v2 exists.** On 2026-11-11, after seeing every round 1 finding (`docs/review_round1/findings_fable.md`, `findings_round1.md`), the user chose to put all six definition gaps into v2. v2 follows the same rules as v1:
- **Rules come from the concepts, not from marks or outcomes.** The round 1 reviewers said where v1 misses what a chart shows. v2 fixes the rule behind each miss. No parameter here was tuned on prices after an as-of date, and none on the user's golden set (still unseen).
- **This file is committed before the code.** The code then follows it. Anything the code needs that this file leaves open is written in the module's docstring, as with v1.
- **Round 1's 15 reads are regenerated under v2** for the user's hand review. They are not a fidelity test.
- **Round 2 (§9, unchanged) scores v2** on the user's golden set, which v1 and v2 have never seen.

Untested. Markers, never signals.

## G1. Structure follows the latest swings (replaces v1 §2's break and protected rules)

**The miss.** v1 changed trend only on a close beyond the protected level. After a CHoCH, that level was the extreme of the whole previous leg, often an all-time high or low. So a timeframe could hold its state through a full move the other way:
- R04 W read "down for 82 bars" through a 69% rally;
- R06 M read "up for 52 bars" through a 67% fall;
- DMART W read "down" through a 2026 HH/HL leg.

All three reviewers raised it.

**The concept.** In SMC swing structure (the reading behind LuxAlgo's Smart Money Concepts, which the user's own charts carry), a trend is broken when price closes beyond the last swing that defended it:
- in an uptrend, the most recent higher low;
- in a downtrend, the most recent lower high.

A break in the trend's direction is a BOS. A break against it is a CHoCH.

**v2 rules (per timeframe, on the §1 zig-zag swings):**
- **Up break:** a close above the most recent confirmed swing high not yet broken.
  - In `up` (or from `none`) it is a BOS.
  - In `down` it is a CHoCH, and the state becomes `up`.
- **Down break:** the mirror.
- **Protected low in `up`:**
  - After every up break, BOS or CHoCH: the lowest low between the bar of the broken swing high and the break bar (v1's BOS rule, now also used after a CHoCH).
  - When a newer swing low is confirmed while the state is `up`, it becomes the protected low. The protected low is always the latest swing that defends the trend.
- **Protected high in `down`:** the mirror.
- **Breaking the protected level:** a close below the protected low in `up` is a CHoCH down, even when no newer swing low has been confirmed. After that CHoCH, the protected high is the highest high between the protected low's bar and the CHoCH bar. The mirror applies in `down`.
- **Unchanged from v1:**
  - the weak level: the extreme since the last break in the trend's direction;
  - age: in bars since the event that started the state;
  - premium and discount: from the protected to the weak level, so the dealing range now runs from the latest defending swing;
  - order blocks: still found from each event's protected bar.

**What this may cost.** States can flip more often, mostly on D (k = 5). The zig-zag's 1-ATR filter (§1) is unchanged and is the only damping. Whether v2 flips too often is for the user's hand review and round 2 to show. No filter is added in advance.

## G2. HTF zones: honest bands, a selective strong flag (amends v1 §6)

**The misses** (all three reviewers):
- 73–83% of zones counted as strong.
- The zones tiled the whole price range.
- A supply, demand or order-block band was clustered as its two edges, so one band credited two zones and left its own middle unzoned (KEI W supply 3875.5–3964.85; DMART W demand 3736.1–3824.3).
- The read said "within 0.3 ATR(W)" while zones grew to 1.5 times that.

**v2 rules:**
- **Which elements enter.**
  - Structure:
    - W and M zig-zag swings **not yet broken by a close** at the read (a broken swing is history; role reversal stays out, as in v1 §8);
    - the protected and weak levels;
    - multi-touch levels (§3.2).
  - Imbalance and liquidity: unchanged.
  - Volume:
    - the last completed W, M, Q and Y profiles (POC, VAL, VAH, both kinds);
    - the 250- and 750-day POC, VAL and VAH, and HVN bands;
    - **only the `watch` virgin levels** (G5). These are the two Ochoa watches per period and kind: the virgin POC, and the virgin VAH or VAL nearest the price.
  - Pivot: unchanged.
- **Bands keep their range.** Demand, supply and order-block zones (§3.1, §3.3) and HVN and LVN runs (§5) enter as bands. A band is never split.
  - Point levels cluster as in v1: a level within 0.3 ATR(W) of the cluster's last level joins it, and a cluster stays at most 1.5 × 0.3 ATR(W) wide.
  - A band and a point cluster merge when the cluster lies within 0.3 ATR(W) of the band.
  - Bands that overlap merge.
  - A merged zone's range is the union of its members, and the read shows that real range.
- **Strong zone:** at least 2 families, **at least one of which is structure, imbalance or liquidity**, that is, a level where price itself turned, left a base or left resting orders.
  - Pivot and volume levels are formulas over every period, so their agreement alone is everywhere by construction.
  - Pivot-and-volume confluence stays recorded as Ochoa's hot zones (§6.1, unchanged).
- **Wording.** Zones are labelled "clustered at 0.3 ATR(W); point clusters at most 0.45 ATR(W); bands keep their full range".

The share of strong zones is reported after the regeneration as a description, not a target. No parameter here is set from it.

## G3. Equal highs and lows (amends v1 §1 and §3.4)

**The miss.** v1 §1 needs a high strictly above every bar on both sides. So a double top printed on two bars (LTM 4850/4850 on 2026-08-11 and 08-12) gives no swing at all. Daily double tops and bottoms were missing from every read.

**v2 rules:**
- **Swing high:** bar *i*'s high is strictly above every high in the *k* bars before it, and **at least** every high in the *k* bars after it. In a run of equal highs, the first one is the swing. Lows mirror. k is unchanged.
- **EQH/EQL on D too.** §3.4's rule now runs on D bars with D swings as well as W and M.
  - D levels are **shown** in the read (the active EQH/EQL nearest the price on each side) but never clustered into the HTF zones. This follows v1 §0: D structure stays out of the HTF map.
- **EQH/EQL tolerance, written down (v1 left it open):** 0.1 × ATR(TF) at the confirmation bar of the later swing.

## G4. Sweeps and failed breaks: frozen (replaces v1's unfrozen weak-level sweep)

**The miss.** Only sweeps of the weak extreme were tracked, and the definition was never frozen. Triple tops and bottoms that were run and reclaimed (NEOGEN, GRSE), a sweep of a protected low (TEJASNET) and recent sweeps (BIOCON) went unnamed. A 1.9-point overshoot (CHOLAFIN) counted as a sweep.

**v2 rules, per timeframe (M, W, D), on confirmed zig-zag swings not yet broken by a close:**
- **Sweep:** a bar whose high goes above such a swing high by at least 0.1 ATR(TF) and closes at or below it. Lows mirror.
  - The swing is then marked swept, with the date and the extreme. A swing is swept once.
  - The protected and weak levels are swept under the same rule when they are such a swing.
- **Failed break:** a close above such a swing high (a break), followed within 3 bars by a close back at or below it. Lows mirror.
  - The break still counts for §2. The failed break is recorded beside it, never undone.
- **Output:** the last 3 sweeps and the last 3 failed breaks per timeframe, each with the level, the extreme or close, and the date. They are labelled "frozen v2".
- §3.4's EQH/EQL sweep (LIQUIDITY_SWEEP) is unchanged.

## G5. Virgin levels must have survived a period (amends v1 §4)

**The miss.** Most of the nearest "virgin" levels came from the week or session that had just closed. They were virgin only because no bar had printed since. They sat 0–0.2 ATR from price and crowded out older untouched levels.

**v2 rule:** a period's POC, VAH or VAL becomes virgin only after **at least one complete later period of the same kind** (W, M, Q or Y; a session for the L2 layer) has closed without trading through it. Until then it is that period's own level, which the read already shows in its profiles line (L1) or as the last session's profile (L2).
- Age is counted from the period of origin, as in v1.
- The `watch` flags are chosen among the virgin levels as in v1.

## G6. Smaller choices v1 left open (amend v1 §4 and §6.1)

| Item | v2 rule | Change? |
|---|---|---|
| Camarilla width | (H3 − L3) / P × 100, with P the floor pivot of the same period, the same denominator as CPR width. v1's code divided by C. | Yes |
| Volume POC tie | The tied bucket nearest the middle of the period's range, then the lower one: the money-zone POC's rule (Ch. 3), now also used for the VPOC. v1's code took the lowest. | Yes |
| Percentile with ties | Previous widths below, plus half of those equal, over their count: the usual mid-rank. This is v1's code, now written down. | No |
| GPZ members | H3, L3, the money-zone POC, VAL and VAH, and the VPOC. Volume VAL and VAH are not members: Ochoa names the VPOC only (Ch. 10). This is v1's code, now written down. | No |
| Bucket step | Each period uses `step_for` of the ATR(D) at its own last bar, as built. A single step from today's ATR would be wrong for old periods at very different prices. Comparisons across periods are in price, not in buckets. Written down. | No |
| Weekly profiles | Built for every completed week whose sessions all have 5-minute bars. The store runs from 2017-12. This replaces v1's out-of-date "(the last 100 days)". | Wording only |

## What is not in v2

- No change to §3.1–§3.3 parameters, §5, §7 alignment, §8's out-of-scope list or §9's fidelity test.
- No weights between families.
- No signals. Sweeps, failed breaks and alignment remain markers.
