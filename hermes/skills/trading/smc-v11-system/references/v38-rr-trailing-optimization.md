# V38.2 RR优化: Trailing阈值2x放宽

## 根因: 42.8%交易RR<=1.5

全量4800分析发现42.8%的交易Reward-to-Risk <= 1.5:
- avgGain=+0.75%, avgLoss=0.70%, implied RR=1.07x
- 赚的和亏的几乎一样多, WR=84.6%也救不了PF
- 90.6%低RR交易通过trailing退出, 仅9.4%到达结构TP
- Bear方向低RR占比50.9% (vs Bull 37.9%) — 做空trailing更紧

## 诊断方法

分析回测结果中按RR分组的交易特征:

```python
# 关键诊断代码
low_rr = [t for t in trades if t.get('rr', 0) <= 1.5]
mid_rr = [t for t in trades if 1.5 < t.get('rr', 0) <= 3.0]
high_rr = [t for t in trades if t.get('rr', 0) > 3.0]

# 检查低RR交易中gain vs loss
low_wins = [t for t in low_rr if t.get('won')]
low_losses = [t for t in low_rr if not t.get('won')]
avg_gain = sum(t['pnl_pct'] for t in low_wins) / len(low_wins)
avg_loss = abs(sum(t['pnl_pct'] for t in low_losses)) / len(low_losses)
# implied RR = avg_gain / avg_loss — 如果≈1, trailing太紧
```

核心信号: **avgGain ≈ avgLoss** + **退出方法90%+为trailing** → trailing阈值需要放宽。

## 修复方案

### 1. Trailing阈值2x放宽

| 盈利区间 | 旧trailing (V38.0) | 新trailing (V38.2) |
|---------|-------------------|-------------------|
| ≥0.5% | 锁+0.2% | 锁保本(b/e) |
| ≥1.0% | 锁-0.5% (亏损) | 锁+0.1% |
| ≥1.5% | (无此级) | 锁+0.3% |
| ≥2.0% | 锁1%回撤 | (合并到3.0%) |
| ≥3.0% | (无此级) | 锁1.5%回撤 |
| ≥4.0% | 锁2%回撤 | (合并到6.0%) |
| ≥6.0% | (无此级) | 锁3%回撤 |

关键观察: 旧阈值在+0.5%处锁+0.2%, 而avgSL≈0.86%, 所以gain barely beats SL。放宽到+0.5%保本后, 更多交易跑到+1.0%以上, 然后用+0.1%锁住。

### 2. 结构TP强制hold

旧逻辑: 结构TP到达95%开始收紧, 100%止盈
新逻辑: 结构TP到达90%即收紧, 98%即可止盈

效果: TP命中率从9.4%提升到更高。持有到TP的交易平均RR明显高于trailing退出。

### 3. Bear trailing对称处理

旧逻辑: 做空trailing只做`min(extreme, ...)`方向检查, 退出检查代码有问题(与做多共用了部分逻辑)
新逻辑: 做空与做多各自完整的退出检查:
- Bear: 价格反弹超过SL → 做空退出 (bar['h'] >= sl)
- Bull: 价格跌破SL → 做多退出 (bar['l'] <= sl)

## 结果

| 指标 | V38.0 | V38.2 | 变化 |
|------|-------|-------|------|
| Low-RR占比 | 42.8% | 23.7% | -45% |
| RR | 3.10x | 4.26x | +37% |
| PF | 44 | 67 | +52% |
| P&L | +2.47% | +3.33% | +35% |
| WR | 92.7% | 92.1% | -0.6pp |
| Max hold | 17 bars | 37 bars | +118% |

## 遇到的陷阱

1. **Bear PnL双次取反**: 做空trailing函数中 `return j, tp_price, True` 返回硬编码 `True`(won), 应该检查 `tp_price < entry_price`。修复前亏损交易被判为盈利, WR被系统性高估。

2. **结构树TP方向**: `StructureTree.get_tp_level()` 只返回摆动高点(适用于做多), 做空时需要摆动低点。需要 `direction='bull'|'bear'` 参数。

3. **Patch时重复代码遗留**: 替换完整函数时, 旧代码的`else`分支可能残留, 导致第二个`else:`无匹配`if`。始终在替换后做语法检查(`py_compile.compile()`)。

## 通用原则

对于高WR(>90%)策略, RR提升比WR提升对PF贡献更大:
- WR从92%→93%: PF从67→75 (+12%)
- RR从3x→4x: PF从67→90 (+34%)

锁定RR瓶颈的方法: 检查低RR交易的gain/loss比, 如果≈1则trailing太紧。
