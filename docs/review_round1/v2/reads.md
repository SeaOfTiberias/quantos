# Round 1 reads under definitions v2 (regenerated 2026-11-11)

The same 15 symbols and as-of dates as `../reads.md` (seed 20261108, `../sample.json`), regenerated with `scripts/review_pack.py --from-sample` after the two code-bug fixes (cd98683) and definitions v2 (`docs/MARKET_MAP_DEFINITIONS_V2.md`; code 0a819d7, f76482f, e8aee97). Generated on the PC from a read-only copy of these 15 symbols' L1 and 5-minute store files on the VM; the same run under the old code reproduced all 525 round 1 items exactly. What changed: `changes.md`.

## R01 KEI, as of 2025-06-23 (last bar 2025-06-20, price 3574.5, ATR(D) 95.69)

```
MAP  KEI at 3574.5 (higher-timeframe map, bhavcopy to 2025-06-20) -- zones untested (no fidelity or signal test yet)
     below: 2178–2762.25 (M bull OB 2223-2719.9 (2023-08); Q virgin vol VAH 2023-Q2; W swing HL 2023-W33; Q S1 +35), 22.72% away
     above: 3622.5–3740 (W TC; W MZ VAH 2025-W25; 250d LVN low (approx.); W H4 +6), 1.34% away
     price is inside the strong zone 3483.75–3620 (W L4; M vol VAH 2025-05; 250d LVN low (approx.); W S1 +13)
L1   structure (untested: no fidelity test yet) -- not aligned: down on M, W, D up
     M: down for 3 bars; last CHoCH down 2025-02 at 3705; protected high 4706 (2024-12), weak low 2424 (2025-04); premium 50.4%
        last sweep: swing high 1661.95 (2022-10) taken to 1730.95 on 2023-02-28, closed back inside (frozen v2)
        last failed break: swing low 3375.6 closed beyond in 2025-02, back inside on 2025-05-30 at 3610.2 (frozen v2)
     W: down for 34 bars; last BOS down 2025-W07 at 3705; protected high 4706 (2024-W50), weak low 2424 (2025-W15); premium 50.4%
        last sweep: swing low 2822.45 (2024-W02) taken to 2762.25 on 2025-03-21, closed back inside (frozen v2)
        last failed break: swing low 2822.45 closed beyond in 2025-W14, back inside on 2025-04-17 at 2826 (frozen v2)
     D: up for 42 bars; last BOS up 2025-05-27 at 3522.7; protected low 3411.4 (2025-05-21), weak high 3861 (2025-06-11); discount 36.3%
        last sweep: swing high 3324 (2025-03-19) taken to 3371.4 on 2025-05-07, closed back inside (frozen v2)
        last failed break: swing low 2822.45 closed beyond in 2025-03-26, back inside on 2025-03-27 at 2883.25 (frozen v2)
        D equal highs/lows (shown, not in the HTF zones): above EQH 4779.9 (2024-07-05, 2024-08-20) | below EQL 2223 (2023-08-01, 2023-08-16); EQL 1554.05 (2023-02-15, 2023-03-13)
     zones (untested) below: bull OB M 2223.00-2719.90; bull OB W 2431.30-2682.75 | above: supply W 3875.50-3964.85; bear OB M 4141.00-4706.00
     HTF strong zones (untested; 2+ families incl. structure, imbalance or liquidity; clustered at 0.3 ATR(W); point clusters at most 0.45 ATR(W); demand, supply and order-block bands keep their full range, 0.3 ATR(W) = 91.28): below 2178-2762.25 [structure+imbalance+volume+pivot] (M bull OB 2223-2719.9 (2023-08); Q virgin vol VAH 2023-Q2; W swing HL 2023-W33; Q S1 +35) | above 3622.5-3740 [imbalance+volume+pivot] (W TC; W MZ VAH 2025-W25; 250d LVN low (approx.); W H4 +6) | inside 3483.75-3620 [imbalance+volume+pivot] (W L4; M vol VAH 2025-05; 250d LVN low (approx.); W S1 +13)
     hot zones (Ochoa, recorded only): 32 DPZ, 31 multi-timeframe; GPZ: W H3 3619.88 bearish; M L3 3424.13 bullish; M MZ POC 3445; M MZ VAH 3520; M VPOC 3445; Q H3 3390.72 bearish; Q MZ VAL 3265; Y MZ POC 4240
     pivots (untested; *Q not Ochoa): W P 3606.5 CPR 3590.5-3622.5, average, lower value (bearish), closes below x1; M P 3430.07 CPR 3340-3520.13, wide, higher value (bullish), closes above x2; Q* P 3409.27 CPR 3151.06-3667.47, wide, lower value (bearish); Y P 4099.6 CPR 3931.07-4268.12, average, higher value (bullish)
     pivot levels below: W prev L 3540; W L3 3529.12; M TC 3520.13 | above: W BC 3590.5; W P 3606.5; W H3 3619.88
     profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 3590 VA 3570-3645, narrow, lower value / VPOC 3585; M MZ POC 3445 VA 3175-3520, average, higher value / VPOC 3445; Q* MZ POC 3910 VA 3265-4520, wide, overlapping lower / VPOC 2910; Y* MZ POC 4240 VA 3765-4690, narrow, higher value / VPOC 4480
     virgin (watch): W 2025-W24 MZ VAL 3720 (1.52 ATR); W 2025-W20 vol VAL 3360 (2.24 ATR); W 2025-W20 MZ VAL 3355 (2.29 ATR); W 2025-W24 vol POC 3815 (2.51 ATR)
     long profile (approximation (daily bars)): 250d POC 2870 VA 2535-4125, 8 HVN, 2 LVN; 750d POC 2870 VA 2220-4420, 9 HVN, 7 LVN
L2   daily layer (untested; intraday layer (definitions v1 §8): shown beside the HTF zones, never clustered into them)
     pivots from 2025-06-20: CPR 3574.6-3574.8 width 0.006% (narrow), lower value vs the day before; R3 3679, R2 3644.3, H4 3612.78, R1 3609.4, H3 3593.64, TC 3574.8, P 3574.7, BC 3574.6, L3 3555.36, S1 3539.8, L4 3536.22, S2 3505.1, S3 3470.2
     session 2025-06-20: money zone POC 3570 VA 3555-3585; volume POC 3570 VA 3555-3580
     virgin session levels (360 from 1871 sessions since 2017-12-01): below money zone POC 3475 (2025-05-26, 1.04 ATR); volume VAL 3445 (2025-05-26, 1.35 ATR); money zone VAL 3440 (2025-05-26, 1.41 ATR) | above money zone POC 3735 (2025-06-12, 1.68 ATR); volume VAH 3735 (2025-06-12, 1.68 ATR); money zone VAH 3800 (2025-06-12, 2.36 ATR)
```

Items:

- `R01.M.state` M: down for 3 bars
- `R01.M.event` M: last CHoCH down in 2025-02 at 3705
- `R01.M.protected` M: protected high 4706 (2024-12)
- `R01.M.weak` M: weak low 2424 (2025-04)
- `R01.M.pd` M: price in premium (50.4% of 2424-4706, eq 3565)
- `R01.M.sweep` M: swing high 1661.95 (2022-10) swept to 1730.95 on 2023-02-28, closed back inside (frozen v2)
- `R01.M.failed` M: swing low 3375.6 closed beyond in 2025-02, back inside on 2025-05-30 at 3610.2 (frozen v2)
- `R01.W.state` W: down for 34 bars
- `R01.W.event` W: last BOS down in 2025-W07 at 3705
- `R01.W.protected` W: protected high 4706 (2024-W50)
- `R01.W.weak` W: weak low 2424 (2025-W15)
- `R01.W.pd` W: price in premium (50.4% of 2424-4706, eq 3565)
- `R01.W.sweep` W: swing low 2822.45 (2024-W02) swept to 2762.25 on 2025-03-21, closed back inside (frozen v2)
- `R01.W.failed` W: swing low 2822.45 closed beyond in 2025-W14, back inside on 2025-04-17 at 2826 (frozen v2)
- `R01.D.state` D: up for 42 bars
- `R01.D.event` D: last BOS up in 2025-05-27 at 3522.7
- `R01.D.protected` D: protected low 3411.4 (2025-05-21)
- `R01.D.weak` D: weak high 3861 (2025-06-11)
- `R01.D.pd` D: price in discount (36.3% of 3411.4-3861, eq 3636.2)
- `R01.D.sweep` D: swing high 3324 (2025-03-19) swept to 3371.4 on 2025-05-07, closed back inside (frozen v2)
- `R01.D.failed` D: swing low 2822.45 closed beyond in 2025-03-26, back inside on 2025-03-27 at 2883.25 (frozen v2)
- `R01.D.liq` D equal highs/lows (shown, not in the HTF zones): above EQH 4779.9 (2024-07-05, 2024-08-20) | below EQL 2223 (2023-08-01, 2023-08-16); EQL 1554.05 (2023-02-15, 2023-03-13)
- `R01.Z.inside` price inside zone 3483.75–3620 [imbalance+volume+pivot] STRONG 0.0 ATR(D) away; W L4; M vol VAH 2025-05; 250d LVN low (approx.); W S1 +13
- `R01.Z.b1` zone below #1: 3325–3445 [volume+pivot] 1.35 ATR(D) away; W virgin MZ VAH 2025-W19; M BC; W virgin vol VAH 2025-W19; W virgin MZ VAL 2025-W20 +9
- `R01.Z.b2` zone below #2: 3151.06–3285 [volume+pivot] 3.03 ATR(D) away; Q BC; 250d HVN high (approx.); Y S1; M MZ VAL 2025-05 +10
- `R01.Z.b3` zone below #3: 2970–3050 [volume+pivot] 5.48 ATR(D) away; 250d HVN low (approx.); M prev L; W virgin MZ VAL 2025-W18; W virgin vol VAL 2025-W18 +1
- `R01.Z.a1` zone above #1: 3622.5–3740 [imbalance+volume+pivot] STRONG 0.5 ATR(D) away; W TC; W MZ VAH 2025-W25; 250d LVN low (approx.); W H4 +6
- `R01.Z.a2` zone above #2: 3760–4040 [imbalance+volume+pivot] STRONG 1.94 ATR(D) away; W supply 3875.5-3964.85 (2025-W09); Y vol VAL 2024; W R2; Y MZ VAL 2024 +16
- `R01.Z.a3` zone above #3: 4056.28–4706 [imbalance+volume+pivot] STRONG 5.03 ATR(D) away; M bear OB 4141-4706 (2024-12); Q R1; 250d VAH (approx.); Y P +25
- `R01.H.hot` Ochoa hot zones: 32 DPZ (31 multi-timeframe); GPZ: W H3 3619.88; M L3 3424.13; M MZ POC 3445; M MZ VAH 3520; M VPOC 3445; Q H3 3390.72; Q MZ VAL 3265; Y MZ POC 4240
- `R01.P.cpr` pivots (untested; *Q not Ochoa): W P 3606.5 CPR 3590.5-3622.5, average, lower value (bearish), closes below x1; M P 3430.07 CPR 3340-3520.13, wide, higher value (bullish), closes above x2; Q* P 3409.27 CPR 3151.06-3667.47, wide, lower value (bearish); Y P 4099.6 CPR 3931.07-4268.12, average, higher value (bullish)
- `R01.P.levels` pivot levels below: W prev L 3540; W L3 3529.12; M TC 3520.13 | above: W BC 3590.5; W P 3606.5; W H3 3619.88
- `R01.V.periods` profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 3590 VA 3570-3645, narrow, lower value / VPOC 3585; M MZ POC 3445 VA 3175-3520, average, higher value / VPOC 3445; Q* MZ POC 3910 VA 3265-4520, wide, overlapping lower / VPOC 2910; Y* MZ POC 4240 VA 3765-4690, narrow, higher value / VPOC 4480
- `R01.V.virgin` virgin (watch): W 2025-W24 MZ VAL 3720 (1.52 ATR); W 2025-W20 vol VAL 3360 (2.24 ATR); W 2025-W20 MZ VAL 3355 (2.29 ATR); W 2025-W24 vol POC 3815 (2.51 ATR)
- `R01.V.long` long profile (approximation (daily bars)): 250d POC 2870 VA 2535-4125, 8 HVN, 2 LVN; 750d POC 2870 VA 2220-4420, 9 HVN, 7 LVN
- `R01.L2.pivots` pivots from 2025-06-20: CPR 3574.6-3574.8 width 0.006% (narrow), lower value vs the day before; R3 3679, R2 3644.3, H4 3612.78, R1 3609.4, H3 3593.64, TC 3574.8, P 3574.7, BC 3574.6, L3 3555.36, S1 3539.8, L4 3536.22, S2 3505.1, S3 3470.2
- `R01.L2.session` session 2025-06-20: money zone POC 3570 VA 3555-3585; volume POC 3570 VA 3555-3580
- `R01.L2.virgin` virgin session levels (360 from 1871 sessions since 2017-12-01): below money zone POC 3475 (2025-05-26, 1.04 ATR); volume VAL 3445 (2025-05-26, 1.35 ATR); money zone VAL 3440 (2025-05-26, 1.41 ATR) | above money zone POC 3735 (2025-06-12, 1.68 ATR); volume VAH 3735 (2025-06-12, 1.68 ATR); money zone VAH 3800 (2025-06-12, 2.36 ATR)
- `R01.X.watch` not aligned: down on M, W, D up; first zone below 2178–2762.25, 8.49 ATR(D) away; first zone above 3622.5–3740, 0.5 ATR(D) away; inside 3483.75–3620

## R02 DMART, as of 2026-08-28 (last bar 2026-08-27, price 3847.4, ATR(D) 91.44)

```
MAP  DMART at 3847.4 (higher-timeframe map, bhavcopy to 2026-08-27) -- zones untested (no fidelity or signal test yet)
     below: 3735–3824.93 (W demand 3736.1-3824.3 (2026-W14); W virgin MZ VAL 2026-W13; W S2; W swing LL 2026-W31 +10), 0.58% away
     above: 4013.5–4380 (W bear OB 4013.5-4349.6 (2026-W25); M TC; M vol VAH 2026-07; W multi-touch x3 +28), 4.32% away
     price is inside the strong zone 3391–4090 (M bull OB 3391-4090 (2025-02); M S2; W swing LL 2024-W51; W virgin MZ POC 2025-W10 +60)
L1   structure (untested: no fidelity test yet) -- aligned down
     M: down for 6 bars; last CHoCH down 2026-01 at 3761.2; protected high 4644 (2026-04), weak low 3529 (2026-02); discount 28.6%
        last sweep: swing low 3644.3 (2024-02) taken to 3564 on 2024-11-29, closed back inside (frozen v2)
        last failed break: swing high 4557.7 closed beyond in 2025-08, back inside on 2025-09-30 at 4475.4 (frozen v2)
     W: down for 5 bars; last CHoCH down 2026-W29 at 3955; protected high 4429.4 (2026-W26), weak low 3755.1 (2026-W31); discount 13.7%
        last sweep: swing high 4032.2 (2026-W07) taken to 4056 on 2026-03-13, closed back inside (frozen v2)
        last failed break: swing low 3955 closed beyond in 2026-W29, back inside on 2026-07-24 at 4018.8 (frozen v2)
     D: down for 32 bars; last BOS down 2026-07-28 at 3886.7; protected high 4098.9 (2026-08-14), weak low 3737.2 (2026-08-26); discount 30.5%
        last sweep: swing low 3755.1 (2026-07-28) taken to 3737.2 on 2026-08-26, closed back inside (frozen v2)
        last failed break: swing low 3886.7 closed beyond in 2026-07-28, back inside on 2026-07-31 at 3921 (frozen v2)
        D equal highs/lows (shown, not in the HTF zones): above none | below EQL 1954.85 (2020-07-17, 2020-10-19)
     zones (untested) below: demand W 3736.10-3824.30; bull OB W 3399.00-3672.50 | above: multi-touch W 3850.00-3881.25; multi-touch W 3930.00-3955.00 | inside: bull OB W 3736.10-3905.30; bull OB M 3391.00-4090.00
     HTF strong zones (untested; 2+ families incl. structure, imbalance or liquidity; clustered at 0.3 ATR(W); point clusters at most 0.45 ATR(W); demand, supply and order-block bands keep their full range, 0.3 ATR(W) = 68.16): below 3735-3824.93 [structure+imbalance+volume+pivot] (W demand 3736.1-3824.3 (2026-W14); W virgin MZ VAL 2026-W13; W S2; W swing LL 2026-W31 +10) | above 4013.5-4380 [structure+imbalance+volume+pivot] (W bear OB 4013.5-4349.6 (2026-W25); M TC; M vol VAH 2026-07; W multi-touch x3 +28) | inside 3391-4090 [structure+imbalance+volume+pivot] (M bull OB 3391-4090 (2025-02); M S2; W swing LL 2024-W51; W virgin MZ POC 2025-W10 +60)
     hot zones (Ochoa, recorded only): 37 DPZ, 36 multi-timeframe; GPZ: W H3 3961.99 bearish; W MZ VAL 3965; M MZ POC 3985; M VPOC 3985; Y MZ POC 4042; Y VPOC 4042
     pivots (untested; *Q not Ochoa): W P 3947.47 CPR 3926.73-3968.2, average, lower value (bearish), closes below x1; M P 4016.93 CPR 3968.97-4064.9, average, lower value (bearish), closes below x1; Q* P 4326.57 CPR 4299.5-4353.63, narrow, higher value (bullish); Y P 4023.9 CPR 3903.05-4144.75, narrow, inside (breakout)
     pivot levels below: W S1 3824.93; W L4 3794.02; M prev L 3755.1 | above: W L3 3850.01; W prev L 3866.4; Y BC 3903.05
     profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 3990 VA 3965-4030, average, overlapping lower / VPOC 3990; M MZ POC 3985 VA 3905-4090, average, overlapping lower / VPOC 3985; Q* MZ POC 4385 VA 4195-4625, average, higher value / VPOC 4385; Y* MZ POC 4042 VA 3742-4456, average, overlapping lower / VPOC 4042
     virgin (watch): W 2026-W13 MZ VAL 3735 (1.23 ATR); Q 2026-Q1 vol VAL 3735 (1.23 ATR); Q 2026-Q1 MZ VAL 3715 (1.45 ATR); M 2026-06 MZ POC 4140 (3.2 ATR)
     long profile (approximation (daily bars)): 250d POC 4010 VA 3735-4325, 3 HVN, 0 LVN; 750d POC 4040 VA 3605-4450, 2 HVN, 0 LVN
L2   daily layer (untested; intraday layer (definitions v1 §8): shown beside the HTF zones, never clustered into them)
     pivots from 2026-08-27: CPR 3846.2-3847 width 0.021% (narrow), higher value vs the day before; R3 3931.6, R2 3903, H4 3878.42, R1 3875.2, H3 3862.91, TC 3847, P 3846.6, BC 3846.2, L3 3831.89, S1 3818.8, L4 3816.38, S2 3790.2, S3 3762.4
     session 2026-08-27: money zone POC 3855 VA 3845-3865; volume POC 3855 VA 3845-3865
     virgin session levels (201 from 2165 sessions since 2017-12-01): below volume POC 3810 (2026-08-26, 0.41 ATR); money zone VAL 3805 (2026-08-26, 0.46 ATR); volume VAL 3770 (2026-08-26, 0.85 ATR) | above money zone POC 3920 (2026-08-26, 0.79 ATR); money zone VAH 3935 (2026-08-26, 0.96 ATR); money zone VAH 3940 (2026-08-25, 1.01 ATR)
```

Items:

- `R02.M.state` M: down for 6 bars
- `R02.M.event` M: last CHoCH down in 2026-01 at 3761.2
- `R02.M.protected` M: protected high 4644 (2026-04)
- `R02.M.weak` M: weak low 3529 (2026-02)
- `R02.M.pd` M: price in discount (28.6% of 3529-4644, eq 4086.5)
- `R02.M.sweep` M: swing low 3644.3 (2024-02) swept to 3564 on 2024-11-29, closed back inside (frozen v2)
- `R02.M.failed` M: swing high 4557.7 closed beyond in 2025-08, back inside on 2025-09-30 at 4475.4 (frozen v2)
- `R02.W.state` W: down for 5 bars
- `R02.W.event` W: last CHoCH down in 2026-W29 at 3955
- `R02.W.protected` W: protected high 4429.4 (2026-W26)
- `R02.W.weak` W: weak low 3755.1 (2026-W31)
- `R02.W.pd` W: price in discount (13.7% of 3755.1-4429.4, eq 4092.25)
- `R02.W.sweep` W: swing high 4032.2 (2026-W07) swept to 4056 on 2026-03-13, closed back inside (frozen v2)
- `R02.W.failed` W: swing low 3955 closed beyond in 2026-W29, back inside on 2026-07-24 at 4018.8 (frozen v2)
- `R02.D.state` D: down for 32 bars
- `R02.D.event` D: last BOS down in 2026-07-28 at 3886.7
- `R02.D.protected` D: protected high 4098.9 (2026-08-14)
- `R02.D.weak` D: weak low 3737.2 (2026-08-26)
- `R02.D.pd` D: price in discount (30.5% of 3737.2-4098.9, eq 3918.05)
- `R02.D.sweep` D: swing low 3755.1 (2026-07-28) swept to 3737.2 on 2026-08-26, closed back inside (frozen v2)
- `R02.D.failed` D: swing low 3886.7 closed beyond in 2026-07-28, back inside on 2026-07-31 at 3921 (frozen v2)
- `R02.D.liq` D equal highs/lows (shown, not in the HTF zones): above none | below EQL 1954.85 (2020-07-17, 2020-10-19)
- `R02.Z.inside` price inside zone 3391–4090 [structure+imbalance+volume+pivot] STRONG 0.0 ATR(D) away; M bull OB 3391-4090 (2025-02); M S2; W swing LL 2024-W51; W virgin MZ POC 2025-W10 +60
- `R02.Z.inside2` price inside zone 3735–3947.47 [structure+imbalance+volume+pivot] STRONG 0.0 ATR(D) away; W bull OB 3736.1-3905.3 (2026-W12); W virgin MZ VAL 2026-W13; W S2; W swing LL 2026-W31 +19
- `R02.Z.b1` zone below #1: 3735–3824.93 [structure+imbalance+volume+pivot] STRONG 0.25 ATR(D) away; W demand 3736.1-3824.3 (2026-W14); W virgin MZ VAL 2026-W13; W S2; W swing LL 2026-W31 +10
- `R02.Z.b2` zone below #2: 3397.33–3715 [structure+imbalance+volume+pivot] STRONG 1.45 ATR(D) away; W bull OB 3399-3672.5 (2024-W51); M S2; W swing LL 2024-W51; W virgin MZ POC 2025-W10 +16
- `R02.Z.b3` zone below #3: 3382.15–3632.1 [structure+imbalance+volume+pivot] STRONG 2.35 ATR(D) away; W demand 3382.15-3632.1 (2023-W24); M S2; W swing LL 2024-W51; W virgin MZ POC 2025-W10 +11
- `R02.Z.a1` zone above #1: 4013.5–4380 [structure+imbalance+volume+pivot] STRONG 1.82 ATR(D) away; W bear OB 4013.5-4349.6 (2026-W25); M TC; M vol VAH 2026-07; W multi-touch x3 +28
- `R02.Z.a2` zone above #2: 4139.1–4805 [structure+imbalance+volume+pivot] STRONG 3.19 ATR(D) away; M bear OB 4139.1-4805 (2025-08); Q vol VAL 2026-Q2; Q L3; W swing LH 2026-W26 +49
- `R02.Z.a3` zone above #3: 4455–5180 [structure+imbalance+volume+pivot] STRONG 6.64 ATR(D) away; M bear OB 4455-5180 (2021-11); Q H3; M virgin MZ VAH 2026-05; W multi-touch x3 +32
- `R02.H.hot` Ochoa hot zones: 37 DPZ (36 multi-timeframe); GPZ: W H3 3961.99; W MZ VAL 3965; M MZ POC 3985; M VPOC 3985; Y MZ POC 4042; Y VPOC 4042
- `R02.P.cpr` pivots (untested; *Q not Ochoa): W P 3947.47 CPR 3926.73-3968.2, average, lower value (bearish), closes below x1; M P 4016.93 CPR 3968.97-4064.9, average, lower value (bearish), closes below x1; Q* P 4326.57 CPR 4299.5-4353.63, narrow, higher value (bullish); Y P 4023.9 CPR 3903.05-4144.75, narrow, inside (breakout)
- `R02.P.levels` pivot levels below: W S1 3824.93; W L4 3794.02; M prev L 3755.1 | above: W L3 3850.01; W prev L 3866.4; Y BC 3903.05
- `R02.V.periods` profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 3990 VA 3965-4030, average, overlapping lower / VPOC 3990; M MZ POC 3985 VA 3905-4090, average, overlapping lower / VPOC 3985; Q* MZ POC 4385 VA 4195-4625, average, higher value / VPOC 4385; Y* MZ POC 4042 VA 3742-4456, average, overlapping lower / VPOC 4042
- `R02.V.virgin` virgin (watch): W 2026-W13 MZ VAL 3735 (1.23 ATR); Q 2026-Q1 vol VAL 3735 (1.23 ATR); Q 2026-Q1 MZ VAL 3715 (1.45 ATR); M 2026-06 MZ POC 4140 (3.2 ATR)
- `R02.V.long` long profile (approximation (daily bars)): 250d POC 4010 VA 3735-4325, 3 HVN, 0 LVN; 750d POC 4040 VA 3605-4450, 2 HVN, 0 LVN
- `R02.L2.pivots` pivots from 2026-08-27: CPR 3846.2-3847 width 0.021% (narrow), higher value vs the day before; R3 3931.6, R2 3903, H4 3878.42, R1 3875.2, H3 3862.91, TC 3847, P 3846.6, BC 3846.2, L3 3831.89, S1 3818.8, L4 3816.38, S2 3790.2, S3 3762.4
- `R02.L2.session` session 2026-08-27: money zone POC 3855 VA 3845-3865; volume POC 3855 VA 3845-3865
- `R02.L2.virgin` virgin session levels (201 from 2165 sessions since 2017-12-01): below volume POC 3810 (2026-08-26, 0.41 ATR); money zone VAL 3805 (2026-08-26, 0.46 ATR); volume VAL 3770 (2026-08-26, 0.85 ATR) | above money zone POC 3920 (2026-08-26, 0.79 ATR); money zone VAH 3935 (2026-08-26, 0.96 ATR); money zone VAH 3940 (2026-08-25, 1.01 ATR)
- `R02.X.watch` aligned down; first zone below 3735–3824.93, 0.25 ATR(D) away; first zone above 4013.5–4380, 1.82 ATR(D) away; inside 3391–4090

