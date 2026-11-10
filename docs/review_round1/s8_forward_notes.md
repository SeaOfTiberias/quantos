# Forward walk-throughs from round 1: notes for the S8 signal test

These are not round 1 scores. Round 1 is a point-in-time correctness review. What price did afterwards belongs to the S8 signal test, which needs its own pre-registration and a placebo control.

The zones cover nearly the whole price range (gap 2), so one case can't separate them from random levels.

Each claim below was checked against TradingView daily bars (`NSE:KEI`, `NSE:DMART`, split-adjusted). The bars were fetched 2026-11-11.

## R01 KEI (as of 2025-06-23; price 3574.5)

**Judge's claim** (`judge/R01_freeform.md`): price held the inside zone, rallied through a1 to about 3800–3860, stalled under 3880–3900, then ranged around 3696–3725.

**The bars show:**
- **The inside zone held.** On 2025-06-23 the low was 3525.3 and the close 3758.9. Zone 3483.75–3620 held, and a1 (3622.5–3740) was crossed on day one.
- **The stall was looser than claimed.** On 06-25 the high was 3940.6, above the claimed 3880–3900 stall. By 07-22/07-23 the high was 4034.4, inside a3 (3910–4040).
- **The range was wider.** It ran about 3600–4080 through July and August (low 3601.1 on 07-11; high 4079 on 08-20), not 3696–3725.
- **Then a breakout.** On 2025-09-19 the high was 4235, above a3.
- **Verdict:** the judge's path is right for the first days and too narrow after that.

## R02 DMART (as of 2026-08-28; price 3847.4)

**Claim in the user's file (Gemini-written, Part 2):**
- price rallied to about 3950–4000 and halted inside a1 (3926.73–4028.53) and the GPZ (3961.99–3985);
- it then broke 3737.2;
- it ran to about 3150–3200 below the M weak low 3340;
- it bounced to 3466.9.

**The bars show:**
- **No rally into a1.** The highest high after the as-of date was 3900 (2026-08-31), with 3880 on 10-01. Price never reached a1 or the GPZ. The "halted precisely inside a1" claim is false.
- **D weak low 3737.2 broken.** On 2026-09-07 the low was 3682.3. Zone b1 (3715–3794.02) was then traded on and off through September, with lows from 3650 to 3780.
- **Break down through b2 and b3.** On 2026-10-05 price gapped down (close 3567, volume 2.55M). On 10-12 it closed at 3364.9 on volume 3.13M.
- **M weak low 3340 broken.** The low reached 3102.3 on 2026-10-23, below the claimed 3150–3200.
- **Bounce.** The close was 3466.9 on 2026-11-09.

## Rule ideas raised (untested hypotheses, not endorsed)

Two signal-rule ideas came in. Both are hypotheses for S8. Neither is a v2 drawing change, and neither is a trade recommendation. Trading is paused (2026-11-02).

1. **Judge on R01:** favour the lower-timeframe direction when the higher timeframe is in deep discount.
2. **User's file on R02, Part 3:**
   - when the timeframes are aligned down and the D/W discount is under 30%, don't sell at market; wait for a retest of the first zone above;
   - a counter-trend case after a sweep onto a virgin level.

**One observation for whoever pre-registers this.** On R02, the retest level the file proposes (3926–3985) was never reached, because the high was 3900. The move it targets happened anyway. A single case says nothing about the rule either way. Any test needs a fixed universe, a placebo, and pass criteria committed before it is run.
