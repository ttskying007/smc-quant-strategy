# V10.0 Failure Mode Analysis & Rolling Window (2026-05-14)

## Zone Type Failure Rates

| Zone | Pattern | avg_loss | SL hit rate | N |
|------|---------|----------|-------------|-----|
| FVG_Bull | ZONE_ONLY | -6.33% | 56% | 7,519 |
| FVG_Bull | CTX→ZONE | -7.00% | 63% | 1,194 |
| FVG_Bull | LIQ→ZONE | -5.07% | 44% | 1,038 |
| OB_Bull | ZONE_ONLY | -1.68% | 18% | 814 |
| OB_Bull | LIQ→ZONE | -1.52% | 20% | 151 |

**结论: OB_Bull zone的SL抗性是FVG_Bull的3倍。FVG_Bull作为入场zone不可靠。**

## Rolling Window Pattern Drift

- 稳定(3窗口同模式): 2,021只 (88%)
- 漂移(模式变化): 280只 (12%)

Most common drift directions:
- ZONE_ONLY→LIQ→ZONE: 86只
- ZONE_ONLY→CTX→ZONE: 73只
- LIQ→ZONE→ZONE_ONLY: 54只

**结论: 88%股票的模式稳定, 12%需要动态切换。静态per-stock模式选择足够。**

## Window Distribution

| Window | ZONE_ONLY | LIQ→ZONE | CTX→ZONE |
|--------|-----------|----------|----------|
| old (earliest 150 bars) | 2,144 | 60 | 52 |
| mid (middle 100 bars) | 1,959 | 90 | 82 |
| recent (last 50 bars) | 381 | 3 | 5 |

## Scripts

- `/root/.hermes/scripts/v11/failure_rolling_v10.py`
- `/root/.hermes/smc_opt_v21/failure_rolling_v10.json`

## Adaptive System Lessons (V8.0 → V9.0)

| System | WR | PnL/笔 | 说明 |
|--------|-----|-----|------|
| V8.0 per-stock best + fixed SL | **80.3%** | +1.19% | ⭐ 最优 |
| V9a dynamic SL | 75.3% | +1.15% | ❌ ATR buffer有害 |
| V9b dynamic SL + 60min | 75.9% | +1.18% | ❌ 过滤有效信号 |

**核心教训: 自适应价值在模式选择(per-stock pattern), 不在SL调整或周期共振。**
紧SL(zone_low*0.995)在所有测试中最优。