## R03 JSL, as of 2026-03-04 (last bar 2026-03-02, price 783.35, ATR(D) 30.17)

```
MAP  JSL at 783.35 (higher-timeframe map, bhavcopy to 2026-03-02) -- zones untested (no fidelity or signal test yet)
     below: 652.2–714.85 (W bull OB 652.2-714.85 (2025-W25); Q S2; 250d HVN high (approx.); Q virgin MZ VAL 2025-Q3 +16), 8.74% away
     above: 840.28–864 (W R2; M swing HH 2024-07; W virgin MZ POC 2026-W02; W virgin vol POC 2026-W02), 7.27% away
     price is inside the strong zone 715.5–802 (W bull OB 715.5-765.6 (2025-W45); W swing LL 2025-W45; Q prev L; W virgin MZ VAL 2025-W46 +49)
L1   structure (untested: no fidelity test yet, history from 2015-11-19 (segment break)) -- aligned up
     M: up for 2 bars; last CHoCH up 2025-12 at 803; protected low 496.6 (2025-04), weak high 884 (2026-01); premium 74%
        last sweep: swing high 848 (2024-07) taken to 867 on 2025-12-31, closed back inside (frozen v2)
        last failed break: swing low 631 closed beyond in 2025-02, back inside on 2025-05-30 at 644.75 (frozen v2)
     W: up for 38 bars; last BOS up 2026-W01 at 826; protected low 730.2 (2026-W05), weak high 884 (2026-W02); discount 34.6%
        last sweep: swing low 729.85 (2025-W40) taken to 715.5 on 2025-11-07, closed back inside (frozen v2)
        last failed break: swing high 826 closed beyond in 2026-W01, back inside on 2026-01-09 at 772.15 (frozen v2)
     D: up for 22 bars; last CHoCH up 2026-01-30 at 816; protected low 734 (2026-02-17), weak high 830 (2026-01-30); premium 51.4%
        last sweep: swing low 748.55 (2026-01-12) taken to 735 on 2026-01-21, closed back inside (frozen v2)
        last failed break: swing low 744.05 closed beyond in 2026-02-17, back inside on 2026-02-18 at 758.3 (frozen v2)
        D equal highs/lows (shown, not in the HTF zones): above none | below EQL 652.2 (2025-06-19, 2025-07-28); EQL 90.55 (2021-06-01, 2021-06-18)
     zones (untested) below: bull OB W 715.50-765.60; multi-touch W 729.85-734.35 | above: none
     HTF strong zones (untested; 2+ families incl. structure, imbalance or liquidity; clustered at 0.3 ATR(W); point clusters at most 0.45 ATR(W); demand, supply and order-block bands keep their full range, 0.3 ATR(W) = 16.95): below 652.2-714.85 [imbalance+volume+pivot] (W bull OB 652.2-714.85 (2025-W25); Q S2; 250d HVN high (approx.); Q virgin MZ VAL 2025-Q3 +16) | above 840.28-864 [structure+volume+pivot] (W R2; M swing HH 2024-07; W virgin MZ POC 2026-W02; W virgin vol POC 2026-W02) | inside 715.5-802 [structure+imbalance+liquidity+volume+pivot] (W bull OB 715.5-765.6 (2025-W45); W swing LL 2025-W45; Q prev L; W virgin MZ VAL 2025-W46 +49)
     hot zones (Ochoa, recorded only): 31 DPZ, 29 multi-timeframe; GPZ: Q L3 797.59 bullish; Q MZ POC 792; Q MZ VAH 803; Y L3 737.39 bullish; Y MZ POC 758
     pivots (untested; *Q not Ochoa): W P 782.98 CPR 779.67-786.3, average, higher value (bullish), closes above x1; M P 778.38 CPR 777.37-779.4, narrow, lower value (bearish), closes below x1; Q* P 807.25 CPR 791.25-823.25, narrow, higher value (bullish); Y P 734.28 CPR 681.8-786.77, average, overlapping higher (moderately bullish)
     pivot levels below: W P 782.98; W BC 779.67; M TC 779.4 | above: W TC 786.3; Y TC 786.77; Q BC 791.25
     profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 794 VA 787-804, narrow, higher value / VPOC 793; M MZ POC 791 VA 769-813, average, inside / VPOC 798; Q* MZ POC 792 VA 748-803, narrow, overlapping higher / VPOC 751; Y* MZ POC 758 VA 634-812, narrow, outside / VPOC 589
     virgin (watch): W 2026-W05 vol VAH 822 (1.28 ATR); M 2026-01 vol VAH 826 (1.41 ATR); M 2026-01 MZ VAH 828 (1.48 ATR); W 2025-W46 MZ VAL 729 (1.8 ATR)
     long profile (approximation (daily bars)): 250d POC 792 VA 648-814, 4 HVN, 2 LVN; 750d POC 682 VA 544-814, 8 HVN, 4 LVN
L2   daily layer (untested; intraday layer (definitions v1 §8): shown beside the HTF zones, never clustered into them)
     pivots from 2026-03-02: CPR 766.65-777.78 width 1.442% (wide), lower value vs the day before; R3 857.73, R2 825.52, H4 812.66, R1 804.43, H3 798.01, TC 777.78, P 772.22, L3 768.69, BC 766.65, L4 754.04, S1 751.13, S2 718.92, S3 697.83
     session 2026-03-02: money zone POC 780 VA 772-788; volume POC 780 VA 776-786
     virgin session levels (320 from 2045 sessions since 2017-12-01): below money zone VAL 736 (2026-02-17, 1.57 ATR); volume VAL 736 (2026-02-17, 1.57 ATR); volume POC 729 (2025-11-12, 1.8 ATR) | above money zone VAH 797 (2026-02-27, 0.45 ATR); money zone VAH 864 (2026-01-07, 2.67 ATR); volume VAH 871 (2026-01-07, 2.91 ATR)
```

Items:

- `R03.M.state` M: up for 2 bars
- `R03.M.event` M: last CHoCH up in 2025-12 at 803
- `R03.M.protected` M: protected low 496.6 (2025-04)
- `R03.M.weak` M: weak high 884 (2026-01)
- `R03.M.pd` M: price in premium (74% of 496.6-884, eq 690.3)
- `R03.M.sweep` M: swing high 848 (2024-07) swept to 867 on 2025-12-31, closed back inside (frozen v2)
- `R03.M.failed` M: swing low 631 closed beyond in 2025-02, back inside on 2025-05-30 at 644.75 (frozen v2)
- `R03.W.state` W: up for 38 bars
- `R03.W.event` W: last BOS up in 2026-W01 at 826
- `R03.W.protected` W: protected low 730.2 (2026-W05)
- `R03.W.weak` W: weak high 884 (2026-W02)
- `R03.W.pd` W: price in discount (34.6% of 730.2-884, eq 807.1)
- `R03.W.sweep` W: swing low 729.85 (2025-W40) swept to 715.5 on 2025-11-07, closed back inside (frozen v2)
- `R03.W.failed` W: swing high 826 closed beyond in 2026-W01, back inside on 2026-01-09 at 772.15 (frozen v2)
- `R03.D.state` D: up for 22 bars
- `R03.D.event` D: last CHoCH up in 2026-01-30 at 816
- `R03.D.protected` D: protected low 734 (2026-02-17)
- `R03.D.weak` D: weak high 830 (2026-01-30)
- `R03.D.pd` D: price in premium (51.4% of 734-830, eq 782)
- `R03.D.sweep` D: swing low 748.55 (2026-01-12) swept to 735 on 2026-01-21, closed back inside (frozen v2)
- `R03.D.failed` D: swing low 744.05 closed beyond in 2026-02-17, back inside on 2026-02-18 at 758.3 (frozen v2)
- `R03.D.liq` D equal highs/lows (shown, not in the HTF zones): above none | below EQL 652.2 (2025-06-19, 2025-07-28); EQL 90.55 (2021-06-01, 2021-06-18)
- `R03.Z.inside` price inside zone 715.5–802 [structure+imbalance+liquidity+volume+pivot] STRONG 0.0 ATR(D) away; W bull OB 715.5-765.6 (2025-W45); W swing LL 2025-W45; Q prev L; W virgin MZ VAL 2025-W46 +49
- `R03.Z.b1` zone below #1: 652.2–714.85 [imbalance+volume+pivot] STRONG 2.27 ATR(D) away; W bull OB 652.2-714.85 (2025-W25); Q S2; 250d HVN high (approx.); Q virgin MZ VAL 2025-Q3 +16
- `R03.Z.b2` zone below #2: 573–664.8 [structure+imbalance+volume+pivot] STRONG 3.93 ATR(D) away; M bull OB 574.1-664.8 (2025-03); Y vol VAL 2025; M S4; W multi-touch x4 +37
- `R03.Z.b3` zone below #3: 544–597.95 [imbalance+volume+pivot] STRONG 6.15 ATR(D) away; W bull OB 547.25-597.95 (2025-W14); 750d VAL (approx.); M S4; M virgin MZ VAL 2025-04 +23
- `R03.Z.a1` zone above #1: 803–828 [volume+pivot] 0.65 ATR(D) away; Q MZ VAH 2025-Q4; Q P; W MZ VAH 2026-W09; W vol VAH 2026-W09 +16
- `R03.Z.a2` zone above #2: 840.28–864 [structure+volume+pivot] STRONG 1.89 ATR(D) away; W R2; M swing HH 2024-07; W virgin MZ POC 2026-W02; W virgin vol POC 2026-W02
- `R03.Z.a3` zone above #3: 867–884 [structure+volume+pivot] STRONG 2.77 ATR(D) away; Q prev H; W swing HH 2026-W02; W virgin MZ VAH 2026-W02; Y prev H +5
- `R03.H.hot` Ochoa hot zones: 31 DPZ (29 multi-timeframe); GPZ: Q L3 797.59; Q MZ POC 792; Q MZ VAH 803; Y L3 737.39; Y MZ POC 758
- `R03.P.cpr` pivots (untested; *Q not Ochoa): W P 782.98 CPR 779.67-786.3, average, higher value (bullish), closes above x1; M P 778.38 CPR 777.37-779.4, narrow, lower value (bearish), closes below x1; Q* P 807.25 CPR 791.25-823.25, narrow, higher value (bullish); Y P 734.28 CPR 681.8-786.77, average, overlapping higher (moderately bullish)
- `R03.P.levels` pivot levels below: W P 782.98; W BC 779.67; M TC 779.4 | above: W TC 786.3; Y TC 786.77; Q BC 791.25
- `R03.V.periods` profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 794 VA 787-804, narrow, higher value / VPOC 793; M MZ POC 791 VA 769-813, average, inside / VPOC 798; Q* MZ POC 792 VA 748-803, narrow, overlapping higher / VPOC 751; Y* MZ POC 758 VA 634-812, narrow, outside / VPOC 589
- `R03.V.virgin` virgin (watch): W 2026-W05 vol VAH 822 (1.28 ATR); M 2026-01 vol VAH 826 (1.41 ATR); M 2026-01 MZ VAH 828 (1.48 ATR); W 2025-W46 MZ VAL 729 (1.8 ATR)
- `R03.V.long` long profile (approximation (daily bars)): 250d POC 792 VA 648-814, 4 HVN, 2 LVN; 750d POC 682 VA 544-814, 8 HVN, 4 LVN
- `R03.L2.pivots` pivots from 2026-03-02: CPR 766.65-777.78 width 1.442% (wide), lower value vs the day before; R3 857.73, R2 825.52, H4 812.66, R1 804.43, H3 798.01, TC 777.78, P 772.22, L3 768.69, BC 766.65, L4 754.04, S1 751.13, S2 718.92, S3 697.83
- `R03.L2.session` session 2026-03-02: money zone POC 780 VA 772-788; volume POC 780 VA 776-786
- `R03.L2.virgin` virgin session levels (320 from 2045 sessions since 2017-12-01): below money zone VAL 736 (2026-02-17, 1.57 ATR); volume VAL 736 (2026-02-17, 1.57 ATR); volume POC 729 (2025-11-12, 1.8 ATR) | above money zone VAH 797 (2026-02-27, 0.45 ATR); money zone VAH 864 (2026-01-07, 2.67 ATR); volume VAH 871 (2026-01-07, 2.91 ATR)
- `R03.X.watch` aligned up; first zone below 652.2–714.85, 2.27 ATR(D) away; first zone above 840.28–864, 1.89 ATR(D) away; inside 715.5–802

## R04 LTM, as of 2026-10-13 (last bar 2026-10-12, price 4018.9, ATR(D) 132.58)

```
MAP  LTM at 4018.9 (higher-timeframe map, bhavcopy to 2026-10-12) -- zones untested (no fidelity or signal test yet)
     below: 3836.27–3967.59 (W S2; 250d HVN high (approx.); 250d LVN low (approx.); W virgin MZ POC 2026-W28 +14), 1.28% away
     above: 4290–4982.05 (W bear OB 4400-4778.9 (2026-W16); M MZ POC 2026-09; M TC; W multi-touch x4 +48), 6.75% away
L1   structure (untested: no fidelity test yet) -- aligned down
     M: down for 7 bars; last BOS down 2026-06 at 3802; protected high 6429.5 (2026-01), weak low 3528 (2026-06); discount 16.9%
        last sweep: swing low 4121 (2023-01) taken to 3802 on 2025-04-30, closed back inside (frozen v2)
        last failed break: swing low 3802 closed beyond in 2026-06, back inside on 2026-07-31 at 4362.1 (frozen v2)
     W: down for 34 bars; last BOS down 2026-W20 at 4000; protected high 4850 (2026-W33), weak low 3528 (2026-W27); discount 37.1%
        last sweep: swing high 4784 (2026-W17) taken to 4850 on 2026-08-14, closed back inside (frozen v2)
        last failed break: swing low 3802 closed beyond in 2026-W26, back inside on 2026-07-10 at 4037.2 (frozen v2)
     D: down for 21 bars; last CHoCH down 2026-09-09 at 4414.8; protected high 4700 (2026-08-28), weak low 3905.6 (2026-10-07); discount 14.3%
        last sweep: swing high 4360 (2026-06-02) taken to 4386.6 on 2026-07-28, closed back inside (frozen v2)
        last failed break: swing high 4784 closed beyond in 2026-08-10, back inside on 2026-08-12 at 4762.1 (frozen v2)
        D equal highs/lows (shown, not in the HTF zones): above none | below EQL 3525 (2021-05-17, 2026-06-30); EQL 724.55 (2017-08-11, 2017-08-24)
     zones (untested) below: demand W 3565.80-3699.30; multi-touch W 3525.00-3570.00 | above: bear OB W 4400.00-4778.90; multi-touch W 4450.00-4513.55
     HTF strong zones (untested; 2+ families incl. structure, imbalance or liquidity; clustered at 0.3 ATR(W); point clusters at most 0.45 ATR(W); demand, supply and order-block bands keep their full range, 0.3 ATR(W) = 88.24): below 3836.27-3967.59 [imbalance+volume+pivot] (W S2; 250d HVN high (approx.); 250d LVN low (approx.); W virgin MZ POC 2026-W28 +14) | above 4290-4982.05 [structure+imbalance+volume+pivot] (W bear OB 4400-4778.9 (2026-W16); M MZ POC 2026-09; M TC; W multi-touch x4 +48)
     hot zones (Ochoa, recorded only): 40 DPZ, 37 multi-timeframe; GPZ: W L3 4018.8 bullish; W MZ VAH 4010; M H3 4243.08 bearish; M MZ POC 4290; M MZ VAL 4130; M VPOC 4130; Q MZ VAL 4100; Y L3 5354.55 bullish
     pivots (untested; *Q not Ochoa): W P 4022.47 CPR 3998.7-4046.23, average, overlapping lower (moderately bearish), closes above x1; M P 4212.43 CPR 4128.72-4296.15, wide, lower value (bearish), closes below x1; Q* P 4143.4 CPR 4094.2-4192.6, narrow, overlapping higher (moderately bullish); Y P 5415.17 CPR 5091-5739.33, average, outside (sideways)
     pivot levels below: W L3 4018.8; W BC 3998.7; W L4 3967.59 | above: W P 4022.47; W TC 4046.23; W prev H 4091.8
     profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 3985 VA 3930-4010, narrow, overlapping lower / VPOC 3985; M MZ POC 4290 VA 4130-4610, wide, overlapping lower / VPOC 4130; Q* MZ POC 4550 VA 4100-4795, wide, overlapping higher / VPOC 4080; Y* MZ POC 5075 VA 4980-6070, average, overlapping lower / VPOC 5070
     virgin (watch): W 2026-W40 MZ VAH 4105 (0.65 ATR); W 2026-W40 vol VAH 4135 (0.88 ATR); M 2026-07 vol VAL 3900 (0.9 ATR); W 2026-W25 MZ VAL 3890 (0.97 ATR)
     long profile (approximation (daily bars)): 250d POC 4070 VA 3555-4850, 6 HVN, 4 LVN; 750d POC 5175 VA 4665-6425, 9 HVN, 2 LVN
L2   daily layer (untested; intraday layer (definitions v1 §8): shown beside the HTF zones, never clustered into them)
     pivots from 2026-10-12: CPR 4030.42-4053.45 width 0.57% (average), overlapping higher vs the day before; R3 4184.77, R2 4144.83, R1 4081.87, H4 4075.49, TC 4053.45, H3 4047.2, P 4041.93, BC 4030.42, L3 3990.6, S1 3978.97, L4 3962.31, S2 3939.03, S3 3876.07
     session 2026-10-12: money zone POC 4055 VA 4035-4085; volume POC 4065 VA 4025-4100
     virgin session levels (273 from 2195 sessions since 2017-12-01): below money zone VAL 4000 (2026-10-09, 0.14 ATR); money zone VAL 3900 (2026-07-10, 0.9 ATR); money zone VAL 3895 (2026-06-15, 0.93 ATR) | above volume VAH 4125 (2026-09-30, 0.8 ATR); money zone VAH 4145 (2026-09-29, 0.95 ATR); money zone VAH 4190 (2026-09-23, 1.29 ATR)
```

Items:

