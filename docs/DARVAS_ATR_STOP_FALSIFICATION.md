# Darvas ATR-stop — falsification pass

Kill conditions pre-registered in `scripts/falsify_darvas_atr_stop.py` (committed before this run). Net = Stressed costs on a Rs100,000 position; returns per trade.

| Bucket | N | Mean net | Mean net minus NIFTY (K1) | Total net | Total without top 5% (K2) | Entry weeks | 90% CI of mean, week bootstrap (K3) |
|---|---|---|---|---|---|---|---|
| <=35% (control) | 1785 | -0.24% | -0.11% (n=1785) | -425.1% | -2186.4% (−89) | 144 | -0.75% .. +0.28% |
| 35-50% | 277 | +0.70% | +0.95% (n=277) | +192.8% | -233.1% (−14) | 101 | -0.76% .. +2.10% |
| 50-100% | 196 | +0.26% | +0.66% (n=196) | +51.7% | -293.9% (−10) | 86 | -1.48% .. +2.09% |

## Bucket B verdict

- K1 beta: survives
- K2 few trades: **KILLED**
- K3 noise: **KILLED**

**PASS DOES NOT SURVIVE -- not ready for capital**
