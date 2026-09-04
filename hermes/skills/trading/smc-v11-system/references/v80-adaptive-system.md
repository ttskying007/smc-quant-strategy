# V8.0-V9.0 自适应SMC系统

## V8.0: Per-Stock Adaptive Pattern Selection

对4779只股票分别找到最优模式:

| 模式 | 股票数 | 说明 |
|------|--------|------|
| ZONE_ONLY | 3866 (81%) | 大部分股票不需要复杂组合 |
| LIQ→ZONE | 516 (11%) | 流动性扫荡确认有价值 |
| CTX→ZONE | 395 (8%) | 趋势确认有价值 |

Adaptive WR=80.3% vs Global fixed WR=79.4% → +0.9% improvement.

## V9.0: Dynamic SL + Multi-TF Resonance (FAILED)

动态SL(ATR buffer below zone) → WR dropped to 75.3%
60min resonance as hard filter → WR dropped to 75.9%

Core lesson: tight fixed SL (zone_low*0.995) is optimal.
Per-stock pattern selection is the only adaptive improvement that works.

## Pitfalls

1. Dynamic SL degrades performance — don't add ATR buffer below zone
2. Cross-pattern sequence dedup must be per-pattern, not global
3. State detection v2 classifies 86% as 'rotational' — thresholds need tuning
4. ENTRY_AT_ZONE (pullback entry) doesn't work with sequences — use CLOSE entry