- `R04.M.state` M: down for 7 bars
- `R04.M.event` M: last BOS down in 2026-06 at 3802
- `R04.M.protected` M: protected high 6429.5 (2026-01)
- `R04.M.weak` M: weak low 3528 (2026-06)
- `R04.M.pd` M: price in discount (16.9% of 3528-6429.5, eq 4978.75)
- `R04.M.sweep` M: swing low 4121 (2023-01) swept to 3802 on 2025-04-30, closed back inside (frozen v2)
- `R04.M.failed` M: swing low 3802 closed beyond in 2026-06, back inside on 2026-07-31 at 4362.1 (frozen v2)
- `R04.W.state` W: down for 34 bars
- `R04.W.event` W: last BOS down in 2026-W20 at 4000
- `R04.W.protected` W: protected high 4850 (2026-W33)
- `R04.W.weak` W: weak low 3528 (2026-W27)
- `R04.W.pd` W: price in discount (37.1% of 3528-4850, eq 4189)
- `R04.W.sweep` W: swing high 4784 (2026-W17) swept to 4850 on 2026-08-14, closed back inside (frozen v2)
- `R04.W.failed` W: swing low 3802 closed beyond in 2026-W26, back inside on 2026-07-10 at 4037.2 (frozen v2)
- `R04.D.state` D: down for 21 bars
- `R04.D.event` D: last CHoCH down in 2026-09-09 at 4414.8
- `R04.D.protected` D: protected high 4700 (2026-08-28)
- `R04.D.weak` D: weak low 3905.6 (2026-10-07)
- `R04.D.pd` D: price in discount (14.3% of 3905.6-4700, eq 4302.8)
- `R04.D.sweep` D: swing high 4360 (2026-06-02) swept to 4386.6 on 2026-07-28, closed back inside (frozen v2)
- `R04.D.failed` D: swing high 4784 closed beyond in 2026-08-10, back inside on 2026-08-12 at 4762.1 (frozen v2)
- `R04.D.liq` D equal highs/lows (shown, not in the HTF zones): above none | below EQL 3525 (2021-05-17, 2026-06-30); EQL 724.55 (2017-08-11, 2017-08-24)
- `R04.Z.inside` price inside zone 3985–4105 [volume+pivot] 0.0 ATR(D) away; W MZ POC 2026-W41; W BC; W vol POC 2026-W41; M vol VAL 2026-09 +11
- `R04.Z.b1` zone below #1: 3836.27–3967.59 [imbalance+volume+pivot] STRONG 0.39 ATR(D) away; W S2; 250d HVN high (approx.); 250d LVN low (approx.); W virgin MZ POC 2026-W28 +14
- `R04.Z.b2` zone below #2: 3520–3805 [structure+imbalance+liquidity+volume+pivot] STRONG 1.61 ATR(D) away; W demand 3565.8-3699.3 (2021-W02); Y virgin vol VAL 2021; M swing HL 2021-05; M EQL +23
- `R04.Z.b3` zone below #3: 3211.1–3492.13 [imbalance+volume+pivot] STRONG 3.97 ATR(D) away; W demand 3211.1-3356.4 (2021-W01); W virgin MZ VAL 2020-W51; Q L4; Q virgin vol POC 2020-Q4 +13
- `R04.Z.a1` zone above #1: 4121.2–4243.08 [volume+pivot] 0.77 ATR(D) away; W H3; M MZ VAL 2026-09; M BC; M vol POC 2026-09 +8
- `R04.Z.a2` zone above #2: 4290–4982.05 [structure+imbalance+volume+pivot] STRONG 2.04 ATR(D) away; W bear OB 4400-4778.9 (2026-W16); M MZ POC 2026-09; M TC; W multi-touch x4 +48
- `R04.Z.a3` zone above #3: 5000–5115 [volume+pivot] 7.4 ATR(D) away; W virgin vol VAL 2026-W08; Y BC; W virgin MZ VAL 2026-W08; W virgin MZ POC 2026-W08 +6
- `R04.H.hot` Ochoa hot zones: 40 DPZ (37 multi-timeframe); GPZ: W L3 4018.8; W MZ VAH 4010; M H3 4243.08; M MZ POC 4290; M MZ VAL 4130; M VPOC 4130; Q MZ VAL 4100; Y L3 5354.55
- `R04.P.cpr` pivots (untested; *Q not Ochoa): W P 4022.47 CPR 3998.7-4046.23, average, overlapping lower (moderately bearish), closes above x1; M P 4212.43 CPR 4128.72-4296.15, wide, lower value (bearish), closes below x1; Q* P 4143.4 CPR 4094.2-4192.6, narrow, overlapping higher (moderately bullish); Y P 5415.17 CPR 5091-5739.33, average, outside (sideways)
- `R04.P.levels` pivot levels below: W L3 4018.8; W BC 3998.7; W L4 3967.59 | above: W P 4022.47; W TC 4046.23; W prev H 4091.8
- `R04.V.periods` profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 3985 VA 3930-4010, narrow, overlapping lower / VPOC 3985; M MZ POC 4290 VA 4130-4610, wide, overlapping lower / VPOC 4130; Q* MZ POC 4550 VA 4100-4795, wide, overlapping higher / VPOC 4080; Y* MZ POC 5075 VA 4980-6070, average, overlapping lower / VPOC 5070
- `R04.V.virgin` virgin (watch): W 2026-W40 MZ VAH 4105 (0.65 ATR); W 2026-W40 vol VAH 4135 (0.88 ATR); M 2026-07 vol VAL 3900 (0.9 ATR); W 2026-W25 MZ VAL 3890 (0.97 ATR)
- `R04.V.long` long profile (approximation (daily bars)): 250d POC 4070 VA 3555-4850, 6 HVN, 4 LVN; 750d POC 5175 VA 4665-6425, 9 HVN, 2 LVN
- `R04.L2.pivots` pivots from 2026-10-12: CPR 4030.42-4053.45 width 0.57% (average), overlapping higher vs the day before; R3 4184.77, R2 4144.83, R1 4081.87, H4 4075.49, TC 4053.45, H3 4047.2, P 4041.93, BC 4030.42, L3 3990.6, S1 3978.97, L4 3962.31, S2 3939.03, S3 3876.07
- `R04.L2.session` session 2026-10-12: money zone POC 4055 VA 4035-4085; volume POC 4065 VA 4025-4100
- `R04.L2.virgin` virgin session levels (273 from 2195 sessions since 2017-12-01): below money zone VAL 4000 (2026-10-09, 0.14 ATR); money zone VAL 3900 (2026-07-10, 0.9 ATR); money zone VAL 3895 (2026-06-15, 0.93 ATR) | above volume VAH 4125 (2026-09-30, 0.8 ATR); money zone VAH 4145 (2026-09-29, 0.95 ATR); money zone VAH 4190 (2026-09-23, 1.29 ATR)
- `R04.X.watch` aligned down; first zone below 3836.27–3967.59, 0.39 ATR(D) away; first zone above 4290–4982.05, 2.04 ATR(D) away

## R05 HCLTECH, as of 2025-07-14 (last bar 2025-07-11, price 1638.3, ATR(D) 32.21)

```
MAP  HCLTECH at 1638.3 (higher-timeframe map, bhavcopy to 2025-07-11) -- zones untested (no fidelity or signal test yet)
     below: 1301.65–1436.73 (M bull OB 1301.65-1377.9 (2024-05); 750d HVN low (approx.); M S4; 750d HVN high (approx.) +19), 12.3% away
     above: 1725.5–1760.1 (W prev H; Q vol VAH 2025-Q2; W weak 2025-W26; W virgin MZ VAH 2025-W27 +9), 5.32% away
     price is inside the strong zone 1527.62–1638.7 (W bull OB 1545-1598 (2025-W19); Q BC; W virgin MZ POC 2025-W14; W protected 2025-W20 +33)
L1   structure (untested: no fidelity test yet) -- not aligned: up on M, W, D down
     M: up for 24 bars; last BOS up 2024-08 at 1697.35; protected low 1302.75 (2025-04), weak high 2012.2 (2025-01); discount 47.3%
        last sweep: swing low 891 (2021-05) taken to 877.35 on 2022-07-29, closed back inside (frozen v2)
        last failed break: swing high 1156.65 closed beyond in 2023-06, back inside on 2023-07-31 at 1116.7 (frozen v2)
     W: up for 47 bars; last BOS up 2025-W25 at 1702.6; protected low 1594 (2025-W20), weak high 1752.5 (2025-W26); discount 27.9%
        last sweep: swing high 1702.6 (2025-W20) taken to 1726 on 2025-06-13, closed back inside (frozen v2)
        last failed break: swing high 1702.6 closed beyond in 2025-W25, back inside on 2025-07-11 at 1638.3 (frozen v2)
     D: down for 2 bars; last CHoCH down 2025-07-09 at 1689.2; protected high 1752.5 (2025-06-27), weak low 1630 (2025-07-11); discount 6.8%
        last sweep: swing high 1745 (2025-06-18) taken to 1752.5 on 2025-06-27, closed back inside (frozen v2)
        last failed break: swing high 1702.6 closed beyond in 2025-06-11, back inside on 2025-06-12 at 1701.2 (frozen v2)
        D equal highs/lows (shown, not in the HTF zones): above none | below EQL 1301.65 (2024-05-13, 2025-04-07); EQL 398.1 (2017-04-27, 2020-04-03)
     zones (untested) below: bull OB W 1545.00-1598.00; bull OB M 1301.65-1377.90 | above: none
     HTF strong zones (untested; 2+ families incl. structure, imbalance or liquidity; clustered at 0.3 ATR(W); point clusters at most 0.45 ATR(W); demand, supply and order-block bands keep their full range, 0.3 ATR(W) = 24.8): below 1301.65-1436.73 [imbalance+volume+pivot] (M bull OB 1301.65-1377.9 (2024-05); 750d HVN low (approx.); M S4; 750d HVN high (approx.) +19) | above 1725.5-1760.1 [structure+volume+pivot] (W prev H; Q vol VAH 2025-Q2; W weak 2025-W26; W virgin MZ VAH 2025-W27 +9) | inside 1527.62-1638.7 [structure+imbalance+volume+pivot] (W bull OB 1545-1598 (2025-W19); Q BC; W virgin MZ POC 2025-W14; W protected 2025-W20 +33)
     hot zones (Ochoa, recorded only): 41 DPZ, 39 multi-timeframe; GPZ: W H3 1664.56 bearish; W MZ VAL 1658; M L3 1688.23 bullish; M MZ POC 1710; M VPOC 1712; Q L3 1604.92 bullish; Q MZ POC 1638; Q MZ VAL 1560; Q VPOC 1576; Y L3 1712.53 bullish
     pivots (untested; *Q not Ochoa): W P 1664.6 CPR 1651.45-1677.75, wide, lower value (bearish), closes below x1; M P 1695.6 CPR 1679.1-1712.1, average, higher value (bullish), closes above x2; Q* P 1594.62 CPR 1527.62-1661.61, wide, overlapping lower (moderately bearish); Y P 1710.8 CPR 1607.5-1814.1, wide, higher value (bullish)
     pivot levels below: W prev L 1630; W L3 1612.04; Y BC 1607.5 | above: M S1 1638.7; M L4 1647.86; W BC 1651.45
     profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 1710 VA 1658-1718, wide, overlapping lower / VPOC 1638; M MZ POC 1710 VA 1670-1742, average, overlapping higher / VPOC 1712; Q* MZ POC 1638 VA 1560-1742, average, inside / VPOC 1576; Y* MZ POC 1580 VA 1414-1830, average, higher value / VPOC 1436
     virgin (watch): W 2025-W23 vol VAL 1626 (0.38 ATR); W 2025-W23 MZ VAL 1624 (0.44 ATR); W 2025-W19 MZ VAH 1580 (1.81 ATR); W 2025-W19 vol VAH 1576 (1.93 ATR)
     long profile (approximation (daily bars)): 250d POC 1714 VA 1530-1830, 5 HVN, 0 LVN; 750d POC 1120 VA 876-1582, 11 HVN, 6 LVN
L2   daily layer (untested; intraday layer (definitions v1 §8): shown beside the HTF zones, never clustered into them)
     pivots from 2025-07-11: CPR 1639.78-1642.75 width 0.181% (narrow), lower value vs the day before; R3 1678.03, R2 1666.77, R1 1652.53, H4 1652.33, H3 1645.31, TC 1642.75, P 1641.27, BC 1639.78, L3 1631.29, S1 1627.03, L4 1624.27, S2 1615.77, S3 1601.53
     session 2025-07-11: money zone POC 1638 VA 1634-1644; volume POC 1638 VA 1634-1640
     virgin session levels (232 from 1886 sessions since 2017-12-01): below money zone VAL 1626 (2025-06-06, 0.38 ATR); money zone VAH 1588 (2025-05-08, 1.56 ATR); volume VAH 1584 (2025-05-08, 1.69 ATR) | above volume VAL 1656 (2025-07-10, 0.55 ATR); money zone POC 1662 (2025-07-10, 0.74 ATR); volume POC 1662 (2025-07-10, 0.74 ATR)
```

Items:

- `R05.M.state` M: up for 24 bars
- `R05.M.event` M: last BOS up in 2024-08 at 1697.35
- `R05.M.protected` M: protected low 1302.75 (2025-04)
- `R05.M.weak` M: weak high 2012.2 (2025-01)
- `R05.M.pd` M: price in discount (47.3% of 1302.75-2012.2, eq 1657.47)
- `R05.M.sweep` M: swing low 891 (2021-05) swept to 877.35 on 2022-07-29, closed back inside (frozen v2)
- `R05.M.failed` M: swing high 1156.65 closed beyond in 2023-06, back inside on 2023-07-31 at 1116.7 (frozen v2)
- `R05.W.state` W: up for 47 bars
- `R05.W.event` W: last BOS up in 2025-W25 at 1702.6
- `R05.W.protected` W: protected low 1594 (2025-W20)
- `R05.W.weak` W: weak high 1752.5 (2025-W26)
- `R05.W.pd` W: price in discount (27.9% of 1594-1752.5, eq 1673.25)
- `R05.W.sweep` W: swing high 1702.6 (2025-W20) swept to 1726 on 2025-06-13, closed back inside (frozen v2)
- `R05.W.failed` W: swing high 1702.6 closed beyond in 2025-W25, back inside on 2025-07-11 at 1638.3 (frozen v2)
- `R05.D.state` D: down for 2 bars
- `R05.D.event` D: last CHoCH down in 2025-07-09 at 1689.2
- `R05.D.protected` D: protected high 1752.5 (2025-06-27)
- `R05.D.weak` D: weak low 1630 (2025-07-11)
- `R05.D.pd` D: price in discount (6.8% of 1630-1752.5, eq 1691.25)
- `R05.D.sweep` D: swing high 1745 (2025-06-18) swept to 1752.5 on 2025-06-27, closed back inside (frozen v2)
- `R05.D.failed` D: swing high 1702.6 closed beyond in 2025-06-11, back inside on 2025-06-12 at 1701.2 (frozen v2)
- `R05.D.liq` D equal highs/lows (shown, not in the HTF zones): above none | below EQL 1301.65 (2024-05-13, 2025-04-07); EQL 398.1 (2017-04-27, 2020-04-03)
- `R05.Z.inside` price inside zone 1527.62–1638.7 [structure+imbalance+volume+pivot] STRONG 0.0 ATR(D) away; W bull OB 1545-1598 (2025-W19); Q BC; W virgin MZ POC 2025-W14; W protected 2025-W20 +33
- `R05.Z.b1` zone below #1: 1481.24–1507.65 [volume+pivot] 4.06 ATR(D) away; Q L4; W virgin MZ VAL 2025-W17; M S3; W virgin vol VAL 2024-W28 +2
- `R05.Z.b2` zone below #2: 1440–1444 [volume+pivot] 6.03 ATR(D) away; 750d HVN high (approx.); Y S1; 750d HVN low (approx.); 750d HVN high (approx.)
- `R05.Z.b3` zone below #3: 1301.65–1436.73 [imbalance+volume+pivot] STRONG 6.26 ATR(D) away; M bull OB 1301.65-1377.9 (2024-05); 750d HVN low (approx.); M S4; 750d HVN high (approx.) +19
- `R05.Z.a1` zone above #1: 1646–1680 [volume+pivot] 0.24 ATR(D) away; 250d HVN high (approx.); M L4; W BC; W MZ VAL 2025-W28 +8
- `R05.Z.a2` zone above #2: 1688.23–1718 [volume+pivot] 1.55 ATR(D) away; M L3; W vol VAH 2025-W28; W H4; M P +12
- `R05.Z.a3` zone above #3: 1725.5–1760.1 [structure+volume+pivot] STRONG 2.71 ATR(D) away; W prev H; Q vol VAH 2025-Q2; W weak 2025-W26; W virgin MZ VAH 2025-W27 +9
- `R05.H.hot` Ochoa hot zones: 41 DPZ (39 multi-timeframe); GPZ: W H3 1664.56; W MZ VAL 1658; M L3 1688.23; M MZ POC 1710; M VPOC 1712; Q L3 1604.92; Q MZ POC 1638; Q MZ VAL 1560; Q VPOC 1576; Y L3 1712.53
- `R05.P.cpr` pivots (untested; *Q not Ochoa): W P 1664.6 CPR 1651.45-1677.75, wide, lower value (bearish), closes below x1; M P 1695.6 CPR 1679.1-1712.1, average, higher value (bullish), closes above x2; Q* P 1594.62 CPR 1527.62-1661.61, wide, overlapping lower (moderately bearish); Y P 1710.8 CPR 1607.5-1814.1, wide, higher value (bullish)
- `R05.P.levels` pivot levels below: W prev L 1630; W L3 1612.04; Y BC 1607.5 | above: M S1 1638.7; M L4 1647.86; W BC 1651.45
- `R05.V.periods` profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 1710 VA 1658-1718, wide, overlapping lower / VPOC 1638; M MZ POC 1710 VA 1670-1742, average, overlapping higher / VPOC 1712; Q* MZ POC 1638 VA 1560-1742, average, inside / VPOC 1576; Y* MZ POC 1580 VA 1414-1830, average, higher value / VPOC 1436
- `R05.V.virgin` virgin (watch): W 2025-W23 vol VAL 1626 (0.38 ATR); W 2025-W23 MZ VAL 1624 (0.44 ATR); W 2025-W19 MZ VAH 1580 (1.81 ATR); W 2025-W19 vol VAH 1576 (1.93 ATR)
- `R05.V.long` long profile (approximation (daily bars)): 250d POC 1714 VA 1530-1830, 5 HVN, 0 LVN; 750d POC 1120 VA 876-1582, 11 HVN, 6 LVN
- `R05.L2.pivots` pivots from 2025-07-11: CPR 1639.78-1642.75 width 0.181% (narrow), lower value vs the day before; R3 1678.03, R2 1666.77, R1 1652.53, H4 1652.33, H3 1645.31, TC 1642.75, P 1641.27, BC 1639.78, L3 1631.29, S1 1627.03, L4 1624.27, S2 1615.77, S3 1601.53
- `R05.L2.session` session 2025-07-11: money zone POC 1638 VA 1634-1644; volume POC 1638 VA 1634-1640
- `R05.L2.virgin` virgin session levels (232 from 1886 sessions since 2017-12-01): below money zone VAL 1626 (2025-06-06, 0.38 ATR); money zone VAH 1588 (2025-05-08, 1.56 ATR); volume VAH 1584 (2025-05-08, 1.69 ATR) | above volume VAL 1656 (2025-07-10, 0.55 ATR); money zone POC 1662 (2025-07-10, 0.74 ATR); volume POC 1662 (2025-07-10, 0.74 ATR)
- `R05.X.watch` not aligned: up on M, W, D down; first zone below 1301.65–1436.73, 6.26 ATR(D) away; first zone above 1725.5–1760.1, 2.71 ATR(D) away; inside 1527.62–1638.7

## R06 ANTELOPUS, as of 2026-08-24 (last bar 2026-08-21, price 800.1, ATR(D) 42.81)

```
MAP  ANTELOPUS at 800.1 (higher-timeframe map, bhavcopy to 2026-08-21) -- zones untested (no fidelity or signal test yet)
     below: 630–668 (M virgin MZ POC 2026-04; W multi-touch x4; M virgin vol POC 2026-04; 250d VAH (approx.) +5), 16.51% away
     above: 848.5–952 (W bear OB 848.5-935 (2024-W39); W prev H; W virgin vol POC 2026-W32; W swing HH 2026-W24 +18), 6.05% away
     price is inside the strong zone 737.6–929 (M bear OB 761.2-929 (2024-10); W S2; M virgin vol VAL 2026-06; Y R1 +48)
L1   structure (untested: no fidelity test yet) -- not aligned: up on M, W, D down
     M: up for 2 bars; last CHoCH up 2026-05 at 767.95; protected low 357 (2026-01), weak high 933.65 (2026-06); premium 76.8%
        last sweep: swing low 496.65 (2025-02) taken to 475.85 on 2025-05-30, closed back inside (frozen v2)
        last failed break: swing low 475.85 closed beyond in 2025-11, back inside on 2026-01-30 at 550.75 (frozen v2)
     W: up for 26 bars; last BOS up 2026-W18 at 652.55; protected low 504 (2026-W13), weak high 933.65 (2026-W24); premium 68.9%
        last sweep: swing high 767.95 (2025-W24) taken to 789.9 on 2026-05-15, closed back inside (frozen v2)
        last failed break: swing high 581.95 closed beyond in 2026-W08, back inside on 2026-02-27 at 514.65 (frozen v2)
     D: down for 17 bars; last BOS down 2026-08-14 at 790; protected high 895.9 (2026-08-06), weak low 776.45 (2026-08-14); discount 19.8%
        last sweep: swing high 889.95 (2026-07-14) taken to 911 on 2026-07-22, closed back inside (frozen v2)
        last failed break: swing low 790 closed beyond in 2026-08-14, back inside on 2026-08-17 at 800.9 (frozen v2)
        D equal highs/lows (shown, not in the HTF zones): above none | below EQL 502.8 (2026-02-26, 2026-03-23); EQL 122.05 (2021-12-01, 2021-12-20)
     zones (untested) below: multi-touch W 652.55-677.40; bull OB M 388.35-581.95 | above: bear OB W 848.50-935.00 | inside: bear OB W 775.30-929.00; bear OB M 761.20-929.00
     HTF strong zones (untested; 2+ families incl. structure, imbalance or liquidity; clustered at 0.3 ATR(W); point clusters at most 0.45 ATR(W); demand, supply and order-block bands keep their full range, 0.3 ATR(W) = 26.88): below 630-668 [structure+volume] (M virgin MZ POC 2026-04; W multi-touch x4; M virgin vol POC 2026-04; 250d VAH (approx.) +5) | above 848.5-952 [structure+imbalance+volume+pivot] (W bear OB 848.5-935 (2024-W39); W prev H; W virgin vol POC 2026-W32; W swing HH 2026-W24 +18) | inside 737.6-929 [imbalance+volume+pivot] (M bear OB 761.2-929 (2024-10); W S2; M virgin vol VAL 2026-06; Y R1 +48)
     hot zones (Ochoa, recorded only): 22 DPZ, 22 multi-timeframe; GPZ: W H3 822.17 bearish; Y H3 553.16 bearish; Y MZ POC 564; Y MZ VAL 506; Y VPOC 568
     pivots (untested; *Q not Ochoa): W P 817.85 CPR 808.98-826.73, average, higher value (bullish); M P 837.18 CPR 829.34-845.02, narrow, higher value (bullish); Q* P 760.75 CPR 743.97-777.53, narrow, higher value (bullish); Y P 550.92 CPR 481.03-620.8, wide, lower value (bearish)
     pivot levels below: W prev L 786.6; M L3 780.65; W L3 778.03 | above: W BC 808.98; W P 817.85; W H3 822.17
     profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 808 VA 792-830, average, outside / VPOC 798; M MZ POC 816 VA 790-862, narrow, inside / VPOC 816; Q* MZ POC 784 VA 648-862, wide, higher value / VPOC 682; Y* MZ POC 564 VA 506-698, average, overlapping lower / VPOC 568
     virgin (watch): M 2026-06 MZ VAL 770 (0.7 ATR); W 2026-W25 MZ VAL 756 (1.03 ATR); W 2026-W25 vol VAL 756 (1.03 ATR); M 2026-06 vol VAL 754 (1.08 ATR)
     long profile (approximation (daily bars)): 250d POC 564 VA 420-634, 2 HVN, 0 LVN; 750d POC 564 VA 384-688, 1 HVN, 0 LVN
L2   daily layer (untested; intraday layer (definitions v1 §8): shown beside the HTF zones, never clustered into them)
     pivots from 2026-08-21: CPR 800.95-802.65 width 0.212% (narrow), higher value vs the day before; R3 842.2, R2 829.3, H4 815.23, R1 814.7, H3 807.66, TC 802.65, P 801.8, BC 800.95, L3 792.54, S1 787.2, L4 784.98, S2 774.3, S3 759.7
     session 2026-08-21: money zone POC 798 VA 796-808; volume POC 800 VA 794-806
     virgin session levels (227 from 2160 sessions since 2017-12-01): below volume VAL 782 (2026-08-14, 0.42 ATR); volume VAL 776 (2026-07-03, 0.56 ATR); volume VAL 770 (2026-06-19, 0.7 ATR) | above volume VAH 818 (2026-08-19, 0.42 ATR); money zone VAH 840 (2026-08-19, 0.93 ATR); money zone VAH 866 (2026-08-18, 1.54 ATR)
```

Items:

