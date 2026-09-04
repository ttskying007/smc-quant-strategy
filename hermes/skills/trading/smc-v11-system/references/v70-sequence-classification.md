# V7.0 SMC Signal Classification & Sequence Ranking

## Signal Categories (7 families)

```
CTX_LONG:  BOS_Bull, CHOCH_Bull, MSS_Bull     (uptrend context)
CTX_SHORT: BOS_Bear, CHOCH_Bear, MSS_Bear     (downtrend context)
LIQ_LONG:  Sweep_SSL, EQL                     (bullish liquidity event)
LIQ_SHORT: Sweep_BSL, EQH                     (bearish liquidity event)
ZONE_LONG: OB_Bull, FVG_Bull                  (demand zone POI)
ZONE_SHORT:OB_Bear, FVG_Bear                  (supply zone POI)
CONFLUENCE:BPR                                (balanced price range)
```

## 13 Time-Ordered Sequence Patterns (ranked by WR)

Full 4836-stock backtest. Entry: T+1 close at zone signal bar. Target: +2%/5bar.

| Rank | Pattern | Dir | WR | N | AvgP&L | TP% |
|------|---------|-----|------|------|--------|-----|
| 1 | LIQ→ZONE | long | 80.3% | 6768 | +1.38% | 74% |
| 2 | CTX→ZONE | long | 79.4% | 6534 | +0.95% | 76% |
| 3 | ZONE_ONLY | long | 79.4% | 45632 | +1.09% | 75% |
| 4 | LIQ→CTX→ZONE | long | 79.3% | 1450 | +0.78% | 76% |
| 5 | CTX→LIQ→ZONE | long | 76.1% | 899 | +0.93% | 69% |
| 6 | CTX→LIQ→CTX→ZONE | long | 75.0% | 108 | +0.68% | 73% |

### Key Findings

1. **LIQ→ZONE beats baseline**: +0.9pp WR over ZONE_ONLY with 15% of volume — higher single-trade quality
2. **BPR confluence harmful**: TP rate drops from 75%→25% when BPR added (tightens zone, SL too close)
3. **Multi-stage doesn't improve WR**: 3-stage and 4-stage patterns trade less but aren't more accurate
4. **Short patterns all fail**: max WR=55.8%, insufficient for A-share T+1
5. **Trend-adaptive selection**: bullish+LIQ→ZONE=82.6%, bearish+CTX→ZONE=74.8%

### Implementation

Script: `full_sequence_backtest_v70.py`
Result: `smc_opt_v21/full_sequence_backtest_v70.json`

Critical fix: dedup sequences PER PATTERN, not globally. Global dedup caused ZONE_ONLY to consume all zone signals, starving multi-stage patterns to zero trades.
