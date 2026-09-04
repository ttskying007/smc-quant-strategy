# V10 Smart Money: SMC Context Filtering Results

## Core Finding
SMC context is the #1 predictor of signal quality. The more context confirmations, the higher the win rate.

```
Context Count   Win Rate
  ctx_0          42.3%  ← untradeable
  ctx_1          64.3%
  ctx_2          79.4%
  ctx_3          87.3%
  ctx_4          92.0%
```

## Context Types Checked
1. LIQ sweep (Sweep_SSL/BSL) within 10 bars before signal
2. STRUCT break (CHOCH/BOS) within 15 bars before signal
3. At swing point (signal bar within 2 bars of swing high/low)
4. FVG nearby (within 5 bars)

## V10 Engine Results (SL=0.5-2% adaptive, SMC context required)

| Context | Trades | WR | avg PnL |
|---------|--------|-----|---------|
| Sweep_SSL_ctx | 205 | 94.1% | +11.18% |
| zone_OB_Bull (Sweep→OB) | 203 | 93.1% | +9.59% |
| zone_FVG_Bull | 118 | 84.7% | +4.57% |
| Sweep_BSL_ctx | 109 | 82.6% | +7.15% |
| BOS_Bull_ctx | 51 | 70.6% | +4.23% |
| CHOCH_Bull_ctx | 22 | 68.2% | +4.75% |
| no_context FVG | 1449 | 38.5% | - |  (removed in V10.1)

**V10.1 improvement**: FVG_Bull now also requires SMC context + weekly bullish + low fill rate.
Daily entries require Pinbar/Engulf confirmation at zone.

## Key Decision Rules
1. Never trade signals without SMC context (ctx_0 WR < 50%)
2. Prefer signals with LIQ sweep before OB (WR > 90%)
3. FVG is only usable with context + weekly bullish + unfilled gap
4. BOS is confirmation-only, not standalone entry
5. CHOCH needs nearby OB zone to be tradeable