- `R06.M.state` M: up for 2 bars
- `R06.M.event` M: last CHoCH up in 2026-05 at 767.95
- `R06.M.protected` M: protected low 357 (2026-01)
- `R06.M.weak` M: weak high 933.65 (2026-06)
- `R06.M.pd` M: price in premium (76.8% of 357-933.65, eq 645.33)
- `R06.M.sweep` M: swing low 496.65 (2025-02) swept to 475.85 on 2025-05-30, closed back inside (frozen v2)
- `R06.M.failed` M: swing low 475.85 closed beyond in 2025-11, back inside on 2026-01-30 at 550.75 (frozen v2)
- `R06.W.state` W: up for 26 bars
- `R06.W.event` W: last BOS up in 2026-W18 at 652.55
- `R06.W.protected` W: protected low 504 (2026-W13)
- `R06.W.weak` W: weak high 933.65 (2026-W24)
- `R06.W.pd` W: price in premium (68.9% of 504-933.65, eq 718.83)
- `R06.W.sweep` W: swing high 767.95 (2025-W24) swept to 789.9 on 2026-05-15, closed back inside (frozen v2)
- `R06.W.failed` W: swing high 581.95 closed beyond in 2026-W08, back inside on 2026-02-27 at 514.65 (frozen v2)
- `R06.D.state` D: down for 17 bars
- `R06.D.event` D: last BOS down in 2026-08-14 at 790
- `R06.D.protected` D: protected high 895.9 (2026-08-06)
- `R06.D.weak` D: weak low 776.45 (2026-08-14)
- `R06.D.pd` D: price in discount (19.8% of 776.45-895.9, eq 836.17)
- `R06.D.sweep` D: swing high 889.95 (2026-07-14) swept to 911 on 2026-07-22, closed back inside (frozen v2)
- `R06.D.failed` D: swing low 790 closed beyond in 2026-08-14, back inside on 2026-08-17 at 800.9 (frozen v2)
- `R06.D.liq` D equal highs/lows (shown, not in the HTF zones): above none | below EQL 502.8 (2026-02-26, 2026-03-23); EQL 122.05 (2021-12-01, 2021-12-20)
- `R06.Z.inside` price inside zone 737.6–929 [imbalance+volume+pivot] STRONG 0.0 ATR(D) away; M bear OB 761.2-929 (2024-10); W S2; M virgin vol VAL 2026-06; Y R1 +48
- `R06.Z.inside2` price inside zone 775.3–929 [imbalance+volume+pivot] STRONG 0.0 ATR(D) away; W bear OB 775.3-929 (2024-W44); W L3; Q MZ POC 2026-Q2; M L3 +34
- `R06.Z.b1` zone below #1: 682–716 [volume+pivot] 1.96 ATR(D) away; Q vol POC 2026-Q2; M S2; 750d VAH (approx.); Q L3 +5
- `R06.Z.b2` zone below #2: 630–668 [structure+volume] STRONG 3.09 ATR(D) away; M virgin MZ POC 2026-04; W multi-touch x4; M virgin vol POC 2026-04; 250d VAH (approx.) +5
- `R06.Z.b3` zone below #3: 388.35–620.8 [structure+imbalance+volume+pivot] STRONG 4.19 ATR(D) away; M bull OB 388.35-581.95 (2025-11); W multi-touch x4; 250d HVN low (approx.); Y BC +50
- `R06.Z.a1` zone above #1: 848.5–952 [structure+imbalance+volume+pivot] STRONG 1.13 ATR(D) away; W bear OB 848.5-935 (2024-W39); W prev H; W virgin vol POC 2026-W32; W swing HH 2026-W24 +18
- `R06.Z.a2` zone above #2: 967.2–1002.94 [structure+volume+pivot] STRONG 3.9 ATR(D) away; Q R1; W swing LH 2024-W45; W virgin MZ POC 2024-W36; W virgin vol POC 2024-W36 +5
- `R06.Z.a3` zone above #3: 1034–1067.32 [volume+pivot] 5.46 ATR(D) away; M virgin MZ VAH 2024-08; M R3; Y virgin MZ VAH 2024; W virgin vol POC 2024-W34 +5
- `R06.H.hot` Ochoa hot zones: 22 DPZ (22 multi-timeframe); GPZ: W H3 822.17; Y H3 553.16; Y MZ POC 564; Y MZ VAL 506; Y VPOC 568
- `R06.P.cpr` pivots (untested; *Q not Ochoa): W P 817.85 CPR 808.98-826.73, average, higher value (bullish); M P 837.18 CPR 829.34-845.02, narrow, higher value (bullish); Q* P 760.75 CPR 743.97-777.53, narrow, higher value (bullish); Y P 550.92 CPR 481.03-620.8, wide, lower value (bearish)
- `R06.P.levels` pivot levels below: W prev L 786.6; M L3 780.65; W L3 778.03 | above: W BC 808.98; W P 817.85; W H3 822.17
- `R06.V.periods` profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 808 VA 792-830, average, outside / VPOC 798; M MZ POC 816 VA 790-862, narrow, inside / VPOC 816; Q* MZ POC 784 VA 648-862, wide, higher value / VPOC 682; Y* MZ POC 564 VA 506-698, average, overlapping lower / VPOC 568
- `R06.V.virgin` virgin (watch): M 2026-06 MZ VAL 770 (0.7 ATR); W 2026-W25 MZ VAL 756 (1.03 ATR); W 2026-W25 vol VAL 756 (1.03 ATR); M 2026-06 vol VAL 754 (1.08 ATR)
- `R06.V.long` long profile (approximation (daily bars)): 250d POC 564 VA 420-634, 2 HVN, 0 LVN; 750d POC 564 VA 384-688, 1 HVN, 0 LVN
- `R06.L2.pivots` pivots from 2026-08-21: CPR 800.95-802.65 width 0.212% (narrow), higher value vs the day before; R3 842.2, R2 829.3, H4 815.23, R1 814.7, H3 807.66, TC 802.65, P 801.8, BC 800.95, L3 792.54, S1 787.2, L4 784.98, S2 774.3, S3 759.7
- `R06.L2.session` session 2026-08-21: money zone POC 798 VA 796-808; volume POC 800 VA 794-806
- `R06.L2.virgin` virgin session levels (227 from 2160 sessions since 2017-12-01): below volume VAL 782 (2026-08-14, 0.42 ATR); volume VAL 776 (2026-07-03, 0.56 ATR); volume VAL 770 (2026-06-19, 0.7 ATR) | above volume VAH 818 (2026-08-19, 0.42 ATR); money zone VAH 840 (2026-08-19, 0.93 ATR); money zone VAH 866 (2026-08-18, 1.54 ATR)
- `R06.X.watch` not aligned: up on M, W, D down; first zone below 630–668, 3.09 ATR(D) away; first zone above 848.5–952, 1.13 ATR(D) away; inside 737.6–929

## R07 NEOGEN, as of 2026-10-21 (last bar 2026-10-19, price 2481.8, ATR(D) 124.18)

```
MAP  NEOGEN at 2481.8 (higher-timeframe map, bhavcopy to 2026-10-19) -- zones untested (no fidelity or signal test yet)
     below: 1957.53–2384.9 (W bull OB 2086.4-2259 (2026-W35); Y R1; W virgin MZ POC 2026-W28; W protected 2026-W35 +49), 3.9% away
     above: 2499.7–2594.83 (M weak 2026-09; M prev H; W MZ POC 2026-W42; Q prev H +7), 0.72% away
L1   structure (untested: no fidelity test yet) -- aligned up
     M: up for 5 bars; last BOS up 2026-05 at 1797; protected low 966.7 (2025-12), weak high 2499.7 (2026-09); premium 98.8%
        last sweep: swing high 2420 (2024-12) taken to 2483.9 on 2026-08-31, closed back inside (frozen v2)
        last failed break: swing low 1390 closed beyond in 2025-11, back inside on 2026-02-27 at 1464.3 (frozen v2)
     W: up for 26 bars; last BOS up 2026-W38 at 2483.9; protected low 2086.4 (2026-W35), weak high 2785 (2026-W42); premium 56.6%
        last sweep: swing high 2374 (2026-W29) taken to 2483.9 on 2026-08-21, closed back inside (frozen v2)
        last failed break: swing high 2483.9 closed beyond in 2026-W38, back inside on 2026-09-25 at 2385.2 (frozen v2)
     D: up for 127 bars; last BOS up 2026-10-12 at 2499.7; protected low 2300 (2026-10-05), weak high 2785 (2026-10-14); discount 37.5%
        last sweep: swing high 2374 (2026-07-16) taken to 2483.9 on 2026-08-18, closed back inside (frozen v2)
        last failed break: swing high 2483.9 closed beyond in 2026-09-18, back inside on 2026-09-21 at 2359.8 (frozen v2)
        D equal highs/lows (shown, not in the HTF zones): above none | below EQL 1094.5 (2026-01-09, 2026-03-30); EQL 1090.5 (2026-01-09, 2026-01-27)
     zones (untested) below: bull OB W 2086.40-2259.00; multi-touch W 1795.00-1846.50 | above: none
     HTF strong zones (untested; 2+ families incl. structure, imbalance or liquidity; clustered at 0.3 ATR(W); point clusters at most 0.45 ATR(W); demand, supply and order-block bands keep their full range, 0.3 ATR(W) = 63.75): below 1957.53-2384.9 [structure+imbalance+volume+pivot] (W bull OB 2086.4-2259 (2026-W35); Y R1; W virgin MZ POC 2026-W28; W protected 2026-W35 +49) | above 2499.7-2594.83 [structure+volume+pivot] (M weak 2026-09; M prev H; W MZ POC 2026-W42; Q prev H +7)
     hot zones (Ochoa, recorded only): 26 DPZ, 25 multi-timeframe; GPZ: M L3 2345.28 bullish; M MZ POC 2375; M VPOC 2375; Q L3 2292.18 bullish; Q MZ VAH 2320; Y H3 1533.11 bearish; Y MZ POC 1600; Y MZ VAL 1398
     pivots (untested; *Q not Ochoa): W P 2551.57 CPR 2518.18-2584.95, wide, higher value (bullish), closes above x1; M P 2354.8 CPR 2306.4-2403.2, average, higher value (bullish), closes above x6; Q* P 2290.43 CPR 2209.85-2371.02, average, higher value (bullish); Y P 1462.12 CPR 1323.16-1601.07, lower value (bearish)
     pivot levels below: M TC 2403.2; W prev L 2384.9; W L3 2374.77 | above: M prev H 2499.7; Q prev H 2499.7; W BC 2518.18
     profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 2515 VA 2430-2585, average, overlapping higher / VPOC 2720; M MZ POC 2375 VA 2265-2480, average, higher value / VPOC 2375; Q* MZ POC 2160 VA 2005-2320, average, overlapping higher / VPOC 2375; Y* MZ POC 1600 VA 1398-1916, inside / VPOC 1096
     virgin (watch): W 2026-W41 MZ VAL 2380 (0.82 ATR); W 2026-W41 vol VAL 2375 (0.86 ATR); W 2026-W38 vol VAL 2290 (1.54 ATR); W 2026-W38 MZ VAL 2280 (1.63 ATR)
     long profile (approximation (daily bars)): 250d POC 1135 VA 975-2065, 6 HVN, 6 LVN; 750d POC 1135 VA 995-2015, 4 HVN, 2 LVN
L2   daily layer (untested; intraday layer (definitions v1 §8): shown beside the HTF zones, never clustered into them)
     pivots from 2026-10-19: CPR 2482-2482.4 width 0.016% (narrow), lower value vs the day before; R3 2608.6, R2 2566.6, H4 2528.22, R1 2524.2, H3 2505.01, TC 2482.4, P 2482.2, BC 2482, L3 2458.59, S1 2439.8, L4 2435.38, S2 2397.8, S3 2355.4
     session 2026-10-19: money zone POC 2480 VA 2475-2500; volume POC 2480 VA 2475-2495
     virgin session levels (181 from 1836 sessions since 2019-05-27): below money zone VAL 2430 (2026-10-13, 0.42 ATR); volume VAL 2430 (2026-10-13, 0.42 ATR); money zone VAL 2400 (2026-10-12, 0.66 ATR) | above money zone POC 2535 (2026-10-15, 0.43 ATR); volume POC 2535 (2026-10-15, 0.43 ATR); volume VAH 2545 (2026-10-15, 0.51 ATR)
```

Items:

- `R07.M.state` M: up for 5 bars
- `R07.M.event` M: last BOS up in 2026-05 at 1797
- `R07.M.protected` M: protected low 966.7 (2025-12)
- `R07.M.weak` M: weak high 2499.7 (2026-09)
- `R07.M.pd` M: price in premium (98.8% of 966.7-2499.7, eq 1733.2)
- `R07.M.sweep` M: swing high 2420 (2024-12) swept to 2483.9 on 2026-08-31, closed back inside (frozen v2)
- `R07.M.failed` M: swing low 1390 closed beyond in 2025-11, back inside on 2026-02-27 at 1464.3 (frozen v2)
- `R07.W.state` W: up for 26 bars
- `R07.W.event` W: last BOS up in 2026-W38 at 2483.9
- `R07.W.protected` W: protected low 2086.4 (2026-W35)
- `R07.W.weak` W: weak high 2785 (2026-W42)
- `R07.W.pd` W: price in premium (56.6% of 2086.4-2785, eq 2435.7)
- `R07.W.sweep` W: swing high 2374 (2026-W29) swept to 2483.9 on 2026-08-21, closed back inside (frozen v2)
- `R07.W.failed` W: swing high 2483.9 closed beyond in 2026-W38, back inside on 2026-09-25 at 2385.2 (frozen v2)
- `R07.D.state` D: up for 127 bars
- `R07.D.event` D: last BOS up in 2026-10-12 at 2499.7
- `R07.D.protected` D: protected low 2300 (2026-10-05)
- `R07.D.weak` D: weak high 2785 (2026-10-14)
- `R07.D.pd` D: price in discount (37.5% of 2300-2785, eq 2542.5)
- `R07.D.sweep` D: swing high 2374 (2026-07-16) swept to 2483.9 on 2026-08-18, closed back inside (frozen v2)
- `R07.D.failed` D: swing high 2483.9 closed beyond in 2026-09-18, back inside on 2026-09-21 at 2359.8 (frozen v2)
- `R07.D.liq` D equal highs/lows (shown, not in the HTF zones): above none | below EQL 1094.5 (2026-01-09, 2026-03-30); EQL 1090.5 (2026-01-09, 2026-01-27)
- `R07.Z.b1` zone below #1: 2403.2–2480 [volume+pivot] 0.01 ATR(D) away; M TC; 250d HVN high (approx.); W MZ VAL 2026-W42; Q vol VAH 2026-Q3 +2
- `R07.Z.b2` zone below #2: 1957.53–2384.9 [structure+imbalance+volume+pivot] STRONG 0.78 ATR(D) away; W bull OB 2086.4-2259 (2026-W35); Y R1; W virgin MZ POC 2026-W28; W protected 2026-W35 +49
- `R07.Z.b3` zone below #3: 1860–1950 [imbalance+volume+pivot] STRONG 4.28 ATR(D) away; M virgin MZ VAL 2026-06; 750d LVN high (approx.); Y H4; 250d LVN high (approx.) +8
- `R07.Z.a1` zone above #1: 2499.7–2594.83 [structure+volume+pivot] STRONG 0.14 ATR(D) away; M weak 2026-09; M prev H; W MZ POC 2026-W42; Q prev H +7
- `R07.Z.a2` zone above #2: 2596.5–2664.23 [pivot] 0.92 ATR(D) away; M R1; Q H3; Q R1; M H4
- `R07.Z.a3` zone above #3: 2704.86–2785 [structure+volume+pivot] STRONG 1.8 ATR(D) away; W H4; W vol POC 2026-W42; W weak 2026-W42; W R1 +5
- `R07.H.hot` Ochoa hot zones: 26 DPZ (25 multi-timeframe); GPZ: M L3 2345.28; M MZ POC 2375; M VPOC 2375; Q L3 2292.18; Q MZ VAH 2320; Y H3 1533.11; Y MZ POC 1600; Y MZ VAL 1398
- `R07.P.cpr` pivots (untested; *Q not Ochoa): W P 2551.57 CPR 2518.18-2584.95, wide, higher value (bullish), closes above x1; M P 2354.8 CPR 2306.4-2403.2, average, higher value (bullish), closes above x6; Q* P 2290.43 CPR 2209.85-2371.02, average, higher value (bullish); Y P 1462.12 CPR 1323.16-1601.07, lower value (bearish)
- `R07.P.levels` pivot levels below: M TC 2403.2; W prev L 2384.9; W L3 2374.77 | above: M prev H 2499.7; Q prev H 2499.7; W BC 2518.18
- `R07.V.periods` profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 2515 VA 2430-2585, average, overlapping higher / VPOC 2720; M MZ POC 2375 VA 2265-2480, average, higher value / VPOC 2375; Q* MZ POC 2160 VA 2005-2320, average, overlapping higher / VPOC 2375; Y* MZ POC 1600 VA 1398-1916, inside / VPOC 1096
- `R07.V.virgin` virgin (watch): W 2026-W41 MZ VAL 2380 (0.82 ATR); W 2026-W41 vol VAL 2375 (0.86 ATR); W 2026-W38 vol VAL 2290 (1.54 ATR); W 2026-W38 MZ VAL 2280 (1.63 ATR)
- `R07.V.long` long profile (approximation (daily bars)): 250d POC 1135 VA 975-2065, 6 HVN, 6 LVN; 750d POC 1135 VA 995-2015, 4 HVN, 2 LVN
- `R07.L2.pivots` pivots from 2026-10-19: CPR 2482-2482.4 width 0.016% (narrow), lower value vs the day before; R3 2608.6, R2 2566.6, H4 2528.22, R1 2524.2, H3 2505.01, TC 2482.4, P 2482.2, BC 2482, L3 2458.59, S1 2439.8, L4 2435.38, S2 2397.8, S3 2355.4
- `R07.L2.session` session 2026-10-19: money zone POC 2480 VA 2475-2500; volume POC 2480 VA 2475-2495
- `R07.L2.virgin` virgin session levels (181 from 1836 sessions since 2019-05-27): below money zone VAL 2430 (2026-10-13, 0.42 ATR); volume VAL 2430 (2026-10-13, 0.42 ATR); money zone VAL 2400 (2026-10-12, 0.66 ATR) | above money zone POC 2535 (2026-10-15, 0.43 ATR); volume POC 2535 (2026-10-15, 0.43 ATR); volume VAH 2545 (2026-10-15, 0.51 ATR)
- `R07.X.watch` aligned up; first zone below 1957.53–2384.9, 0.78 ATR(D) away; first zone above 2499.7–2594.83, 0.14 ATR(D) away

## R08 GRSE, as of 2026-08-07 (last bar 2026-08-06, price 2599.4, ATR(D) 71.37)

```
MAP  GRSE at 2599.4 (higher-timeframe map, bhavcopy to 2026-08-06) -- zones untested (no fidelity or signal test yet)
     below: 1963.7–2576 (M bull OB 1963.7-2576 (2026-03); M swing LL 2026-03; Q L4; Y MZ VAL 2025 +39), 0.9% away
     above: 3320–3359.47 (W virgin vol VAH 2026-W18; M swing HH 2026-04; Q prev H; M virgin MZ VAH 2026-04 +5), 27.72% away
     price is inside the strong zone 2487.9–3130 (M bear OB 2525-2979.6 (2025-11); M S1; 750d VAH (approx.); W swing HL 2026-W24 +71)
L1   structure (untested: no fidelity test yet) -- not aligned: up on M, W, D down
     M: up for 3 bars; last CHoCH up 2026-04 at 2845; protected low 1963.7 (2026-03), weak high 3339 (2026-04); discount 46.2%
        last sweep: swing high 2979.6 (2025-11) taken to 3339 on 2026-04-30, closed back inside (frozen v2)
        last failed break: swing low 2168.6 closed beyond in 2026-03, back inside on 2026-04-30 at 2930.8 (frozen v2)
     W: up for 14 bars; last CHoCH up 2026-W17 at 2844.9; protected low 2530 (2026-W24), weak high 3339 (2026-W18); discount 8.6%
        last sweep: swing high 2979.6 (2025-W47) taken to 3339 on 2026-04-30, closed back inside (frozen v2)
        last failed break: swing high 2979.6 closed beyond in 2026-W19, back inside on 2026-05-15 at 2685.9 (frozen v2)
     D: down for 21 bars; last BOS down 2026-08-05 at 2535.5; protected high 2665 (2026-07-29), weak low 2471.7 (2026-08-06); premium 66.1%
        last sweep: swing high 2576 (2026-03-06) taken to 2641 on 2026-04-10, closed back inside (frozen v2)
        last failed break: swing low 2535.5 closed beyond in 2026-08-05, back inside on 2026-08-06 at 2599.4 (frozen v2)
        D equal highs/lows (shown, not in the HTF zones): above EQH 3538.4 (2025-06-05, 2025-06-23) | below EQL 446 (2023-04-21, 2023-05-25)
     zones (untested) below: multi-touch W 2525.00-2579.70; bull OB M 1963.70-2576.00 | above: multi-touch W 2829.80-2844.90 | inside: bear OB M 2525.00-2979.60
     HTF strong zones (untested; 2+ families incl. structure, imbalance or liquidity; clustered at 0.3 ATR(W); point clusters at most 0.45 ATR(W); demand, supply and order-block bands keep their full range, 0.3 ATR(W) = 65.04): below 1963.7-2576 [structure+imbalance+volume+pivot] (M bull OB 1963.7-2576 (2026-03); M swing LL 2026-03; Q L4; Y MZ VAL 2025 +39) | above 3320-3359.47 [structure+volume+pivot] (W virgin vol VAH 2026-W18; M swing HH 2026-04; Q prev H; M virgin MZ VAH 2026-04 +5) | inside 2487.9-3130 [structure+imbalance+volume+pivot] (M bear OB 2525-2979.6 (2025-11); M S1; 750d VAH (approx.); W swing HL 2026-W24 +71)
     hot zones (Ochoa, recorded only): 27 DPZ, 27 multi-timeframe; GPZ: W MZ POC 2612; W VPOC 2614; M MZ POC 2632; M MZ VAH 2664
     pivots (untested; *Q not Ochoa): W P 2610.97 CPR 2606.08-2615.85, narrow, higher value (bullish), closes above x1; M P 2648.8 CPR 2625-2672.6, narrow, lower value (bearish), closes below x1; Q* P 2705.73 CPR 2695.5-2715.97, narrow, higher value (bullish); Y P 2389.13 CPR 2361.65-2416.62, higher value (bullish)
     pivot levels below: W L3 2574.17; W prev L 2566.7; W S1 2556.93 | above: W BC 2606.08; W P 2610.97; W TC 2615.85
     profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 2612 VA 2586-2624, narrow, overlapping higher / VPOC 2614; M MZ POC 2632 VA 2554-2664, narrow, overlapping lower / VPOC 2614; Q* MZ POC 2675 VA 2555-2945, narrow, overlapping higher / VPOC 2675; Y* MZ POC 2610 VA 2040-3535, overlapping higher / VPOC 2610
     virgin (watch): W 2026-W28 vol POC 2695 (1.34 ATR); W 2026-W28 MZ VAH 2710 (1.55 ATR); W 2026-W28 vol VAH 2725 (1.76 ATR); W 2026-W12 vol POC 2385 (3 ATR)
     long profile (approximation (daily bars)): 250d POC 2610 VA 2405-2860, 1 HVN, 0 LVN; 750d POC 830 VA 585-2515, 8 HVN, 2 LVN
L2   daily layer (untested; intraday layer (definitions v1 §8): shown beside the HTF zones, never clustered into them)
     pivots from 2026-08-06: CPR 2558.1-2585.63 width 1.071% (wide), higher value vs the day before; R3 2844.83, R2 2744.67, H4 2694.44, R1 2672.03, H3 2646.92, TC 2585.63, P 2571.87, BC 2558.1, L3 2551.88, L4 2504.36, S1 2499.23, S2 2399.07, S3 2326.43
     session 2026-08-06: money zone POC 2600 VA 2545-2640; volume POC 2600 VA 2560-2640
     virgin session levels (350 from 1926 sessions since 2018-10-30): below volume VAL 2435 (2026-04-08, 2.3 ATR); money zone POC 2385 (2026-03-18, 3.0 ATR); volume POC 2385 (2026-03-18, 3.0 ATR) | above money zone POC 2680 (2026-07-08, 1.13 ATR); money zone VAH 2695 (2026-07-08, 1.34 ATR); money zone POC 2700 (2026-07-07, 1.41 ATR)
```

