# V19 Evidence-Based Scoring Methodology

## Problem: V18 Autopsy Was Circular

V18's SLTP dimension scored trades based on exit reason:
- `trailing` exit → 8.3/10 (profitable)
- `sl` exit → 1.3/10 (loss)

This made SLTP a **function of the outcome, not a predictor**. 84.7% of trades exited via trailing → score automatically inflated.

The other three dimensions (signal accuracy, entry position, combo fidelity) had **zero predictive power** (diff=+0.2 won vs lost). They measured "form" (displacement, swing distance) not "substance".

## V19 Redesign: Evidence-Based

All 5 dimensions are based on empirical PnL data from V18 full backtest:

### D1: Signal Sequence (35% weight)
Based on actual average PnL per sequence type:

| Sequence | PnL | Score |
|----------|-----|-------|
| LIQ→OB→CH→IDM | +11.20% | 10.0 |
| LIQ→OB→IDM | +10.37% | 9.5 |
| OB→CH→FVG→PB→IDM | +9.16% | 9.0 |
| OB→CH→FVG→IDM | +8.54% | 7.5 |
| OB→CH→PB→IDM | +8.43% | 7.5 |
| OB→CH→IDM | +5.79% | 6.5 |
| OB→IDM | +3.76% | 5.0 |

### D2: Market Regime (20%)
Based on actual average PnL per regime:

| Regime | PnL | Score |
|--------|-----|-------|
| HIGH_VOLATILITY | +7.83% | 10.0 |
| RANGING | +1.18% | 6.0 |
| STRONG_TREND_UP | +3.27% | 5.0 |
| WEAK_TREND_UP | +0.58% | 3.0 |

### D3: Capital Efficiency (20%)
`score = min(PnL% / hold_bars * 10, 10.0)`
Measures return per bar of risk exposure. Directly correlated (+6.1) with PnL.

### D4: Exit Quality (15%)
For winning trades: `capture_ratio = exit_price / post_exit_high`
For losing trades: did exit avoid further decline?

### D5: Risk Structure (10%)
SL/ATR ratio: empirical data shows tight SL (0.5-1.5x ATR) = best PnL (+7.77%)

## Validation

V19.1 PnL correlations (won vs lost score diff):
- efficiency: +6.1 (strongest predictor)
- risk: +2.0
- overall: +1.8
- exit_qual: +1.8
- regime: +1.3
- sequence: -0.5 (needs regime context)

All dimensions positive except sequence (which varies by regime).
