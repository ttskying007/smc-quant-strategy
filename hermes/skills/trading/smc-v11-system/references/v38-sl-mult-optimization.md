# V38 SL乘数参数优化方法

## 目标

找到Wyckoff阶段自适应SL乘数(sl_mult)的最优值, 在保持WR不变的前提下最大化RR和PF。

## 方法: 模块级补丁测试

不需要修改引擎代码。通过直接patch `wyckoff_phases_v38.PHASE_ADAPTIVE_PARAMS` 来测试不同乘数:

```python
import copy, v11.wyckoff_phases_v38 as wyckoff

# 保存原始
orig = copy.deepcopy(wyckoff.PHASE_ADAPTIVE_PARAMS)

# 测试SL×0.5
for phase in wyckoff.PHASE_ADAPTIVE_PARAMS:
    wyckoff.PHASE_ADAPTIVE_PARAMS[phase]['sl_mult'] = round(
        orig[phase]['sl_mult'] * 0.5, 2)

# 运行回测 (导入evaluate_v38_entry/backtest_stock_v38)
# ... 正常调用 rolling_backtest_v38 ...

# 恢复原始
for phase in wyckoff.PHASE_ADAPTIVE_PARAMS:
    wyckoff.PHASE_ADAPTIVE_PARAMS[phase]['sl_mult'] = orig[phase]['sl_mult']
```

## 测试组合

SL乘数比例: 0.5, 0.7, 1.0, 1.3
TP乘数比例: 0.7, 1.0, 1.3, 1.5

## 发现 (A股日线)

| SL乘数 | WR | RR | PF | P&L | 结论 |
|--------|----|----|----|-----|------|
| ×1.0(基线) | 92.1% | 4.26x | 67 | +3.33% | 基线 |
| **×0.5** | **92.1%** | **7.64x** | **122** | **+3.35%** | **最优, 无代价** |
| ×0.7 | 92.1% | 5.75x | 97 | +2.98% | 好 |
| ×1.3 | 92.1% | 3.51x | 59 | +2.96% | 较差 |

TP乘数完全无影响 — 因为99%交易通过trailing退出, 结构TP极少到达。

## 根因分析

WR不变的原理: A股日线1-bar gap退出特性使初次SL位置不影响胜率。
- 交易在进入后第1根K线的gap中决定胜负
- 追踪止盈在price move后快速上移SL, 初始SL宽度影响短暂
- 因此减半SL=风险减半, 利润不变, RR翻倍

## 陷阱

- 仅对A股日线适用(1-bar gap特性)
- 对intraday策略可能不同(多根K线内SL被测试)
- 不要在调整SL乘数的同时调整TP乘数 — TP在日线无影响
- 验证: 必须全量4800跑完, 200只的结果可能因样本偏差不准确(但本案例中200只结果与全量一致)