Items:

- `R08.M.state` M: up for 3 bars
- `R08.M.event` M: last CHoCH up in 2026-04 at 2845
- `R08.M.protected` M: protected low 1963.7 (2026-03)
- `R08.M.weak` M: weak high 3339 (2026-04)
- `R08.M.pd` M: price in discount (46.2% of 1963.7-3339, eq 2651.35)
- `R08.M.sweep` M: swing high 2979.6 (2025-11) swept to 3339 on 2026-04-30, closed back inside (frozen v2)
- `R08.M.failed` M: swing low 2168.6 closed beyond in 2026-03, back inside on 2026-04-30 at 2930.8 (frozen v2)
- `R08.W.state` W: up for 14 bars
- `R08.W.event` W: last CHoCH up in 2026-W17 at 2844.9
- `R08.W.protected` W: protected low 2530 (2026-W24)
- `R08.W.weak` W: weak high 3339 (2026-W18)
- `R08.W.pd` W: price in discount (8.6% of 2530-3339, eq 2934.5)
- `R08.W.sweep` W: swing high 2979.6 (2025-W47) swept to 3339 on 2026-04-30, closed back inside (frozen v2)
- `R08.W.failed` W: swing high 2979.6 closed beyond in 2026-W19, back inside on 2026-05-15 at 2685.9 (frozen v2)
- `R08.D.state` D: down for 21 bars
- `R08.D.event` D: last BOS down in 2026-08-05 at 2535.5
- `R08.D.protected` D: protected high 2665 (2026-07-29)
- `R08.D.weak` D: weak low 2471.7 (2026-08-06)
- `R08.D.pd` D: price in premium (66.1% of 2471.7-2665, eq 2568.35)
- `R08.D.sweep` D: swing high 2576 (2026-03-06) swept to 2641 on 2026-04-10, closed back inside (frozen v2)
- `R08.D.failed` D: swing low 2535.5 closed beyond in 2026-08-05, back inside on 2026-08-06 at 2599.4 (frozen v2)
- `R08.D.liq` D equal highs/lows (shown, not in the HTF zones): above EQH 3538.4 (2025-06-05, 2025-06-23) | below EQL 446 (2023-04-21, 2023-05-25)
- `R08.Z.inside` price inside zone 2487.9–3130 [structure+imbalance+volume+pivot] STRONG 0.0 ATR(D) away; M bear OB 2525-2979.6 (2025-11); M S1; 750d VAH (approx.); W swing HL 2026-W24 +71
- `R08.Z.b1` zone below #1: 1963.7–2576 [structure+imbalance+volume+pivot] STRONG 0.33 ATR(D) away; M bull OB 1963.7-2576 (2026-03); M swing LL 2026-03; Q L4; Y MZ VAL 2025 +39
- `R08.Z.b2` zone below #2: 2060–2249 [imbalance+pivot] STRONG 4.91 ATR(D) away; W bull OB 2060-2249 (2026-W13); Q S1; M S4; M S3
- `R08.Z.b3` zone below #3: 1741.2–1905 [imbalance+volume+pivot] STRONG 9.73 ATR(D) away; W demand 1741.2-1894.6 (2025-W20); M virgin MZ VAL 2025-05; Y L3; Q virgin vol POC 2025-Q2 +11
- `R08.Z.a1` zone above #1: 3197.2 [pivot] 8.38 ATR(D) away; M R4
- `R08.Z.a2` zone above #2: 3320–3359.47 [structure+volume+pivot] STRONG 10.1 ATR(D) away; W virgin vol VAH 2026-W18; M swing HH 2026-04; Q prev H; M virgin MZ VAH 2026-04 +5
- `R08.Z.a3` zone above #3: 3434.05 [pivot] 11.69 ATR(D) away; Q H4
- `R08.H.hot` Ochoa hot zones: 27 DPZ (27 multi-timeframe); GPZ: W MZ POC 2612; W VPOC 2614; M MZ POC 2632; M MZ VAH 2664
- `R08.P.cpr` pivots (untested; *Q not Ochoa): W P 2610.97 CPR 2606.08-2615.85, narrow, higher value (bullish), closes above x1; M P 2648.8 CPR 2625-2672.6, narrow, lower value (bearish), closes below x1; Q* P 2705.73 CPR 2695.5-2715.97, narrow, higher value (bullish); Y P 2389.13 CPR 2361.65-2416.62, higher value (bullish)
- `R08.P.levels` pivot levels below: W L3 2574.17; W prev L 2566.7; W S1 2556.93 | above: W BC 2606.08; W P 2610.97; W TC 2615.85
- `R08.V.periods` profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 2612 VA 2586-2624, narrow, overlapping higher / VPOC 2614; M MZ POC 2632 VA 2554-2664, narrow, overlapping lower / VPOC 2614; Q* MZ POC 2675 VA 2555-2945, narrow, overlapping higher / VPOC 2675; Y* MZ POC 2610 VA 2040-3535, overlapping higher / VPOC 2610
- `R08.V.virgin` virgin (watch): W 2026-W28 vol POC 2695 (1.34 ATR); W 2026-W28 MZ VAH 2710 (1.55 ATR); W 2026-W28 vol VAH 2725 (1.76 ATR); W 2026-W12 vol POC 2385 (3 ATR)
- `R08.V.long` long profile (approximation (daily bars)): 250d POC 2610 VA 2405-2860, 1 HVN, 0 LVN; 750d POC 830 VA 585-2515, 8 HVN, 2 LVN
- `R08.L2.pivots` pivots from 2026-08-06: CPR 2558.1-2585.63 width 1.071% (wide), higher value vs the day before; R3 2844.83, R2 2744.67, H4 2694.44, R1 2672.03, H3 2646.92, TC 2585.63, P 2571.87, BC 2558.1, L3 2551.88, L4 2504.36, S1 2499.23, S2 2399.07, S3 2326.43
- `R08.L2.session` session 2026-08-06: money zone POC 2600 VA 2545-2640; volume POC 2600 VA 2560-2640
- `R08.L2.virgin` virgin session levels (350 from 1926 sessions since 2018-10-30): below volume VAL 2435 (2026-04-08, 2.3 ATR); money zone POC 2385 (2026-03-18, 3.0 ATR); volume POC 2385 (2026-03-18, 3.0 ATR) | above money zone POC 2680 (2026-07-08, 1.13 ATR); money zone VAH 2695 (2026-07-08, 1.34 ATR); money zone POC 2700 (2026-07-07, 1.41 ATR)
- `R08.X.watch` not aligned: up on M, W, D down; first zone below 1963.7–2576, 0.33 ATR(D) away; first zone above 3320–3359.47, 10.1 ATR(D) away; inside 2487.9–3130

## R09 IRFC, as of 2025-07-28 (last bar 2025-07-25, price 132.03, ATR(D) 3.19)

```
MAP  IRFC at 132.03 (higher-timeframe map, bhavcopy to 2025-07-25) -- zones untested (no fidelity or signal test yet)
     below: 112.96–117.2 (Y L3; W swing HL 2025-W15; 750d LVN high (approx.); Q prev L +1), 11.23% away
     above: 132.54–155.52 (W bear OB 134.72-155.52 (2025-W05); M S1; Y vol VAL 2024; W swing HH 2025-W24 +63), 0.39% away
     price is inside the strong zone 118–134.6 (W bull OB 123.69-134.6 (2025-W13); W virgin MZ VAL 2025-W19; Q S1; W swing HL 2025-W25 +33)
L1   structure (untested: no fidelity test yet) -- not aligned: down on M, D, W up
     M: down for 4 bars; last CHoCH down 2025-02 at 132.8; protected high 166.9 (2024-12), weak low 108.04 (2025-03); discount 40.8%
        last sweep: swing low 132.8 (2024-10) taken to 127.71 on 2025-01-31, closed back inside (frozen v2)
        last failed break: swing low 132.8 closed beyond in 2025-02, back inside on 2025-05-30 at 138.95 (frozen v2)
     W: up for 10 bars; last CHoCH up 2025-W20 at 134.6; protected low 131.56 (2025-W25), weak high 148.95 (2025-W24); discount 2.7%
        last sweep: swing low 131.56 (2025-W25) taken to 130.51 on 2025-07-25, closed back inside (frozen v2)
        last failed break: swing low 116.65 closed beyond in 2025-W09, back inside on 2025-03-07 at 123.42 (frozen v2)
     D: down for 26 bars; last BOS down 2025-07-22 at 131.56; protected high 143.15 (2025-07-01), weak low 130.51 (2025-07-22); discount 12%
        last sweep: swing high 143.61 (2025-05-19) taken to 144.3 on 2025-06-03, closed back inside (frozen v2)
        last failed break: swing low 131.56 closed beyond in 2025-07-22, back inside on 2025-07-23 at 134.85 (frozen v2)
        D equal highs/lows (shown, not in the HTF zones): above none | below EQL 20.8 (2022-08-23, 2022-09-26)
     zones (untested) below: demand W 96.05-100.75; bull OB M 50.10-92.35 | above: bear OB W 134.72-155.52; bear OB M 144.70-166.90 | inside: bull OB W 123.69-134.60
     HTF strong zones (untested; 2+ families incl. structure, imbalance or liquidity; clustered at 0.3 ATR(W); point clusters at most 0.45 ATR(W); demand, supply and order-block bands keep their full range, 0.3 ATR(W) = 3.03): below 112.96-117.2 [structure+imbalance+pivot] (Y L3; W swing HL 2025-W15; 750d LVN high (approx.); Q prev L +1) | above 132.54-155.52 [structure+imbalance+volume+pivot] (W bear OB 134.72-155.52 (2025-W05); M S1; Y vol VAL 2024; W swing HH 2025-W24 +63) | inside 118-134.6 [structure+imbalance+volume+pivot] (W bull OB 123.69-134.6 (2025-W13); W virgin MZ VAL 2025-W19; Q S1; W swing HL 2025-W25 +33)
     hot zones (Ochoa, recorded only): 35 DPZ, 30 multi-timeframe; GPZ: W H3 134.09 bearish; Q L3 131.83 bullish
     pivots (untested; *Q not Ochoa): W P 133.51 CPR 132.77-134.25, average, lower value (bearish), closes below x3; M P 140.74 CPR 140.25-141.23, narrow, higher value (bullish), closes above x3; Q* P 134.56 CPR 130.97-138.14, average, overlapping higher (moderately bullish); Y P 158.61 CPR 153.83-163.4, higher value (bullish)
     pivot levels below: Q L3 131.83; M prev L 131.56; Q BC 130.97 | above: M L4 132.16; M S1 132.54; W BC 132.77
     profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 134.4 VA 131.6-135.2, average, overlapping lower / VPOC 134.4; M MZ POC 140 VA 135.4-145.4, narrow, overlapping higher / VPOC 140; Q* MZ POC 140 VA 124.6-142.6, average, inside / VPOC 140; Y* MZ POC 147.4 VA 135-178.6, higher value / VPOC 146.6
     virgin (watch): W 2025-W20 MZ POC 130.2 (0.57 ATR); W 2025-W20 vol POC 130 (0.64 ATR); M 2025-05 vol VAL 129.2 (0.89 ATR); W 2025-W20 MZ VAL 125.2 (2.14 ATR)
     long profile (approximation (daily bars)): 250d POC 140 VA 122.4-159.8, 10 HVN, 2 LVN; 750d POC 33.2 VA 20.4-142.2, 11 HVN, 6 LVN
L2   daily layer (untested; intraday layer (definitions v1 §8): shown beside the HTF zones, never clustered into them)
     pivots from 2025-07-25: CPR 132.43-133.24 width 0.607% (average), lower value vs the day before; R3 139.21, R2 137.36, R1 134.69, H4 134.52, H3 133.27, TC 133.24, P 132.84, BC 132.43, L3 130.79, S1 130.17, L4 129.54, S2 128.32, S3 125.65
     session 2025-07-25: money zone POC 132.6 VA 131.8-133.4; volume POC 132.8 VA 131.6-133.2
     virgin session levels (240 from 1101 sessions since 2021-02-17): below volume VAL 130.9 (2025-07-22, 0.35 ATR); money zone VAL 129.8 (2025-05-15, 0.7 ATR); volume VAL 129.6 (2025-05-15, 0.76 ATR) | above money zone VAL 135.6 (2025-07-24, 1.12 ATR); money zone POC 135.8 (2025-07-24, 1.18 ATR); volume VAL 135.8 (2025-07-24, 1.18 ATR)
```

Items:

- `R09.M.state` M: down for 4 bars
- `R09.M.event` M: last CHoCH down in 2025-02 at 132.8
- `R09.M.protected` M: protected high 166.9 (2024-12)
- `R09.M.weak` M: weak low 108.04 (2025-03)
- `R09.M.pd` M: price in discount (40.8% of 108.04-166.9, eq 137.47)
- `R09.M.sweep` M: swing low 132.8 (2024-10) swept to 127.71 on 2025-01-31, closed back inside (frozen v2)
- `R09.M.failed` M: swing low 132.8 closed beyond in 2025-02, back inside on 2025-05-30 at 138.95 (frozen v2)
- `R09.W.state` W: up for 10 bars
- `R09.W.event` W: last CHoCH up in 2025-W20 at 134.6
- `R09.W.protected` W: protected low 131.56 (2025-W25)
- `R09.W.weak` W: weak high 148.95 (2025-W24)
- `R09.W.pd` W: price in discount (2.7% of 131.56-148.95, eq 140.25)
- `R09.W.sweep` W: swing low 131.56 (2025-W25) swept to 130.51 on 2025-07-25, closed back inside (frozen v2)
- `R09.W.failed` W: swing low 116.65 closed beyond in 2025-W09, back inside on 2025-03-07 at 123.42 (frozen v2)
- `R09.D.state` D: down for 26 bars
- `R09.D.event` D: last BOS down in 2025-07-22 at 131.56
- `R09.D.protected` D: protected high 143.15 (2025-07-01)
- `R09.D.weak` D: weak low 130.51 (2025-07-22)
- `R09.D.pd` D: price in discount (12% of 130.51-143.15, eq 136.83)
- `R09.D.sweep` D: swing high 143.61 (2025-05-19) swept to 144.3 on 2025-06-03, closed back inside (frozen v2)
- `R09.D.failed` D: swing low 131.56 closed beyond in 2025-07-22, back inside on 2025-07-23 at 134.85 (frozen v2)
- `R09.D.liq` D equal highs/lows (shown, not in the HTF zones): above none | below EQL 20.8 (2022-08-23, 2022-09-26)
- `R09.Z.inside` price inside zone 118–134.6 [structure+imbalance+volume+pivot] STRONG 0.0 ATR(D) away; W bull OB 123.69-134.6 (2025-W13); W virgin MZ VAL 2025-W19; Q S1; W swing HL 2025-W25 +33
- `R09.Z.b1` zone below #1: 112.96–117.2 [structure+imbalance+pivot] STRONG 4.65 ATR(D) away; Y L3; W swing HL 2025-W15; 750d LVN high (approx.); Q prev L +1
- `R09.Z.b2` zone below #2: 107.8–109.4 [structure+imbalance+volume] STRONG 7.09 ATR(D) away; W virgin MZ VAH 2024-W02; M swing LL 2025-03; 750d LVN high (approx.); W virgin vol VAL 2025-W10 +3
- `R09.Z.b3` zone below #3: 96.05–105.96 [imbalance+volume+pivot] STRONG 8.17 ATR(D) away; W demand 96.05-100.75 (2024-W03); W virgin MZ VAL 2023-W52; Y prev L; W virgin vol VAL 2023-W52 +14
- `R09.Z.a1` zone above #1: 132.54–155.52 [structure+imbalance+volume+pivot] STRONG 0.16 ATR(D) away; W bear OB 134.72-155.52 (2025-W05); M S1; Y vol VAL 2024; W swing HH 2025-W24 +63
- `R09.Z.a2` zone above #2: 144.7–170.51 [structure+imbalance+volume+pivot] STRONG 3.97 ATR(D) away; M bear OB 144.7-166.9 (2024-12); M H3; Y vol POC 2024; W swing HH 2025-W24 +53
- `R09.Z.a3` zone above #3: 173–177 [imbalance+volume+pivot] STRONG 12.84 ATR(D) away; W virgin MZ VAL 2024-W36; M R4; 250d LVN high (approx.); 750d HVN low (approx.) +4
- `R09.H.hot` Ochoa hot zones: 35 DPZ (30 multi-timeframe); GPZ: W H3 134.09; Q L3 131.83
- `R09.P.cpr` pivots (untested; *Q not Ochoa): W P 133.51 CPR 132.77-134.25, average, lower value (bearish), closes below x3; M P 140.74 CPR 140.25-141.23, narrow, higher value (bullish), closes above x3; Q* P 134.56 CPR 130.97-138.14, average, overlapping higher (moderately bullish); Y P 158.61 CPR 153.83-163.4, higher value (bullish)
- `R09.P.levels` pivot levels below: Q L3 131.83; M prev L 131.56; Q BC 130.97 | above: M L4 132.16; M S1 132.54; W BC 132.77
- `R09.V.periods` profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 134.4 VA 131.6-135.2, average, overlapping lower / VPOC 134.4; M MZ POC 140 VA 135.4-145.4, narrow, overlapping higher / VPOC 140; Q* MZ POC 140 VA 124.6-142.6, average, inside / VPOC 140; Y* MZ POC 147.4 VA 135-178.6, higher value / VPOC 146.6
- `R09.V.virgin` virgin (watch): W 2025-W20 MZ POC 130.2 (0.57 ATR); W 2025-W20 vol POC 130 (0.64 ATR); M 2025-05 vol VAL 129.2 (0.89 ATR); W 2025-W20 MZ VAL 125.2 (2.14 ATR)
- `R09.V.long` long profile (approximation (daily bars)): 250d POC 140 VA 122.4-159.8, 10 HVN, 2 LVN; 750d POC 33.2 VA 20.4-142.2, 11 HVN, 6 LVN
- `R09.L2.pivots` pivots from 2025-07-25: CPR 132.43-133.24 width 0.607% (average), lower value vs the day before; R3 139.21, R2 137.36, R1 134.69, H4 134.52, H3 133.27, TC 133.24, P 132.84, BC 132.43, L3 130.79, S1 130.17, L4 129.54, S2 128.32, S3 125.65
- `R09.L2.session` session 2025-07-25: money zone POC 132.6 VA 131.8-133.4; volume POC 132.8 VA 131.6-133.2
- `R09.L2.virgin` virgin session levels (240 from 1101 sessions since 2021-02-17): below volume VAL 130.9 (2025-07-22, 0.35 ATR); money zone VAL 129.8 (2025-05-15, 0.7 ATR); volume VAL 129.6 (2025-05-15, 0.76 ATR) | above money zone VAL 135.6 (2025-07-24, 1.12 ATR); money zone POC 135.8 (2025-07-24, 1.18 ATR); volume VAL 135.8 (2025-07-24, 1.18 ATR)
- `R09.X.watch` not aligned: down on M, D, W up; first zone below 112.96–117.2, 4.65 ATR(D) away; first zone above 132.54–155.52, 0.16 ATR(D) away; inside 118–134.6

## R10 TEJASNET, as of 2025-04-21 (last bar 2025-04-17, price 857.5, ATR(D) 47.5)

```
MAP  TEJASNET at 857.5 (higher-timeframe map, bhavcopy to 2025-04-17) -- zones untested (no fidelity or signal test yet)
     below: 615–846.88 (M bull OB 651.25-779 (2024-03); M virgin MZ VAL 2023-04; W swing LL 2025-W12; W EQL +55), 1.24% away
     above: 906–953.67 (250d LVN low (approx.); 750d HVN high (approx.); Q H3; W virgin vol VAH 2025-W05 +6), 5.66% away
L1   structure (untested: no fidelity test yet) -- not aligned: down on M, W, D up
     M: down for 2 bars; last CHoCH down 2025-01 at 1102.85; protected high 1459.9 (2024-11), weak low 646.55 (2025-03); discount 25.9%
        last sweep: swing high 206 (2019-04) taken to 220.85 on 2021-02-26, closed back inside (frozen v2)
     W: down for 14 bars; last CHoCH down 2025-W02 at 1102.85; protected high 1459.9 (2024-W45), weak low 646.55 (2025-W12); discount 25.9%
        last sweep: swing high 1369 (2024-W36) taken to 1425.2 on 2024-10-25, closed back inside (frozen v2)
        last failed break: swing high 1369 closed beyond in 2024-W44, back inside on 2024-11-08 at 1347.2 (frozen v2)
     D: up for 16 bars; last BOS up 2025-04-03 at 844.45; protected low 731.05 (2025-04-07), weak high 904 (2025-04-03); premium 73.1%
        last sweep: swing low 681 (2025-03-03) taken to 676.2 on 2025-03-11, closed back inside (frozen v2)
        last failed break: swing high 844.45 closed beyond in 2025-04-03, back inside on 2025-04-04 at 842.65 (frozen v2)
        D equal highs/lows (shown, not in the HTF zones): above none | below EQL 618 (2023-04-24, 2023-05-05); EQL 565.05 (2023-03-16, 2023-03-27)
     zones (untested) below: bull OB M 651.25-779.00; multi-touch W 773.00-779.00 | above: bear OB M 1102.85-1425.20; bear OB W 1218.00-1381.35
     HTF strong zones (untested; 2+ families incl. structure, imbalance or liquidity; clustered at 0.3 ATR(W); point clusters at most 0.45 ATR(W); demand, supply and order-block bands keep their full range, 0.3 ATR(W) = 33.98): below 615-846.88 [structure+imbalance+liquidity+volume+pivot] (M bull OB 651.25-779 (2024-03); M virgin MZ VAL 2023-04; W swing LL 2025-W12; W EQL +55) | above 906-953.67 [imbalance+volume+pivot] (250d LVN low (approx.); 750d HVN high (approx.); Q H3; W virgin vol VAH 2025-W05 +6)
     hot zones (Ochoa, recorded only): 26 DPZ, 25 multi-timeframe; GPZ: W MZ POC 862; W VPOC 860; M VPOC 746; Q H3 918.15 bearish; Y MZ VAL 1114
     pivots (untested; *Q not Ochoa): W P 861.63 CPR 859.57-863.7, narrow, higher value (bullish), closes above x1; M P 750.48 CPR 745.5-755.47, narrow, overlapping lower (moderately bearish); Q* P 875.67 CPR 818.06-933.27, wide, lower value (bearish); Y P 1110.65 CPR 1073.12-1148.17, higher value (bullish)
     pivot levels below: M R1 854.42; W L3 846.88; M prev H 844.45 | above: W BC 859.57; W P 861.63; W TC 863.7
     profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 862 VA 856-866, narrow, higher value / VPOC 860; M MZ POC 744 VA 682-798, wide, overlapping lower / VPOC 746; Q* MZ POC 786 VA 650-1002, wide, lower value / VPOC 760; Y* MZ POC 1292 VA 1114-1434, higher value / VPOC 1340
     virgin (watch): W 2025-W15 vol POC 836 (0.45 ATR); W 2025-W14 vol VAH 896 (0.81 ATR); W 2025-W15 MZ POC 806 (1.08 ATR); W 2025-W05 vol VAH 916 (1.23 ATR)
     long profile (approximation (daily bars)): 250d POC 786 VA 646-1270, 2 HVN, 1 LVN; 750d POC 860 VA 428-922, 8 HVN, 1 LVN
L2   daily layer (untested; intraday layer (definitions v1 §8): shown beside the HTF zones, never clustered into them)
     pivots from 2025-04-17: CPR 857.15-857.38 width 0.027% (narrow), lower value vs the day before; R3 889.03, R2 878.37, H4 869.11, R1 867.93, H3 863.3, TC 857.38, P 857.27, BC 857.15, L3 851.7, S1 846.83, L4 845.89, S2 836.17, S3 825.73
     session 2025-04-17: money zone POC 856 VA 852-860; volume POC 854 VA 852-860
     virgin session levels (437 from 1827 sessions since 2017-12-01): below volume VAH 844 (2025-04-11, 0.28 ATR); money zone VAH 840 (2025-04-11, 0.37 ATR); money zone POC 836 (2025-04-11, 0.45 ATR) | above volume VAH 872 (2025-04-16, 0.31 ATR); volume VAH 892 (2025-04-03, 0.73 ATR); money zone VAH 904 (2025-04-03, 0.98 ATR)
```

