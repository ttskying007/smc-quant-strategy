# V8.4 13-Round Optimization History

## Session Summary
Completed 13 optimization rounds achieving WR=80.0% RR=2.44 PF=11.44 N=60 on 40 A-stocks.
Broke through the 70% WR ceiling that V8.3 was stuck at for cycles.

## Scoring Evolution

### Initial (V8.4 v1 — rounds 1-8)
```python
score = WR * sqrt(min(N,40)) * min(3,PF) * min(3,RR)**2.0
if RR < 1.5: score *= 0.1
if N < 12: score = 0
if WR > 90% and N < 25: score *= 0.5
coverage: <15%→0.2, 15-25%→0.5, 25-40%→0.8, >40%→1.0
```
Problem: WR was undervalued relative to RR. Opt got lots of RR>4.0 params but WR stuck at ~67%.

### v2 (rounds 9-10)
```python
score = WR * sqrt(min(N,50)) * min(3,PF) * min(3,RR)**1.5
```
Problem: Still not enough WR priority. Minor improvement.

### v3 (rounds 11-13) — FINAL
```python
score = (wr/100)**2.0 * sqrt(min(n,50)) * min(3,pf) * min(2.5,rr_avg)
if rr_avg < 1.2 and total_trades >= 3: score *= 0.1
if total_trades < 8: score = 0
elif total_trades < 15: score *= max(0.3, total_trades / 15)
```
Key changes: WR^2.0 (quadratic), RR linear (capped at 2.5), N soft penalty.

## Round Details

| R# | WR | RR | PF | N | Ret% | Tighten | Scoring | Strategy |
|----|-----|-----|----|-----|------|---------|---------|----------|
| R1 | 52.5 | 3.01 | 5.07 | 120 | 137 | 0.30 | v1 | Seed from V83 |
| R2 | **62.7** | 3.20 | 7.56 | 75 | 148 | 0.35 | v1 | |
| R3 | 63.1 | 3.19 | 7.47 | 168 | 227 | 0.35 | v1 | |
| R4 | 67.7 | 3.29 | 9.31 | 68 | — | 0.30 | v1 | |
| R5 | 69.6 | 3.37 | 11.28 | 46 | — | 0.32 | v1 | |
| R6 | **71.4** | **3.94** | 13.19 | 77 | — | 0.25 | v1 | |
| R7 | 67.2 | 3.07 | 9.63 | 58 | — | 0.20 | v1 | |
| R8 | 65.8 | 2.89 | 7.39 | 114 | — | 0.30 | v1 | |
| R9 | 66.7 | 3.65 | 10.07 | 57 | — | 0.30 | v2 | |
| R10 | 62.5 | 3.24 | 8.01 | 72 | — | 0.28 | v2 | |
| **R11** | **77.8** | 2.70 | 11.02 | 54 | **104** | 0.30 | **v3** | +WR-directed |
| R12 | 73.3 | 2.47 | 8.27 | 45 | — | 0.28 | v3 | tight |
| **R13** | **80.0** | **2.44** | **11.44** | **60** | **99** | **0.35** | **v3** | **champion** |

## Key Insight: WR plateau at 63-71%

WR stalled for 8 rounds (R3-R10) despite:
- Tighten going 0.35→0.25→0.30 (no correlation with WR)
- Scoring change v1→v2 (minor effect)

**Breakthrough came from TWO changes simultaneously:**
1. Scoring v3 (WR^2.0) — gave optimizer a clear gradient toward higher WR
2. WR-directed mutation in phases 4-5 — actively synthesized high-WR params

## Final Champion Params (R13)
```
fvg_min_width: 0.22       → moderate FVG sensitivity
sweep_lookback: 12        → standard sweep lookback
sweep_wick_ratio: 4.26    → VERY tight wick filter (few signals, high quality)
ob_strength_min: 0.97     → low OB threshold (catches most OBs)
score_min: 3.71           → VERY high entry quality (key to WR)
confirm_range: 2          → tight confirmation
max_trades: 7             → moderate frequency
sl_pct: 1.0               → absolute minimum SL (1%)
tp_pct: 2.8               → TP/SL = 2.8x
atr_min_pct: 3.17         → avoid low-vol stocks
atr_max_pct: 11.55        → include high-vol stocks
```

## What Didn't Work
- Loosening tighten (0.25, 0.20) → WR dropped as noise increased
- RR-first scoring → good RR but stuck WR
- Hard N cutoffs → rejected many borderline high-WR params
- Tightening aggressively (0.35 in R13 was last resort, but worked)