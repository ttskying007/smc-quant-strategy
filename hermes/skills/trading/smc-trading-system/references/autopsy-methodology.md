# V19 Evidence-Based Autopsy Methodology

## Design Principle

The autopsy must measure what ACTUALLY predicts trade outcomes, not what "looks correct" formally. All scoring weights derive from empirical PnL data from full 4905-stock backtests.

## V18 Failures (corrected in V19)

### 1. SLTP Circular Reasoning (FATAL)
V18 scored SLTP based on exit reason: trailing=8.3, SL=1.3. Since 84.7% of trades exit via trailing, this inflated scores artificially. The SLTP score was measuring the OUTCOME (did the trade win?) not predicting it.

### 2. Near-Zero Predictive Power
Without SLTP, signal+entry+combo combined had diff=+0.2 between winning and losing trades. The scoring system measured noise.

### 3. Score Compression
Each dimension had only 2-12% unique values across 295 trades. For example, signal accuracy had only 8 unique values — meaning the scoring couldn't discriminate between good and bad signals.

### 4. Score Paradox
Best PnL trades scored below average (300091.SZ: +18.2% PnL, autopsy=5.0/10). Worst PnL trades scored above average (001210.SZ: -3.8% PnL, signal=7.0/10).

## V19 Dimensions

### D1: Sequence Quality (35% weight)
Based on empirical PnL from V18 full backtest:
- LIQ→OB→CH→IDM: +11.20% PnL → 10/10
- LIQ→OB→IDM: +10.37% → 9.5
- OB→CH→FVG→PB→IDM: +9.16% → 9.0
- OB→CH→FVG→IDM: +8.54% → 7.5
- OB→CH→IDM: +5.79% → 6.5
- OB→IDM: +3.76% → 5.0

### D2: Market Regime (20% weight)
Based on empirical PnL by regime:
- HIGH_VOLATILITY: +7.83% PnL, 97% WR → 10/10
- RANGING: +1.18% PnL, 89% WR → 6/10
- STRONG_TREND_UP: +3.27% PnL, 73% WR → 5/10
- WEAK_TREND_UP: +0.58% PnL, 60% WR → 3/10
- Any DOWN regime: filtered out (no trades taken)

### D3: Capital Efficiency (20% weight)
PnL% / hold_bars, capped at 10. Higher = more profit per day of risk exposure. This dimension has the strongest correlation with PnL (+5.2 diff) and no circular reasoning.

### D4: Exit Quality (15% weight)
For winning trades: capture_ratio = exit_price / post_exit_peak. >=98% = perfect exit (10/10).
For losing trades: did exit avoid further decline? >3% avoided = good (8/10).

### D5: Risk Structure (10% weight)
SL/ATR ratio. Evidence: tight SL (0.5-1.5×ATR) yields best PnL (+7.8%). Wider SL (>2×ATR) yields worse (+4.4%).

## Closed-Loop Iteration

```
V19 Engine runs → 295 trades with autopsy scores
     ↓
Aggregation: which dimension is weakest?
     ↓
If worst_dim < threshold → apply param fix → write params_override.json
     ↓
Re-run backtest with override → compare scores
     ↓
If score improved > 0.1 → continue iterating
If score stalled → stop (converged)
Max 3 iterations
```

## Key Pitfalls Fixed

1. **CH window mismatch**: Autopsy searched ob_idx→entry_idx+5, engine searched ob_idx→n. Fixed: autopsy uses same window as engine.
2. **OB distance threshold**: Fixed 5bar threshold doesn't work for A-stock daily gaps. Fixed: dynamic threshold based on displacement strength.
3. **T+1 chase false positive**: A-stock T+1 means buying on an up day is normal. Fixed: removed "chase entry" penalty, check post-entry bars only.
4. **Float score TypeError**: Score bars use `'█' * int(score)` not `'█' * score`.