Items:

- `R10.M.state` M: down for 2 bars
- `R10.M.event` M: last CHoCH down in 2025-01 at 1102.85
- `R10.M.protected` M: protected high 1459.9 (2024-11)
- `R10.M.weak` M: weak low 646.55 (2025-03)
- `R10.M.pd` M: price in discount (25.9% of 646.55-1459.9, eq 1053.22)
- `R10.M.sweep` M: swing high 206 (2019-04) swept to 220.85 on 2021-02-26, closed back inside (frozen v2)
- `R10.W.state` W: down for 14 bars
- `R10.W.event` W: last CHoCH down in 2025-W02 at 1102.85
- `R10.W.protected` W: protected high 1459.9 (2024-W45)
- `R10.W.weak` W: weak low 646.55 (2025-W12)
- `R10.W.pd` W: price in discount (25.9% of 646.55-1459.9, eq 1053.22)
- `R10.W.sweep` W: swing high 1369 (2024-W36) swept to 1425.2 on 2024-10-25, closed back inside (frozen v2)
- `R10.W.failed` W: swing high 1369 closed beyond in 2024-W44, back inside on 2024-11-08 at 1347.2 (frozen v2)
- `R10.D.state` D: up for 16 bars
- `R10.D.event` D: last BOS up in 2025-04-03 at 844.45
- `R10.D.protected` D: protected low 731.05 (2025-04-07)
- `R10.D.weak` D: weak high 904 (2025-04-03)
- `R10.D.pd` D: price in premium (73.1% of 731.05-904, eq 817.52)
- `R10.D.sweep` D: swing low 681 (2025-03-03) swept to 676.2 on 2025-03-11, closed back inside (frozen v2)
- `R10.D.failed` D: swing high 844.45 closed beyond in 2025-04-03, back inside on 2025-04-04 at 842.65 (frozen v2)
- `R10.D.liq` D equal highs/lows (shown, not in the HTF zones): above none | below EQL 618 (2023-04-24, 2023-05-05); EQL 565.05 (2023-03-16, 2023-03-27)
- `R10.Z.inside` price inside zone 854–900.23 [volume+pivot] 0.0 ATR(D) away; W vol VAL 2025-W16; M R1; W MZ VAL 2025-W16; W BC +17
- `R10.Z.b1` zone below #1: 615–846.88 [structure+imbalance+liquidity+volume+pivot] STRONG 0.22 ATR(D) away; M bull OB 651.25-779 (2024-03); M virgin MZ VAL 2023-04; W swing LL 2025-W12; W EQL +55
- `R10.Z.b2` zone below #2: 615–698.9 [structure+imbalance+liquidity+volume+pivot] STRONG 3.34 ATR(D) away; W bull OB 651.25-698.9 (2024-W13); M virgin MZ VAL 2023-04; W swing LL 2025-W12; W EQL +21
- `R10.Z.b3` zone below #3: 510–615 [structure+imbalance+volume+pivot] STRONG 5.11 ATR(D) away; M bull OB 510-615 (2023-01); M swing HL 2023-01; Q S1; W virgin vol VAL 2023-W05 +31
- `R10.Z.a1` zone above #1: 906–953.67 [imbalance+volume+pivot] STRONG 1.02 ATR(D) away; 250d LVN low (approx.); 750d HVN high (approx.); Q H3; W virgin vol VAH 2025-W05 +6
- `R10.Z.a2` zone above #2: 986–1014 [imbalance+volume] STRONG 2.71 ATR(D) away; W virgin vol VAL 2025-W04; 250d LVN high (approx.); M virgin MZ VAL 2025-01; Q MZ VAH 2025-Q1 +2
- `R10.Z.a3` zone above #3: 1046–1495 [structure+imbalance+volume+pivot] STRONG 3.97 ATR(D) away; M bear OB 1102.85-1425.2 (2024-10); M virgin vol POC 2025-01; M R3; M swing LH 2024-11 +62
- `R10.H.hot` Ochoa hot zones: 26 DPZ (25 multi-timeframe); GPZ: W MZ POC 862; W VPOC 860; M VPOC 746; Q H3 918.15; Y MZ VAL 1114
- `R10.P.cpr` pivots (untested; *Q not Ochoa): W P 861.63 CPR 859.57-863.7, narrow, higher value (bullish), closes above x1; M P 750.48 CPR 745.5-755.47, narrow, overlapping lower (moderately bearish); Q* P 875.67 CPR 818.06-933.27, wide, lower value (bearish); Y P 1110.65 CPR 1073.12-1148.17, higher value (bullish)
- `R10.P.levels` pivot levels below: M R1 854.42; W L3 846.88; M prev H 844.45 | above: W BC 859.57; W P 861.63; W TC 863.7
- `R10.V.periods` profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 862 VA 856-866, narrow, higher value / VPOC 860; M MZ POC 744 VA 682-798, wide, overlapping lower / VPOC 746; Q* MZ POC 786 VA 650-1002, wide, lower value / VPOC 760; Y* MZ POC 1292 VA 1114-1434, higher value / VPOC 1340
- `R10.V.virgin` virgin (watch): W 2025-W15 vol POC 836 (0.45 ATR); W 2025-W14 vol VAH 896 (0.81 ATR); W 2025-W15 MZ POC 806 (1.08 ATR); W 2025-W05 vol VAH 916 (1.23 ATR)
- `R10.V.long` long profile (approximation (daily bars)): 250d POC 786 VA 646-1270, 2 HVN, 1 LVN; 750d POC 860 VA 428-922, 8 HVN, 1 LVN
- `R10.L2.pivots` pivots from 2025-04-17: CPR 857.15-857.38 width 0.027% (narrow), lower value vs the day before; R3 889.03, R2 878.37, H4 869.11, R1 867.93, H3 863.3, TC 857.38, P 857.27, BC 857.15, L3 851.7, S1 846.83, L4 845.89, S2 836.17, S3 825.73
- `R10.L2.session` session 2025-04-17: money zone POC 856 VA 852-860; volume POC 854 VA 852-860
- `R10.L2.virgin` virgin session levels (437 from 1827 sessions since 2017-12-01): below volume VAH 844 (2025-04-11, 0.28 ATR); money zone VAH 840 (2025-04-11, 0.37 ATR); money zone POC 836 (2025-04-11, 0.45 ATR) | above volume VAH 872 (2025-04-16, 0.31 ATR); volume VAH 892 (2025-04-03, 0.73 ATR); money zone VAH 904 (2025-04-03, 0.98 ATR)
- `R10.X.watch` not aligned: down on M, W, D up; first zone below 615–846.88, 0.22 ATR(D) away; first zone above 906–953.67, 1.02 ATR(D) away

## R11 BIOCON, as of 2026-05-13 (last bar 2026-05-12, price 402.45, ATR(D) 11.87)

```
MAP  BIOCON at 402.45 (higher-timeframe map, bhavcopy to 2026-05-12) -- zones untested (no fidelity or signal test yet)
     below: 379.53–401.45 (W bear OB 383.55-401.45 (2025-W51); W TC; W multi-touch x3; W MZ POC 2026-W19 +16), 0.25% away
     above: 431–487.75 (W bear OB 437-487.75 (2020-W52); W virgin MZ VAL 2020-W49; Y R1; M swing HH 2020-12 +21), 7.09% away
     price is inside the strong zone 359.02–430.74 (M bear OB 363.25-424.75 (2021-02); W multi-touch x4; W prev L; 750d HVN low (approx.) +82)
L1   structure (untested: no fidelity test yet) -- aligned down
     M: down for 14 bars; last CHoCH down 2025-02 at 303; protected high 424.95 (2025-11), weak low 291 (2025-03); premium 83.2%
        last sweep: swing high 406 (2025-07) taken to 424.95 on 2025-11-28, closed back inside (frozen v2)
        last failed break: swing high 395.8 closed beyond in 2025-11, back inside on 2025-12-31 at 393.9 (frozen v2)
     W: down for 15 bars; last BOS down 2026-W14 at 359.05; protected high 402.8 (2026-W11), weak low 337.7 (2026-W15); premium 99.5%
        last sweep: swing low 375.55 (2025-W50) taken to 372.15 on 2026-01-09, closed back inside (frozen v2)
        last failed break: swing low 375.55 closed beyond in 2026-W04, back inside on 2026-02-13 at 377.95 (frozen v2)
     D: down for 33 bars; last CHoCH down 2026-03-19 at 375.35; protected high 402.8 (2026-03-11), weak low 337.7 (2026-04-07); premium 99.5%
        last sweep: swing high 402.8 (2026-03-11) taken to 406.6 on 2026-05-12, closed back inside (frozen v2)
        last failed break: swing low 375.35 closed beyond in 2026-03-19, back inside on 2026-03-20 at 380.95 (frozen v2)
        D equal highs/lows (shown, not in the HTF zones): above EQH 424.95 (2021-04-09, 2025-11-18) | below EQL 337.05 (2025-09-30, 2026-04-07); EQL 146.95 (2016-12-27, 2017-05-25)
     zones (untested) below: bear OB W 383.55-401.45; bear OB W 375.35-394.25 | above: multi-touch W 402.80-406.00; multi-touch W 420.25-424.95 | inside: bear OB W 401.55-424.40; bear OB W 383.25-420.25
     HTF strong zones (untested; 2+ families incl. structure, imbalance or liquidity; clustered at 0.3 ATR(W); point clusters at most 0.45 ATR(W); demand, supply and order-block bands keep their full range, 0.3 ATR(W) = 6.62): below 379.53-401.45 [structure+imbalance+volume+pivot] (W bear OB 383.55-401.45 (2025-W51); W TC; W multi-touch x3; W MZ POC 2026-W19 +16) | above 431-487.75 [structure+imbalance+volume+pivot] (W bear OB 437-487.75 (2020-W52); W virgin MZ VAL 2020-W49; Y R1; M swing HH 2020-12 +21) | inside 359.02-430.74 [structure+imbalance+liquidity+volume+pivot] (M bear OB 363.25-424.75 (2021-02); W multi-touch x4; W prev L; 750d HVN low (approx.) +82)
     hot zones (Ochoa, recorded only): 37 DPZ, 34 multi-timeframe; GPZ: Q H3 373.41 bearish; Q MZ POC 375; Q VPOC 375; Y MZ POC 361
     pivots (untested; *Q not Ochoa): W P 378.67 CPR 377.8-379.53, average, higher value (bullish), closes above x2; M P 356.42 CPR 354.8-358.03, narrow, lower value (bearish), closes below x2; Q* P 373.67 CPR 367.28-380.05, average, lower value (bearish); Y P 369.95 CPR 357.98-381.92, average, higher value (bullish)
     pivot levels below: W H4 400.86; W R1 398.13; W prev H 396.4 | above: Q prev H 402.8; M R3 409.33; W R2 415.87
     profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 381.5 VA 368-396, wide, higher value / VPOC 381.5; M MZ POC 350.5 VA 347.5-362.5, narrow, lower value / VPOC 350.5; Q* MZ POC 375 VA 366-387, narrow, overlapping lower / VPOC 375; Y* MZ POC 361 VA 329.5-389, average, overlapping higher / VPOC 350.5
     virgin (watch): Q 2025-Q4 vol VAH 412.5 (0.85 ATR); W 2025-W47 MZ POC 418.5 (1.35 ATR); Q 2025-Q4 MZ VAH 420.5 (1.52 ATR); W 2025-W47 vol POC 421 (1.56 ATR)
     long profile (approximation (daily bars)): 250d POC 350.5 VA 345.5-393, 2 HVN, 0 LVN; 750d POC 350.5 VA 281-402.5, 5 HVN, 0 LVN
L2   daily layer (untested; intraday layer (definitions v1 §8): shown beside the HTF zones, never clustered into them)
     pivots from 2026-05-12: CPR 399.43-401.44 width 0.504% (average), higher value vs the day before; R3 422.97, R2 414.78, H4 410.34, R1 408.62, H3 406.4, TC 401.44, P 400.43, BC 399.43, L3 398.5, L4 394.56, S1 394.27, S2 386.08, S3 379.92
     session 2026-05-12: money zone POC 400.5 VA 399.5-404.5; volume POC 402.5 VA 399.5-404
     virgin session levels (144 from 2090 sessions since 2017-12-01): below money zone POC 392 (2026-05-11, 0.88 ATR); volume POC 392 (2026-05-11, 0.88 ATR); volume VAL 389 (2026-05-11, 1.13 ATR) | above money zone VAH 412 (2025-12-03, 0.8 ATR); money zone POC 413.5 (2025-11-19, 0.93 ATR); volume VAH 414 (2025-11-19, 0.97 ATR)
```

Items:

- `R11.M.state` M: down for 14 bars
- `R11.M.event` M: last CHoCH down in 2025-02 at 303
- `R11.M.protected` M: protected high 424.95 (2025-11)
- `R11.M.weak` M: weak low 291 (2025-03)
- `R11.M.pd` M: price in premium (83.2% of 291-424.95, eq 357.98)
- `R11.M.sweep` M: swing high 406 (2025-07) swept to 424.95 on 2025-11-28, closed back inside (frozen v2)
- `R11.M.failed` M: swing high 395.8 closed beyond in 2025-11, back inside on 2025-12-31 at 393.9 (frozen v2)
- `R11.W.state` W: down for 15 bars
- `R11.W.event` W: last BOS down in 2026-W14 at 359.05
- `R11.W.protected` W: protected high 402.8 (2026-W11)
- `R11.W.weak` W: weak low 337.7 (2026-W15)
- `R11.W.pd` W: price in premium (99.5% of 337.7-402.8, eq 370.25)
- `R11.W.sweep` W: swing low 375.55 (2025-W50) swept to 372.15 on 2026-01-09, closed back inside (frozen v2)
- `R11.W.failed` W: swing low 375.55 closed beyond in 2026-W04, back inside on 2026-02-13 at 377.95 (frozen v2)
- `R11.D.state` D: down for 33 bars
- `R11.D.event` D: last CHoCH down in 2026-03-19 at 375.35
- `R11.D.protected` D: protected high 402.8 (2026-03-11)
- `R11.D.weak` D: weak low 337.7 (2026-04-07)
- `R11.D.pd` D: price in premium (99.5% of 337.7-402.8, eq 370.25)
- `R11.D.sweep` D: swing high 402.8 (2026-03-11) swept to 406.6 on 2026-05-12, closed back inside (frozen v2)
- `R11.D.failed` D: swing low 375.35 closed beyond in 2026-03-19, back inside on 2026-03-20 at 380.95 (frozen v2)
- `R11.D.liq` D equal highs/lows (shown, not in the HTF zones): above EQH 424.95 (2021-04-09, 2025-11-18) | below EQL 337.05 (2025-09-30, 2026-04-07); EQL 146.95 (2016-12-27, 2017-05-25)
- `R11.Z.inside` price inside zone 359.02–430.74 [structure+imbalance+liquidity+volume+pivot] STRONG 0.0 ATR(D) away; M bear OB 363.25-424.75 (2021-02); W multi-touch x4; W prev L; 750d HVN low (approx.) +82
- `R11.Z.inside2` price inside zone 400–424.4 [structure+imbalance+volume+pivot] STRONG 0.0 ATR(D) away; W bear OB 401.55-424.4 (2021-W14); Y vol VAH 2025; W H4; W swing LH 2026-W11 +13
- `R11.Z.inside3` price inside zone 379.53–420.5 [structure+imbalance+volume+pivot] STRONG 0.0 ATR(D) away; W bear OB 383.25-420.25 (2021-W23); W TC; W multi-touch x3; W MZ POC 2026-W19 +32
- `R11.Z.b1` zone below #1: 379.53–401.45 [structure+imbalance+volume+pivot] STRONG 0.08 ATR(D) away; W bear OB 383.55-401.45 (2025-W51); W TC; W multi-touch x3; W MZ POC 2026-W19 +16
- `R11.Z.b2` zone below #2: 375.35–398.13 [structure+imbalance+volume+pivot] STRONG 0.36 ATR(D) away; W bear OB 375.35-394.25 (2026-W10); W TC; W multi-touch x3; W MZ POC 2026-W19 +16
- `R11.Z.b3` zone below #3: 337.7–370.95 [structure+imbalance+volume+pivot] STRONG 2.65 ATR(D) away; W bull OB 337.7-370.95 (2025-W39); W swing LL 2026-W15; M prev L; Y vol VAL 2025 +46
- `R11.Z.a1` zone above #1: 431–487.75 [structure+imbalance+volume+pivot] STRONG 2.41 ATR(D) away; W bear OB 437-487.75 (2020-W52); W virgin MZ VAL 2020-W49; Y R1; M swing HH 2020-12 +21
- `R11.Z.a2` zone above #2: 457.05–481 [imbalance+volume+pivot] STRONG 4.6 ATR(D) away; W supply 457.05-477.5 (2021-W03); W virgin MZ VAH 2021-W03; Y H4; W virgin MZ VAL 2021-W02 +10
- `R11.Z.a3` zone above #3: 503.9 [pivot] 8.55 ATR(D) away; Y R2
- `R11.H.hot` Ochoa hot zones: 37 DPZ (34 multi-timeframe); GPZ: Q H3 373.41; Q MZ POC 375; Q VPOC 375; Y MZ POC 361
- `R11.P.cpr` pivots (untested; *Q not Ochoa): W P 378.67 CPR 377.8-379.53, average, higher value (bullish), closes above x2; M P 356.42 CPR 354.8-358.03, narrow, lower value (bearish), closes below x2; Q* P 373.67 CPR 367.28-380.05, average, lower value (bearish); Y P 369.95 CPR 357.98-381.92, average, higher value (bullish)
- `R11.P.levels` pivot levels below: W H4 400.86; W R1 398.13; W prev H 396.4 | above: Q prev H 402.8; M R3 409.33; W R2 415.87
- `R11.V.periods` profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 381.5 VA 368-396, wide, higher value / VPOC 381.5; M MZ POC 350.5 VA 347.5-362.5, narrow, lower value / VPOC 350.5; Q* MZ POC 375 VA 366-387, narrow, overlapping lower / VPOC 375; Y* MZ POC 361 VA 329.5-389, average, overlapping higher / VPOC 350.5
- `R11.V.virgin` virgin (watch): Q 2025-Q4 vol VAH 412.5 (0.85 ATR); W 2025-W47 MZ POC 418.5 (1.35 ATR); Q 2025-Q4 MZ VAH 420.5 (1.52 ATR); W 2025-W47 vol POC 421 (1.56 ATR)
- `R11.V.long` long profile (approximation (daily bars)): 250d POC 350.5 VA 345.5-393, 2 HVN, 0 LVN; 750d POC 350.5 VA 281-402.5, 5 HVN, 0 LVN
- `R11.L2.pivots` pivots from 2026-05-12: CPR 399.43-401.44 width 0.504% (average), higher value vs the day before; R3 422.97, R2 414.78, H4 410.34, R1 408.62, H3 406.4, TC 401.44, P 400.43, BC 399.43, L3 398.5, L4 394.56, S1 394.27, S2 386.08, S3 379.92
- `R11.L2.session` session 2026-05-12: money zone POC 400.5 VA 399.5-404.5; volume POC 402.5 VA 399.5-404
- `R11.L2.virgin` virgin session levels (144 from 2090 sessions since 2017-12-01): below money zone POC 392 (2026-05-11, 0.88 ATR); volume POC 392 (2026-05-11, 0.88 ATR); volume VAL 389 (2026-05-11, 1.13 ATR) | above money zone VAH 412 (2025-12-03, 0.8 ATR); money zone POC 413.5 (2025-11-19, 0.93 ATR); volume VAH 414 (2025-11-19, 0.97 ATR)
- `R11.X.watch` aligned down; first zone below 379.53–401.45, 0.08 ATR(D) away; first zone above 431–487.75, 2.41 ATR(D) away; inside 359.02–430.74

## R12 SSWL, as of 2025-09-17 (last bar 2025-09-16, price 244.65, ATR(D) 7.87)

```
MAP  SSWL at 244.65 (higher-timeframe map, bhavcopy to 2025-09-16) -- zones untested (no fidelity or signal test yet)
     below: 169.71–213 (M bull OB 172.01-200.03 (2025-02); Y L3; M virgin vol VAL 2025-03; W multi-touch x3 +51), 12.94% away
     above: 275.5–297.9 (W bear OB 275.5-289.6 (2023-W45); 750d VAH (approx.); W swing HH 2025-W27; Y prev H +12), 12.61% away
     price is inside the strong zone 233.28–282 (W bear OB 244.15-282 (2024-W02); M prev H; 750d HVN high (approx.); W L3 +48)
L1   structure (untested: no fidelity test yet) -- not aligned: up on M, W, D down
     M: up for 3 bars; last CHoCH up 2025-05 at 225; protected low 167.41 (2025-03), weak high 280 (2025-07); premium 68.6%
        last sweep: swing high 248 (2024-07) taken to 252.5 on 2025-05-30, closed back inside (frozen v2)
        last failed break: swing high 225 closed beyond in 2025-05, back inside on 2025-08-29 at 216.14 (frozen v2)
     W: up for 17 bars; last CHoCH up 2025-W20 at 225; protected low 167.41 (2025-W12), weak high 280 (2025-W27); premium 68.6%
        last sweep: swing high 248 (2024-W29) taken to 252.5 on 2025-05-23, closed back inside (frozen v2)
        last failed break: swing high 236.47 closed beyond in 2025-W21, back inside on 2025-05-30 at 233.14 (frozen v2)
     D: down for 34 bars; last CHoCH down 2025-07-28 at 234.9; protected high 259.45 (2025-07-18), weak low 207.39 (2025-08-26); premium 71.6%
        last sweep: swing low 208.1 (2025-08-14) taken to 207.39 on 2025-08-26, closed back inside (frozen v2)
        last failed break: swing low 234.9 closed beyond in 2025-07-28, back inside on 2025-07-30 at 235.85 (frozen v2)
        D equal highs/lows (shown, not in the HTF zones): above none | below EQL 62.5 (2021-02-26, 2021-03-25); EQL 45.375 (2020-10-16, 2020-11-05)
     zones (untested) below: bull OB M 172.01-200.03; multi-touch W 190.55-195.84 | above: bear OB W 275.50-289.60 | inside: bear OB W 244.15-282.00
     HTF strong zones (untested; 2+ families incl. structure, imbalance or liquidity; clustered at 0.3 ATR(W); point clusters at most 0.45 ATR(W); demand, supply and order-block bands keep their full range, 0.3 ATR(W) = 5.65): below 169.71-213 [structure+imbalance+volume+pivot] (M bull OB 172.01-200.03 (2025-02); Y L3; M virgin vol VAL 2025-03; W multi-touch x3 +51) | above 275.5-297.9 [structure+imbalance+volume+pivot] (W bear OB 275.5-289.6 (2023-W45); 750d VAH (approx.); W swing HH 2025-W27; Y prev H +12) | inside 233.28-282 [imbalance+volume+pivot] (W bear OB 244.15-282 (2024-W02); M prev H; 750d HVN high (approx.); W L3 +48)
     hot zones (Ochoa, recorded only): 35 DPZ, 31 multi-timeframe; GPZ: Q L3 245.55 bullish; Q MZ POC 241; Q VPOC 241; Y H3 225.07 bearish; Y MZ POC 213; Y VPOC 224.4
     pivots (untested; *Q not Ochoa): W P 239.82 CPR 238.03-241.61, average, higher value (bullish), closes above x3; M P 218.94 CPR 217.54-220.33, average, lower value (bearish), closes below x2; Q* P 242.85 CPR 227.27-258.42, wide, higher value (bullish); Y P 225.25 CPR 211.32-239.18, average, overlapping lower (moderately bearish)
     pivot levels below: Q P 242.85; W TC 241.61; W P 239.82 | above: M R2 244.83; Q L3 245.55; W H3 250.42
     profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 243.5 VA 242-246.5, narrow, higher value / VPOC 243.5; M MZ POC 217 VA 210.2-220.6, narrow, lower value / VPOC 211.6; Q* MZ POC 241 VA 218-275.5, wide, higher value / VPOC 241; Y* MZ POC 213 VA 201.2-241, narrow, inside / VPOC 224.4
     virgin (watch): W 2025-W30 vol VAH 252 (0.93 ATR); M 2025-07 vol POC 253.5 (1.12 ATR); M 2025-07 MZ VAH 258 (1.7 ATR); M 2025-07 vol VAH 259 (1.82 ATR)
     long profile (approximation (daily bars)): 250d POC 211.5 VA 182-246, 4 HVN, 0 LVN; 750d POC 227.5 VA 202.5-279.5, 5 HVN, 0 LVN
L2   daily layer (untested; intraday layer (definitions v1 §8): shown beside the HTF zones, never clustered into them)
     pivots from 2025-09-16: CPR 243.6-244.3 width 0.287% (average), overlapping lower vs the day before; R3 254.62, R2 250.83, H4 248.43, R1 247.74, H3 246.54, TC 244.3, P 243.95, BC 243.6, L3 242.76, L4 240.87, S1 240.86, S2 237.07, S3 233.98
     session 2025-09-16: money zone POC 243 VA 242.5-245.5; volume POC 244 VA 242.5-244.5
     virgin session levels (548 from 1931 sessions since 2017-12-01): below money zone VAL 237.5 (2025-09-08, 0.91 ATR); money zone POC 225 (2025-09-05, 2.5 ATR); volume VAL 224 (2025-09-05, 2.62 ATR) | above money zone VAH 248.5 (2025-09-15, 0.49 ATR); volume VAH 248.5 (2025-09-15, 0.49 ATR); money zone POC 256 (2025-07-21, 1.44 ATR)
```

Items:

- `R12.M.state` M: up for 3 bars
- `R12.M.event` M: last CHoCH up in 2025-05 at 225
- `R12.M.protected` M: protected low 167.41 (2025-03)
- `R12.M.weak` M: weak high 280 (2025-07)
- `R12.M.pd` M: price in premium (68.6% of 167.41-280, eq 223.7)
- `R12.M.sweep` M: swing high 248 (2024-07) swept to 252.5 on 2025-05-30, closed back inside (frozen v2)
- `R12.M.failed` M: swing high 225 closed beyond in 2025-05, back inside on 2025-08-29 at 216.14 (frozen v2)
- `R12.W.state` W: up for 17 bars
- `R12.W.event` W: last CHoCH up in 2025-W20 at 225
- `R12.W.protected` W: protected low 167.41 (2025-W12)
- `R12.W.weak` W: weak high 280 (2025-W27)
- `R12.W.pd` W: price in premium (68.6% of 167.41-280, eq 223.7)
- `R12.W.sweep` W: swing high 248 (2024-W29) swept to 252.5 on 2025-05-23, closed back inside (frozen v2)
- `R12.W.failed` W: swing high 236.47 closed beyond in 2025-W21, back inside on 2025-05-30 at 233.14 (frozen v2)
- `R12.D.state` D: down for 34 bars
- `R12.D.event` D: last CHoCH down in 2025-07-28 at 234.9
- `R12.D.protected` D: protected high 259.45 (2025-07-18)
- `R12.D.weak` D: weak low 207.39 (2025-08-26)
- `R12.D.pd` D: price in premium (71.6% of 207.39-259.45, eq 233.42)
- `R12.D.sweep` D: swing low 208.1 (2025-08-14) swept to 207.39 on 2025-08-26, closed back inside (frozen v2)
- `R12.D.failed` D: swing low 234.9 closed beyond in 2025-07-28, back inside on 2025-07-30 at 235.85 (frozen v2)
- `R12.D.liq` D equal highs/lows (shown, not in the HTF zones): above none | below EQL 62.5 (2021-02-26, 2021-03-25); EQL 45.375 (2020-10-16, 2020-11-05)
- `R12.Z.inside` price inside zone 233.28–282 [imbalance+volume+pivot] STRONG 0.0 ATR(D) away; W bear OB 244.15-282 (2024-W02); M prev H; 750d HVN high (approx.); W L3 +48
- `R12.Z.b1` zone below #1: 223–230.48 [volume+pivot] 1.8 ATR(D) away; 250d HVN high (approx.); M H3; Y vol POC 2024; W virgin MZ POC 2025-W36 +11
- `R12.Z.b2` zone below #2: 214.3–222.5 [volume+pivot] 2.81 ATR(D) away; W S2; W virgin MZ VAH 2025-W35; M MZ POC 2025-08; Q L4 +8
- `R12.Z.b3` zone below #3: 169.71–213 [structure+imbalance+volume+pivot] STRONG 4.02 ATR(D) away; M bull OB 172.01-200.03 (2025-02); Y L3; M virgin vol VAL 2025-03; W multi-touch x3 +51
- `R12.Z.a1` zone above #1: 275.5–297.9 [structure+imbalance+volume+pivot] STRONG 3.92 ATR(D) away; W bear OB 275.5-289.6 (2023-W45); 750d VAH (approx.); W swing HH 2025-W27; Y prev H +12
- `R12.Z.a2` zone above #2: 299–302.45 [structure+pivot] STRONG 6.91 ATR(D) away; M swing HH 2023-10; Q H3; W swing HH 2023-W42
- `R12.Z.a3` zone above #3: 308.5–312 [volume+pivot] 8.11 ATR(D) away; W virgin vol VAL 2021-W32; Q R1; W virgin MZ VAL 2021-W32; W virgin vol POC 2021-W32
- `R12.H.hot` Ochoa hot zones: 35 DPZ (31 multi-timeframe); GPZ: Q L3 245.55; Q MZ POC 241; Q VPOC 241; Y H3 225.07; Y MZ POC 213; Y VPOC 224.4
- `R12.P.cpr` pivots (untested; *Q not Ochoa): W P 239.82 CPR 238.03-241.61, average, higher value (bullish), closes above x3; M P 218.94 CPR 217.54-220.33, average, lower value (bearish), closes below x2; Q* P 242.85 CPR 227.27-258.42, wide, higher value (bullish); Y P 225.25 CPR 211.32-239.18, average, overlapping lower (moderately bearish)
- `R12.P.levels` pivot levels below: Q P 242.85; W TC 241.61; W P 239.82 | above: M R2 244.83; Q L3 245.55; W H3 250.42
- `R12.V.periods` profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 243.5 VA 242-246.5, narrow, higher value / VPOC 243.5; M MZ POC 217 VA 210.2-220.6, narrow, lower value / VPOC 211.6; Q* MZ POC 241 VA 218-275.5, wide, higher value / VPOC 241; Y* MZ POC 213 VA 201.2-241, narrow, inside / VPOC 224.4
- `R12.V.virgin` virgin (watch): W 2025-W30 vol VAH 252 (0.93 ATR); M 2025-07 vol POC 253.5 (1.12 ATR); M 2025-07 MZ VAH 258 (1.7 ATR); M 2025-07 vol VAH 259 (1.82 ATR)
- `R12.V.long` long profile (approximation (daily bars)): 250d POC 211.5 VA 182-246, 4 HVN, 0 LVN; 750d POC 227.5 VA 202.5-279.5, 5 HVN, 0 LVN
- `R12.L2.pivots` pivots from 2025-09-16: CPR 243.6-244.3 width 0.287% (average), overlapping lower vs the day before; R3 254.62, R2 250.83, H4 248.43, R1 247.74, H3 246.54, TC 244.3, P 243.95, BC 243.6, L3 242.76, L4 240.87, S1 240.86, S2 237.07, S3 233.98
- `R12.L2.session` session 2025-09-16: money zone POC 243 VA 242.5-245.5; volume POC 244 VA 242.5-244.5
- `R12.L2.virgin` virgin session levels (548 from 1931 sessions since 2017-12-01): below money zone VAL 237.5 (2025-09-08, 0.91 ATR); money zone POC 225 (2025-09-05, 2.5 ATR); volume VAL 224 (2025-09-05, 2.62 ATR) | above money zone VAH 248.5 (2025-09-15, 0.49 ATR); volume VAH 248.5 (2025-09-15, 0.49 ATR); money zone POC 256 (2025-07-21, 1.44 ATR)
- `R12.X.watch` not aligned: up on M, W, D down; first zone below 169.71–213, 4.02 ATR(D) away; first zone above 275.5–297.9, 3.92 ATR(D) away; inside 233.28–282

## R13 BLUESTARCO, as of 2025-08-07 (last bar 2025-08-06, price 1770.4, ATR(D) 50.12)

```
MAP  BLUESTARCO at 1770.4 (higher-timeframe map, bhavcopy to 2025-08-06) -- zones untested (no fidelity or signal test yet)
     below: 1521–1578.16 (M swing LL 2025-05; Q prev L; Q MZ VAL 2025-Q2; W swing LL 2025-W22 +13), 10.86% away
     above: 1980.86–2269.8 (W bear OB 2002.45-2254.75 (2025-W12); Q H4; 750d HVN low (approx.); M swing HH 2024-09 +27), 11.89% away
     price is inside the strong zone 1745.67–2199.55 (M bear OB 1814-2197.3 (2024-12); W R1; W vol VAH 2025-W31; M swing HH 2024-09 +53)
L1   structure (untested: no fidelity test yet) -- aligned down
     M: down for 3 bars; last CHoCH down 2025-04 at 1711.05; protected high 2417 (2025-01), weak low 1521 (2025-05); discount 27.8%
        last sweep: swing high 2199.55 (2024-09) taken to 2417 on 2025-01-31, closed back inside (frozen v2)
        last failed break: swing low 1711.05 closed beyond in 2025-04, back inside on 2025-07-31 at 1738.1 (frozen v2)
     W: down for 14 bars; last BOS down 2025-W18 at 1711.05; protected high 2269.8 (2025-W13), weak low 1521 (2025-W22); discount 33.3%
        last sweep: swing low 1711.05 (2025-W05) taken to 1656.05 on 2025-04-11, closed back inside (frozen v2)
        last failed break: swing low 1539.1 closed beyond in 2025-W22, back inside on 2025-06-06 at 1589.2 (frozen v2)
     D: down for 11 bars; last CHoCH down 2025-07-22 at 1774; protected high 1922.4 (2025-07-17), weak low 1687 (2025-08-01); discount 35.4%
        last sweep: swing low 1656.05 (2025-04-07) taken to 1637 on 2025-05-02, closed back inside (frozen v2)
        last failed break: swing high 1877.8 closed beyond in 2025-07-15, back inside on 2025-07-16 at 1860.6 (frozen v2)
        D equal highs/lows (shown, not in the HTF zones): above none | below EQL 429.525 (2021-10-06, 2022-07-04); EQL 204.45 (2016-05-03, 2020-03-24)
     zones (untested) below: bull OB W 901.55-990.10; demand W 926.00-959.60 | above: bear OB M 1814.00-2197.30; bear OB W 2002.45-2254.75
     HTF strong zones (untested; 2+ families incl. structure, imbalance or liquidity; clustered at 0.3 ATR(W); point clusters at most 0.45 ATR(W); demand, supply and order-block bands keep their full range, 0.3 ATR(W) = 45.78): below 1521-1578.16 [structure+volume+pivot] (M swing LL 2025-05; Q prev L; Q MZ VAL 2025-Q2; W swing LL 2025-W22 +13) | above 1980.86-2269.8 [structure+imbalance+volume+pivot] (W bear OB 2002.45-2254.75 (2025-W12); Q H4; 750d HVN low (approx.); M swing HH 2024-09 +27) | inside 1745.67-2199.55 [structure+imbalance+volume+pivot] (M bear OB 1814-2197.3 (2024-12); W R1; W vol VAH 2025-W31; M swing HH 2024-09 +53)
     hot zones (Ochoa, recorded only): 28 DPZ, 27 multi-timeframe; GPZ: W H3 1718.45 bearish; M MZ POC 1758; Q H3 1808.23 bearish; Y L3 1790 bullish; Y MZ POC 1715; Y VPOC 1720
     pivots (untested; *Q not Ochoa): W P 1716.33 CPR 1706.67-1726, average, lower value (bearish), closes below x2; M P 1764.03 CPR 1751.07-1777, narrow, higher value (bullish), closes above x2; Q* P 1768.45 CPR 1702.03-1834.88, wide, lower value (bearish); Y P 1756.2 CPR 1564.73-1947.67, wide, higher value (bullish)
     pivot levels below: Q P 1768.45; W prev H 1765; M P 1764.03 | above: M TC 1777; Y L3 1790; W R2 1794.33
     profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 1736 VA 1730-1754, narrow, overlapping lower / VPOC 1730; M MZ POC 1758 VA 1726-1850, average, higher value / VPOC 1800; Q* MZ POC 1640 VA 1532-1920, wide, overlapping lower / VPOC 1620; Y* MZ POC 1715 VA 1375-2055, wide, higher value / VPOC 1720
     virgin (watch): W 2025-W29 MZ VAL 1844 (1.47 ATR); W 2025-W29 MZ POC 1882 (2.23 ATR); W 2025-W29 vol VAH 1884 (2.27 ATR); M 2025-06 MZ POC 1620 (3 ATR)
     long profile (approximation (daily bars)): 250d POC 1640 VA 1548-2012, 4 HVN, 0 LVN; 750d POC 716 VA 476-1822, 11 HVN, 7 LVN
L2   daily layer (untested; intraday layer (definitions v1 §8): shown beside the HTF zones, never clustered into them)
     pivots from 2025-08-06: CPR 1771.47-1773.6 width 0.12% (narrow), higher value vs the day before; R3 1925.67, R2 1875.33, H4 1826.94, R1 1822.87, H3 1798.67, TC 1773.6, P 1772.53, BC 1771.47, L3 1742.13, S1 1720.07, L4 1713.86, S2 1669.73, S3 1617.27
     session 2025-08-06: money zone POC 1746 VA 1730-1756; volume POC 1744 VA 1732-1748
     virgin session levels (284 from 1904 sessions since 2017-12-01): below money zone POC 1718 (2025-08-04, 1.05 ATR); volume POC 1718 (2025-08-04, 1.05 ATR); money zone VAL 1710 (2025-08-04, 1.21 ATR) | above money zone VAH 1826 (2025-07-21, 1.11 ATR); money zone VAL 1838 (2025-07-18, 1.35 ATR); money zone POC 1846 (2025-07-18, 1.51 ATR)
```

Items:

- `R13.M.state` M: down for 3 bars
- `R13.M.event` M: last CHoCH down in 2025-04 at 1711.05
- `R13.M.protected` M: protected high 2417 (2025-01)
- `R13.M.weak` M: weak low 1521 (2025-05)
- `R13.M.pd` M: price in discount (27.8% of 1521-2417, eq 1969)
- `R13.M.sweep` M: swing high 2199.55 (2024-09) swept to 2417 on 2025-01-31, closed back inside (frozen v2)
- `R13.M.failed` M: swing low 1711.05 closed beyond in 2025-04, back inside on 2025-07-31 at 1738.1 (frozen v2)
- `R13.W.state` W: down for 14 bars
- `R13.W.event` W: last BOS down in 2025-W18 at 1711.05
- `R13.W.protected` W: protected high 2269.8 (2025-W13)
- `R13.W.weak` W: weak low 1521 (2025-W22)
- `R13.W.pd` W: price in discount (33.3% of 1521-2269.8, eq 1895.4)
- `R13.W.sweep` W: swing low 1711.05 (2025-W05) swept to 1656.05 on 2025-04-11, closed back inside (frozen v2)
- `R13.W.failed` W: swing low 1539.1 closed beyond in 2025-W22, back inside on 2025-06-06 at 1589.2 (frozen v2)
- `R13.D.state` D: down for 11 bars
- `R13.D.event` D: last CHoCH down in 2025-07-22 at 1774
- `R13.D.protected` D: protected high 1922.4 (2025-07-17)
- `R13.D.weak` D: weak low 1687 (2025-08-01)
- `R13.D.pd` D: price in discount (35.4% of 1687-1922.4, eq 1804.7)
- `R13.D.sweep` D: swing low 1656.05 (2025-04-07) swept to 1637 on 2025-05-02, closed back inside (frozen v2)
- `R13.D.failed` D: swing high 1877.8 closed beyond in 2025-07-15, back inside on 2025-07-16 at 1860.6 (frozen v2)
- `R13.D.liq` D equal highs/lows (shown, not in the HTF zones): above none | below EQL 429.525 (2021-10-06, 2022-07-04); EQL 204.45 (2016-05-03, 2020-03-24)
- `R13.Z.inside` price inside zone 1745.67–2199.55 [structure+imbalance+volume+pivot] STRONG 0.0 ATR(D) away; M bear OB 1814-2197.3 (2024-12); W R1; W vol VAH 2025-W31; M swing HH 2024-09 +53
- `R13.Z.b1` zone below #1: 1675.55–1744 [volume+pivot] 0.53 ATR(D) away; W L3; Q vol VAH 2025-Q2; W prev L; Q BC +15
- `R13.Z.b2` zone below #2: 1605.67–1667.67 [volume+pivot] 2.05 ATR(D) away; M S1; W virgin vol VAL 2025-W26; W virgin MZ VAL 2025-W26; Q vol POC 2025-Q2 +15
- `R13.Z.b3` zone below #3: 1521–1578.16 [structure+volume+pivot] STRONG 3.84 ATR(D) away; M swing LL 2025-05; Q prev L; Q MZ VAL 2025-Q2; W swing LL 2025-W22 +13
- `R13.Z.a1` zone above #1: 1980.86–2269.8 [structure+imbalance+volume+pivot] STRONG 4.2 ATR(D) away; W bear OB 2002.45-2254.75 (2025-W12); Q H4; 750d HVN low (approx.); M swing HH 2024-09 +27
- `R13.Z.a2` zone above #2: 2345.63 [pivot] 11.48 ATR(D) away; M R4
- `R13.Z.a3` zone above #3: 2396.2–2417 [structure+pivot] STRONG 12.49 ATR(D) away; Q R2; M swing HH 2025-01; W swing HH 2025-W02; M protected 2025-01
- `R13.H.hot` Ochoa hot zones: 28 DPZ (27 multi-timeframe); GPZ: W H3 1718.45; M MZ POC 1758; Q H3 1808.23; Y L3 1790; Y MZ POC 1715; Y VPOC 1720
- `R13.P.cpr` pivots (untested; *Q not Ochoa): W P 1716.33 CPR 1706.67-1726, average, lower value (bearish), closes below x2; M P 1764.03 CPR 1751.07-1777, narrow, higher value (bullish), closes above x2; Q* P 1768.45 CPR 1702.03-1834.88, wide, lower value (bearish); Y P 1756.2 CPR 1564.73-1947.67, wide, higher value (bullish)
- `R13.P.levels` pivot levels below: Q P 1768.45; W prev H 1765; M P 1764.03 | above: M TC 1777; Y L3 1790; W R2 1794.33
- `R13.V.periods` profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 1736 VA 1730-1754, narrow, overlapping lower / VPOC 1730; M MZ POC 1758 VA 1726-1850, average, higher value / VPOC 1800; Q* MZ POC 1640 VA 1532-1920, wide, overlapping lower / VPOC 1620; Y* MZ POC 1715 VA 1375-2055, wide, higher value / VPOC 1720
- `R13.V.virgin` virgin (watch): W 2025-W29 MZ VAL 1844 (1.47 ATR); W 2025-W29 MZ POC 1882 (2.23 ATR); W 2025-W29 vol VAH 1884 (2.27 ATR); M 2025-06 MZ POC 1620 (3 ATR)
- `R13.V.long` long profile (approximation (daily bars)): 250d POC 1640 VA 1548-2012, 4 HVN, 0 LVN; 750d POC 716 VA 476-1822, 11 HVN, 7 LVN
- `R13.L2.pivots` pivots from 2025-08-06: CPR 1771.47-1773.6 width 0.12% (narrow), higher value vs the day before; R3 1925.67, R2 1875.33, H4 1826.94, R1 1822.87, H3 1798.67, TC 1773.6, P 1772.53, BC 1771.47, L3 1742.13, S1 1720.07, L4 1713.86, S2 1669.73, S3 1617.27
- `R13.L2.session` session 2025-08-06: money zone POC 1746 VA 1730-1756; volume POC 1744 VA 1732-1748
- `R13.L2.virgin` virgin session levels (284 from 1904 sessions since 2017-12-01): below money zone POC 1718 (2025-08-04, 1.05 ATR); volume POC 1718 (2025-08-04, 1.05 ATR); money zone VAL 1710 (2025-08-04, 1.21 ATR) | above money zone VAH 1826 (2025-07-21, 1.11 ATR); money zone VAL 1838 (2025-07-18, 1.35 ATR); money zone POC 1846 (2025-07-18, 1.51 ATR)
- `R13.X.watch` aligned down; first zone below 1521–1578.16, 3.84 ATR(D) away; first zone above 1980.86–2269.8, 4.2 ATR(D) away; inside 1745.67–2199.55

## R14 NBCC, as of 2025-05-30 (last bar 2025-05-29, price 116.2, ATR(D) 3.87)

```
MAP  NBCC at 116.2 (higher-timeframe map, bhavcopy to 2025-05-29) -- zones untested (no fidelity or signal test yet)
     below: 67.08–96.25 (M bull OB 70.0667-92.9667 (2024-03); Q S1; W virgin vol VAL 2024-W04; W swing HL 2024-W11 +64), 17.17% away
     above: 116.44–140.89 (W bear OB 117.047-139.833 (2024-W35); W weak 2025-W21; W prev H; Y MZ VAH 2024 +39), 0.21% away
     price is inside the strong zone 101.6–140.89 (M bear OB 108.667-139.833 (2024-08); M vol VAH 2025-04; M prev H; W weak 2025-W21 +69)
L1   structure (untested: no fidelity test yet) -- not aligned: up on W, D, M down
     M: down for 2 bars; last CHoCH down 2025-02 at 85.21; protected high 121.13 (2024-10), weak low 70.8 (2025-03); premium 90.2%
        last sweep: swing low 85.21 (2024-10) taken to 78.39 on 2025-01-31, closed back inside (frozen v2)
        last failed break: swing low 85.21 closed beyond in 2025-02, back inside on 2025-04-30 at 95.19 (frozen v2)
     W: up for 1 bars; last CHoCH up 2025-W20 at 104.15; protected low 70.8 (2025-W10), weak high 116.44 (2025-W21); premium 99.5%
        last sweep: swing low 78.39 (2025-W03) taken to 76.8 on 2025-02-21, closed back inside (frozen v2)
        last failed break: swing low 78.39 closed beyond in 2025-W09, back inside on 2025-03-07 at 80.76 (frozen v2)
     D: up for 46 bars; last BOS up 2025-05-14 at 102.5; protected low 90.07 (2025-05-09), weak high 117.76 (2025-05-28); premium 94.4%
        last sweep: swing high 116.44 (2025-05-19) taken to 117.76 on 2025-05-28, closed back inside (frozen v2)
        last failed break: swing low 78.39 closed beyond in 2025-02-18, back inside on 2025-02-19 at 80.71 (frozen v2)
        D equal highs/lows (shown, not in the HTF zones): above none | below EQL 19.8667 (2022-07-15, 2022-09-30); EQL 5.95556 (2013-12-17, 2014-03-04)
     zones (untested) below: bull OB M 70.07-92.97; bull OB W 70.07-85.27 | above: bear OB W 117.05-139.83 | inside: bear OB M 108.67-139.83
     HTF strong zones (untested; 2+ families incl. structure, imbalance or liquidity; clustered at 0.3 ATR(W); point clusters at most 0.45 ATR(W); demand, supply and order-block bands keep their full range, 0.3 ATR(W) = 2.98): below 67.08-96.25 [structure+imbalance+liquidity+volume+pivot] (M bull OB 70.0667-92.9667 (2024-03); Q S1; W virgin vol VAL 2024-W04; W swing HL 2024-W11 +64) | above 116.44-140.89 [structure+imbalance+volume+pivot] (W bear OB 117.047-139.833 (2024-W35); W weak 2025-W21; W prev H; Y MZ VAH 2024 +39) | inside 101.6-140.89 [structure+imbalance+volume+pivot] (M bear OB 108.667-139.833 (2024-08); M vol VAH 2025-04; M prev H; W weak 2025-W21 +69)
     hot zones (Ochoa, recorded only): 28 DPZ, 27 multi-timeframe; GPZ: W MZ POC 112.8; W VPOC 113
     pivots (untested; *Q not Ochoa): W P 112.96 CPR 112.73-113.2, narrow, higher value (bullish), closes above x2; M P 90.9 CPR 88.75-93.04, average, higher value (bullish), closes above x1; Q* P 85.61 CPR 83.75-87.47, average, lower value (bearish); Y P 95.15 CPR 94.05-96.25, narrow, higher value (bullish)
     pivot levels below: W H4 116.05; W R1 115.97; W H3 114.27 | above: W prev H 116.44; Y H3 116.92; M R2 118.4
     profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 112.8 VA 111.6-114.2, narrow, overlapping higher / VPOC 113; M MZ POC 99.2 VA 84-102.4, wide, overlapping higher / VPOC 99.2; Q* MZ POC 82 VA 77.6-92.6, average, overlapping lower / VPOC 82; Y* MZ POC 92 VA 83.6-119.4, average, higher value / VPOC 124.2
     virgin (watch): W 2024-W40 MZ VAH 120.4 (1.08 ATR); W 2024-W40 vol VAH 120.4 (1.08 ATR); M 2024-10 MZ VAH 121 (1.24 ATR); M 2024-10 vol VAH 121 (1.24 ATR)
     long profile (approximation (daily bars)): 250d POC 124.2 VA 96.6-131.2, 5 HVN, 0 LVN; 750d POC 27.4 VA 18.4-96.6, 9 HVN, 4 LVN
L2   daily layer (untested; intraday layer (definitions v1 §8): shown beside the HTF zones, never clustered into them)
     pivots from 2025-05-29: CPR 116.32-116.55 width 0.2% (narrow), higher value vs the day before; R3 119.17, R2 118.33, R1 117.27, H4 117.25, H3 116.72, TC 116.55, P 116.43, BC 116.32, L3 115.68, S1 115.37, L4 115.16, S2 114.53, S3 113.47
     session 2025-05-29: money zone POC 116.4 VA 116-116.6; volume POC 116.2 VA 116-116.6
     virgin session levels (265 from 1855 sessions since 2017-12-01): below money zone VAL 115.4 (2025-05-28, 0.21 ATR); money zone POC 114.8 (2025-05-27, 0.36 ATR); money zone VAL 114.6 (2025-05-27, 0.41 ATR) | above volume VAH 117.8 (2024-10-10, 0.41 ATR); money zone VAH 120.2 (2024-10-01, 1.03 ATR); volume VAH 120.2 (2024-10-01, 1.03 ATR)
```

Items:

- `R14.M.state` M: down for 2 bars
- `R14.M.event` M: last CHoCH down in 2025-02 at 85.21
- `R14.M.protected` M: protected high 121.13 (2024-10)
- `R14.M.weak` M: weak low 70.8 (2025-03)
- `R14.M.pd` M: price in premium (90.2% of 70.8-121.13, eq 95.97)
- `R14.M.sweep` M: swing low 85.21 (2024-10) swept to 78.39 on 2025-01-31, closed back inside (frozen v2)
- `R14.M.failed` M: swing low 85.21 closed beyond in 2025-02, back inside on 2025-04-30 at 95.19 (frozen v2)
- `R14.W.state` W: up for 1 bars
- `R14.W.event` W: last CHoCH up in 2025-W20 at 104.15
- `R14.W.protected` W: protected low 70.8 (2025-W10)
- `R14.W.weak` W: weak high 116.44 (2025-W21)
- `R14.W.pd` W: price in premium (99.5% of 70.8-116.44, eq 93.62)
- `R14.W.sweep` W: swing low 78.39 (2025-W03) swept to 76.8 on 2025-02-21, closed back inside (frozen v2)
- `R14.W.failed` W: swing low 78.39 closed beyond in 2025-W09, back inside on 2025-03-07 at 80.76 (frozen v2)
- `R14.D.state` D: up for 46 bars
- `R14.D.event` D: last BOS up in 2025-05-14 at 102.5
- `R14.D.protected` D: protected low 90.07 (2025-05-09)
- `R14.D.weak` D: weak high 117.76 (2025-05-28)
- `R14.D.pd` D: price in premium (94.4% of 90.07-117.76, eq 103.91)
- `R14.D.sweep` D: swing high 116.44 (2025-05-19) swept to 117.76 on 2025-05-28, closed back inside (frozen v2)
- `R14.D.failed` D: swing low 78.39 closed beyond in 2025-02-18, back inside on 2025-02-19 at 80.71 (frozen v2)
- `R14.D.liq` D equal highs/lows (shown, not in the HTF zones): above none | below EQL 19.8667 (2022-07-15, 2022-09-30); EQL 5.95556 (2013-12-17, 2014-03-04)
- `R14.Z.inside` price inside zone 101.6–140.89 [structure+imbalance+volume+pivot] STRONG 0.0 ATR(D) away; M bear OB 108.667-139.833 (2024-08); M vol VAH 2025-04; M prev H; W weak 2025-W21 +69
- `R14.Z.b1` zone below #1: 96.6–101 [volume+pivot] 3.93 ATR(D) away; 250d VAL (approx.); Q H4; 750d VAH (approx.); 750d HVN high (approx.) +4
- `R14.Z.b2` zone below #2: 67.08–96.25 [structure+imbalance+liquidity+volume+pivot] STRONG 5.16 ATR(D) away; M bull OB 70.0667-92.9667 (2024-03); Q S1; W virgin vol VAL 2024-W04; W swing HL 2024-W11 +64
- `R14.Z.b3` zone below #3: 67.08–87 [structure+imbalance+liquidity+volume+pivot] STRONG 7.55 ATR(D) away; W bull OB 70.0667-85.2667 (2024-W11); Q S1; W virgin vol VAL 2024-W04; W swing HL 2024-W11 +35
- `R14.Z.a1` zone above #1: 116.44–140.89 [structure+imbalance+volume+pivot] STRONG 0.06 ATR(D) away; W bear OB 117.047-139.833 (2024-W35); W weak 2025-W21; W prev H; Y MZ VAH 2024 +39
- `R14.Z.a2` zone above #2: 145.9 [pivot] 7.67 ATR(D) away; M R4
- `R14.Z.a3` zone above #3: 182.32 [pivot] 17.09 ATR(D) away; Y R2
- `R14.H.hot` Ochoa hot zones: 28 DPZ (27 multi-timeframe); GPZ: W MZ POC 112.8; W VPOC 113
- `R14.P.cpr` pivots (untested; *Q not Ochoa): W P 112.96 CPR 112.73-113.2, narrow, higher value (bullish), closes above x2; M P 90.9 CPR 88.75-93.04, average, higher value (bullish), closes above x1; Q* P 85.61 CPR 83.75-87.47, average, lower value (bearish); Y P 95.15 CPR 94.05-96.25, narrow, higher value (bullish)
- `R14.P.levels` pivot levels below: W H4 116.05; W R1 115.97; W H3 114.27 | above: W prev H 116.44; Y H3 116.92; M R2 118.4
- `R14.V.periods` profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 112.8 VA 111.6-114.2, narrow, overlapping higher / VPOC 113; M MZ POC 99.2 VA 84-102.4, wide, overlapping higher / VPOC 99.2; Q* MZ POC 82 VA 77.6-92.6, average, overlapping lower / VPOC 82; Y* MZ POC 92 VA 83.6-119.4, average, higher value / VPOC 124.2
- `R14.V.virgin` virgin (watch): W 2024-W40 MZ VAH 120.4 (1.08 ATR); W 2024-W40 vol VAH 120.4 (1.08 ATR); M 2024-10 MZ VAH 121 (1.24 ATR); M 2024-10 vol VAH 121 (1.24 ATR)
- `R14.V.long` long profile (approximation (daily bars)): 250d POC 124.2 VA 96.6-131.2, 5 HVN, 0 LVN; 750d POC 27.4 VA 18.4-96.6, 9 HVN, 4 LVN
- `R14.L2.pivots` pivots from 2025-05-29: CPR 116.32-116.55 width 0.2% (narrow), higher value vs the day before; R3 119.17, R2 118.33, R1 117.27, H4 117.25, H3 116.72, TC 116.55, P 116.43, BC 116.32, L3 115.68, S1 115.37, L4 115.16, S2 114.53, S3 113.47
- `R14.L2.session` session 2025-05-29: money zone POC 116.4 VA 116-116.6; volume POC 116.2 VA 116-116.6
- `R14.L2.virgin` virgin session levels (265 from 1855 sessions since 2017-12-01): below money zone VAL 115.4 (2025-05-28, 0.21 ATR); money zone POC 114.8 (2025-05-27, 0.36 ATR); money zone VAL 114.6 (2025-05-27, 0.41 ATR) | above volume VAH 117.8 (2024-10-10, 0.41 ATR); money zone VAH 120.2 (2024-10-01, 1.03 ATR); volume VAH 120.2 (2024-10-01, 1.03 ATR)
- `R14.X.watch` not aligned: up on W, D, M down; first zone below 67.08–96.25, 5.16 ATR(D) away; first zone above 116.44–140.89, 0.06 ATR(D) away; inside 101.6–140.89

## R15 CHOLAFIN, as of 2024-12-19 (last bar 2024-12-18, price 1242.75, ATR(D) 38.67)

```
MAP  CHOLAFIN at 1242.75 (higher-timeframe map, bhavcopy to 2024-12-18) -- zones untested (no fidelity or signal test yet)
     below: 1056–1236 (M bull OB 1061.55-1193.15 (2024-02); M virgin vol POC 2024-03; Y P; W swing LL 2024-W46 +46), 0.54% away
     above: 1520.83–1628 (W bear OB 1557.4-1614 (2024-W38); Q P; W virgin vol VAH 2024-W42; M R4 +10), 22.38% away
L1   structure (untested: no fidelity test yet) -- not aligned: up on M, D, W down
     M: up for 48 bars; last BOS up 2024-06 at 1310; protected low 1011.2 (2024-03), weak high 1652 (2024-09); discount 36.1%
        last sweep: swing high 1310 (2024-01) taken to 1352.6 on 2024-05-31, closed back inside (frozen v2)
        last failed break: swing high 768 closed beyond in 2022-08, back inside on 2022-09-30 at 732.2 (frozen v2)
     W: down for 6 bars; last CHoCH down 2024-W44 at 1302.5; protected high 1652 (2024-W39), weak low 1181.15 (2024-W46); discount 13.1%
        last sweep: swing low 1197.6 (2024-W23) taken to 1181.15 on 2024-11-14, closed back inside (frozen v2)
        last failed break: swing high 1272.9 closed beyond in 2024-W18, back inside on 2024-05-10 at 1272.65 (frozen v2)
     D: up for 6 bars; last CHoCH up 2024-12-10 at 1320; protected low 1181.15 (2024-11-14), weak high 1364 (2024-12-11); discount 33.7%
        last sweep: swing low 1197.6 (2024-06-04) taken to 1181.15 on 2024-11-14, closed back inside (frozen v2)
        last failed break: swing high 1320 closed beyond in 2024-12-10, back inside on 2024-12-13 at 1304.85 (frozen v2)
        D equal highs/lows (shown, not in the HTF zones): above none | below EQL 600 (2022-05-12, 2022-06-14); EQL 469.25 (2021-08-02, 2021-12-20)
     zones (untested) below: bull OB M 1061.55-1193.15; bull OB W 1100.50-1180.00 | above: bear OB W 1557.40-1614.00
     HTF strong zones (untested; 2+ families incl. structure, imbalance or liquidity; clustered at 0.3 ATR(W); point clusters at most 0.45 ATR(W); demand, supply and order-block bands keep their full range, 0.3 ATR(W) = 27.68): below 1056-1236 [structure+imbalance+volume+pivot] (M bull OB 1061.55-1193.15 (2024-02); M virgin vol POC 2024-03; Y P; W swing LL 2024-W46 +46) | above 1520.83-1628 [imbalance+volume+pivot] (W bear OB 1557.4-1614 (2024-W38); Q P; W virgin vol VAH 2024-W42; M R4 +10)
     hot zones (Ochoa, recorded only): 35 DPZ, 33 multi-timeframe; GPZ: M MZ POC 1250; Q L3 1511.89 bullish; Y L3 1089.05 bullish; Y MZ POC 1135; Y MZ VAL 1022; Y VPOC 1136
     pivots (untested; *Q not Ochoa): W P 1313.83 CPR 1309.34-1318.33, average, higher value (bullish), closes above x3; M P 1245.03 CPR 1239.49-1250.58, narrow, lower value (bearish), closes below x2; Q* P 1520.83 CPR 1477.25-1564.42, average, higher value (bullish); Y P 1065.57 CPR 968.45-1162.68, wide, higher value (bullish)
     pivot levels below: M BC 1239.49; W S2 1222.48; M L3 1195.77 | above: M P 1245.03; M TC 1250.58; W L4 1254.61
     profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 1286 VA 1280-1340, average, overlapping higher / VPOC 1326; M MZ POC 1250 VA 1230-1290, average, lower value / VPOC 1236; Q* MZ POC 1420 VA 1332-1474, narrow, higher value / VPOC 1408; Y* MZ POC 1135 VA 1022-1263, average, higher value / VPOC 1136
     virgin (watch): W 2024-W48 MZ VAL 1232 (0.28 ATR); W 2024-W48 vol VAL 1230 (0.33 ATR); W 2024-W47 MZ POC 1210 (0.85 ATR); W 2024-W47 vol POC 1210 (0.85 ATR)
     long profile (approximation (daily bars)): 250d POC 1250 VA 1152-1458, 3 HVN, 0 LVN; 750d POC 714 VA 468-1166, 3 HVN, 2 LVN
L2   daily layer (untested; intraday layer (definitions v1 §8): shown beside the HTF zones, never clustered into them)
     pivots from 2024-12-18: CPR 1243.78-1245.85 width 0.166% (narrow), lower value vs the day before; R3 1283.23, R2 1271.12, H4 1257.21, R1 1256.93, H3 1249.98, TC 1245.85, P 1244.82, BC 1243.78, L3 1235.52, S1 1230.63, L4 1228.29, S2 1218.52, S3 1204.33
     session 2024-12-18: money zone POC 1242 VA 1236-1246; volume POC 1242 VA 1240-1248
     virgin session levels (289 from 1746 sessions since 2017-12-01): below volume VAL 1232 (2024-11-29, 0.28 ATR); money zone VAL 1230 (2024-11-29, 0.33 ATR); money zone VAH 1214 (2024-11-22, 0.74 ATR) | above money zone VAH 1262 (2024-12-17, 0.5 ATR); volume VAH 1288 (2024-12-16, 1.17 ATR); money zone VAH 1296 (2024-12-16, 1.38 ATR)
```

Items:

- `R15.M.state` M: up for 48 bars
- `R15.M.event` M: last BOS up in 2024-06 at 1310
- `R15.M.protected` M: protected low 1011.2 (2024-03)
- `R15.M.weak` M: weak high 1652 (2024-09)
- `R15.M.pd` M: price in discount (36.1% of 1011.2-1652, eq 1331.6)
- `R15.M.sweep` M: swing high 1310 (2024-01) swept to 1352.6 on 2024-05-31, closed back inside (frozen v2)
- `R15.M.failed` M: swing high 768 closed beyond in 2022-08, back inside on 2022-09-30 at 732.2 (frozen v2)
- `R15.W.state` W: down for 6 bars
- `R15.W.event` W: last CHoCH down in 2024-W44 at 1302.5
- `R15.W.protected` W: protected high 1652 (2024-W39)
- `R15.W.weak` W: weak low 1181.15 (2024-W46)
- `R15.W.pd` W: price in discount (13.1% of 1181.15-1652, eq 1416.58)
- `R15.W.sweep` W: swing low 1197.6 (2024-W23) swept to 1181.15 on 2024-11-14, closed back inside (frozen v2)
- `R15.W.failed` W: swing high 1272.9 closed beyond in 2024-W18, back inside on 2024-05-10 at 1272.65 (frozen v2)
- `R15.D.state` D: up for 6 bars
- `R15.D.event` D: last CHoCH up in 2024-12-10 at 1320
- `R15.D.protected` D: protected low 1181.15 (2024-11-14)
- `R15.D.weak` D: weak high 1364 (2024-12-11)
- `R15.D.pd` D: price in discount (33.7% of 1181.15-1364, eq 1272.58)
- `R15.D.sweep` D: swing low 1197.6 (2024-06-04) swept to 1181.15 on 2024-11-14, closed back inside (frozen v2)
- `R15.D.failed` D: swing high 1320 closed beyond in 2024-12-10, back inside on 2024-12-13 at 1304.85 (frozen v2)
- `R15.D.liq` D equal highs/lows (shown, not in the HTF zones): above none | below EQL 600 (2022-05-12, 2022-06-14); EQL 469.25 (2021-08-02, 2021-12-20)
- `R15.Z.inside` price inside zone 1239.49–1280 [volume+pivot] 0.0 ATR(D) away; M BC; M MZ POC 2024-11; M P; 250d POC (approx.) +10
- `R15.Z.b1` zone below #1: 1056–1236 [structure+imbalance+volume+pivot] STRONG 0.17 ATR(D) away; M bull OB 1061.55-1193.15 (2024-02); M virgin vol POC 2024-03; Y P; W swing LL 2024-W46 +46
- `R15.Z.b2` zone below #2: 1100.5–1181.15 [structure+imbalance+volume+pivot] STRONG 1.59 ATR(D) away; W bull OB 1100.5-1180 (2024-W16); W virgin MZ VAL 2024-W16; M S2; W swing LL 2024-W46 +20
- `R15.Z.b3` zone below #3: 960–1050 [structure+imbalance+volume+pivot] STRONG 4.98 ATR(D) away; W bull OB 997.25-1041.9 (2023-W33); W virgin MZ VAH 2023-W18; M S4; W swing HL 2023-W33 +20
- `R15.Z.a1` zone above #1: 1284–1320 [volume+pivot] 1.07 ATR(D) away; M vol VAH 2024-11; Q prev L; W MZ POC 2024-W50; M MZ VAH 2024-11 +10
- `R15.Z.a2` zone above #2: 1326–1364 [volume+pivot] 2.15 ATR(D) away; W vol POC 2024-W50; W H3; Q MZ VAL 2024-Q3; W MZ VAH 2024-W50 +4
- `R15.Z.a3` zone above #3: 1383.88–1420 [volume+pivot] 3.65 ATR(D) away; M R2; W virgin MZ VAL 2024-W43; W virgin vol VAL 2024-W43; Q S1 +8
- `R15.H.hot` Ochoa hot zones: 35 DPZ (33 multi-timeframe); GPZ: M MZ POC 1250; Q L3 1511.89; Y L3 1089.05; Y MZ POC 1135; Y MZ VAL 1022; Y VPOC 1136
- `R15.P.cpr` pivots (untested; *Q not Ochoa): W P 1313.83 CPR 1309.34-1318.33, average, higher value (bullish), closes above x3; M P 1245.03 CPR 1239.49-1250.58, narrow, lower value (bearish), closes below x2; Q* P 1520.83 CPR 1477.25-1564.42, average, higher value (bullish); Y P 1065.57 CPR 968.45-1162.68, wide, higher value (bullish)
- `R15.P.levels` pivot levels below: M BC 1239.49; W S2 1222.48; M L3 1195.77 | above: M P 1245.03; M TC 1250.58; W L4 1254.61
- `R15.V.periods` profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): W MZ POC 1286 VA 1280-1340, average, overlapping higher / VPOC 1326; M MZ POC 1250 VA 1230-1290, average, lower value / VPOC 1236; Q* MZ POC 1420 VA 1332-1474, narrow, higher value / VPOC 1408; Y* MZ POC 1135 VA 1022-1263, average, higher value / VPOC 1136
- `R15.V.virgin` virgin (watch): W 2024-W48 MZ VAL 1232 (0.28 ATR); W 2024-W48 vol VAL 1230 (0.33 ATR); W 2024-W47 MZ POC 1210 (0.85 ATR); W 2024-W47 vol POC 1210 (0.85 ATR)
- `R15.V.long` long profile (approximation (daily bars)): 250d POC 1250 VA 1152-1458, 3 HVN, 0 LVN; 750d POC 714 VA 468-1166, 3 HVN, 2 LVN
- `R15.L2.pivots` pivots from 2024-12-18: CPR 1243.78-1245.85 width 0.166% (narrow), lower value vs the day before; R3 1283.23, R2 1271.12, H4 1257.21, R1 1256.93, H3 1249.98, TC 1245.85, P 1244.82, BC 1243.78, L3 1235.52, S1 1230.63, L4 1228.29, S2 1218.52, S3 1204.33
- `R15.L2.session` session 2024-12-18: money zone POC 1242 VA 1236-1246; volume POC 1242 VA 1240-1248
- `R15.L2.virgin` virgin session levels (289 from 1746 sessions since 2017-12-01): below volume VAL 1232 (2024-11-29, 0.28 ATR); money zone VAL 1230 (2024-11-29, 0.33 ATR); money zone VAH 1214 (2024-11-22, 0.74 ATR) | above money zone VAH 1262 (2024-12-17, 0.5 ATR); volume VAH 1288 (2024-12-16, 1.17 ATR); money zone VAH 1296 (2024-12-16, 1.38 ATR)
- `R15.X.watch` not aligned: up on M, D, W down; first zone below 1056–1236, 0.17 ATR(D) away; first zone above 1520.83–1628, 7.19 ATR(D) away
